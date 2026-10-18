"""Safety regression tests; all native mouse and window APIs are mocked."""
import unittest
from unittest.mock import Mock, patch

from run_control import RunControl, StopRequested
from arbiter_window import ArbiterWindow
from arbiter_platform import ArbiterPlatform
from arbiter_geometry import BoardGeometry
from Board import Board
from test_board_platform import build_platform


class TestRunSafety(unittest.TestCase):
    @patch('arbiter_window.ImageGrab.grab')
    def test_capture_uses_physical_client_pixels(self, grab):
        from PIL import Image
        window = ArbiterWindow(hwnd=42)
        window.client_origin_screen = Mock(return_value=(100, 200))
        window.client_size = Mock(return_value=(350, 438))
        window.check_input = Mock()
        window._capture_printwindow = Mock()
        grab.return_value = Image.new('RGB', (350, 438))
        self.assertEqual(window.capture_client().shape, (438, 350, 3))
        grab.assert_called_once_with(bbox=(100, 200, 450, 638))
        window._capture_printwindow.assert_not_called()

    def test_wrong_difficulty_is_rejected_before_any_click(self):
        from test_arbiter_geometry import render
        window = Mock()
        platform = ArbiterPlatform(difficulty=1, window=window,
                                   geometry=BoardGeometry(8, 40, 16, 16), use_saved=False)
        window.capture_client.return_value = render(16, 16, 16, 8, 40)
        with self.assertRaisesRegex(RuntimeError, 'detected 16x16'):
            platform.validate_fresh_board()
        window.left_click.assert_not_called()

    def test_platform_does_not_refocus_on_each_capture(self):
        window = Mock()
        platform = ArbiterPlatform(window=window, geometry=BoardGeometry(0, 0, 16, 16),
                                   use_saved=False)
        platform.begin_read()
        platform.begin_read()
        window.focus.assert_called_once()

    def test_out_of_client_geometry_blocks_click(self):
        window = Mock()
        window.client_size.return_value = (10, 10)
        platform = ArbiterPlatform(window=window, geometry=BoardGeometry(0, 0, 16, 16),
                                   use_saved=False)
        with self.assertRaisesRegex(RuntimeError, 'outside'):
            platform.click_cell(0, 0)
        window.left_click.assert_not_called()

    def test_monitor_failure_stops_instead_of_disabling_escape(self):
        control = RunControl(10, probe=Mock(side_effect=OSError('unavailable')))
        with self.assertRaisesRegex(StopRequested, 'monitor failed'):
            control.check()

    def test_deadline_blocks_further_moves(self):
        now = [0]
        control = RunControl(1, clock=lambda: now[0])
        platform = build_platform(1, 1, set())
        platform.click_cell = Mock()
        board = Board(platform, log=False, check=control.check)
        now[0] = 1
        with self.assertRaises(StopRequested):
            board.play()
        platform.click_cell.assert_not_called()

    def test_emergency_stop_is_latched_after_key_release(self):
        control = RunControl(10, probe=Mock(side_effect=['Esc pressed.', None]))
        control.poll()
        with self.assertRaisesRegex(StopRequested, 'Esc'):
            control.check()

    @patch('arbiter_window.win32api')
    @patch('arbiter_window.win32gui')
    def test_focus_loss_blocks_mouse_movement(self, gui, api):
        gui.IsWindow.return_value = True
        gui.IsIconic.return_value = False
        gui.GetForegroundWindow.return_value = 99
        window = ArbiterWindow(hwnd=42)
        with self.assertRaisesRegex(StopRequested, 'lost focus'):
            window.left_click(100, 100, delay=0)
        api.SetCursorPos.assert_not_called()
        api.mouse_event.assert_not_called()

    @patch('arbiter_window.win32api')
    @patch('arbiter_window.win32gui')
    def test_covered_target_blocks_click(self, gui, api):
        gui.IsWindow.return_value = True
        gui.IsIconic.return_value = False
        gui.GetForegroundWindow.return_value = 42
        gui.GetAncestor.return_value = 99
        with self.assertRaisesRegex(StopRequested, 'covered'):
            ArbiterWindow(hwnd=42).left_click(100, 100, delay=0)
        api.SetCursorPos.assert_not_called()
        api.mouse_event.assert_not_called()

    @patch('arbiter_window.win32api')
    @patch('arbiter_window.win32gui')
    def test_stop_after_movement_still_prevents_button_press(self, gui, api):
        gui.IsWindow.return_value = True
        gui.IsIconic.return_value = False
        gui.GetForegroundWindow.return_value = 42
        gui.GetAncestor.return_value = 42
        control = Mock()
        control.check.side_effect = [None, StopRequested('Esc')]
        with self.assertRaises(StopRequested):
            ArbiterWindow(hwnd=42, control=control).left_click(100, 100, delay=0)
        api.SetCursorPos.assert_called_once()
        api.mouse_event.assert_not_called()

    @patch('arbiter_window.ctypes.windll.user32.PrintWindow', return_value=1)
    @patch('arbiter_window.win32ui')
    @patch('arbiter_window.win32gui')
    def test_screenshot_uses_client_only_coordinates(self, gui, ui, print_window):
        bmp = ui.CreateBitmap.return_value
        bmp.GetInfo.return_value = {'bmWidth': 2, 'bmHeight': 2}
        bmp.GetBitmapBits.return_value = bytes(16)
        frame = ArbiterWindow(hwnd=42)._capture_printwindow(2, 2)
        self.assertEqual(frame.shape, (2, 2, 3))
        self.assertEqual(print_window.call_args.args[-1], 1)


if __name__ == '__main__':
    unittest.main()
