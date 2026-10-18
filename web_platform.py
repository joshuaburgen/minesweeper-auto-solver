"""WebPlatform: drives minesweeperonline.com via Selenium.

This preserves the original project's behaviour behind the new Platform
interface, so `Board(platform=WebPlatform(...))` behaves exactly like the old
`Board(difficulty=...)`. Requires the `selenium` package and a chromedriver.
"""
import os
import time
import re

import Info
from game_platform import Platform
from game_pacer import GamePacer

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
                 headless=True, control=None, settle=0, input_mode='events', score_name=None,
                 target_seconds=None) -> None:
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
        self.score_name = score_name
        self.score_prompt_submitted = False
        self.target_seconds = target_seconds
        self.pacer = None

        options = webdriver.ChromeOptions()
        options.page_load_strategy = 'eager'
        options.set_capability('unhandledPromptBehavior', 'ignore' if score_name else 'dismiss')
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
            if score_name:
                self._watch_score_request()
        except BaseException:
            self.driver.quit()
            raise

    def _check(self):
        if self.control:
            self.control.check()

    def start_game(self):
        # Board calls this after browser setup and after each new-game reset.
        self.pacer = (GamePacer(self.target_seconds, self.rows * self.cols, self.control)
                      if self.target_seconds is not None else None)

    def note_progress(self, completed):
        if getattr(self, 'pacer', None):
            self.pacer.note_progress(completed)

    def _before_input(self):
        self._check()
        if getattr(self, 'pacer', None):
            self.pacer.wait_before_input()

    def _note_visible_progress(self):
        if not getattr(self, 'pacer', None):
            return
        if self._snapshot is None:
            self.begin_read()
        if self._snapshot:
            cells = self._snapshot['cells']
            self.note_progress(sum(
                token == 'square bombflagged' or token.startswith('square open')
                for r in range(self.rows) for c in range(self.cols)
                for token in [cells.get(f'{r + 1}_{c + 1}', '')]))

    def _watch_score_request(self):
        # Observe the site's normal request, without altering its payload.
        self.driver.execute_script('''
            if (window.__solverScoreWatch) return;
            window.__solverScoreWatch = true;
            const open = XMLHttpRequest.prototype.open;
            XMLHttpRequest.prototype.open = function(method, url, ...rest) {
                if (new URL(url, location.href).pathname.endsWith('/win.php')) {
                    this.addEventListener('loadstart', () => {
                        window.__solverScoreRequest = {done: false};
                    });
                    this.addEventListener('loadend', () => {
                        window.__solverScoreRequest = {done: true, status: this.status};
                    });
                }
                return open.call(this, method, url, ...rest);
            };
        ''')

    def _handle_score_prompt(self):
        from selenium.common.exceptions import NoAlertPresentException
        if not getattr(self, 'score_name', None):
            return False
        try:
            alert = self.driver.switch_to.alert
            text = alert.text
        except NoAlertPresentException:
            return False
        recognized = (re.fullmatch(r'Please enter your name to submit your score \([\d.]+\)', text)
                      or re.fullmatch(r'[\d.]+ is a new .* high score! Please enter your name', text))
        if not recognized:
            raise RuntimeError(f'Unexpected browser prompt; score name was not sent: {text!r}')
        alert.send_keys(self.score_name)
        alert.accept()
        self.score_prompt_submitted = True
        print(f'Score name submitted: {self.score_name}. Waiting for the website response.', flush=True)
        return True

    def _execute_script(self, script, *args):
        from selenium.common.exceptions import UnexpectedAlertPresentException
        try:
            result = self.driver.execute_script(script, *args)
        except UnexpectedAlertPresentException:
            if not self._handle_score_prompt():
                raise
            return None  # never replay an interrupted batch of clicks
        if result is None:
            self._handle_score_prompt()
        return result

    def finish_score_submission(self):
        if not self.score_prompt_submitted:
            print('No score-entry prompt appeared; no name was submitted.', flush=True)
            return
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            state = self.driver.execute_script('return window.__solverScoreRequest || null;')
            if state and state.get('done'):
                print(f'Score request finished (HTTP {state.get("status")}); '
                      'leaderboard placement is not verified.', flush=True)
                return
            time.sleep(0.05)
        print('Score request response not confirmed; check the website leaderboard.', flush=True)

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
        script = '''
            if (!document.getElementById('face')) return null;
            return {face: document.getElementById('face').className,
                    cells: Object.fromEntries(Array.from(
                        document.querySelectorAll('.square[id]'),
                        e => [e.id, e.className]))};
        '''
        self._snapshot = self._execute_script(script)
        if self._snapshot is None and getattr(self, 'score_prompt_submitted', False):
            self._snapshot = self._execute_script(script)

    def _event_batch(self, positions, flag=False):
        """Dispatch ordinary DOM mouse events; read only visible class names."""
        if getattr(self, 'pacer', None) and self._snapshot:
            positions = [(r, c) for r, c in positions
                         if self._snapshot['cells'].get(f'{r + 1}_{c + 1}') == 'square blank']
            if not positions:
                self._check()
                return
        self._before_input()
        self._snapshot = self._execute_script('''
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
        self._note_visible_progress()

    def reveal_cells(self, positions):
        # Bound each synchronous browser command so cancellation is checked
        # between small batches, and stop a batch at the game's loss/win state.
        chunk_size = 1 if getattr(self, 'pacer', None) else 32
        for start in range(0, len(positions), chunk_size):
            if self.input_mode == 'events':
                self._event_batch(positions[start:start + chunk_size])
            else:
                for row, col in positions[start:start + chunk_size]:
                    if self.game_won() or self._snapshot['face'] == 'facedead':
                        return
                    if self.read_cell(row, col) == 'square blank':
                        self.click_cell(row, col)
            if self.game_won() or self._snapshot['face'] == 'facedead':
                return

    def flag_cells(self, positions):
        chunk_size = 1 if getattr(self, 'pacer', None) else 32
        for start in range(0, len(positions), chunk_size):
            if self.input_mode == 'events':
                self._event_batch(positions[start:start + chunk_size], flag=True)
            else:
                for row, col in positions[start:start + chunk_size]:
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
        self._before_input()
        self._element(row, col).click()
        self._after_move()
        self._note_visible_progress()

    def flag_cell(self, row, col):
        if self.input_mode == 'events':
            self._event_batch([(row, col)], flag=True)
            return
        self._before_input()
        self._ActionChains(self.driver, duration=0).context_click(self._element(row, col)).perform()
        self._after_move()
        self._note_visible_progress()

    def reset(self):
        self._check()
        self.driver.refresh()
        self.score_prompt_submitted = False
        self._after_move()
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            self._check()
            self.begin_read()
            if (self._snapshot and self._snapshot['face'] == 'facesmile'
                    and all(self._snapshot['cells'].get(f'{r + 1}_{c + 1}') == 'square blank'
                            for r in range(self.rows) for c in range(self.cols))):
                if getattr(self, 'score_name', None):
                    self._watch_score_request()
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
