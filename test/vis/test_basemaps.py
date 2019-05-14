import unittest
from cartoframes import vis


class TestBasemaps(unittest.TestCase):
    def test_is_defined(self):
        "vis.basemaps"
        self.assertNotEqual(vis.basemaps, None)

    def test_has_defined_basemaps(self):
        "vis.basemaps content"
        self.assertEqual(vis.basemaps.positron, 'Positron')
        self.assertEqual(vis.basemaps.darkmatter, 'DarkMatter')
        self.assertEqual(vis.basemaps.voyager, 'Voyager')
