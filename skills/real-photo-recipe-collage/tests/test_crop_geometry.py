"""Tests that safe zoom reacts to projected ellipse geometry and actual centering."""
import sys
import unittest
from pathlib import Path
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from recipe_collage import crop_original

class EllipseAwareCropTests(unittest.TestCase):
    def setUp(self):
        self.im = Image.new("RGB", (960, 1280), "#bbb6a9")
        self.ratio = 740 / 656
        self.ellipse = dict(
            center=[.50, .46], radius_fraction=.21,
            ellipse_aspect_yx=.78)

    def test_ellipse_zoom_is_larger_than_circular_fallback(self):
        crop, rect, qa = crop_original(self.im, self.ellipse, self.ratio, .92, .48)
        circular = dict(self.ellipse, ellipse_aspect_yx=1.0)
        _, _, qa_circle = crop_original(self.im, circular, self.ratio, .92, .48)
        self.assertGreater(qa["actual_subject_fill"], qa_circle["actual_subject_fill"])
        self.assertGreaterEqual(qa["actual_subject_fill"], .90)
        self.assertEqual(qa["estimated_rim_cut_fraction"], 0.0)
        self.assertLess(abs(qa["center_error_x"]), .01)
        self.assertLess(abs(qa["center_y"] - .48), .02)
        self.assertTrue(qa["no_stretch"])
        self.assertEqual(crop.size, (rect[2]-rect[0], rect[3]-rect[1]))

    def test_per_step_framing_changes_actual_zoom(self):
        _, _, small = crop_original(self.im, self.ellipse, self.ratio, .80, .48)
        _, _, big = crop_original(self.im, self.ellipse, self.ratio, .94, .48)
        self.assertGreater(big["actual_subject_fill"], small["actual_subject_fill"])
        self.assertLessEqual(big["actual_subject_fill"], .95)
        self.assertEqual(big["estimated_rim_cut_fraction"], 0.)

    def test_vertical_geometry_limits_zoom_without_cropping(self):
        circle = dict(self.ellipse, ellipse_aspect_yx=1.0)
        _, _, qa = crop_original(self.im, circle, self.ratio, 1.0, .48)
        self.assertTrue(qa["zoom_limited_by_geometry"])
        self.assertLess(qa["actual_subject_fill"], .94)
        self.assertEqual(qa["estimated_rim_cut_fraction"], 0.)

    def test_invalid_ellipse_and_framing_fails(self):
        with self.assertRaises(ValueError):
            crop_original(self.im, dict(self.ellipse, ellipse_aspect_yx=.2),
                          self.ratio, .94, .48)
        with self.assertRaises(ValueError):
            crop_original(self.im, self.ellipse, self.ratio, 1.2, .48)

if __name__ == "__main__":
    unittest.main()
