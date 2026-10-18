"""ArbiterPlatform: play the desktop "Minesweeper Arbiter" via 方案 A.

Wires together the win32 window plumbing (arbiter_window), the pure grid
detector (arbiter_geometry) and the pure cell classifier (arbiter_skin) behind
the common Platform interface, so the exact same Cell/Board reasoning engine
drives it.

Design notes
------------
* The board is read by *screenshot*: one capture per read cycle, then each cell
  is sliced out and classified by colour. `begin_read()` grabs a fresh frame
  and `read_cell()` answers from that frame, so a whole update pass costs a
  single capture instead of one per cell.
* Input moves the system cursor. RunControl and window guards bound this
  mode; use headless WebPlatform for input isolated from the desktop cursor.
* Chord input is available but the reasoning engine reveals individually.
"""
import time

import numpy as np

import Info
from game_platform import Platform
import arbiter_geometry as geo
import arbiter_skin as skin_mod
from arbiter_window import ArbiterWindow, set_dpi_aware
from game_pacer import GamePacer

CALIB_PATH = 'arbiter_calibration.json'


def _load_calibration():
    """Return the saved calibration dict, or None if absent/unreadable."""
    import json
    import os
    if not os.path.exists(CALIB_PATH):
        return None
    try:
        with open(CALIB_PATH) as fh:
            return json.load(fh)
    except Exception:
        return None


class ArbiterPlatform(Platform):
    def __init__(self,
                 difficulty: int = 3,
                 settle: float = 0.02,
                 skin: 'skin_mod.Skin' = None,
                 geometry: 'geo.BoardGeometry' = None,
                 window: ArbiterWindow = None,
                 auto_calibrate: bool = True,
                 use_saved: bool = True, control=None, target_seconds=None) -> None:
        if not 1 <= difficulty <= 3:
            raise Exception('Difficulty should be in range [1, 3]')
        rows, cols, mines, _link = Info.DIFFICULTIES[difficulty - 1]
        self._rows, self._cols, self._mines = rows, cols, mines
        self.settle = settle
        self.control = control
        self.pacer = (GamePacer(target_seconds, rows * cols, control)
                      if target_seconds is not None else None)

        # start from the default skin, then overlay any saved tweaks
        self.skin = skin or skin_mod.DEFAULT_SKIN
        self._calib = _load_calibration() if use_saved else None
        if self._calib and skin is None:
            for k, v in self._calib.get('skin', {}).items():
                if hasattr(self.skin, k):
                    setattr(self.skin, k, v)

        set_dpi_aware()
        self.window = window or ArbiterWindow(control=control)
        if control:
            control.check()
        self.window.focus()

        self._frame = None            # last captured client image (HxWx3)
        self._frame_ready = False
        self._tokens = {}
        self.geometry = geometry
        if self.geometry is None:
            # prefer a saved geometry that matches this difficulty
            g = self._calib.get('geometry') if self._calib else None
            if (g and self._calib.get('difficulty') == difficulty):
                self.geometry = geo.BoardGeometry(
                    g['x0'], g['y0'], g['cell_w'], g['cell_h'])
            elif auto_calibrate:
                self.calibrate()


    # -- geometry / calibration ----------------------------------------------
    def calibrate(self) -> None:
        """Locate the minefield on screen and cache its geometry."""
        frame = self.window.capture_client()
        self.geometry = geo.detect_grid(frame, self._rows, self._cols, skin=self.skin)

    # -- Platform interface ---------------------------------------------------
    @property
    def rows(self):
        return self._rows

    @property
    def cols(self):
        return self._cols

    @property
    def mines(self):
        return self._mines

    def begin_read(self) -> None:
        """Capture a fresh frame for the upcoming read cycle."""
        self.window.check_input()
        if self._frame_ready:
            self._frame_ready = False
            return
        self._frame = self.window.capture_client()
        self._tokens.clear()

    def start_game(self):
        if self.pacer:
            self.pacer.begin_game()

    def note_progress(self, completed):
        if self.pacer:
            self.pacer.note_progress(completed)

    def _before_input(self):
        if self.control:
            self.control.check()
        if self.pacer:
            self.pacer.wait_before_input()
        self.window.check_input()

    def _invalidate(self):
        self._frame = None
        self._frame_ready = False
        self._tokens.clear()

    def validate_fresh_board(self):
        self.begin_read()
        # Detect the actual extent before using the selected mine count.
        actual_cols = actual_rows = 0
        height, width = self._frame.shape[:2]
        for col in range(width // self.geometry.cell_w + 1):
            left, top, right, bottom = self.geometry.cell_box(0, col)
            if left < 0 or top < 0 or right > width or bottom > height:
                break
            patch = self._frame[top:bottom, left:right]
            if not geo.is_covered_tile(patch, self.skin):
                break
            actual_cols += 1
        for row in range(height // self.geometry.cell_h + 1):
            left, top, right, bottom = self.geometry.cell_box(row, 0)
            if left < 0 or top < 0 or right > width or bottom > height:
                break
            patch = self._frame[top:bottom, left:right]
            if not geo.is_covered_tile(patch, self.skin):
                break
            actual_rows += 1
        if (actual_rows, actual_cols) != (self.rows, self.cols):
            raise RuntimeError(
                f'Expected fresh {self.rows}x{self.cols}, detected {actual_rows}x{actual_cols}. '
                'Difficulty 1=9x9, 2=16x16, 3=16x30. Select matching game difficulty and press F2.')
        for r in range(self.rows):
            for c in range(self.cols):
                if self.control:
                    self.control.check()
                if self.read_cell(r, c) != 'square blank':
                    state = self.read_cell(r, c)
                    raise RuntimeError(
                        f'Expected a fresh {self.rows}x{self.cols} covered board; '
                        f'cell ({r + 1},{c + 1}) was {state!r}. '
                        f'Detected origin=({self.geometry.x0},{self.geometry.y0}), '
                        f'cell size={self.geometry.cell_w}x{self.geometry.cell_h}. '
                        'Check game difficulty, press F2, or run diagnose_arbiter.py.')

    def _settle(self):
        if self.control:
            self.control.wait(self.settle)
        else:
            time.sleep(self.settle)

    def _cell_patch(self, row, col):
        if self._frame is None:
            self.begin_read()
        left, top, right, bottom = self.geometry.cell_box(row, col)
        return self._frame[top:bottom, left:right]

    def read_cell(self, row, col) -> str:
        if self._frame is None:
            self.begin_read()
        key = (row, col)
        if key not in self._tokens:
            self._tokens[key] = self.skin.classify(self._cell_patch(row, col))
        return self._tokens[key]

    def _screen_xy(self, row, col):
        if not (0 <= row < self.rows and 0 <= col < self.cols):
            raise RuntimeError('Cell outside board bounds.')
        self.window.check_input()
        left, top, right, bottom = self.geometry.cell_box(row, col)
        width, height = self.window.client_size()
        if left < 0 or top < 0 or right > width or bottom > height:
            raise RuntimeError('Calibration places the cell outside the game client.')
        cx, cy = self.geometry.cell_center(row, col)
        ox, oy = self.window.client_origin_screen()
        return ox + cx, oy + cy

    def click_cell(self, row, col) -> None:
        self._before_input()
        self.window.left_click(*self._screen_xy(row, col), delay=0.003)
        self._settle()
        self._invalidate()

    def flag_cell(self, row, col) -> None:
        self._before_input()
        self.window.right_click(*self._screen_xy(row, col), delay=0.003)
        self._settle()
        self._invalidate()

    def _batch_cells(self, positions, flag=False):
        from Board import GameLost
        chunk_size = 1 if self.pacer else 4
        for start in range(0, len(positions), chunk_size):
            chunk = positions[start:start + chunk_size]
            clicked = []
            for row, col in chunk:
                # Skip tiles opened by an earlier chunk's flood reveal.
                if not flag and self._frame is not None and self.read_cell(row, col) != 'square blank':
                    continue
                self._before_input()
                click = self.window.right_click if flag else self.window.left_click
                click(*self._screen_xy(row, col), delay=0.003)
                clicked.append((row, col))
            if not clicked:
                continue
            self._settle()
            self._invalidate()
            self.begin_read()
            for row, col in clicked:
                token = self.read_cell(row, col)
                if token == skin_mod.BOOM:
                    raise GameLost('Hit a mine.')
                if flag and token != 'square bombflagged':
                    raise RuntimeError('Flag was not observed; stopping batch.')
                if not flag and not token.startswith('square open'):
                    raise RuntimeError('Click did not reveal the cell; stopping batch.')
            self._frame_ready = True
            if self.pacer:
                self.pacer.note_progress(self.pacer.progress + len(clicked))

    def flag_cells(self, positions):
        self._batch_cells(positions, flag=True)

    def reveal_cells(self, positions):
        self._batch_cells(positions)

    def chord_cell(self, row, col) -> None:
        """Reveal all neighbours of (row, col) with one both-button click."""
        self._before_input()
        self.window.both_click(*self._screen_xy(row, col), delay=0.003)
        self._settle()
        self._invalidate()

    def reset(self) -> None:
        # F2 starts a fresh game in Arbiter at the current difficulty.
        import win32api
        import win32con
        self.window.check_input()
        try:
            win32api.keybd_event(win32con.VK_F2, 0, 0, 0)
        finally:
            win32api.keybd_event(win32con.VK_F2, 0, win32con.KEYEVENTF_KEYUP, 0)
        self._invalidate()
        if self.control:
            self.control.wait(max(0.05, self.settle * 4))
        else:
            time.sleep(max(0.05, self.settle * 4))
        self.window.check_input()
        # F2 normally preserves geometry. Avoid a full template search unless
        # validation shows the layout changed; never swallow a stop request.
        from run_control import StopRequested
        try:
            self.validate_fresh_board()
        except StopRequested:
            raise
        except RuntimeError:
            self.calibrate()
            self.validate_fresh_board()
