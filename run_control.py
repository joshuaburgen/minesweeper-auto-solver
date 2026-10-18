"""Time limit and a latched emergency stop independent of window focus."""
import threading
import time
import math


class StopRequested(RuntimeError):
    pass


class RunControl:
    def __init__(self, seconds, probe=None, clock=time.monotonic):
        if not math.isfinite(seconds) or seconds <= 0:
            raise ValueError('seconds must be positive')
        self.clock = clock
        self.deadline = clock() + seconds
        self.probe = probe or (lambda: None)
        self.reason = None
        self.closed = threading.Event()
        self.thread = None
        self.lock = threading.Lock()

    def poll(self):
        with self.lock:
            if self.reason is None:
                try:
                    self.reason = ('Time limit reached.' if self.clock() >= self.deadline
                                   else self.probe())
                except Exception as exc:
                    self.reason = f'Stop monitor failed: {exc}'

    def check(self):
        self.poll()
        if self.reason:
            raise StopRequested(self.reason)

    def wait(self, seconds):
        end = self.clock() + seconds
        while self.clock() < end:
            self.check()
            self.closed.wait(min(0.02, max(0, end - self.clock())))
        self.check()

    def start(self):
        def watch():
            while not self.closed.wait(0.02):
                self.poll()
        self.thread = threading.Thread(target=watch, daemon=True)
        self.thread.start()

    def close(self):
        self.closed.set()
        if self.thread:
            self.thread.join(timeout=0.2)


def desktop_stop_probe():
    import win32api
    import win32con
    if win32api.GetAsyncKeyState(win32con.VK_ESCAPE) & 0x8000:
        return 'Esc pressed.'
    x, y = win32api.GetCursorPos()
    if x <= 3 and y <= 3:
        return 'Mouse moved to the top-left emergency stop corner.'
    return None
