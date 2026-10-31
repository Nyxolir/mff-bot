from datetime import datetime,timedelta,timezone
import hashlib
from io import BytesIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch,Mock

from lib import app_updates as u
from lib.screen_reader import ScreenEvidence


class UpdateTests(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory(dir=Path(__file__).resolve().parents[3]/'work')
        self.root=Path(self.temp.name);self.cache=self.root/'.cache/updates'
        self.binary=b'verified installer payload';self.digest=hashlib.sha256(self.binary).hexdigest()
        self.manifest={'version':'0.1.10','source_commit':'a'*40,'self_test':{'passed':True},'installation_test':{'passed':True},'artifacts':{u.INSTALLER:self.digest}}
        self.manifest_raw=json.dumps(self.manifest).encode()
        self.release={'tag_name':'v0.1.10','target_commitish':'a'*40,'draft':False,'prerelease':False,'assets':[
            self.asset(u.INSTALLER,self.binary),self.asset(u.MANIFEST,self.manifest_raw)]}
        self.opened=[]

    def tearDown(self):self.temp.cleanup()

    def asset(self,name,data):
        return {'name':name,'browser_download_url':'https://github.com/Nyxolir/mff-bot/releases/download/v0.1.10/'+name,
            'size':len(data),'digest':'sha256:'+hashlib.sha256(data).hexdigest()}

    def opener(self,url):
        self.opened.append(url)
        if url==u.LATEST:return BytesIO(json.dumps(self.release).encode())
        return BytesIO(self.manifest_raw if url.endswith(u.MANIFEST) else self.binary)

    def test_verified_download_is_atomic_and_cached_payload_is_rechecked(self):
        candidate=u.fetch_update('0.1.9',self.cache,opener=self.opener)
        self.assertEqual(Path(candidate['installer']).read_bytes(),self.binary)
        self.assertFalse(list(self.cache.rglob('*.part')))
        self.opened=[];u.fetch_update('0.1.9',self.cache,opener=self.opener)
        self.assertFalse(any(url.endswith(u.INSTALLER) for url in self.opened))
        Path(candidate['installer']).write_bytes(b'tampered')
        u.fetch_update('0.1.9',self.cache,opener=self.opener)
        self.assertEqual(Path(candidate['installer']).read_bytes(),self.binary)

    def test_old_equal_and_failed_versions_never_download_an_installer(self):
        for current,failed in (('0.1.10',None),('1.0.0',None),('0.1.9','0.1.10')):
            self.opened=[];self.assertIsNone(u.fetch_update(current,self.cache,failed,opener=self.opener))
            self.assertEqual(self.opened,[u.LATEST])

    def test_rejects_unpublished_external_duplicate_or_unpinned_releases(self):
        changes=[{'draft':True},{'prerelease':True},{'target_commitish':'main'},
            {'assets':self.release['assets']*2},{'tag_name':'v../0.1.10'}]
        for change in changes:
            with self.subTest(change=change),self.assertRaises(ValueError):u.parse_release(dict(self.release,**change),'0.1.9')
        for field,value in (('digest',''),('size',True),('browser_download_url','https://example.com/installer.exe')):
            changed=dict(self.release);changed['assets']=[dict(self.release['assets'][0],**{field:value}),self.release['assets'][1]]
            with self.subTest(field=field),self.assertRaises(ValueError):u.parse_release(changed,'0.1.9')

    def test_trusted_release_redirects_reject_downgrades_and_unrelated_hosts(self):
        for url in ('http://github.com/x','https://github.com.evil.test/x','https://github.com@evil.test/x','https://github.com:444/x','https://example.com/x'):
            with self.subTest(url=url),self.assertRaises(ValueError):u.trusted_url(url)
        self.assertEqual(u.trusted_url('https://release-assets.githubusercontent.com/path?signature=ok'),'https://release-assets.githubusercontent.com/path?signature=ok')

    def test_truncated_or_changed_download_never_becomes_executable_candidate(self):
        original=self.binary
        for data in (original[:-1],original+b'extra',b'x'*len(original)):
            self.binary=data
            with self.assertRaises(ValueError):u.fetch_update('0.1.9',self.cache,opener=self.opener)
            self.assertFalse(list(self.cache.rglob('*.exe')));self.assertFalse(list(self.cache.rglob('*.part')))

    def test_cancelled_download_never_stages_an_installer(self):
        calls=[]
        def cancelled():calls.append(1);return len(calls)>1
        with self.assertRaises(InterruptedError):u.fetch_update('0.1.9',self.cache,opener=self.opener,cancelled=cancelled)
        self.assertFalse(list(self.cache.rglob('*.exe')));self.assertFalse(list(self.cache.rglob('*.part')))

    def test_manifest_must_match_source_tests_and_installer(self):
        for changes in ({'source_commit':'b'*40},{'self_test':{'passed':False}},{'installation_test':{'passed':False}}, {'artifacts':{u.INSTALLER:'0'*64}}):
            self.manifest_raw=json.dumps(dict(self.manifest,**changes)).encode()
            self.release['assets'][1]=self.asset(u.MANIFEST,self.manifest_raw)
            with self.subTest(changes=changes),self.assertRaises(ValueError):u.fetch_update('0.1.9',self.cache,opener=self.opener)
        self.assertFalse(any(url.endswith(u.INSTALLER) for url in self.opened))

    def test_stopped_receipt_stays_stopped_running_receipt_resumes_correct_queue_once(self):
        for resume in (False,True):
            directory=self.cache/'0.1.10';directory.mkdir(parents=True,exist_ok=True)
            path=directory/'handoff.json'
            plan={'protocol':1,'token':'a'*32,'version':'0.1.10','created_at':datetime.now(timezone.utc).isoformat(),
                'profile':str(self.root),'executable':str(self.root/'MFF Bot.exe'),'resume':resume,'connected':False,'minimized':True,'queue_index':2}
            u.atomic_json(path,plan);u.atomic_json(directory/'result.json',{'token':plan['token'],'stage':'success'})
            receipt=u.consume_update_result(path,root=self.root,executable=self.root/'MFF Bot.exe',current='0.1.10')
            self.assertEqual(receipt['resume'],resume);self.assertEqual(receipt['connected'],resume);self.assertEqual(receipt['queue_index'],2)
            with self.assertRaises(FileExistsError):u.consume_update_result(path,root=self.root,executable=self.root/'MFF Bot.exe',current='0.1.10')
            (directory/'consumed.json').unlink()

    def test_failed_or_changed_pending_state_never_resumes_after_update(self):
        directory=self.cache/'0.1.10';directory.mkdir(parents=True)
        path=directory/'handoff.json';plan={'protocol':1,'token':'a'*32,'version':'0.1.10',
            'created_at':datetime.now(timezone.utc).isoformat(),'profile':str(self.root),'executable':str(self.root/'MFF Bot.exe'),
            'resume':True,'connected':True,'queue_index':1}
        u.atomic_json(path,plan)
        for stage in ('failed','success'):
            u.atomic_json(directory/'result.json',{'token':plan['token'],'stage':stage,'error':'installer failed'})
            if stage=='success':u.atomic_json(self.root/'settings/gui/pending-clear.json',{'pending':['saved','DIMENSION MISSION',10]})
            receipt=u.consume_update_result(path,root=self.root,executable=self.root/'MFF Bot.exe',current='0.1.10')
            self.assertFalse(receipt['resume']);self.assertFalse(receipt['connected'])
            (directory/'consumed.json').unlink()

    def test_resume_receipt_rejects_foreign_stale_wrong_version_and_token(self):
        directory=self.cache/'0.1.10';directory.mkdir(parents=True)
        path=directory/'handoff.json';base={'protocol':1,'token':'a'*32,'version':'0.1.10',
            'created_at':datetime.now(timezone.utc).isoformat(),'profile':str(self.root),'executable':str(self.root/'MFF Bot.exe'),'queue_index':0}
        u.atomic_json(directory/'result.json',{'token':'a'*32,'stage':'success'})
        for changes in ({'token':'b'*32},{'created_at':(datetime.now(timezone.utc)-timedelta(hours=2)).isoformat()},
                        {'version':'0.1.9'},{'executable':str(self.root/'other.exe')},{'queue_index':7}):
            u.atomic_json(path,dict(base,**changes))
            with self.subTest(changes=changes),self.assertRaises(ValueError):u.consume_update_result(path,root=self.root,executable=self.root/'MFF Bot.exe',current='0.1.10')
        with self.assertRaises(ValueError):u.consume_update_result(self.root/'outside.json',root=self.root)

    def test_saved_submission_or_malformed_state_blocks_handoff(self):
        path=self.root/'settings/gui/pending-clear.json'
        for value in ({'pending':['saved','mode',1]},{},{'pending':None,'contribution_followup':True}):
            u.atomic_json(path,value);self.assertIsNotNone(u.saved_update_blocker(self.root))
        path.write_text('{broken');self.assertIsNotNone(u.saved_update_blocker(self.root))
        u.atomic_json(path,{'pending':None});self.assertIsNone(u.saved_update_blocker(self.root))
        u.atomic_json(path.with_name('world-event.json'),{'pending':False,'started':True});self.assertIsNotNone(u.saved_update_blocker(self.root))

    def test_only_fresh_live_idle_pages_authorize_connected_updates(self):
        now=datetime.now(timezone.utc);idle=ScreenEvidence('game_home')
        self.assertTrue(u.idle_update_evidence(idle,now,now,True))
        self.assertTrue(u.idle_update_evidence(ScreenEvidence('challenge_navigation',{'home_available':True,'menu_available':True}),now,now,True))
        self.assertFalse(u.idle_update_evidence(ScreenEvidence('challenge_navigation',{'home_available':True}),now,now,True))
        for evidence,stamp,live in ((idle,now-timedelta(seconds=31),True),(idle,now,False),
                                   (ScreenEvidence('we_battle'),now,True),(ScreenEvidence('unknown'),now,True)):
            self.assertFalse(u.idle_update_evidence(evidence,stamp,now,live))

    def test_source_checkout_never_claims_installer_version(self):
        import sys
        with patch.object(sys,'frozen',False,create=True):self.assertIsNone(u.installed_version())

    def test_numeric_version_comparison_rejects_invalid_or_oversize_versions(self):
        self.assertGreater(u.version_tuple('0.1.10'),u.version_tuple('0.1.9'))
        for value in ('latest','v0.1.3','0.1.3-beta','0.1.65536','../0.1.3','0.01.3'):
            with self.assertRaises(ValueError):u.version_tuple(value)

    def test_handoff_rechecks_installer_and_uses_its_own_helper_copy(self):
        candidate=u.fetch_update('0.1.9',self.cache,opener=self.opener)
        exe=self.root/'app/MFF Bot.exe';exe.parent.mkdir();exe.write_bytes(b'app')
        helper=self.root/'helper.exe';helper.write_bytes(b'helper')
        path,copied,plan=u.prepare_handoff(candidate,True,True,False,exe,self.root,helper,queue_index=3)
        self.assertEqual(copied.read_bytes(),helper.read_bytes());self.assertNotEqual(copied,helper)
        self.assertEqual(plan['queue_index'],3);self.assertTrue(plan['resume'])
        self.assertEqual(json.loads(path.read_text())['token'],plan['token'])
        Path(candidate['installer']).write_bytes(b'changed after download')
        with self.assertRaises(ValueError):u.prepare_handoff(candidate,True,True,False,exe,self.root,helper)

    def test_network_or_oversize_metadata_failure_cannot_stage_an_installer(self):
        def unavailable(url):raise OSError('offline')
        with self.assertRaises(OSError):u.fetch_update('0.1.9',self.cache,opener=unavailable)
        with self.assertRaises(ValueError):u.read_asset(u.LATEST,10,lambda url:BytesIO(b'x'*11))
        self.assertFalse(self.cache.exists())
