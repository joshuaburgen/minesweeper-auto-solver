"""Interactive calibration helper for the Arbiter automation (方案 A).

Run this *with Minesweeper Arbiter open and a fresh game started*. It will:

  1. locate the Arbiter window,
  2. capture the client area,
  3. auto-detect the minefield geometry,
  4. dump a per-cell classification so you can eyeball that the colours are
     being read correctly,
  5. save the detected geometry (and let you tweak the skin thresholds) to
     arbiter_calibration.json, which ArbiterPlatform can then load to skip
     auto-detection and use tuned colours.

Usage:
    python calibrate.py [difficulty]      # difficulty 1/2/3, default 3
    python calibrate.py --sample r c      # print raw pixels of one cell
"""
import json
import os
import sys

import numpy as np

import Info
import arbiter_geometry as geo
import arbiter_skin as skin_mod
from arbiter_window import ArbiterWindow, set_dpi_aware

CALIB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          'arbiter_calibration.json')


def main(argv):
    set_dpi_aware()
    difficulty = 3
    if argv and argv[0].isdigit():
        difficulty = int(argv[0])
    rows, cols, mines, _ = Info.DIFFICULTIES[difficulty - 1]
    print(f'Calibrating for difficulty {difficulty}: {rows}x{cols}, {mines} mines')

    win = ArbiterWindow()
    win.focus()
    frame = win.capture_client()
    print(f'Captured client area: {frame.shape[1]}x{frame.shape[0]} px')

    # load any previously saved skin tweaks
    skin = skin_mod.DEFAULT_SKIN
    saved = {}
    if os.path.exists(CALIB_PATH):
        saved = json.load(open(CALIB_PATH))
        for k, v in saved.get('skin', {}).items():
            if hasattr(skin, k):
                setattr(skin, k, v)

    try:
        g = geo.detect_grid(frame, rows, cols, skin=skin)
    except ValueError as exc:
        print('Auto-detection failed:', exc)
        print('Tip: make sure a *fresh* Arbiter game is visible (covered tiles '
              'present) and that the window is not minimised.')
        return 1

    print(f'Detected grid: origin=({g.x0},{g.y0}) cell={g.cell_w}x{g.cell_h}')

    # classify every cell and print an ASCII board
    print('\nClassified board (# = covered, f = flag, . = empty, 1-8 = number,')
    print('                   X = explosion/mine, ? = unknown):')
    legend = {'square blank': '#', 'square bombflagged': 'f',
              'square bombdeath': 'X'}
    for r in range(rows):
        line = []
        for c in range(cols):
            left, top, right, bottom = g.cell_box(r, c)
            tok = skin.classify(frame[top:bottom, left:right])
            if tok in legend:
                line.append(legend[tok])
            elif tok.startswith('square open'):
                n = tok.replace('square open', '')
                line.append('.' if n == '0' else n)
            else:
                line.append('?')
        print('  ' + ' '.join(line))

    # save calibration
    out = {
        'difficulty': difficulty,
        'rows': rows, 'cols': cols, 'mines': mines,
        'geometry': {'x0': g.x0, 'y0': g.y0,
                     'cell_w': g.cell_w, 'cell_h': g.cell_h},
        'skin': {k: getattr(skin, k) for k in
                 ('empty_grey', 'bevel_bright', 'bevel_delta', 'red_min',
                  'red_dom', 'boom_frac', 'flag_frac', 'bg_dist')},
    }
    json.dump(out, open(CALIB_PATH, 'w'), indent=2)
    print(f'\nSaved calibration to {CALIB_PATH}')
    print('If any cell above looks wrong, your skin/DPI differs from the '
          'default; tweak the "skin" values in that file and re-run.')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
