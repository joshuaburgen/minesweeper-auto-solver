"""Synthetic-image tests for arbiter_skin.Skin.

We cannot click a real Arbiter window in CI, so we *draw* cell tiles the way
the default Arbiter skin renders them and assert the classifier recovers the
right state token. This exercises the exact code path used at runtime.
"""
import numpy as np
from PIL import Image, ImageDraw
from unittest import TestCase

import arbiter_skin as skin_mod
from arbiter_skin import Skin, BLANK, FLAG, BOOM, open_tok

GREY = (192, 192, 192)
DIGIT = skin_mod.NUMBER_COLORS


def covered(cell=20):
    """A raised 3-D 'unrevealed' tile: bright top/left, dark bottom/right."""
    img = Image.new('RGB', (cell, cell), GREY)
    d = ImageDraw.Draw(img)
    # ~2px bevel like the real default skin
    d.rectangle([0, 0, cell - 1, 1], fill=(255, 255, 255))   # top highlight
    d.rectangle([0, 0, 1, cell - 1], fill=(255, 255, 255))   # left highlight
    d.rectangle([0, cell - 2, cell - 1, cell - 1], fill=(128, 128, 128))
    d.rectangle([cell - 2, 0, cell - 1, cell - 1], fill=(128, 128, 128))
    return np.asarray(img)


def flagged(cell=20):
    """Covered tile with a red flag glyph near the centre."""
    img = Image.fromarray(covered(cell).copy())
    d = ImageDraw.Draw(img)
    c = cell // 2
    d.polygon([(c - 3, c - 5), (c - 3, c + 4), (c + 3, c + 4)], fill=(255, 0, 0))
    d.line([(c - 3, c - 5), (c - 3, c + 6)], fill=(255, 0, 0), width=2)
    return np.asarray(img)


def revealed(n=0, cell=20):
    """A flat revealed tile; digit n>0 drawn in its classic colour.

    The glyph is drawn large and solid so its core colour matches the classic
    digit colour exactly (the classifier reads the glyph core).
    """
    img = Image.new('RGB', (cell, cell), GREY)
    if n > 0:
        d = ImageDraw.Draw(img)
        # draw a chunky block glyph in the centre to stand in for the digit
        x0, y0 = cell // 2 - 3, cell // 2 - 4
        d.rectangle([x0, y0, x0 + 5, y0 + 8], fill=DIGIT[n])
    return np.asarray(img)


def mine_death(cell=20):
    """A losing click: red background flooding the cell."""
    img = Image.new('RGB', (cell, cell), (255, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse((4, 4, cell - 5, cell - 5), fill=(0, 0, 0))
    return np.asarray(img)


class TestSkin(TestCase):
    def setUp(self):
        self.skin = Skin()

    def test_covered_is_blank(self):
        self.assertEqual(self.skin.classify(covered()), BLANK)

    def test_flagged_is_flag(self):
        self.assertEqual(self.skin.classify(flagged()), FLAG)

    def test_revealed_empty_is_open0(self):
        self.assertEqual(self.skin.classify(revealed(0)), open_tok(0))

    def test_revealed_digits(self):
        for n in range(1, 9):
            tok = self.skin.classify(revealed(n))
            self.assertEqual(tok, open_tok(n),
                             msg='digit %d classified as %s' % (n, tok))

    def test_mine_death(self):
        self.assertEqual(self.skin.classify(mine_death()), BOOM)

    def test_boom_token_not_in_reps(self):
        # game-over must be distinguishable from every REPS key
        import Info
        self.assertNotIn(BOOM, Info.REPS)

    def test_small_cell(self):
        # 16px cells (100% scaling) must classify just as well as 20px
        self.assertEqual(self.skin.classify(covered(16)), BLANK)
        self.assertEqual(self.skin.classify(revealed(3, 16)), open_tok(3))

    def test_rejects_tiny_patch(self):
        with self.assertRaises(ValueError):
            self.skin.classify(np.zeros((2, 2, 3), dtype=np.uint8))
