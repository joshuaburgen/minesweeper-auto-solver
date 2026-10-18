import os
import time
import Info
import random
from Cell import Cell


class GameLost(RuntimeError):
    """A confirmed mine hit, distinct from recognition or input failures."""
    pass


# returns one random element from the given set
def get_one_random(s: set):
    return random.choice(tuple(s))


# represents a MineSweeper Board
class Board:
    # global dictionary of actions for logging purposes
    ACTIONS: dict = {'flag': Info.LOG_FLAG,
                     'reveal': Info.LOG_REVEAL,
                     'random': Info.LOG_REVEAL_RANDOM,
                     'reset': Info.LOG_GAME_RESET,
                     'complete': Info.LOG_GAME_COMPLETE}

    # constructor
    def __init__(self, platform, log: bool = True, mark_flags: bool = False,
                 check=None) -> None:

        start_t = time.time()

        # the platform supplies the dimensions and all I/O (web or Arbiter)
        self.platform = platform
        self.check = check or (lambda: None)
        self.won = False

        # assign fields
        self.log: bool = log
        self.mark_flags: bool = mark_flags
        self.rows: int = platform.rows
        self.cols: int = platform.cols
        self.mines: int = platform.mines
        self.blank: set = set()
        self.bombs: set = set()
        self.numbers: set = set()
        self.workset: set = set()
        self.matrix: list = list()

        # let the platform snapshot the board before the first read cycle
        if hasattr(self.platform, 'begin_read'):
            self.platform.begin_read()

        # initialize fields and cells todo is this a good idea to call this here?
        self.init_fields_and_cells()
        if hasattr(self.platform, 'start_game'):
            self.platform.start_game()
        self.log_action(f'\t{round(time.time() - start_t, 3)} seconds to initialize '
                        + f'a board with {self.rows * self.cols} cells')

    # main game loop
    def play(self) -> None:
        while self.blank and not self.won:
            self.check()
            to_flag: set = self.get_cells_to_flag()
            if not len(to_flag) == 0:
                self.log_action('flag')
                self.flag_all(to_flag)
            else:
                to_reveal: set = self.get_cells_to_reveal()
                if not len(to_reveal) == 0:
                    self.log_action('reveal')
                    self.reveal_all(to_reveal)
                else:
                    self.log_action('random')
                    self.reveal_random()
        self.log_action('Game victory verified.' if self.won else 'complete')

    # resets the board's sets and cells
    def reset_game(self) -> None:
        self.log_action('reset')
        # start a brand new game on the platform
        self.platform.reset()
        if hasattr(self.platform, 'begin_read'):
            self.platform.begin_read()
        # clear sets
        self.blank.clear()
        self.bombs.clear()
        self.numbers.clear()
        self.workset.clear()
        # reset every cell in the matrix
        for row in self.matrix:
            for cell in row:
                cell.reset()
                self.blank.add(cell)

    # reveals a random cell from the blank set
    def reveal_random(self) -> None:
        no_numbers: set = set(filter(lambda c: len(c.non_zero_number_neighbors()) == 0, self.blank))
        # account for the case when set has length zero and yields a zero probability
        if len(no_numbers) == 0:
            lowest_prob: float = 1
            random_cell: Cell = get_one_random(self.blank)
        else:
            # todo find a way to subtract the number of bombs accounted for in the workset
            lowest_prob: float = (self.mines - len(self.bombs)) / len(no_numbers)
            random_cell: Cell = get_one_random(no_numbers)
        for cell in self.workset:
            blank: set = cell.blank_neighbors()
            if not len(blank) == 0:
                prob: float = cell.bombs_remaining() / len(blank)
                if prob < lowest_prob:
                    lowest_prob = prob
                    random_cell = get_one_random(blank)
        random_cell.click()
        self.update_from({random_cell})
        if random_cell.blank and not self.won:
            raise RuntimeError('Click did not reveal the cell; check capture, geometry and focus.')

    # initialize the board's matrix, blank set with cells
    def init_fields_and_cells(self) -> None:
        # initialize matrix and blank set
        for row in range(self.rows):
            row_to_add: list = []
            for col in range(self.cols):
                cell: Cell = Cell(row, col, self.platform)
                row_to_add.append(cell)
                self.blank.add(cell)
            self.matrix.append(row_to_add)
        # for each cell assigns the neighbors in range
        for row in self.matrix:
            for cell in row:
                cell.assign_neighbors(
                    # returns a set of cells at the given posns
                    set([self.matrix[posn.row][posn.col] for posn in cell.neighbors_posns(self.rows, self.cols)]))

    # if log is turned on returns the print out associated with the given action
    def log_action(self, action: str) -> None:
        if self.log:
            print(self.ACTIONS.get(action, action))

    # flags all cells in the given set
    def flag_all(self, to_flag: set) -> None:
        batched = self.mark_flags and hasattr(self.platform, 'flag_cells')
        if batched:
            self.check()
            self.platform.flag_cells([(c.posn.row, c.posn.col) for c in to_flag])
        for cell in to_flag:
            self.check()
            if self.mark_flags:
                if not batched:
                    self.platform.flag_cell(cell.posn.row, cell.posn.col)
                if self.platform.read_cell(cell.posn.row, cell.posn.col) != 'square bombflagged':
                    raise RuntimeError('Flag was not observed; stopping to avoid incorrect moves.')
            cell.flag(False)
            self.blank.discard(cell)
            self.bombs.add(cell)
        self._report_progress()

    def _report_progress(self):
        if hasattr(self.platform, 'note_progress'):
            self.platform.note_progress(self.rows * self.cols - len(self.blank))

    # updates the cells from a set of cells
    def update_from(self, workset: set) -> None:
        start_time = time.time()
        counter: int = 0
        if hasattr(self.platform, 'begin_read'):
            self.platform.begin_read()
        if hasattr(self.platform, 'game_won') and self.platform.game_won():
            self.won = True
            return
        if hasattr(self.platform, 'game_lost') and self.platform.game_lost():
            raise GameLost('Hit a mine.')
        visited: set = set()
        while not len(workset) == 0:
            self.check()
            popped: Cell = workset.pop()
            if popped not in visited:
                visited.add(popped)
                updated, boom = popped.update()
                if boom:
                    raise GameLost('Hit a mine.')
                elif updated:
                    workset |= popped.blank_neighbors()
                    self.blank.discard(popped)
                    self.numbers.add(popped)
                    if popped.should_add_to_workset():
                        self.workset.add(popped)
                    counter += 1
        self.log_action(f'\t{round(time.time() - start_time, 3)} seconds to update {counter} cells')
        self._report_progress()

    # reveals all cells in the given set
    def reveal_all(self, to_reveal: set) -> None:
        if hasattr(self.platform, 'reveal_cells'):
            self.check()
            self.platform.reveal_cells([(c.posn.row, c.posn.col) for c in to_reveal if c.blank])
            self.update_from(set(to_reveal))
            if not self.won and any(c.blank for c in to_reveal):
                raise RuntimeError('Click did not reveal the cell; check browser input.')
            return
        for cell in to_reveal:
            self.check()
            if self.won:
                break
            if not cell.blank:  # an earlier click may have flood-revealed it
                continue
            cell.click()
            self.update_from({cell})
            if cell.blank and not self.won:
                raise RuntimeError('Click did not reveal the cell; check capture, geometry and focus.')

    # returns a set of cells to flag
    def get_cells_to_flag(self) -> set:
        to_flag: set = set()
        for cell in self.workset:
            to_flag |= cell.get_neighbors_to_flag()
        return to_flag

    # returns a set of cells to reveal
    def get_cells_to_reveal(self) -> set:
        to_reveal: set = set()
        to_discard: set = set()
        for cell in self.workset:
            exhausted, neighbors = cell.get_neighbors_to_reveal()
            if exhausted:
                to_discard.add(cell)
            to_reveal |= neighbors
        # discards the exhausted cells from the workset
        self.workset = self.workset.difference(to_discard)
        return to_reveal

    # returns a string representation of the state of this board
    def __str__(self) -> str:

        # blank = len(self.blank)
        # bombs = len(self.bombs)
        # numbers = len(self.numbers)
        # workset = len(self.workset)
        # total = blank + bombs + numbers
        # return f'{blank}\t{bombs}\t{numbers}\t{total}\t\t{workset}'

        out: str = f'Board(rows = {self.rows},\n' \
                   + f'\tcols = {self.cols}\n' \
                   + f'\tmines = {self.mines}\n' \
                   + f'\tblank.size = {len(self.blank)}\n' \
                   + f'\tbombs.size = {len(self.bombs)}\n' \
                   + f'\tnumbers.size = {len(self.numbers)}\n' \
                   + f'\tworkset.size = {len(self.workset)}\n' \
                   + f'\tMatrix as String:\n'
        field: str = ''
        for row in self.matrix:
            field += '\t\t'
            for cell in row:
                field += cell.field_string() + ' '
            field += '\n'
        return out + field
