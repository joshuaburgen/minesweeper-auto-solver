"""Pure, GUI-free board-geometry detection for Minesweeper Arbiter.

Given a screenshot of the Arbiter *client area* (H x W x 3 uint8 RGB) and the
known board dimensions (rows, cols), work out where the minefield starts and
how big each cell is, returning a BoardGeometry:

    BoardGeometry(x0, y0, cell_w, cell_h)

Strategy (no OpenCV / pyautogui required, pure numpy):

  1. Build a synthetic "covered cell" template for each candidate cell size
     using the default skin (192-grey face, 2px bright top/left bevel, 2px
     dark bottom/right bevel) -- see arbiter_skin for the colour model.
  2. For each candidate size, slide the template over the grayscale screenshot
     with a fast Sum-of-Absolute-Differences search and record the best match.
  3. Keep the size whose best match is strongest (lowest normalised SAD). That
     match is a real covered cell, pinning both cell size and grid *phase*.
  4. Recover the grid origin by walking left/up from the anchor in cell steps
     while cells still look like field tiles, stopping at the field boundary.

Everything here is decoupled from win32 so it can be unit-tested against a
synthetically rendered board (see test_arbiter_geometry.py).
"""
from dataclasses import dataclass

import numpy as np

import arbiter_skin as skin_mod
from arbiter_skin import Skin


@dataclass
class BoardGeometry:
    x0: int
    y0: int
    cell_w: int
    cell_h: int

    def cell_center(self, row: int, col: int):
        """Absolute (x, y) centre of the cell at (row, col)."""
        cx = self.x0 + col * self.cell_w + self.cell_w // 2
        cy = self.y0 + row * self.cell_h + self.cell_h // 2
        return cx, cy

    def cell_box(self, row: int, col: int):
        """(left, top, right, bottom) pixel box of the cell at (row, col)."""
        left = self.x0 + col * self.cell_w
        top = self.y0 + row * self.cell_h
        return left, top, left + self.cell_w, top + self.cell_h


# candidate cell sizes (px) across common DPI scalings for the default skin
DEFAULT_SIZES = (16, 20, 24, 28, 32)


def _covered_template(size: int) -> np.ndarray:
    """Grayscale template of one covered cell for the default skin."""
    g = np.full((size, size), skin_mod.DEFAULT_SKIN.empty_grey, dtype=np.uint8)
    b = 2 if size >= 12 else 1
    g[0:b, :] = 255            # top highlight
    g[:, 0:b] = 255            # left highlight
    g[size - b:size, :] = 128  # bottom shadow
    g[:, size - b:size] = 128  # right shadow
    return g


def is_covered_tile(patch, skin):
    """Reject panel borders that the corner-only classifier calls covered."""
    if (patch.ndim != 3 or patch.shape[0] != patch.shape[1]
            or patch.shape[0] < 8):
        return False
    if skin.classify(patch) != skin_mod.BLANK:
        return False
    error = np.abs(patch.mean(axis=2) - _covered_template(patch.shape[0])).mean()
    return error < 20


def _best_sad(gray: np.ndarray, tmpl: np.ndarray, band: int = 32):
    """Memory-bounded SAD match. Returns (score, x, y) of best top-left.

    The naive `sliding_window_view(...).astype(int16)` materialises a huge
    (H, W, th, tw) dense array plus temporaries, which can exhaust memory on
    large client areas. We instead scan in horizontal bands so peak memory is
    bounded to ~band * W * th * tw and freed each iteration.
    """
    th, tw = tmpl.shape
    H, W = gray.shape
    if H < th or W < tw:
        return None
    t = tmpl.astype(np.int16)
    g = gray.astype(np.int16)
    out_h, out_w = H - th + 1, W - tw + 1
    best = None  # (score, x, y)
    for y0 in range(0, out_h, band):
        y1 = min(y0 + band, out_h)
        sub = g[y0:y1 + th - 1]
        win = np.lib.stride_tricks.sliding_window_view(sub, (th, tw))
        sad = np.abs(win - t).sum(axis=(-1, -2))
        idx = int(np.argmin(sad))
        ly, lx = divmod(idx, sad.shape[1])
        score = int(sad[ly, lx])
        if best is None or score < best[0]:
            best = (score, lx, y0 + ly)
    return best


def _looks_like_field(patch: np.ndarray, skin: Skin) -> bool:
    """Does this cell patch still belong to the minefield (not chrome)?

    A field cell is *grey-dominant*: its pixels are achromatic (all three
    channels close together) and mid-to-bright -- the 192 face, the 255 bevel
    highlight and the 128 bevel shadow all qualify. Coloured digit pixels are
    chromatic and thus excluded, but they are a small minority of any cell.
    Window chrome (e.g. a coloured title/menu background) is rejected.
    """
    if patch.size == 0:
        return False
    # Window panels use the same grey as revealed cells. A real tile has a
    # bevel, a grid edge or a glyph; a flat panel must not extend the board.
    if np.ptp(patch.astype(np.int16), axis=(0, 1)).max() < 12:
        return False
    flat = patch.reshape(-1, 3).astype(int)
    mx = flat.max(axis=1)
    mn = flat.min(axis=1)
    achromatic = (mx - mn) <= 24          # R~G~B
    mid_bright = (mx >= 80) & (mx <= 235)  # not pure black, not blown out
    greyish = achromatic & mid_bright
    return greyish.mean() > 0.6


def detect_grid(img: np.ndarray,
                rows: int,
                cols: int,
                sizes=DEFAULT_SIZES,
                skin: Skin = None,
                max_sad: float = 30.0) -> BoardGeometry:
    """Detect the minefield origin and cell size in a client-area screenshot.

    max_sad is the maximum allowed *normalised* best-match score (mean absolute
    grayscale error per pixel). A genuine covered-cell match is near 0; a blank
    image with no field scores high and is rejected.

    Raises ValueError if no plausible grid is found (caller should then fall
    back to a saved calibration).
    """
    skin = skin or skin_mod.DEFAULT_SKIN
    if img.ndim != 3 or img.shape[2] < 3:
        raise ValueError('expected an HxWx3 RGB image')
    img = img[..., :3]
    gray = img.mean(axis=2).astype(np.uint8)
    H, W = gray.shape

    # 1-3) find the cell size with the strongest covered-cell match
    best = None  # (normalised_sad, size, ax, ay)
    for size in sizes:
        if size < 8 or size > min(H, W):
            continue
        res = _best_sad(gray, _covered_template(size))
        if res is None:
            continue
        sad, ax, ay = res
        norm = sad / float(size * size)  # compare sizes fairly
        if best is None or norm < best[0]:
            best = (norm, size, ax, ay)

    if best is None or best[0] > max_sad:
        raise ValueError('could not locate a covered cell (grid not found)')

    _, size, ax, ay = best

    # 4) recover the grid origin by walking left/up from the anchor in steps
    #    of one cell, using the anchor's true coordinates (which carry the
    #    grid phase) so we stop exactly at the field's top-left boundary.
    x0, y0 = ax, ay
    while x0 - size >= 0:
        patch = img[ay:ay + size, x0 - size:x0]
        if not _looks_like_field(patch, skin):
            break
        x0 -= size
    while y0 - size >= 0:
        patch = img[y0 - size:y0, ax:ax + size]
        # A grey counter panel can contain borders and digits, just like an
        # open tile. Follow the anchor's covered column, not the counter panel.
        if skin.classify(patch) not in (skin_mod.BLANK, skin_mod.FLAG):
            break
        y0 -= size

    # sanity: the implied field must roughly fit within the image; otherwise
    # anchor at the matched covered cell's grid phase
    if x0 + cols * size > W + size or y0 + rows * size > H + size:
        x0, y0 = ax % size, ay % size

    return BoardGeometry(x0=x0, y0=y0, cell_w=size, cell_h=size)

