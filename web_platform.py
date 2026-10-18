"""WebPlatform: drives minesweeperonline.com via Selenium.

This preserves the original project's behaviour behind the new Platform
interface, so `Board(platform=WebPlatform(...))` behaves exactly like the old
`Board(difficulty=...)`. Requires the `selenium` package and a chromedriver.
"""
import os
import time

import Info
from game_platform import Platform

# minesweeperonline.com cell id -> Info.REPS token (its 'class' attribute)
_CELL_CLASSES = {
    'square blank': 'square blank',
    'square bombflagged': 'square bombflagged',
    'square open0': 'square open0',
    'square open1': 'square open1',
    'square open2': 'square open2',
    'square open3': 'square open3',
    'square open4': 'square open4',
    'square open5': 'square open5',
    'square open6': 'square open6',
    'square open7': 'square open7',
    'square open8': 'square open8',
}


class WebPlatform(Platform):
    def __init__(self, difficulty: int = 3, driver_path: str = None,
                 headless=True, control=None, settle=0, input_mode='events') -> None:
        from selenium import webdriver  # imported lazily; optional dependency
        from selenium.webdriver import ActionChains
        from selenium.webdriver.chrome.service import Service
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait

        if not 1 <= difficulty <= 3:
            raise Exception('Difficulty should be in range [1, 3]')
        rows, cols, mines, link = Info.DIFFICULTIES[difficulty - 1]
        self._rows, self._cols, self._mines = rows, cols, mines
        self._ActionChains = ActionChains
        self.control = control
        self.settle = settle
        self._By = By
        self._snapshot = None
        self._snapshot_ready = False
        self.input_mode = input_mode

        options = webdriver.ChromeOptions()
        options.page_load_strategy = 'eager'
        # The site prompts for a public leaderboard name on victory. Cancel it.
        options.set_capability('unhandledPromptBehavior', 'dismiss')
        if headless:
            options.add_argument('--headless=new')
        options.add_argument('--window-size=1200,900')
        # Selenium Manager finds a matching driver; ignore the old bundled binary.
        self.driver = webdriver.Chrome(service=Service(driver_path) if driver_path else Service(),
                                       options=options)
        try:
            self.driver.set_page_load_timeout(15)
            self.driver.get(link.replace('http:', 'https:'))
            self.face = WebDriverWait(self.driver, 10).until(
                lambda d: d.find_element(By.ID, 'face'))
        except BaseException:
            self.driver.quit()
            raise

    def _check(self):
        if self.control:
            self.control.check()

    def _after_move(self):
        self._snapshot = None
        self._snapshot_ready = False
        if self.control:
            self.control.wait(self.settle)
        else:
            import time
            time.sleep(self.settle)

    def begin_read(self):
        self._check()
        if getattr(self, '_snapshot_ready', False):
            self._snapshot_ready = False
            return
        self._snapshot = self.driver.execute_script('''
            if (!document.getElementById('face')) return null;
            return {face: document.getElementById('face').className,
                    cells: Object.fromEntries(Array.from(
                        document.querySelectorAll('.square[id]'),
                        e => [e.id, e.className]))};
        ''')

    def _event_batch(self, positions, flag=False):
        """Dispatch ordinary DOM mouse events; read only visible class names."""
        self._check()
        self._snapshot = self.driver.execute_script('''
            const positions = arguments[0], flag = arguments[1];
            for (const [row, col] of positions) {
                const face = document.getElementById('face').className;
                if (face === 'facewin' || face === 'facedead') break;
                const cell = document.getElementById(`${row + 1}_${col + 1}`);
                if (!cell) throw Error('Cell outside board');
                if (cell.className !== 'square blank') continue;
                const button = flag ? 2 : 0;
                cell.dispatchEvent(new MouseEvent('mousedown', {
                    bubbles: true, cancelable: true, button, buttons: flag ? 2 : 1}));
                cell.dispatchEvent(new MouseEvent('mouseup', {
                    bubbles: true, cancelable: true, button, buttons: 0}));
            }
            return {face: document.getElementById('face').className,
                    cells: Object.fromEntries(Array.from(
                        document.querySelectorAll('.square[id]'),
                        e => [e.id, e.className]))};
        ''', positions, flag)
        # A victory prompt can interrupt execute_script and produce null even
        # when unhandledPromptBehavior dismisses it. Read back the DOM once.
        if self._snapshot is None:
            self._snapshot_ready = False
            self.begin_read()
        self._snapshot_ready = True
        if self.control:
            self.control.wait(self.settle)
        elif self.settle:
            import time
            time.sleep(self.settle)

    def reveal_cells(self, positions):
        # Bound each synchronous browser command so cancellation is checked
        # between small batches, and stop a batch at the game's loss/win state.
        for start in range(0, len(positions), 32):
            if self.input_mode == 'events':
                self._event_batch(positions[start:start + 32])
            else:
                for row, col in positions[start:start + 32]:
                    if self.game_won() or self._snapshot['face'] == 'facedead':
                        return
                    if self.read_cell(row, col) == 'square blank':
                        self.click_cell(row, col)
            if self.game_won() or self._snapshot['face'] == 'facedead':
                return

    def flag_cells(self, positions):
        for start in range(0, len(positions), 32):
            if self.input_mode == 'events':
                self._event_batch(positions[start:start + 32], flag=True)
            else:
                for row, col in positions[start:start + 32]:
                    self.flag_cell(row, col)

    def game_won(self):
        self._check()
        if self._snapshot is None:
            self.begin_read()
        return self._snapshot['face'] == 'facewin'

    def game_lost(self):
        self._check()
        if self._snapshot is None:
            self.begin_read()
        return self._snapshot['face'] == 'facedead'

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

    def _element(self, row, col):
        self._check()
        return self.driver.find_element(self._By.ID, f'{row + 1}_{col + 1}')

    def read_cell(self, row, col):
        self._check()
        if self._snapshot is None:
            self.begin_read()
        cls = self._snapshot['cells'].get(f'{row + 1}_{col + 1}', 'unknown cell')
        return _CELL_CLASSES.get(cls, cls)

    def click_cell(self, row, col):
        if self.input_mode == 'events':
            self._event_batch([(row, col)])
            return
        self._element(row, col).click()
        self._after_move()

    def flag_cell(self, row, col):
        if self.input_mode == 'events':
            self._event_batch([(row, col)], flag=True)
            return
        self._ActionChains(self.driver, duration=0).context_click(self._element(row, col)).perform()
        self._after_move()

    def reset(self):
        self._check()
        self.driver.refresh()
        self._after_move()
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            self._check()
            self.begin_read()
            if (self._snapshot and self._snapshot['face'] == 'facesmile'
                    and all(self._snapshot['cells'].get(f'{r + 1}_{c + 1}') == 'square blank'
                            for r in range(self.rows) for c in range(self.cols))):
                return
            if self.control:
                self.control.wait(0.05)
            else:
                time.sleep(0.05)
        raise RuntimeError('New game was not observed within 5 seconds; stopped.')

    def close(self):
        try:
            self.driver.quit()
        except Exception:
            pass

    def save_result(self, path):
        if not self.driver.save_screenshot(str(path)):
            raise RuntimeError('Could not save web result screenshot.')
