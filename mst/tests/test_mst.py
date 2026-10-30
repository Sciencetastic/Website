"""Tests run against real NES Maker projects. Point MST_SAMPLES at a folder holding them:

    MST_SAMPLES=/path/to/Projects python -m unittest discover -s tests -v

Files used (skipped when absent): BEFORE_Moo.MST, AFTER_Moo.MST, MST_C.MST (differential edits made in the
real editor), plus any *.MST for the round-trip check.
"""
import glob
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from nesmaker_mst import MSTProject  # noqa: E402

DIR = os.environ.get('MST_SAMPLES', '')


def sample(name):
    p = os.path.join(DIR, name)
    if not os.path.exists(p):
        raise unittest.SkipTest(f'{name} not found in MST_SAMPLES')
    return p


def rd(name):
    with open(sample(name), 'rb') as f:
        return f.read()


class RoundTrip(unittest.TestCase):
    def test_every_sample_is_lossless(self):
        files = glob.glob(os.path.join(DIR, '*.MST*')) if DIR else []
        if not files:
            self.skipTest('no samples')
        for f in files:
            with self.subTest(f=os.path.basename(f)):
                self.assertTrue(MSTProject.open(f).verify_roundtrip())


class Differential(unittest.TestCase):
    """The editor's own edits must be reproduced byte-for-byte from the headless API."""

    def test_reproduce_after_edit(self):
        p = MSTProject(rd('BEFORE_Moo.MST'))
        self.assertEqual(p.screens[2].set_tile(7, 8, 4), 'preview-updated')
        self.assertEqual(p.to_bytes(), rd('AFTER_Moo.MST'))

    def test_reproduce_c_edit(self):
        p = MSTProject(rd('BEFORE_Moo.MST'))
        s = p.screens[2]
        lib = p.cell_library()
        s.set_tile(6, 7, 2, 1, library=lib)
        s.set_tile(7, 8, 4, library=lib)
        self.assertEqual(p.to_bytes(), rd('MST_C.MST'))


class Edits(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = rd('BEFORE_Moo.MST')

    def test_palette_and_vars_and_save(self):
        p = MSTProject(self.data)
        p.palettes[3].set_color(1, 1, 33)
        p.palettes[3].name = 'HeadlessPal'
        p.user_vars()[0].value = 9
        p.ram_sections()['zeropage'].add('hl_test', 1, 'x')
        p.add_user_var('hl_user', 3, 'y')
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, 'o.MST')
            p.save(out)
            with self.assertRaises(FileExistsError):
                p.save(out)
            q = MSTProject.open(out)
            self.assertEqual(q.palettes[3].colors[5], 33)
            self.assertEqual(q.palettes[3].name, 'HeadlessPal')
            self.assertEqual(q.user_vars()[0].value, 9)
            self.assertEqual(q.user_vars()[-1].name, 'hl_user')
            self.assertIn('hl_test', [v.name for v in q.ram_sections()['zeropage'].vars()])
            self.assertTrue(q.verify_roundtrip())

    def test_clone_place_delete_screen(self):
        p = MSTProject(self.data)
        n = len(p.screens)
        g = p.clone_screen(2)
        self.assertEqual((len(p.screens), p.leaves[3].val), (n + 1, n + 1))
        p.place_screen('overworld', 14, 14, g)
        self.assertEqual(len(p.world_map()), 39)
        p.delete_screen(g)
        self.assertEqual((len(p.screens), len(p.world_map())), (n, 38))
        self.assertEqual(p.to_bytes(), self.data)           # add + delete is a perfect no-op

    def test_asset_image_replace(self):
        p = MSTProject(self.data)
        a = p.assets[0]
        im = a.image()
        im.putpixel((0, 0), (1, 2, 3))
        a.replace_image(im)
        self.assertEqual(p.assets[0].image().getpixel((0, 0)), (1, 2, 3))
        self.assertTrue(MSTProject(p.to_bytes()).assets[0].image().getpixel((0, 0)) == (1, 2, 3))


if __name__ == '__main__':
    unittest.main()
