"""Read-only recognition diagnostic. No focus changes, clicks or key events."""
import argparse
from collections import Counter
from pathlib import Path
import json

from PIL import Image

from arbiter_window import ArbiterWindow, set_dpi_aware
from arbiter_geometry import detect_grid
from arbiter_skin import DEFAULT_SKIN
import Info


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--difficulty', type=int, choices=(1, 2, 3), default=1)
    args = parser.parse_args()
    set_dpi_aware()
    window = ArbiterWindow()
    frame = window.capture_client()
    directory = Path('arbiter_diagnostic')
    directory.mkdir(exist_ok=True)
    Image.fromarray(frame).save(directory / 'client.png')
    rows, cols, _, _ = Info.DIFFICULTIES[args.difficulty - 1]
    geometry = detect_grid(frame, rows, cols)
    counts = Counter()
    lines = []
    for r in range(rows):
        line = []
        for c in range(cols):
            left, top, right, bottom = geometry.cell_box(r, c)
            token = DEFAULT_SKIN.classify(frame[top:bottom, left:right])
            counts[token] += 1
            line.append('#' if token == 'square blank' else
                        'f' if token == 'square bombflagged' else
                        token.removeprefix('square open') if token.startswith('square open') else 'X')
        lines.append(' '.join(line))
    report = {'client_size': [frame.shape[1], frame.shape[0]],
              'difficulty': args.difficulty, 'geometry': vars(geometry),
              'counts': dict(counts), 'board': lines}
    (directory / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report, indent=2))
    print(f'Read-only diagnostic saved to {directory.resolve()}')


if __name__ == '__main__':
    main()
