"""Game I/O abstraction (named to avoid shadowing Python's platform module).

The pure reasoning engine (Cell / Board) never talks to a GUI directly. It
talks to a *Platform*, which knows how to:

  * report the board dimensions (rows, cols, mines),
  * read the current state token of one cell,
  * left-click a cell to reveal it,
  * right-click a cell to place a flag,
  * reset / start a new game.

Two concrete platforms ship with the project:

  * WebPlatform     -- drives minesweeperonline.com through Selenium
                       (the original behaviour, preserved).
  * ArbiterPlatform -- drives the desktop "Minesweeper Arbiter" via screen
                       capture + real mouse/keyboard input (方案 A).

Keeping this seam small is what lets the exact same solver logic play either
game, and lets the reasoning engine be unit-tested with a FakePlatform.
"""
from abc import ABC, abstractmethod


class Platform(ABC):
    """Minimal GUI surface the solver depends on."""

    @property
    @abstractmethod
    def rows(self) -> int:
        ...

    @property
    @abstractmethod
    def cols(self) -> int:
        ...

    @property
    @abstractmethod
    def mines(self) -> int:
        ...

    @abstractmethod
    def read_cell(self, row: int, col: int) -> str:
        """Return the cell's current state token.

        The token MUST be one of the keys of Info.REPS (e.g. 'square blank',
        'square open3', 'square bombflagged') for a normal cell, or any token
        that is *not* in Info.REPS to signal an explosion / game over.
        """
        ...

    @abstractmethod
    def click_cell(self, row: int, col: int) -> None:
        """Left-click to reveal the cell at (row, col)."""
        ...

    @abstractmethod
    def flag_cell(self, row: int, col: int) -> None:
        """Right-click to place a flag on the cell at (row, col)."""
        ...

    @abstractmethod
    def reset(self) -> None:
        """Start a brand new game on the same platform."""
        ...

    def close(self) -> None:
        """Release any OS resources (windows, drivers). Optional."""
        pass
