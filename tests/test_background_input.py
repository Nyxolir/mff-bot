from io import BytesIO
from pathlib import Path
from unittest.mock import Mock,patch
import unittest
import struct
from PIL import Image
from lib.background_input import AdbBackend,set_backend
from lib.resource_check import click_game_point,InputNotSent

class BackgroundInputTests(unittest.TestCase):
    def test_board_up_swipe_starts_inside_the_scrollable_list(self):
        for screen in ('content_board','trivia_list'):
            with self.subTest(screen=screen):
                backend=self.backend();backend.input_evidence={'screen':screen}
                backend.send(1000,500,scroll=('up',8))
                self.assertEqual(backend._run.call_args.args[0][-6:],['swipe','1000','250','1000','680','450'])

    def test_second_input_needs_capture_after_previous_command_finishes(self):
        from datetime import datetime,timedelta,timezone
        backend=self.backend();now=datetime.now(timezone.utc)
        backend.input_evidence={'screen':'content_board','captured_at':now.isoformat()}
        backend.send(1185,36)
        with self.assertRaisesRegex(InputNotSent,'Fresh screenshot'):backend.send(1185,36)
        self.assertEqual(backend._run.call_count,1)
        backend.input_evidence={'screen':'navigation_menu','captured_at':(backend.last_input_at+timedelta(milliseconds=1)).isoformat()}
        backend.send(630,642);self.assertEqual(backend._run.call_count,2)

    def test_home_gear_is_never_used_as_home_navigation(self):
        backend=self.backend()
        for screen in ('game_home','we_home'):
            backend.input_evidence={'screen':screen}
            with self.assertRaisesRegex(InputNotSent,'Settings gear'):backend.send(1185,36)
        backend._run.assert_not_called()

    def test_input_audit_records_evidence_only_after_guard_allows_input(self):
        import json
        from tempfile import TemporaryDirectory
        root=Path(__file__).resolve().parents[3]/'work/audit-tests';root.mkdir(parents=True,exist_ok=True)
        with TemporaryDirectory(dir=root) as directory:
            backend=self.backend();backend.input_audit_path=Path(directory)/'input.jsonl'
            backend.input_evidence={'screen':'arena_repeat_ended','mode':'TIMELINE BATTLE'}
            with self.assertRaises(InputNotSent):backend.send(755,604,guard=lambda:False)
            self.assertFalse(backend.input_audit_path.exists())
            backend.send(755,604,guard=lambda:True)
            record=json.loads(backend.input_audit_path.read_text())
            self.assertEqual(record['action'],['tap','755','604'])
            self.assertEqual(record['evidence']['mode'],'TIMELINE BATTLE')
    def test_named_instance_uses_runtime_port_instead_of_stale_configured_port(self):
        from lib.background_input import instance_port
        config='bst.instance.Pie64.display_name="BlueStacks App Player 1080"\nbst.instance.Pie64.adb_port="5555"\nbst.instance.Pie64.status.adb_port="5556"\nbst.instance.Pie64_7.display_name="BlueStacks App Player 4k"\nbst.instance.Pie64_7.adb_port="5625"\n'
        self.assertEqual(instance_port(config,'BlueStacks App Player 1080'),5556)
        self.assertEqual(instance_port(config,'Pie64_7'),5625)
        with self.assertRaisesRegex(RuntimeError,'Multiple'):instance_port(config)
        with self.assertRaisesRegex(RuntimeError,'uniquely'):instance_port(config,'Unknown window')

    def test_private_adb_server_does_not_replace_webcam_server(self):
        backend=AdbBackend();result=Mock(returncode=0,stdout=b'device',stderr=b'')
        with patch('lib.background_input.subprocess.run',return_value=result) as run:
            self.assertEqual(backend._run(['devices']),b'device')
            self.assertEqual(run.call_args.args[0][1:],['-P','5042','devices'])

    def test_restart_only_verified_game_package_and_order(self):
        backend=self.backend();backend._run.return_value=b'package:com.netmarble.mherosgb\npackage:com.other.app\n'
        backend.restart_game(lambda:True)
        calls=[c.args[0] for c in backend._run.call_args_list]
        self.assertEqual(calls[1][-3:],['input','keyevent','3'])
        self.assertEqual(calls[2][-3:],['am','force-stop','com.netmarble.mherosgb'])
        self.assertEqual(calls[3][-6:],['monkey','-p','com.netmarble.mherosgb','-c','android.intent.category.LAUNCHER','1'])
    def test_restart_rejects_missing_package_or_cancelled_guard(self):
        backend=self.backend()
        with self.assertRaisesRegex(RuntimeError,'verified'):backend.restart_game()
        self.assertEqual(backend._run.call_count,1)
        backend._run.reset_mock()
        with self.assertRaisesRegex(RuntimeError,'cancelled'):backend.restart_game(lambda:False)
        backend._run.assert_not_called()
    def test_black_frames_never_reach_recognition_and_retry_png(self):
        backend=self.backend();bad=BytesIO();Image.new('RGB',(1280,720)).save(bad,format='PNG')
        good=BytesIO();Image.new('RGB',(1280,720),(20,20,20)).save(good,format='PNG')
        backend._run.side_effect=[bad.getvalue(),good.getvalue()]
        image,_=backend.capture();self.assertEqual(image.getpixel((10,10)),(20,20,20))
        self.assertEqual(backend._run.call_args.args[0][-1],'-p')
        backend._run.side_effect=None;backend._run.return_value=bad.getvalue()
        with self.assertRaisesRegex(RuntimeError,'three captures'):backend.capture()
    def tearDown(self):set_backend()

    def backend(self):
        backend=AdbBackend();backend.serial='127.0.0.1:5555';backend.connected=True
        backend.device_size=(1280,720)
        backend._run=Mock(return_value=b'')
        return backend

    def test_required_background_never_falls_back_to_windows(self):
        set_backend(required=True)
        with self.assertRaises(InputNotSent):click_game_point(11,400,300)
        backend=self.backend();set_backend(backend,required=True)
        click_game_point(11,400,300,guard=lambda:True)
        backend._run.assert_called_once_with(['-s','127.0.0.1:5555','shell','input','tap','400','300'],timeout=10)

    def test_stop_blocks_android_input_and_errors_do_not_use_mouse(self):
        backend=self.backend();set_backend(backend,required=True)
        with self.assertRaises(InputNotSent):click_game_point(11,400,300,guard=lambda:False)
        backend._run.assert_not_called()
        backend._run.side_effect=RuntimeError('offline')
        with self.assertRaisesRegex(RuntimeError,'offline'):click_game_point(11,400,300)

    def test_back_swipe_and_board_scroll_are_android_commands(self):
        backend=self.backend()
        backend.send(35,36,key='back')
        self.assertEqual(backend._run.call_args.args[0][-2:],['keyevent','4'])
        backend.send(500,658,drag_to=(80,658))
        self.assertEqual(backend._run.call_args.args[0][-6:],['swipe','500','658','80','658','650'])
        backend.send(640,518,drag_to=(640,228))
        self.assertEqual(backend._run.call_args.args[0][-6:],['swipe','640','518','640','228','650'])
        backend.send(1000,500,scroll=('down',3))
        self.assertEqual(backend._run.call_args.args[0][-6:],['swipe','1000','600','1000','300','450'])
        with self.assertRaises(ValueError):backend.send(1,1,drag_to=(1200,500))

    def test_disabled_debugging_requires_user_setting_without_commands(self):
        backend=self.backend()
        with patch.object(Path,'read_text',return_value='bst.enable_adb_access="0"\n'):
            with self.assertRaisesRegex(RuntimeError,'Enable BlueStacks'):backend.connect()
        backend._run.assert_not_called()

    def test_connection_is_explicit_local_device_and_resolution(self):
        png=BytesIO();Image.new('RGB',(3840,2160),(20,20,20)).save(png,format='PNG')
        backend=AdbBackend();backend._run=Mock(side_effect=[b'List of devices attached\n',b'connected',b'device\n',png.getvalue()])
        config='bst.enable_adb_access="1"\nbst.instance.Pie64.adb_port="5555"\n'
        with patch.object(Path,'read_text',return_value=config),patch.object(Path,'is_file',return_value=True):backend.connect()
        self.assertTrue(backend.connected)
        self.assertEqual(backend.device_size,(3840,2160))
        self.assertEqual(backend._run.call_args_list[1].args[0],['connect','127.0.0.1:5555'])
        self.assertEqual(backend._run.call_args_list[2].args[0],['-s','127.0.0.1:5555','get-state'])

    def test_native_bluestacks_transport_is_used_when_already_available(self):
        png=BytesIO();Image.new('RGB',(1280,720),(20,20,20)).save(png,format='PNG')
        backend=AdbBackend();backend._run=Mock(side_effect=[b'List of devices attached\nemulator-5554\tdevice\n',b'device\n',png.getvalue()])
        config='bst.enable_adb_access="1"\nbst.instance.Pie64.adb_port="5555"\n'
        with patch.object(Path,'read_text',return_value=config),patch.object(Path,'is_file',return_value=True):backend.connect()
        self.assertEqual(backend.serial,'emulator-5554')
        self.assertFalse(any(call.args[0][0]=='connect' for call in backend._run.call_args_list))

    def test_capture_comes_from_android_and_rejects_changed_resolution(self):
        backend=self.backend();data=BytesIO();Image.new('RGB',(1280,720),(20,20,20)).save(data,format='PNG')
        backend._run.return_value=data.getvalue()
        image,_=backend.capture();self.assertEqual(image.size,(1280,720))
        self.assertEqual(backend._run.call_args.args[0][-2:],['exec-out','screencap'])
        data=BytesIO();Image.new('RGB',(720,1280),(20,20,20)).save(data,format='PNG');backend._run.return_value=data.getvalue()
        with self.assertRaisesRegex(RuntimeError,'landscape'):backend.capture()

    def test_four_k_capture_and_tap_swipe_scroll_scaling(self):
        backend=self.backend();backend.device_size=None
        png=BytesIO();Image.new('RGB',(3840,2160),(20,20,20)).save(png,format='PNG')
        backend._run.return_value=png.getvalue()
        image,data=backend.capture()
        self.assertEqual(image.size,(1280,720));self.assertEqual(Image.open(BytesIO(data)).size,(1280,720))
        backend.send(640,360)
        self.assertEqual(backend._run.call_args.args[0][-3:],['tap','1920','1080'])
        backend.send(1030,318,drag_to=(220,318))
        self.assertEqual(backend._run.call_args.args[0][-6:],['swipe','3090','954','660','954','650'])
        backend.send(1000,500,scroll=('down',3))
        self.assertEqual(backend._run.call_args.args[0][-6:],['swipe','3000','1800','3000','900','450'])

    def test_changed_landscape_resolution_requires_new_capture_session(self):
        backend=self.backend();png=BytesIO();Image.new('RGB',(1920,1080)).save(png,format='PNG')
        backend._run.return_value=png.getvalue()
        with self.assertRaisesRegex(RuntimeError,'reconnect'):backend.capture()
        self.assertEqual(backend.device_size,(1280,720))

    def test_truncated_capture_is_retried_without_using_partial_pixels(self):
        backend=self.backend();png=BytesIO();Image.new('RGB',(1280,720),(20,20,20)).save(png,format='PNG')
        backend._run.side_effect=[png.getvalue()[:100],png.getvalue()]
        image,_=backend.capture()
        self.assertEqual(image.size,(1280,720));self.assertEqual(backend._run.call_count,2)
        backend._run.side_effect=None;backend._run.return_value=png.getvalue()[:100]
        with self.assertRaisesRegex(RuntimeError,'three captures'):backend.capture()

    def test_lost_capture_transport_reconnects_without_retrying_input(self):
        backend=self.backend();png=BytesIO();Image.new('RGB',(1280,720),(20,20,20)).save(png,format='PNG')
        backend._run.side_effect=[RuntimeError('device not found'),b'connected',png.getvalue()]
        image,_=backend.capture();self.assertEqual(image.size,(1280,720))
        self.assertEqual(backend._run.call_args_list[1].args[0],['connect','127.0.0.1:5555'])

    def test_uncompressed_android_capture_is_decoded_and_normalized(self):
        backend=self.backend();backend.device_size=None
        raw=Image.new('RGBA',(3840,2160),(10,20,30,255)).tobytes()
        backend._run.return_value=struct.pack('<III',3840,2160,1)+raw
        image,_=backend.capture()
        self.assertEqual(image.size,(1280,720));self.assertEqual(image.getpixel((500,300)),(10,20,30))
        backend.device_size=None
        backend._run.return_value=struct.pack('<III',1280,720,2)+Image.new('RGBX',(1280,720),(40,50,60,255)).tobytes()
        image,_=backend.capture();self.assertEqual(image.getpixel((500,300)),(40,50,60))

