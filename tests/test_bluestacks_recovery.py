from datetime import datetime,timedelta,timezone
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock,patch
import unittest
from PIL import Image
from lib import bluestacks_recovery as recovery
from lib.background_input import AdbBackend

class RecoveryWorkerTests(unittest.TestCase):
    def setUp(self):
        root=Path(__file__).resolve().parents[3]/'work/recovery-tests';root.mkdir(parents=True,exist_ok=True)
        self.temp=TemporaryDirectory(dir=root);self.addCleanup(self.temp.cleanup)
        self.backend=Mock();self.backend.executable=Path(self.temp.name)/'HD-Adb.exe'
        self.player=self.backend.executable.with_name('HD-Player.exe');self.player.touch()
        self.backend.selected_instance.return_value=('Pie64',{'display_name':'BlueStacks App Player 1080'})
        self.backend.initial_frame=(Image.new('RGB',(1280,720),(20,20,20)),b'frame')
        self.backend.capture.return_value=self.backend.initial_frame
        self.clock=0
        def sleep(seconds):self.clock+=seconds
        for item in (patch.object(recovery.time,'monotonic',side_effect=lambda:self.clock),
                     patch.object(recovery.time,'sleep',side_effect=sleep),
                     patch.object(recovery,'players_running',return_value=True),
                     patch.object(recovery.subprocess,'Popen'),patch('lib.android_home.android_home',return_value=None)):
            item.start();self.addCleanup(item.stop)

    def test_fully_closed_player_starts_exact_instance_once_then_launches_game(self):
        recovery.players_running.side_effect=[False,True,True]
        self.backend.connect.side_effect=[RuntimeError('still booting'),None]
        probe=Mock(return_value=44);messages=[]
        result=recovery.recover_connection(self.backend,probe,lambda:True,messages.append,timeout=10)
        recovery.subprocess.Popen.assert_called_once()
        self.assertEqual(recovery.subprocess.Popen.call_args.args[0],[str(self.player),'--instance','Pie64'])
        self.assertEqual(probe.call_args.args,('BlueStacks App Player 1080',))
        self.assertTrue(result.launched);self.assertTrue(result.game_opened);self.assertEqual(result.handle,44)
        self.backend.launch_game.assert_called_once();self.backend.restart_game.assert_not_called()
        self.assertIn('Pie64',messages[0])

    def test_temporary_transport_loss_reconnects_existing_player_without_launch(self):
        result=recovery.recover_connection(self.backend,lambda title:44,lambda:True)
        recovery.subprocess.Popen.assert_not_called();self.backend.connect.assert_called_once()
        self.backend.launch_game.assert_not_called();self.assertFalse(result.launched)

    def test_other_instance_window_is_not_a_reason_to_launch_or_connect_old_port(self):
        with self.assertRaisesRegex(RuntimeError,'no duplicate'):
            recovery.recover_connection(self.backend,lambda title:None,lambda:True,timeout=5)
        recovery.subprocess.Popen.assert_not_called();self.backend.connect.assert_not_called()

    def test_stop_before_recovery_prevents_every_launch_and_connection(self):
        with self.assertRaisesRegex(RuntimeError,'cancelled'):
            recovery.recover_connection(self.backend,lambda title:44,lambda:False)
        recovery.subprocess.Popen.assert_not_called();self.backend.connect.assert_not_called()

    def test_target_window_disappearing_during_connect_prevents_game_launch(self):
        probe=Mock(side_effect=[44,None,None,None])
        with self.assertRaisesRegex(RuntimeError,'timed out'):
            recovery.recover_connection(self.backend,probe,lambda:True,timeout=5)
        self.backend.launch_game.assert_not_called();recovery.subprocess.Popen.assert_not_called()

    def test_stop_during_boot_does_not_retry_player_or_launch_game(self):
        recovery.players_running.return_value=False
        with self.assertRaisesRegex(RuntimeError,'cancelled'):
            recovery.recover_connection(self.backend,lambda title:None,lambda:self.clock<2,timeout=10)
        recovery.subprocess.Popen.assert_called_once();self.backend.connect.assert_not_called();self.backend.launch_game.assert_not_called()

    def test_failed_player_boot_is_bounded_and_does_not_spawn_repeated_players(self):
        recovery.players_running.return_value=False
        with self.assertRaisesRegex(RuntimeError,'timed out'):
            recovery.recover_connection(self.backend,lambda title:None,lambda:True,timeout=5)
        recovery.subprocess.Popen.assert_called_once();self.backend.connect.assert_not_called()

    def test_ambiguous_identity_or_disabled_adb_prevents_launch(self):
        for message in ('Multiple BlueStacks instances configured','Enable BlueStacks ADB'):
            self.backend.selected_instance.side_effect=RuntimeError(message)
            with self.assertRaisesRegex(RuntimeError,message):recovery.recover_connection(self.backend,lambda title:44,lambda:True)
        recovery.subprocess.Popen.assert_not_called()

    def test_verified_launcher_can_open_game_without_restarting_emulator(self):
        with patch('lib.android_home.android_home',return_value=object()):
            result=recovery.recover_connection(self.backend,lambda title:44,lambda:True)
        self.assertTrue(result.game_opened);self.assertFalse(result.launched)
        self.backend.launch_game.assert_called_once();self.backend.restart_game.assert_not_called()

    def test_persistent_bridge_failure_stops_verified_player_once_and_relaunches_same_instance(self):
        running=[True]
        recovery.players_running.side_effect=lambda:running[0]
        recovery.subprocess.Popen.side_effect=lambda *a,**k:running.__setitem__(0,True)
        self.backend.connect.side_effect=[RuntimeError('device offline'),None]
        with patch.object(recovery,'stop_selected_player',side_effect=lambda *a:running.__setitem__(0,False)) as stop:
            result=recovery.recover_connection(self.backend,lambda title:44,lambda:True,timeout=12,restart_after=0)
        stop.assert_called_once();self.assertEqual(stop.call_args.args[1:3],('BlueStacks App Player 1080',44))
        recovery.subprocess.Popen.assert_called_once()
        self.assertEqual(recovery.subprocess.Popen.call_args.args[0][-2:],['--instance','Pie64'])
        self.assertTrue(result.launched);self.backend.launch_game.assert_called_once()

    def test_failed_bridge_after_relaunch_never_causes_a_second_kill_or_launch(self):
        running=[True];recovery.players_running.side_effect=lambda:running[0]
        recovery.subprocess.Popen.side_effect=lambda *a,**k:running.__setitem__(0,True)
        self.backend.connect.side_effect=RuntimeError('device offline')
        with patch.object(recovery,'stop_selected_player',side_effect=lambda *a:running.__setitem__(0,False)) as stop:
            with self.assertRaisesRegex(RuntimeError,'timed out'):
                recovery.recover_connection(self.backend,lambda title:44,lambda:True,timeout=12,restart_after=0)
        stop.assert_called_once();recovery.subprocess.Popen.assert_called_once()

class TargetedPlayerStopTests(unittest.TestCase):
    def test_pid_lookup_requires_window_owner_and_matching_player_process(self):
        import ctypes
        from ctypes import wintypes
        user32=Mock()
        def owner(handle,out):ctypes.cast(out,ctypes.POINTER(wintypes.DWORD)).contents.value=647;return 1
        user32.GetWindowThreadProcessId.side_effect=owner
        for body,accepted in ((b'"HD-Player.exe","647","Console"\r\n',True),
                              (b'"other.exe","647","Console"\r\n',False),
                              (b'"HD-Player.exe","648","Console"\r\n',False),(b'error',False)):
            with patch.object(ctypes,'WinDLL',return_value=user32),patch.object(recovery.subprocess,'run',return_value=Mock(returncode=0,stdout=body)):
                if accepted:self.assertEqual(recovery.selected_player_pid(44),647)
                else:
                    with self.assertRaisesRegex(RuntimeError,'verified BlueStacks'):recovery.selected_player_pid(44)

    def test_verified_pid_only_and_only_private_bridge_reset(self):
        backend=Mock(connected=True,server_port=5042)
        with patch.object(recovery,'selected_player_pid',return_value=647),patch.object(recovery.subprocess,'run',return_value=Mock(returncode=0)) as run:
            recovery.stop_selected_player(backend,'Selected',44,lambda title:44,lambda:True)
        self.assertEqual(run.call_args.args[0][1:],['/PID','647','/T','/F'])
        backend._run.assert_called_once_with(['kill-server'],timeout=10);self.assertFalse(backend.connected)
        backend=Mock(server_port=5037)
        with patch.object(recovery,'selected_player_pid',return_value=647),patch.object(recovery.subprocess,'run',return_value=Mock(returncode=0)):
            recovery.stop_selected_player(backend,'Selected',44,lambda title:44,lambda:True)
        backend._run.assert_not_called()

    def test_cancel_changed_window_or_changed_pid_prevents_kill(self):
        for guard,probe,pids in ((lambda:False,lambda title:44,[647]),(lambda:True,lambda title:None,[647]),(lambda:True,lambda title:44,[647,648])):
            with patch.object(recovery,'selected_player_pid',side_effect=pids),patch.object(recovery.subprocess,'run') as run:
                with self.assertRaises(RuntimeError):recovery.stop_selected_player(Mock(),'Selected',44,probe,guard)
                run.assert_not_called()

    def test_failed_termination_never_resets_another_bridge(self):
        backend=Mock(server_port=5042)
        with patch.object(recovery,'selected_player_pid',return_value=647),patch.object(recovery.subprocess,'run',return_value=Mock(returncode=1)):
            with self.assertRaisesRegex(RuntimeError,'Could not stop'):recovery.stop_selected_player(backend,'Selected',44,lambda title:44,lambda:True)
        backend._run.assert_not_called()

    def test_real_capture_error_hint_is_not_a_transport_loss(self):
        message='Background screenshot incomplete after three captures; reconnect'
        self.assertTrue(recovery.capture_failure(message));self.assertFalse(recovery.transport_failure(message))
        self.assertTrue(recovery.transport_failure("device 'emulator-5554' not found"))

class LaunchGameTests(unittest.TestCase):
    def test_open_game_verifies_package_and_never_force_stops_or_sends_home(self):
        backend=AdbBackend();backend.connected=True;backend.serial='emulator-5554'
        backend._run=Mock(return_value=b'package:com.netmarble.mherosgb\n')
        backend.launch_game(lambda:True)
        self.assertEqual(len(backend._run.call_args_list),2)
        command=backend._run.call_args_list[1].args[0]
        self.assertEqual(command[-6:],['monkey','-p','com.netmarble.mherosgb','-c','android.intent.category.LAUNCHER','1'])
        self.assertNotIn('force-stop',str(backend._run.call_args_list));self.assertNotIn('keyevent',str(backend._run.call_args_list))

    def test_unverified_package_and_stop_prevent_game_launch(self):
        backend=AdbBackend();backend.connected=True;backend.serial='emulator-5554';backend._run=Mock(return_value=b'package:other\n')
        with self.assertRaisesRegex(RuntimeError,'verified'):backend.launch_game(lambda:True)
        self.assertEqual(backend._run.call_count,1);backend._run.reset_mock()
        with self.assertRaisesRegex(RuntimeError,'cancelled'):backend.launch_game(lambda:False)
        backend._run.assert_not_called()

    def test_remembered_instance_name_survives_changed_display_title(self):
        backend=AdbBackend(instance_hint='Old title');backend.instance_name='Pie64'
        text='bst.enable_adb_access="1"\nbst.instance.Pie64.display_name="New title"\nbst.instance.Pie64.adb_port="5555"\nbst.instance.Pie64_7.adb_port="5625"\n'
        with patch.object(Path,'read_text',return_value=text):self.assertEqual(backend.selected_instance()[0],'Pie64')

class ProcessSnapshotTests(unittest.TestCase):
    def test_snapshot_requires_valid_csv_and_never_infers_absence_from_command_failure(self):
        for body,expected in ((b'"python.exe","12","Console"\r\n',False),
                              (b'"HD-Player.exe","34","Console"\r\n',True)):
            with patch.object(recovery.subprocess,'run',return_value=Mock(returncode=0,stdout=body)):
                self.assertEqual(recovery.players_running(),expected)
        for result in (Mock(returncode=1,stdout=b''),Mock(returncode=0,stdout=b'error'),Mock(returncode=0,stdout=b'')):
            with patch.object(recovery.subprocess,'run',return_value=result):
                with self.assertRaises(RuntimeError):recovery.players_running()

if __name__=='__main__':unittest.main()
