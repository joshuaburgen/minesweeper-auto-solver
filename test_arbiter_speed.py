"""Image-backed native I/O tests: no real mouse, keyboard or screenshots."""
from unittest import TestCase
from unittest.mock import Mock, patch
import numpy as np

from arbiter_platform import ArbiterPlatform
from arbiter_geometry import BoardGeometry
from game_pacer import GamePacer
from run_control import StopRequested
from Board import GameLost
from test_arbiter_skin import covered, flagged, revealed, mine_death


def platform_with_images():
    frame = np.tile(covered(20), (9, 9, 1))
    window = Mock()
    window.client_size.return_value = (180, 180)
    window.client_origin_screen.return_value = (0, 0)
    window.capture_client.side_effect = lambda: frame.copy()
    platform = ArbiterPlatform(difficulty=1, window=window,
                               geometry=BoardGeometry(0, 0, 20, 20),
                               use_saved=False, settle=0)
    def paint(x, y, image):
        row, col = y // 20, x // 20
        frame[row * 20:(row + 1) * 20, col * 20:(col + 1) * 20] = image
    window.right_click.side_effect = lambda x, y, **kw: paint(x, y, flagged(20))
    window.left_click.side_effect = lambda x, y, **kw: paint(x, y, revealed(1, 20))
    return platform, window, frame, paint


class TestArbiterSpeed(TestCase):
    def test_paced_flags_are_individually_spaced_and_observed(self):
        platform, window, _, paint = platform_with_images()
        now = [0]
        times = []
        control = Mock()
        def wait(seconds):
            now[0] += seconds
        control.wait.side_effect = wait
        platform.control = control
        platform.pacer = GamePacer(35, 81, control, clock=lambda: now[0])
        def click(x, y, **kw):
            times.append(now[0])
            paint(x, y, flagged(20))
        window.right_click.side_effect = click
        platform.flag_cells([(0, c) for c in range(5)])
        self.assertEqual(len(times), 5)
        self.assertTrue(all(0 < b - a <= 0.5 for a, b in zip(times, times[1:])))
        self.assertEqual(window.capture_client.call_count, 5)

    @patch('Runner.RunControl')
    @patch('Runner.Board')
    @patch('arbiter_platform.ArbiterPlatform')
    def test_target_is_passed_without_replacing_total_timeout(self, platform_type, board_type, control_type):
        from Runner import main
        self.assertEqual(main(['--platform', 'arbiter', '--seconds', '60', '--target-seconds', '5']), 0)
        self.assertEqual(platform_type.call_args.kwargs['target_seconds'], 5)
        self.assertEqual(platform_type.call_args.kwargs['settle'], 0.02)
        self.assertEqual(control_type.call_args.args[0], 60)

    def test_five_flags_need_two_captures_and_verify_all_flags(self):
        platform, window, _, _ = platform_with_images()
        platform.flag_cells([(0, c) for c in range(5)])
        self.assertEqual(window.right_click.call_count, 5)
        self.assertEqual(window.capture_client.call_count, 2)
        for c in range(5):
            self.assertEqual(platform.read_cell(0, c), 'square bombflagged')
        platform.begin_read()  # Board consumes the final already-captured frame
        self.assertEqual(window.capture_client.call_count, 2)

    def test_reveal_chunk_skips_next_chunk_cells_opened_by_flood(self):
        platform, window, frame, _ = platform_with_images()
        def flood(*args, **kwargs):
            frame[:] = np.tile(revealed(0, 20), (9, 9, 1))
        window.left_click.side_effect = flood
        platform.reveal_cells([(0, c) for c in range(8)])
        self.assertEqual(window.left_click.call_count, 4)
        self.assertEqual(window.capture_client.call_count, 1)

    def test_mine_stops_before_next_chunk(self):
        platform, window, _, paint = platform_with_images()
        window.left_click.side_effect = lambda x, y, **kw: paint(x, y, mine_death(20))
        with self.assertRaises(GameLost):
            platform.reveal_cells([(0, c) for c in range(8)])
        self.assertEqual(window.left_click.call_count, 4)

    def test_emergency_stop_still_checked_between_batch_clicks(self):
        platform, window, _, _ = platform_with_images()
        platform.control = Mock()
        platform.control.check.side_effect = [None, StopRequested('Esc')]
        with self.assertRaises(StopRequested):
            platform.flag_cells([(0, c) for c in range(4)])
        self.assertEqual(window.right_click.call_count, 1)


class TestGamePacer(TestCase):
    def test_reasoning_pause_does_not_trigger_catchup_burst(self):
        now = [0]
        control = Mock()
        control.wait.side_effect = lambda seconds: now.__setitem__(0, now[0] + seconds)
        pacer = GamePacer(35, 480, control, clock=lambda: now[0])
        pacer.wait_before_input()
        now[0] = 10
        pacer.wait_before_input()
        pacer.wait_before_input()
        waits = [call.args[0] for call in control.wait.call_args_list]
        self.assertEqual(waits[1], 0)
        self.assertGreater(waits[2], 0)

    def test_completion_does_not_pad_the_finish_time(self):
        control = Mock()
        pacer = GamePacer(10, 100, control)
        pacer.note_progress(100)
        control.wait.assert_not_called()

    def test_flood_progress_is_spread_over_clicks_without_a_long_pause(self):
        now = [100]
        control = Mock()
        def wait(seconds):
            now[0] += seconds
        control.wait.side_effect = wait
        pacer = GamePacer(35, 480, control, clock=lambda: now[0])
        pacer.wait_before_input()
        pacer.note_progress(300)
        for _ in range(5):
            pacer.wait_before_input()
        delays = [call.args[0] for call in control.wait.call_args_list]
        self.assertEqual(delays[0], 0)
        self.assertTrue(all(0 < delay <= 0.5 for delay in delays[1:]))

    def test_slow_machine_does_not_add_delay(self):
        now = [100]
        control = Mock()
        pacer = GamePacer(5, 100, control, clock=lambda: now[0])
        pacer.note_progress(50)
        now[0] = 110
        pacer.wait_before_input()
        control.wait.assert_called_once_with(0)

    def test_each_game_resets_pacing_without_changing_global_timer(self):
        now = [100]
        control = Mock()
        pacer = GamePacer(10, 100, control, clock=lambda: now[0])
        pacer.note_progress(90)
        now[0] = 110
        pacer.begin_game()
        pacer.wait_before_input()
        self.assertEqual(pacer.progress, 0)
        control.wait.assert_called_once_with(0)
        control.start.assert_not_called()

