"""Smooth per-click pacing; flood reveals never create a backlog of waits."""
import math
import time


class GamePacer:
    def __init__(self, target_seconds, total_cells, control=None, clock=time.monotonic):
        if not math.isfinite(target_seconds) or target_seconds <= 0:
            raise ValueError('target seconds must be finite and positive')
        self.target = target_seconds
        self.total = total_cells
        self.control = control
        self.clock = clock
        self.begin_game()

    def begin_game(self):
        self.started = self.clock()
        self.progress = 0
        self.clicks = 0
        self.last_input = None
        self.interval = min(0.5, self.target / self.total)

    def note_progress(self, completed):
        self.progress = max(self.progress, min(self.total, completed))

    def wait_before_input(self):
        now = self.clock()
        remaining_time = max(0, self.target - (now - self.started))
        if self.clicks and self.progress:
            cells_per_click = max(1, self.progress / self.clicks)
            remaining_clicks = max(1, (self.total - self.progress) / cells_per_click)
            desired = min(0.5, remaining_time / remaining_clicks)
            self.interval = 0.8 * self.interval + 0.2 * desired
        if remaining_time == 0:
            delay = 0
        elif self.last_input is None:
            delay = 0
        else:
            # Include capture/reasoning time in the interval. Never catch up
            # to a cumulative progress timeline after a large flood opening.
            delay = min(0.5, max(0, self.interval - (now - self.last_input)))
        if self.control:
            self.control.wait(delay)
        elif delay:
            time.sleep(delay)
        self.last_input = self.clock()
        self.clicks += 1
