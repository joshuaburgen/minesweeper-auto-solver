"""Pure, GUI-free classifier that maps a single Minesweeper-Arbiter cell
image (an H x W x 3 uint8 RGB patch) to one of the same state tokens the web
solver uses in Info.REPS:

    'square blank'        -> covered / unrevealed tile
    'square bombflagged'  -> covered tile carrying a red flag
    'square open0'..'open8' -> revealed tile showing 0..8
    'square bombdeath'    -> revealed red mine (game over)  [not in REPS]

It targets the *default* Arbiter skin at 100% scaling, where:
  * a covered tile is a raised 3-D button: bright top/left bevel, dark
    bottom/right bevel, ~192 grey face;
  * a revealed tile is flat ~192 grey with a thin grid line;
  * digits are drawn in the classic colours (1 blue, 2 green, 3 red,
    4 navy, 5 maroon, 6 teal, 7 black, 8 dark-grey).

The thresholds live on the Skin dataclass so calibrate.py can persist tuned
values for non-default skins. Keeping this module free of any win32 / capture
imports makes it unit-testable with synthetic PIL images (see tests).
"""
import numpy as np

# state tokens (kept identical to the web solver's vocabulary)
BLANK = 'square blank'
FLAG = 'square bombflagged'
BOOM = 'square bombdeath'  # deliberately absent from Info.REPS


def open_tok(n: int) -> str:
    return 'square open%d' % n


# classic digit colours used by the default skin
NUMBER_COLORS = {
    1: (0, 0, 255),      # blue
    2: (0, 128, 0),      # green
    3: (255, 0, 0),      # red
    4: (0, 0, 128),      # navy
    5: (128, 0, 0),      # maroon
    6: (0, 128, 128),    # teal
    7: (0, 0, 0),        # black
    8: (128, 128, 128),  # dark grey (handled specially, excluded from match)
}


class Skin:
    """Tunable colour thresholds for one Arbiter skin."""

    def __init__(self,
                 empty_grey: int = 192,
                 bevel_bright: int = 200,
                 bevel_delta: int = 40,
                 red_min: int = 140,
                 red_dom: int = 50,
                 boom_frac: float = 0.5,
                 flag_frac: float = 0.04,
                 bg_dist: int = 60) -> None:
        self.empty_grey = empty_grey
        self.bevel_bright = bevel_bright
        self.bevel_delta = bevel_delta
        self.red_min = red_min
        self.red_dom = red_dom
        self.boom_frac = boom_frac
        self.flag_frac = flag_frac
        self.bg_dist = bg_dist

    # ---- small pixel helpers -------------------------------------------------
    @staticmethod
    def _brightness(px) -> float:
        return (int(px[0]) + int(px[1]) + int(px[2])) / 3.0

    def _red_mask(self, patch: np.ndarray) -> np.ndarray:
        r = patch[..., 0].astype(int)
        g = patch[..., 1].astype(int)
        b = patch[..., 2].astype(int)
        return (r >= self.red_min) & (r - g >= self.red_dom) & (r - b >= self.red_dom)

    # ---- main entry point ----------------------------------------------------
    def classify(self, patch: np.ndarray) -> str:
        """Return the state token for one cell patch (HxWx3 uint8)."""
        if patch.ndim != 3 or patch.shape[2] < 3:
            raise ValueError('expected an HxWx3 RGB patch')
        patch = patch[..., :3]
        h, w = patch.shape[0], patch.shape[1]
        if h < 4 or w < 4:
            raise ValueError('cell patch too small to classify')

        off = 1
        tl = patch[off, off]                       # top-left inner corner
        br = patch[h - 2, w - 2]                   # bottom-right inner corner

        red_frac = float(self._red_mask(patch).mean())

        # 1) explosion: a losing click paints a red background over the cell
        if red_frac > self.boom_frac:
            return BOOM

        # 2) raised 3-D bevel => this is still a covered surface
        covered = (self._brightness(tl) >= self.bevel_bright
                   and (self._brightness(tl) - self._brightness(br)) > self.bevel_delta)
        if covered:
            # a flag is a red glyph sitting on an otherwise covered tile
            return FLAG if red_frac > self.flag_frac else BLANK

        # 3) flat surface => revealed; identify the digit
        return self._classify_number(patch)

    def _classify_number(self, patch: np.ndarray) -> str:
        h, w = patch.shape[0], patch.shape[1]
        # look at the central region only, away from bevel / grid lines
        y0, y1 = max(2, h // 4), min(h - 1, (3 * h) // 4)
        x0, x1 = max(2, w // 4), min(w - 1, (3 * w) // 4)
        region = patch[y0:y1, x0:x1].reshape(-1, 3).astype(int)
        if region.size == 0:
            region = patch.reshape(-1, 3).astype(int)

        # glyph pixels = those far from the flat revealed-grey background
        bg = np.array([self.empty_grey] * 3)
        dist = np.abs(region - bg).sum(axis=1)
        mask = dist > self.bg_dist
        glyph = region[mask]
        if glyph.shape[0] < 3:
            return open_tok(0)          # essentially flat => empty

        # use the *core* of the glyph (the pixels farthest from the
        # background) so anti-aliased edges don't drag the colour estimate.
        gdist = dist[mask]
        k = max(3, glyph.shape[0] // 3)
        core = glyph[np.argsort(gdist)[-k:]]
        med = np.median(core, axis=0)

        # nearest classic digit colour (7 black vs 8 dark-grey included)
        best, best_d = 0, None
        for n, (cr, cg, cb) in NUMBER_COLORS.items():
            d = (med[0] - cr) ** 2 + (med[1] - cg) ** 2 + (med[2] - cb) ** 2
            if best_d is None or d < best_d:
                best_d, best = d, n
        return open_tok(best)



# default singleton
DEFAULT_SKIN = Skin()
