# Mine Sweeper Solver (Web + Arbiter)

A Minesweeper solver in Python. The reasoning engine is a generalized version
of the strategy described in the [minesweeper.info guide](http://www.minesweeper.info/wiki/Strategy).
It can drive **two different games** through a small `Platform` interface:

| Platform | Target | How it plays |
|----------|--------|--------------|
| `WebPlatform` | [minesweeperonline.com](http://minesweeperonline.com/) | Selenium (the original behaviour) |
| `ArbiterPlatform` | desktop **Minesweeper Arbiter** | screen capture + **real** mouse/keyboard input |

The pure logic (`Cell.py`, `Board.py`, `Posn.py`) is identical for both; only
the I/O seam differs. This means the solver, and its unit tests, work with no
GUI at all (see `test_board_platform.py`, which drives a fake in-memory board).

---

## Current usage

Run from this directory with Python 3.11+. Create an isolated environment:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

### Web mode: no system mouse control

```powershell
.\.venv\Scripts\python.exe -u Runner.py --platform web --difficulty 1 --seconds 60
```

This starts a separate **headless Chrome** game at minesweeperonline.com;
Selenium sends browser events without moving the OS cursor. It does not
control the Arbiter window. Chrome must be installed; on first use Selenium
Manager may need internet access to obtain a matching driver. The bundled
legacy chromedriver is not used. Add `--show-browser` to view the game.
Press Ctrl+C in the terminal to stop. To watch each move, use:

```powershell
.\.venv\Scripts\python.exe -u Runner.py --platform web --difficulty 1 --seconds 180 --show-browser --settle 0
```

With `--show-browser`, the browser stays open after the game stops; press Enter
in the terminal to close it. The result is saved as `web_result.png` when the
browser is still available, including on time limits or losses. Browser setup has a separate 60-second cooperative budget. The web play timer
starts only after the browser is ready; default web play time is 180 seconds.
Default web settling delay is zero. Web mode dispatches DOM mouse events in
batches of at most 32 known-safe reveals or flags and returns the visible
board classes in the same browser command. No hidden mine data is read.
The game stops each batch on its visible victory/loss indicator. Set
`--web-input webdriver` for the older Selenium element/action input path. Use `--settle 0.5` only for slow observation.
Browser/driver startup and network commands can block beyond the cooperative
deadline, but cannot move the mouse.

### Desktop Arbiter mode: bounded system mouse control

Open `arbiter/ms_arbiter.exe`, select a difficulty, and press F2 for a fully
covered board. Difficulty 1/2/3 means beginner/intermediate/expert. Then run:

```powershell
.\.venv\Scripts\python.exe -u Runner.py --platform arbiter --difficulty 1 --seconds 10
```

**This mode moves the system mouse.** Defaults: 3-second countdown, 15-second
limit after the countdown (including setup), 0.15-second settling delay,
and one game only. Stop with **Esc**, the **top-left screen corner**, or by
switching away from Arbiter. Esc is monitored every 20 ms and latched; stop
checks run before moving the pointer and again before pressing a button.
No further moves are sent after a stop is observed. In-flight OS calls are
not forcibly terminated; a click already sent cannot be undone.

Arbiter is focused once at startup. Later focus loss, another window covering
a click target, out-of-client coordinates, unrecognized cell states, unchanged
reveals, unobserved flags, or hitting a mine stop the run. There is no automatic
retry. Checks reduce accidental clicks but are not isolation from the desktop;
use web mode if you need the mouse free.

The runner detects geometry anew and requires a fully covered board; old
calibration files are ignored to avoid stale coordinates after skin/DPI changes.
`calibrate.py 1` (or 2/3) remains available for a visual classification check.
It does not start the solver. Desktop screenshot classification targets the
default skin and still requires a real-game validation on your display.

### Reasoning and completion

`Board.py` and `Cell.py` use local number constraints and set differences to
flag mines and open safe cells. When logic stalls, the solver uses a heuristic
risk estimate and guesses. A guess can lose; this is not a guaranteed solver.
Every reveal is read back, including the last batch, and flood-opened cells
are skipped rather than clicked again. Web mode reads the site's `facewin` indicator and prints `Game victory verified.`;
it cancels the leaderboard-name prompt without submitting a score. Desktop
completion only means all cells have been classified as revealed or flagged;
it does not independently verify Arbiter's victory indicator.

`game_platform.py` defines the shared I/O interface. It is deliberately not
named `platform.py`, which would shadow Python's standard library and break
third-party packages. `arbiter_window.py` captures the physical client-area screen pixels after
checking foreground ownership. Older DPI-unaware Arbiter versions can render
logical-size PrintWindow images with black padding, so those images are no
longer used for runtime clicking. Keep the game visible and unobstructed.
Grid detection rejects flat grey panels and counter rows; the fresh-board
check measures actual dimensions before selecting the mine count.
`diagnose_arbiter.py --difficulty 1` reads the current foreground game without
clicking and saves a client capture and classification report.

## Tests

```powershell
.\.venv\Scripts\python.exe -m unittest test_run_safety test_web_platform test_board_platform test_arbiter_skin test_arbiter_geometry -v
```

These tests mock native input. They exercise stop latching, the deadline,
focus/occlusion guards, client-only capture, first-click compatibility,
explosion handling, unchanged clicks, flood reveals and synthetic recognition.
They do not prove a desktop game was won.

Validation: a live headless beginner game completed with `Game victory verified.`.
A separate live run stopped at its time limit. Desktop GUI input has not been
replayed for validation; native-input tests use mocks. Chrome tab crashes
inside the agent sandbox required running the browser integration test outside
that sandbox. Ordinary terminal use is separate from that agent restriction.

### Fast Expert mode

```powershell
.\.venv\Scripts\python.exe -u Runner.py --platform web --difficulty 3 --show-browser --settle 0 --seconds 180 --quiet
```

This selects 16x30 with 99 mines. `--quiet` omits per-move console output;
`--settle 0` removes deliberate batch delays. Remove `--show-browser` for
headless runs. A same-session benchmark of placing 20 flags took 0.6447s
with WebDriver actions and 0.0135s with batched DOM events; that comparison
is for flag input, not a guaranteed whole-game speedup. Guesses can still lose.

### Retry web games after a loss

Add `--retry-on-loss` to start a fresh web game after each confirmed mine hit:

```powershell
.\.venv\Scripts\python.exe -u Runner.py --platform web --difficulty 3 --show-browser --settle 0 --seconds 180 --quiet --delay 0 --retry-on-loss
```

This is off by default and available only in web mode. It refreshes the page and waits for a fully covered board at the same difficulty. All
attempts share the same total play time limit; the timer is not reset on a loss.
A victory, Ctrl+C, time limit, or unexpected input/recognition error stops the
run. The browser is kept open for review with `--show-browser`.
