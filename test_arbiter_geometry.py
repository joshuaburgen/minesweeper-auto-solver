"""Synthetic-image tests for arbiter_geometry.detect_grid.

Renders a fake Arbiter client area (window-chrome background surrounding a grid
of covered cells at a known offset/size) and asserts detect_grid recovers the
origin and cell size. Pure numpy, no GUI.
"""
import numpy as np
from PIL import Image, ImageDraw
from unittest import TestCase

from arbiter_geometry import detect_grid, BoardGeometry
import arbiter_skin as skin_mod

GREY = (192, 192, 192)
CHROME = (60, 60, 90)  # distinct window background so the field stands out


def render(rows, cols, size, ox, oy, margin=8, chrome=CHROME):
    W = ox + cols * size + margin
    H = oy + rows * size + margin
    img = Image.new('RGB', (W, H), chrome)
    d = ImageDraw.Draw(img)
    b = 2 if size >= 12 else 1
    for r in range(rows):
        for c in range(cols):
            x = ox + c * size
            y = oy + r * size
            d.rectangle([x, y, x + size - 1, y + size - 1], fill=GREY)
            d.rectangle([x, y, x + size - 1, y + b - 1], fill=(255, 255, 255))
            d.rectangle([x, y, x + b - 1, y + size - 1], fill=(255, 255, 255))
            d.rectangle([x, y + size - b, x + size - 1, y + size - 1], fill=(128, 128, 128))
            d.rectangle([x + size - b, y, x + size - 1, y + size - 1], fill=(128, 128, 128))
    return np.asarray(img)


class TestDetectGrid(TestCase):
    def test_counter_panel_above_grid_is_not_a_tile_row(self):
        img = render(9, 9, 16, 8, 56, chrome=GREY).copy()
        img[40:42, 8:152] = 128
        img[46:50, 8:152] = 0
        g = detect_grid(img, 9, 9)
        self.assertEqual((g.x0, g.y0), (8, 56))

    def test_grey_window_background_is_not_part_of_grid(self):
        img = render(9, 9, 16, 8, 40, chrome=GREY)
        g = detect_grid(img, 9, 9)
        self.assertEqual((g.x0, g.y0, g.cell_w), (8, 40, 16))

    def test_recovers_origin_and_size(self):
        rows, cols, size, ox, oy = 9, 9, 16, 8, 40
        img = render(rows, cols, size, ox, oy)
        g = detect_grid(img, rows, cols)
        self.assertIsInstance(g, BoardGeometry)
        # size should be found exactly
        self.assertEqual(g.cell_w, size)
        self.assertEqual(g.cell_h, size)
        # origin within one cell of the truth
        self.assertLessEqual(abs(g.x0 - ox), size)
        self.assertLessEqual(abs(g.y0 - oy), size)

    def test_expert_size_20(self):
        rows, cols, size, ox, oy = 16, 30, 20, 8, 40
        img = render(rows, cols, size, ox, oy)
        g = detect_grid(img, rows, cols)
        self.assertEqual(g.cell_w, 20)
        self.assertLessEqual(abs(g.x0 - ox), size)
        self.assertLessEqual(abs(g.y0 - oy), size)

    def test_cell_center_and_box(self):
        g = BoardGeometry(x0=8, y0=40, cell_w=16, cell_h=16)
        self.assertEqual(g.cell_center(0, 0), (16, 48))
        self.assertEqual(g.cell_box(1, 2), (40, 56, 56, 72))

    def test_no_grid_raises(self):
        # a blank chrome image has no covered cells -> should raise
        img = np.full((120, 120, 3), CHROME, dtype=np.uint8)
        with self.assertRaises(ValueError):
            detect_grid(img, 9, 9)

    def test_left_cells_revealed_still_finds_origin(self):
        # simulate the common mid-game case: the leftmost column already
        # revealed (flat grey) while covered cells remain to the right.
        rows, cols, size, ox, oy = 9, 9, 16, 8, 40
        img = render(rows, cols, size, ox, oy).copy()
        # blank out the leftmost column to flat revealed grey via PIL
        from PIL import Image as I
        im = I.fromarray(img)
        d = ImageDraw.Draw(im)
        d.rectangle([ox, oy, ox + size - 1, oy + rows * size - 1], fill=GREY)
        img = np.asarray(im)
        g = detect_grid(img, rows, cols)
        self.assertLessEqual(abs(g.x0 - ox), size)
