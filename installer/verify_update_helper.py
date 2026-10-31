"""Exercise the native helper against isolated fake apps/installers, never a game."""
from datetime import datetime,timezone
import hashlib,json,os
from pathlib import Path
import subprocess
import sys,tempfile,time

ROOT=Path(__file__).resolve().parents[1]
STUB=r'''
using System;using System.IO;using System.Threading;using System.Diagnostics;
class Stub {
 static int Main(string[] args) {
  string root=Environment.GetEnvironmentVariable("MFF_HELPER_TEST_ROOT");
  string exe=Process.GetCurrentProcess().MainModule.FileName;
  if(Path.GetFileName(exe)=="MFF-Bot-Setup.exe") {
   if(!File.Exists(Path.Combine(root,"parent-exited")))return 8;
   File.WriteAllText(Path.Combine(root,"installer-arguments"),String.Join(" ",args));
   if(Environment.GetEnvironmentVariable("MFF_HELPER_TEST_FAIL")=="1")return 9;
   File.WriteAllText(Path.Combine(root,"app","_internal","build-info.json"),"{\"version\":\"0.1.99\"}");return 0;
  }
  if(args.Length>0 && args[0]=="--hold") {
   while(!File.Exists(Path.Combine(root,"release-parent")))Thread.Sleep(25);
   File.WriteAllText(Path.Combine(root,"parent-exited"),"true");return 0;
  }
  if(args.Length>0 && args[0]=="--self-test") {
   if(Environment.GetEnvironmentVariable("MFF_HELPER_TEST_BAD_CHECK")=="1")return 0;
   File.WriteAllText(args[1],"{\"passed\":true,\"game_connected\":false,\"queue_started\":false}");return 0;
  }
  File.WriteAllText(Path.Combine(root,"restarted-arguments"),String.Join(" ",args));return 0;
 }
}
'''


def wait_for(path,process=None,timeout=20):
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        if path.exists():return
        if process is not None and process.poll() is not None:raise AssertionError('Helper exited early: '+str(process.returncode))
        time.sleep(.05)
    raise AssertionError('Timed out waiting for '+path.name)


def run_checks(helper,work):
    compiler=Path(os.environ['WINDIR'])/'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
    source=work/'Stub.cs';source.write_text(STUB)
    payload=work/'Stub.exe'
    subprocess.run([str(compiler),'/nologo','/target:winexe','/out:'+str(payload),str(source)],check=True)
    outcomes=[]
    for case in ('success','cancel','no_commit','changed_installer','install_failure','app_check_failure'):
        root=work/case;app=root/'app';(app/'_internal').mkdir(parents=True)
        exe=app/'MFF Bot.exe';exe.write_bytes(payload.read_bytes())
        job=root/'profile/.cache/updates/0.1.99';job.mkdir(parents=True)
        installer=job/'MFF-Bot-Setup.exe';installer.write_bytes(payload.read_bytes())
        plan={'protocol':1,'token':'a'*32,'version':'0.1.99','created_at':datetime.now(timezone.utc).isoformat(),
              'executable':str(exe),'profile':str(root/'profile'),'installer':str(installer),
              'sha256':hashlib.sha256(installer.read_bytes()).hexdigest(),'resume':True,'connected':True,'queue_index':2}
        env=dict(os.environ,MFF_HELPER_TEST_ROOT=str(root),MFF_HELPER_TEST_FAIL='1' if case=='install_failure' else '0',MFF_HELPER_TEST_BAD_CHECK='1' if case=='app_check_failure' else '0')
        if case=='app_check_failure':(job/'application-check.json').write_text('{"passed":true,"game_connected":false,"queue_started":false}')
        env.pop('MFF_UPDATER_SELFTEST',None)
        parent=subprocess.Popen([str(exe),'--hold'],env=env,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        plan['parent_pid']=parent.pid;path=job/'handoff.json';path.write_text(json.dumps(plan))
        process=subprocess.Popen([str(helper),str(path)],env=env,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        try:
            wait_for(job/'ready.json',process)
            assert parent.poll() is None and not (root/'installer-arguments').exists()
            marker='cancel.json' if case=='cancel' else 'commit.json'
            if case!='no_commit':(job/marker).write_text(json.dumps({'token':plan['token']}))
            if case=='changed_installer':installer.write_bytes(installer.read_bytes()+b'changed')
            (root/'release-parent').write_text('true');parent.wait(timeout=10)
            process.wait(timeout=30)
            result=json.loads((job/'result.json').read_text())
            if case=='success':
                assert process.returncode==0 and result['stage']=='success'
                wait_for(root/'restarted-arguments')
                arguments=(root/'installer-arguments').read_text()
                assert '/NOCLOSEAPPLICATIONS' in arguments and '/NORESTART' in arguments and '/FORCECLOSEAPPLICATIONS' not in arguments
                assert json.loads((job/'application-check.json').read_text())['passed']
            else:
                assert process.returncode!=0 and result['stage']=='failed'
                if case not in ('install_failure','app_check_failure'):assert not (root/'installer-arguments').exists()
            outcomes.append(case)
        finally:
            (root/'release-parent').write_text('true')
            parent.wait(timeout=10)
            if process.poll() is None:
                (job/'cancel.json').write_text(json.dumps({'token':plan['token']}));process.wait(timeout=10)
    return {'passed':True,'native_helper_cases':outcomes,'game_connected':False}


if __name__=='__main__':
    helper=Path(sys.argv[1]).resolve();base=Path(sys.argv[2]).resolve();base.mkdir(parents=True,exist_ok=True)
    work=Path(tempfile.mkdtemp(prefix='run-',dir=base))
    report=run_checks(helper,work)
    (base/'native-helper-validation.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(report))
