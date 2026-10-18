"""Bounded solver runner. Use --platform web to avoid the system mouse."""
import argparse
import time
import math
from pathlib import Path

from Board import Board, GameLost
from run_control import RunControl, StopRequested, desktop_stop_probe


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--platform', choices=('arbiter', 'web'), default='arbiter')
    parser.add_argument('--difficulty', type=int, choices=(1, 2, 3), default=3)
    parser.add_argument('--seconds', type=float, help='play time limit (web: 180s; arbiter: 15s)')
    parser.add_argument('--delay', type=int, default=3, help='countdown before starting')
    parser.add_argument('--settle', type=float, help='delay after each move (web: 0s; arbiter: 0.15s)')
    parser.add_argument('--show-browser', action='store_true', help='show the web browser')
    parser.add_argument('--web-input', choices=('events', 'webdriver'), default='events')
    parser.add_argument('--quiet', action='store_true', help='omit per-move logs')
    parser.add_argument('--retry-on-loss', action='store_true',
                        help='web only: start a new game after a mine hit, within the total time limit')
    args = parser.parse_args(argv)
    if args.retry_on_loss and args.platform != 'web':
        parser.error('--retry-on-loss is only available with --platform web')
    if args.seconds is None:
        args.seconds = 180 if args.platform == 'web' else 15
    if args.settle is None:
        args.settle = 0 if args.platform == 'web' else 0.15
    if (not math.isfinite(args.seconds) or not math.isfinite(args.settle)
            or args.seconds <= 0 or args.delay < 0 or args.settle < 0):
        parser.error('seconds must be positive; delay and settle must be nonnegative')

    platform = None
    control = None
    play_started = None
    try:
        mode = 'Retry on mine hits' if args.retry_on_loss else 'One game only'
        print(f'{mode}; total play time limit: {args.seconds:g}s.', flush=True)
        if args.platform == 'arbiter':
            print('STOP: Esc, mouse to top-left corner, or switch away from Arbiter.', flush=True)
            print('Use a fresh board matching --difficulty. The system mouse WILL move.', flush=True)
        else:
            print('Web mode uses browser events; the system mouse stays free.', flush=True)
            print('This is a separate web game; it does not change the Arbiter window.', flush=True)
            if not args.show_browser:
                print('Browser is hidden. Use --show-browser to watch; result is saved to web_result.png.', flush=True)
        for second in range(args.delay, 0, -1):
            print(f'Starting in {second}...', flush=True)
            time.sleep(1)
        control = RunControl(60 if args.platform == 'web' else args.seconds,
                             desktop_stop_probe if args.platform == 'arbiter' else None)
        control.start()
        control.check()
        if args.platform == 'arbiter':
            from arbiter_platform import ArbiterPlatform
            platform = ArbiterPlatform(difficulty=args.difficulty, settle=args.settle,
                                       use_saved=False, control=control)
            platform.validate_fresh_board()
        else:
            from web_platform import WebPlatform
            platform = WebPlatform(difficulty=args.difficulty,
                                   headless=not args.show_browser, control=control,
                                   settle=args.settle, input_mode=args.web_input)
            control.check()
            control.close()
            control = RunControl(args.seconds)
            control.start()
            platform.control = control
            print(f'Browser ready. Play timer starts now; move delay: {args.settle:g}s.', flush=True)
        play_started = time.monotonic()
        attempt = 1
        while True:
            control.check()
            board = Board(platform, log=not args.quiet, mark_flags=True, check=control.check)
            try:
                board.play()
            except GameLost:
                if not args.retry_on_loss:
                    raise
                control.check()
                print(f'Game {attempt} lost; starting a fresh game.', flush=True)
                platform.reset()
                attempt += 1
                continue
            if args.quiet:
                print('Game victory verified.' if board.won else 'All cells accounted for.', flush=True)
            break
        return 0
    except (StopRequested, KeyboardInterrupt) as exc:
        print(f'Stopped: {exc or "Ctrl+C"}', flush=True)
        return 0
    except Exception as exc:
        print(f'Stopped: {exc}', flush=True)
        return 1
    finally:
        if play_started is not None:
            print(f'Play elapsed: {time.monotonic() - play_started:.2f}s.', flush=True)
        if control:
            control.close()
        if platform:
            if args.platform == 'web':
                try:
                    result_path = Path('web_result.png').resolve()
                    platform.save_result(result_path)
                    print(f'Result screenshot: {result_path}', flush=True)
                except Exception as exc:
                    print(f'Could not save result screenshot: {exc}', flush=True)
                if args.show_browser:
                    try:
                        input('Game stopped. Browser remains open; press Enter here to close it. ')
                    except (KeyboardInterrupt, EOFError):
                        pass
            platform.close()


if __name__ == '__main__':
    raise SystemExit(main())
