"""Windows-only plumbing for driving the desktop "Minesweeper Arbiter".

This module is deliberately kept free of any solver / reasoning imports and of
the pure geometry / skin logic, so it can be swapped or mocked. It provides:

  * set_dpi_aware()          -- make screen coords & screenshots agree
  * find_arbiter_window()    -- locate the Arbiter main window (class TMainWindow)
  * ArbiterWindow            -- focus, client<->screen mapping, capture, input

Capture uses PrintWindow (works even if the window is partly occluded) with an
ImageGrab fallback. Input uses OS-level cursor moves and button events,
guarded by stop checks.
"""
import ctypes
import time

import numpy as np

try:
    import win32api
    import win32con
    import win32gui
    import win32ui
    _WIN = True
except Exception:  # pragma: no cover - non-Windows
    _WIN = False

from PIL import Image, ImageGrab
from run_control import StopRequested

# Arbiter's Delphi main-window class name (from the packed exe resources)
ARBITER_CLASS = 'TMainWindow'
ARBITER_TITLE_HINT = 'Minesweeper Arbiter'


def set_dpi_aware() -> None:
    """Ask Windows for physical pixels so screenshots and cursor coords match.

    Without this, a scaled display makes GetWindowRect and ImageGrab disagree,
    which would throw off every click. Best-effort: ignore if unavailable.
    """
    if not _WIN:
        return
    try:
        # -4 == DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2
        ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def find_arbiter_window():
    """Return the HWND of the Arbiter main window, or raise if not found."""
    if not _WIN:
        raise RuntimeError('Arbiter automation requires Windows')
    matches = []

    def _cb(hwnd, _):
        if not win32gui.IsWindowVisible(hwnd):
            return True
        cls = win32gui.GetClassName(hwnd)
        title = win32gui.GetWindowText(hwnd)
        if cls == ARBITER_CLASS or ARBITER_TITLE_HINT.lower() in title.lower():
            matches.append(hwnd)
        return True

    win32gui.EnumWindows(_cb, None)
    if not matches:
        raise RuntimeError('Minesweeper Arbiter window not found -- is it running?')
    return matches[0]


class ArbiterWindow:
    """Thin wrapper around the Arbiter window for focus / capture / input."""

    def __init__(self, hwnd: int = None, control=None) -> None:
        self.hwnd = hwnd or find_arbiter_window()
        self.control = control

    def check_input(self, sx=None, sy=None):
        if self.control:
            self.control.check()
        if (not win32gui.IsWindow(self.hwnd) or win32gui.IsIconic(self.hwnd)
                or win32gui.GetForegroundWindow() != self.hwnd):
            raise StopRequested('Arbiter lost focus; stopped without stealing it back.')
        if sx is not None:
            target = win32gui.WindowFromPoint((int(sx), int(sy)))
            if win32gui.GetAncestor(target, win32con.GA_ROOT) != self.hwnd:
                raise StopRequested('Click target is covered by another window.')

    # -- focus ----------------------------------------------------------------
    def focus(self) -> None:
        """Bring Arbiter to the foreground so real clicks land on it."""
        try:
            if win32gui.IsIconic(self.hwnd):
                win32gui.ShowWindow(self.hwnd, win32con.SW_RESTORE)
            win32gui.SetForegroundWindow(self.hwnd)
            time.sleep(0.05)
        except Exception:
            pass

    # -- coordinate mapping ---------------------------------------------------
    def client_origin_screen(self):
        """Screen (x, y) of the client area's top-left corner."""
        left, top, _, _ = win32gui.GetClientRect(self.hwnd)
        return win32gui.ClientToScreen(self.hwnd, (left, top))

    def client_size(self):
        _, _, right, bottom = win32gui.GetClientRect(self.hwnd)
        return right, bottom

    # -- capture --------------------------------------------------------------
    def capture_client(self) -> np.ndarray:
        """Capture the client area as an H x W x 3 uint8 RGB numpy array."""
        ox, oy = self.client_origin_screen()
        cw, ch = self.client_size()
        # A DPI-unaware Arbiter can PrintWindow its logical-size contents into
        # a physical-size bitmap, leaving black padding. Screen pixels match
        # physical mouse coordinates. Require an unobstructed foreground game.
        self.check_input()
        bbox = (ox, oy, ox + cw, oy + ch)
        img = ImageGrab.grab(bbox=bbox)
        return np.asarray(img.convert('RGB'))

    def _capture_printwindow(self, cw, ch):
        """BitBlt the window into a bitmap via PrintWindow (occlusion-proof)."""
        hwnd_dc = win32gui.GetWindowDC(self.hwnd)
        mfc_dc = win32ui.CreateDCFromHandle(hwnd_dc)
        mem_dc = mfc_dc.CreateCompatibleDC()
        bmp = win32ui.CreateBitmap()
        bmp.CreateCompatibleBitmap(mfc_dc, cw, ch)
        mem_dc.SelectObject(bmp)
        try:
            result = ctypes.windll.user32.PrintWindow(
                self.hwnd, mem_dc.GetSafeHdc(), 1)  # PW_CLIENTONLY
            if not result:
                raise RuntimeError('PrintWindow failed')
            info = bmp.GetInfo()
            raw = bmp.GetBitmapBits(True)
            img = Image.frombuffer(
                'RGB', (info['bmWidth'], info['bmHeight']), raw, 'raw', 'BGRX', 0, 1)
            return np.asarray(img)
        finally:
            mem_dc.DeleteDC()
            mfc_dc.DeleteDC()
            win32gui.ReleaseDC(self.hwnd, hwnd_dc)
            win32gui.DeleteObject(bmp.GetHandle())

    # -- input (real OS-level events) ----------------------------------------
    def move_to(self, sx, sy) -> None:
        self.check_input(sx, sy)
        win32api.SetCursorPos((int(sx), int(sy)))

    def left_click(self, sx, sy, delay=0.02) -> None:
        self.move_to(sx, sy)
        time.sleep(delay)
        self.check_input(sx, sy)
        win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0)
        win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0)

    def right_click(self, sx, sy, delay=0.02) -> None:
        self.move_to(sx, sy)
        time.sleep(delay)
        self.check_input(sx, sy)
        win32api.mouse_event(win32con.MOUSEEVENTF_RIGHTDOWN, 0, 0)
        win32api.mouse_event(win32con.MOUSEEVENTF_RIGHTUP, 0, 0)

    def both_click(self, sx, sy, delay=0.02) -> None:
        """Chord: press both buttons together (reveals neighbours of a number)."""
        self.move_to(sx, sy)
        time.sleep(delay)
        self.check_input(sx, sy)
        win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0)
        win32api.mouse_event(win32con.MOUSEEVENTF_RIGHTDOWN, 0, 0)
        win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0)
        win32api.mouse_event(win32con.MOUSEEVENTF_RIGHTUP, 0, 0)

