"""Build an isolated Windows application and Inno installer from explicit inputs."""
import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile

ROOT=Path(__file__).resolve().parents[1]


def sha(path):
    digest=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):digest.update(block)
    return digest.hexdigest()


def run(*args,**kwargs):
    subprocess.run([str(a) for a in args],check=True,**kwargs)


def copy_ocr(node,modules,model,target):
    target.mkdir(parents=True)
    shutil.copy2(node,target/'node.exe')
    license_path=node.parent/'LICENSE'
    if not license_path.is_file():raise ValueError('Use the official Node Windows distribution with its LICENSE file')
    shutil.copy2(license_path,target/'NODE-LICENSE.txt')
    (target/'tessdata').mkdir();shutil.copy2(model,target/'tessdata/eng.traineddata')
    selected={};pending=['tesseract.js']
    while pending:
        name=pending.pop()
        if name in selected:continue
        if not re.fullmatch(r'(?:@[a-z0-9._-]+/)?[a-z0-9._-]+',name):raise ValueError('Invalid runtime package name')
        source=modules/name;metadata=json.loads((source/'package.json').read_text(encoding='utf-8'))
        selected[name]=metadata['version']
        shutil.copytree(source,target/'node_modules'/name,ignore=shutil.ignore_patterns('.git','node_modules','test','tests','examples','coverage'))
        pending.extend(metadata.get('dependencies',{}))
    return selected


def make_licenses(target):
    target.mkdir(parents=True)
    for name in ('LICENSE','NOTICE'):
        shutil.copy2(ROOT/name,target/name)
    shutil.copy2(ROOT/'installer/LICENSING.md',target/'LICENSING.md')
    for name in ('GPL-3.0.txt','LGPL-3.0.txt'):
        shutil.copy2(ROOT/'installer/licenses'/name,target/name)
    python_license=Path(sys.base_prefix)/'LICENSE.txt'
    if not python_license.is_file():python_license=Path(sys.base_prefix)/'LICENSE'
    if python_license.is_file():shutil.copy2(python_license,target/'PYTHON-LICENSE.txt')
    inventory=[]
    for dist in importlib.metadata.distributions():
        name=dist.metadata['Name'];version=dist.version;files=dist.files or []
        component={'name':name,'version':version,'license':dist.metadata.get('License-Expression') or dist.metadata.get('License','See component notices'),'source_files':f'https://pypi.org/project/{name}/{version}/#files','notice_files':[]}
        inventory.append(component)
        for file in files:
            if Path(file).is_absolute() or '..' in Path(file).parts:continue
            if any(word in str(file).lower() for word in ('license','copying','notice')) and not str(file).endswith(('.py','.pyc')):
                source=Path(dist.locate_file(file))
                if source.is_file():
                    # Keep notice paths short enough for ordinary Windows installers.
                    # The inventory preserves each original distribution path.
                    dest=target/'python'/name/(f'{len(component["notice_files"])+1:03d}-'+Path(file).name)
                    dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,dest)
                    component['notice_files'].append({'original':str(file),'included':dest.relative_to(target).as_posix()})
    (target/'dependency-inventory.json').write_text(json.dumps(inventory,indent=2),encoding='utf-8')
    notice='MFF Bot by Nyxolir\n\nThe original bot source retains its Apache-2.0 notices. The combined installed application includes GPL-3.0 PyQt5 and is distributed under the applicable GPL-3.0 terms; individual libraries retain their licenses.\n\nCorresponding bot source and build scripts: MFF-Bot-Source.zip accompanying this installer, and https://github.com/Nyxolir/mff-bot . Exact component versions and source locations are listed in dependency-inventory.json. Qt 5.15.2 source: https://download.qt.io/archive/qt/5.15/5.15.2/single/ .\n\n'
    (target/'DISTRIBUTION-LICENSE.txt').write_text(notice+(target/'GPL-3.0.txt').read_text(encoding='utf-8'),encoding='utf-8')


def version_info(version,path):
    parts=tuple(int(v) for v in version.split('.'))+(0,)
    path.write_text("VSVersionInfo(ffi=FixedFileInfo(filevers="+repr(parts)+",prodvers="+repr(parts)+",mask=0x3f,flags=0,OS=0x40004,fileType=0x1,subtype=0,date=(0,0)),kids=[StringFileInfo([StringTable('040904B0',[StringStruct('CompanyName','Nyxolir'),StringStruct('FileDescription','MFF Bot'),StringStruct('FileVersion','"+version+"'),StringStruct('ProductName','MFF Bot'),StringStruct('ProductVersion','"+version+"'),StringStruct('LegalCopyright','Modern version by Nyxolir; upstream and third-party notices retained')])]),VarFileInfo([VarStruct('Translation',[1033,1200])])])",encoding='utf-8')


def private_terms():
    candidates=[os.environ.get('USERNAME',''),Path.home().name,*os.environ.get('MFF_PRIVATE_TERMS','').split(',')]
    return {name.lower() for name in candidates if len(name)>=5 and name.lower() not in ('runneradmin','defaultuser','sandbox')}


def audit_identity(paths):
    terms=private_terms()
    forbidden=[raw for name in terms for raw in (name.encode('utf-8'),name.encode('utf-16-le'))]
    findings=[]
    for path in paths:
        if not path.is_file():continue
        content=path.read_bytes().lower()
        if any(word in content for word in forbidden):findings.append(path.name)
    if findings:raise ValueError('Personal builder identity found in release payload: '+repr(findings))


def audit_bundle(bundle):
    audit_identity(bundle.rglob('*'))
    terms=private_terms()
    from PyInstaller.archive.readers import CArchiveReader
    import marshal,types
    def inspect_code(code):
        if not isinstance(code,types.CodeType):return
        if re.search(r'(?i)[a-z]:[/\\]users[/\\]',code.co_filename) or any(name in code.co_filename.lower() for name in terms):raise ValueError('Personal source filename in frozen bytecode')
        for value in code.co_consts:
            if isinstance(value,types.CodeType):inspect_code(value)
    archive=CArchiveReader(str(bundle/'MFF Bot.exe'))
    for name,entry in archive.toc.items():
        if entry[-1]=='s':inspect_code(marshal.loads(archive.extract(name)))
        elif entry[-1]=='z':
            pyz=archive.open_embedded_archive(name)
            for module in pyz.toc:
                obj=pyz.extract(module)
                if isinstance(obj,types.CodeType):inspect_code(obj)


def main(argv=None):
    parser=argparse.ArgumentParser()
    parser.add_argument('--version',default='0.1.0')
    parser.add_argument('--node',type=Path,required=True)
    parser.add_argument('--node-modules',type=Path,default=ROOT/'installer/ocr/node_modules')
    parser.add_argument('--model',type=Path,required=True)
    parser.add_argument('--iscc',type=Path,required=True)
    parser.add_argument('--output',type=Path,default=ROOT/'dist/release')
    args=parser.parse_args(argv)
    if sys.platform!='win32':parser.error('Build the Windows installer on Windows')
    if not re.fullmatch(r'\d+\.\d+\.\d+',args.version):parser.error('Version must be three numeric fields')
    if any(int(n)>65535 for n in args.version.split('.')):parser.error('Version fields must fit Windows version resources')
    work_parent=ROOT/'build';work_parent.mkdir(exist_ok=True)
    stage=Path(tempfile.mkdtemp(prefix='installer-',dir=work_parent))
    update_helper=stage/'updater';update_helper.mkdir()
    compiler=Path(os.environ['WINDIR'])/'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
    run(compiler,'/nologo','/target:winexe','/platform:x64','/reference:System.Web.Extensions.dll',
        '/out:'+str(update_helper/'MFF Bot Update Helper.exe'),ROOT/'installer/UpdateHelper.cs')
    run(sys.executable,ROOT/'installer/verify_update_helper.py',update_helper/'MFF Bot Update Helper.exe',stage/'helper-checks')
    build_info=stage/'build-info.json'
    build_info.write_text(json.dumps({'version':args.version,'source_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT).decode().strip()}),encoding='utf-8')
    output=args.output.resolve();output.mkdir(parents=True,exist_ok=True)
    ocr=stage/'ocr';packages=copy_ocr(args.node.resolve(),args.node_modules.resolve(),args.model.resolve(),ocr)
    licenses=stage/'licenses';make_licenses(licenses)
    info=stage/'version-info.txt';version_info(args.version,info)
    command=[sys.executable,'-m','PyInstaller','--noconfirm','--onedir','--windowed','--name','MFF Bot','--icon',str(ROOT/'icon.ico'),'--version-file',str(info),'--runtime-hook',str(ROOT/'installer/runtime_hook.py'),'--distpath',str(stage/'dist'),'--workpath',str(stage/'pyinstaller'),'--specpath',str(stage),'--paths',str(ROOT),'--collect-all','autoit','--collect-all','multiprocess','--hidden-import','win32timezone']
    for source,dest in [(ROOT/'images','images'),(ROOT/'icon.ico','.'),(ROOT/'scripts','scripts'),(ROOT/'settings/gui/trivia-answers.json','settings/gui'),(ocr,'ocr'),(licenses,'licenses'),(ROOT/'README.md','.'),(ROOT/'SETUP.md','.'),(ROOT/'installer/QUICK-START.txt','.'),(update_helper,'updater'),(build_info,'.')]:
        command.extend(['--add-data',str(source)+os.pathsep+dest])
    command.append(str(ROOT/'app_gui.py'));run(*command,cwd=ROOT)
    bundle=stage/'dist/MFF Bot';audit_bundle(bundle)
    profile=stage/'smoke-profile';report=stage/'application-selftest.json'
    environment=dict(os.environ,MFF_DATA_DIR=str(profile),QT_QPA_PLATFORM='offscreen')
    run(bundle/'MFF Bot.exe','--self-test',report,env=environment,timeout=180)
    evidence=json.loads(report.read_text(encoding='utf-8'));assert evidence['passed']
    run(args.iscc,'/Qp','/DAppVersion='+args.version,'/DBundleDir='+str(bundle),'/DOutputDir='+str(output),ROOT/'installer/mff-bot.iss',cwd=ROOT)
    installer=output/'MFF-Bot-Setup.exe';assert installer.is_file()
    audit_identity([installer])
    run('powershell.exe','-NoProfile','-File',ROOT/'installer/verify_installation.ps1','-Installer',installer,'-WorkRoot',stage/'installed-smoke',cwd=ROOT,timeout=540)
    installation=json.loads((stage/'installed-smoke/installer-validation.json').read_text(encoding='utf-8-sig'));assert installation['passed']
    source_files=subprocess.check_output(['git','ls-files','-z'],cwd=ROOT).decode().split('\0')[:-1]
    for name in source_files:
        if (name.startswith(('diagnostics/','logs/','build/','dist/','tests/fixtures/','settings/gui/'))
                and name not in ('tests/fixtures/README.md','settings/gui/trivia-answers.json')):
            raise ValueError('Private runtime files must not enter the source release')
    audit_identity(ROOT/name for name in source_files)
    with zipfile.ZipFile(output/'MFF-Bot-Source.zip','w',zipfile.ZIP_DEFLATED) as archive:
        for name in source_files:
            path=ROOT/name
            if path.is_file():archive.write(path,'mff-bot/'+name)
    manifest={'version':args.version,'source_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT).decode().strip(),'creator':'Nyxolir','platform':'Windows x64','python':sys.version.split()[0],'ocr_packages':packages,'english_model_sha256':sha(args.model),'self_test':evidence,'installation_test':installation,'artifacts':{p.name:sha(p) for p in (installer,output/'MFF-Bot-Source.zip')}}
    (output/'BUILD-MANIFEST.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    artifacts=[installer,output/'MFF-Bot-Source.zip',output/'BUILD-MANIFEST.json']
    (output/'SHA256SUMS.txt').write_text(''.join(sha(p)+'  '+p.name+'\n' for p in artifacts),encoding='ascii')
    (stage/'build-result.json').write_text(json.dumps({'bundle':str(bundle),'output':str(output)},indent=2),encoding='utf-8')
    print(json.dumps({'passed':True,'version':args.version,'installer':str(installer),'bytes':installer.stat().st_size,'bundle':str(bundle)},indent=2))
    return 0


if __name__=='__main__':raise SystemExit(main())
