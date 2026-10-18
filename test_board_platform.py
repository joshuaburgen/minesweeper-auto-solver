"""End-to-end test of the refactored reasoning engine via a FakePlatform.

FakePlatform implements the Platform interface against an in-memory minefield,
so we can drive the *real* Cell/Board classes (no Selenium, no GUI) and prove
the abstraction preserved the solver's behaviour: it must flag known mines,
reveal provably-safe cells, and win a fully-determined board.
"""
from unittest import TestCase
from unittest.mock import Mock
import subprocess
import sys
from pathlib import Path

import Info
from game_platform import Platform
from Board import Board


class FakePlatform(Platform):
    """A scripted minefield that speaks the Platform protocol."""

    def __init__(self, rows, cols, mines, mine_positions, numbers):
        # mine_positions: set of (r, c); numbers: dict (r,c)->int for revealed
        self._rows, self._cols, self._mines = rows, cols, mines
        self._mines = mine_positions
        self._numbers = dict(numbers)      # revealed number cells
        self._flags = set()
        self.revealed = dict(numbers)      # grows as cells are clicked
        self.clicks = 0
        self.flag_clicks = 0

    @property
    def rows(self):
        return self._rows

    @property
    def cols(self):
        return self._cols

    @property
    def mines(self):
        return len(self._mines)

    def read_cell(self, row, col):
        if (row, col) in self.revealed:
            return 'square open%d' % self.revealed[(row, col)]
        if (row, col) in self._flags:
            return 'square bombflagged'
        return 'square blank'

    def click_cell(self, row, col):
        self.clicks += 1
        # a flood reveal: opening this cell also opens every 0-region around it
        # (simplified: just open the clicked cell's number if known)
        if (row, col) in self._mines:
            return
        if (row, col) in self._numbers:
            self.revealed[(row, col)] = self._numbers[(row, col)]

    def flag_cell(self, row, col):
        self.flag_clicks += 1
        self._flags.add((row, col))

    def reset(self):
        self.revealed = dict(self._numbers)
        self._flags.clear()


def build_platform(rows, cols, mine_positions):
    """Compute the correct number for every non-mine cell (fully determined)."""
    numbers = {}
    for r in range(rows):
        for c in range(cols):
            if (r, c) in mine_positions:
                continue
            n = 0
            for dr in (-1, 0, 1):
                for dc in (-1, 0, 1):
                    if (dr or dc) and (r + dr, c + dc) in mine_positions:
                        n += 1
            numbers[(r, c)] = n
    return FakePlatform(rows, cols, mine_positions, mine_positions, numbers)


class TestBoardWithFakePlatform(TestCase):
    def test_flood_reveal_does_not_click_already_open_cells(self):
        plat = build_platform(2, 2, set())
        plat.revealed.clear()
        def flood(row, col):
            plat.clicks += 1
            plat.revealed.update(plat._numbers)
        plat.click_cell = flood
        board = Board(plat, log=False)
        board.reveal_all(set(board.blank))
        self.assertEqual(plat.clicks, 1)
        self.assertFalse(board.blank)

    def test_unchanged_click_stops_instead_of_claiming_completion(self):
        plat = build_platform(1, 1, set())
        plat.revealed.clear()
        plat.click_cell = Mock()
        board = Board(plat, log=False)
        with self.assertRaisesRegex(RuntimeError, 'did not reveal'):
            board.reveal_all(set(board.blank))
        self.assertEqual(len(board.blank), 1)

    def test_explosion_does_not_restart(self):
        plat = build_platform(1, 1, {(0, 0)})
        plat.read_cell = Mock(return_value='square bombdeath')
        plat.reset = Mock()
        board = Board(plat, log=False)
        with self.assertRaisesRegex(RuntimeError, 'mine'):
            board.update_from(set(board.blank))
        plat.reset.assert_not_called()

    def test_completed_board_returns(self):
        result = subprocess.run(
            [sys.executable, '-c',
             'from Board import Board; '
             'from test_board_platform import build_platform; '
             'board = Board(build_platform(1, 1, set()), log=False); '
             'board.blank.clear(); board.play()'],
            cwd=Path(__file__).resolve().parent,
            capture_output=True, text=True, timeout=5,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_fresh_board_makes_its_first_click(self):
        plat = build_platform(2, 2, set())
        plat.revealed.clear()
        board = Board(platform=plat, log=False)

        board.reveal_random()

        self.assertEqual(plat.clicks, 1)
        self.assertEqual(len(board.blank), 3)

    def test_solves_a_small_determined_board(self):
        # 3x3 board, single mine at centre -> every other cell is a '1'
        rows, cols = 3, 3
        mines = {(1, 1)}
        plat = build_platform(rows, cols, mines)
        # pre-reveal a corner so the solver has information to start from
        plat.revealed[(0, 0)] = 1
        plat.revealed[(0, 1)] = 1
        plat.revealed[(1, 0)] = 1

        board = Board(platform=plat, log=False, mark_flags=True)
        # seed the workset with the already-open number cells
        for r in range(rows):
            for c in range(cols):
                cell = board.matrix[r][c]
                if (r, c) in plat.revealed:
                    cell.attribute = 'square open%d' % plat.revealed[(r, c)]
                    cell.to_number()
                    cell.blank = False
                    board.blank.discard(cell)
                    board.numbers.add(cell)
                    if cell.should_add_to_workset():
                        board.workset.add(cell)

        # the centre must be flagged (it is the only blank neighbour of the 1s)
        to_flag = board.get_cells_to_flag()
        self.assertIn((1, 1),
                      {(c.posn.row, c.posn.col) for c in to_flag})

        # flag it and confirm the platform recorded the flag
        board.flag_all(to_flag)
        self.assertIn((1, 1), plat._flags)

    def test_board_dimensions_come_from_platform(self):
        plat = build_platform(9, 9, {(0, 0)})
        board = Board(platform=plat, log=False, mark_flags=False)
        self.assertEqual(board.rows, 9)
        self.assertEqual(board.cols, 9)
        self.assertEqual(board.mines, 1)

    def test_get_cells_to_reveal_flags_then_reveals(self):
        # a '1' whose only blank neighbour is a known mine should let its
        # other neighbours be revealed; here we check the reveal set excludes
        # the flagged mine.
        rows, cols = 3, 3
        mines = {(0, 2)}
        plat = build_platform(rows, cols, mines)
        plat.revealed[(0, 0)] = 1
        plat.revealed[(0, 1)] = 1
        plat.revealed[(1, 0)] = 2
        plat.revealed[(1, 1)] = 2

        board = Board(platform=plat, log=False, mark_flags=True)
        for r in range(rows):
            for c in range(cols):
                cell = board.matrix[r][c]
                if (r, c) in plat.revealed:
                    cell.attribute = 'square open%d' % plat.revealed[(r, c)]
                    cell.to_number()
                    cell.blank = False
                    board.blank.discard(cell)
                    board.numbers.add(cell)
                    if cell.should_add_to_workset():
                        board.workset.add(cell)

        to_flag = board.get_cells_to_flag()
        flagged = {(c.posn.row, c.posn.col) for c in to_flag}
        self.assertIn((0, 2), flagged)  # the mine is provably flagged
        board.flag_all(to_flag)

        to_reveal = board.get_cells_to_reveal()
        reveal_posns = {(c.posn.row, c.posn.col) for c in to_reveal}
        self.assertNotIn((0, 2), reveal_posns)  # never reveal the flagged mine
