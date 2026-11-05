"""Regression tests for deterministic, color-first, source-locked recipe collage."""
import argparse
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import recipe_collage as recipe


class RecipeCollageContractTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.steps = []
        for i in range(6):
            path = self.root / f"photo_{i+1:02d}.png"
            Image.new("RGB", (350, 420), (80 + 15*i, 110 + 8*i, 120)).save(path)
            self.steps.append({
                "number": f"{i+1:02d}",
                "file": path.name,
                "label": f"步骤{i+1}",
                "role": f"第{i+1}步的实际照片",
            })
        self.config = {
            "width": 1500,
            "height": 2000,
            "preset": "natural_appetizing_v4",
            "steps": self.steps,
        }
        self.config_path = self.root / "config.json"
        self.save_config()

    def save_config(self):
        self.config_path.write_text(json.dumps(self.config, ensure_ascii=False), encoding="utf-8")

    def test_source_lock_detects_changed_photo(self):
        locked = recipe.write_locked_config(self.config_path)
        self.assertTrue(locked.exists())
        data = json.loads(locked.read_text("utf-8"))
        self.assertTrue(data["require_source_sha256"])
        recipe.validate_source_mapping(data, data["steps"], locked.parent)
        # Change pixels without changing filename: the lock must fail.
        Image.new("RGB", (350, 420), (0, 0, 0)).save(self.root / "photo_03.png")
        with self.assertRaisesRegex(ValueError, "SHA256"):
            recipe.validate_source_mapping(data, data["steps"], locked.parent)

    def test_lock_requires_human_assigned_photo_role(self):
        self.steps[4].pop("role")
        self.save_config()
        with self.assertRaisesRegex(ValueError, "role"):
            recipe.write_locked_config(self.config_path)

    def test_swapping_images_also_swaps_source_hash_and_role(self):
        locked = recipe.write_locked_config(self.config_path)
        data = json.loads(locked.read_text("utf-8"))
        args = argparse.Namespace(swap=[(1, 3)], set_label=None,
                                  set_step_saturation=None)
        updated = recipe.modify(data, args)
        recipe.validate_source_mapping(updated, updated["steps"], locked.parent)
        self.assertEqual(updated["steps"][0]["role"], "第3步的实际照片")
        self.assertEqual(updated["steps"][2]["role"], "第1步的实际照片")

    def test_duplicate_and_nonsequential_files_rejected(self):
        self.steps[2]["file"] = self.steps[1]["file"]
        with self.assertRaisesRegex(ValueError, "重复"):
            recipe.validate_source_mapping(self.config, self.steps, self.root)
        self.steps[2]["file"] = "photo_03.png"
        self.steps[2]["number"] = "04"
        with self.assertRaisesRegex(ValueError, "编号"):
            recipe.validate_source_mapping(self.config, self.steps, self.root)

    def test_strong_color_is_validated_without_changing_geometry(self):
        im = Image.new("RGB", (20, 12), (120, 110, 100))
        valid = dict(brightness=1.04, contrast=1.09, saturation=1.30,
                     warmth=0.01, sharpness=1.10)
        result = recipe.natural_grade(im, valid)
        self.assertEqual(result.size, im.size)
        with self.assertRaises(ValueError):
            recipe.natural_grade(im, dict(valid, saturation=1.33))
        with self.assertRaises(ValueError):
            recipe.natural_grade(im, dict(valid, saturation=float("nan")))

    def test_all_neutral_grade_is_rejected(self):
        neutral = dict(brightness=1.0, contrast=1.0, saturation=1.0,
                       warmth=0.0, sharpness=1.0)
        with self.assertRaisesRegex(ValueError, "必须.*调色"):
            recipe.natural_grade(Image.new("RGB", (30, 30), "gray"), neutral)

    def test_mandatory_grade_happens_before_every_crop(self):
        try:
            recipe.font_file()
        except FileNotFoundError:
            self.skipTest("Noto Sans CJK SC Bold is required for rendering")
        locked = recipe.write_locked_config(self.config_path)
        args = argparse.Namespace(output=str(self.root / "ordering.png"), debug=False,
                                  save_qa=False, swap=None, set_label=None,
                                  set_step_saturation=None, save_config=None,
                                  saturation=None, make_calibration=False, strict=False)
        events = []
        original_grade, original_crop = recipe.natural_grade, recipe.crop_original
        def tracking_grade(im, settings):
            events.append("grade")
            return original_grade(im, settings)
        def tracking_crop(*a, **kw):
            events.append("crop")
            return original_crop(*a, **kw)
        rim = dict(ok=True, source="auto_radial_outer_rim", score=1.0,
                   center=[0.5, 0.50], radius_fraction=0.29)
        with patch.object(recipe, "detect_circle", return_value=rim), \
             patch.object(recipe, "natural_grade", side_effect=tracking_grade), \
             patch.object(recipe, "crop_original", side_effect=tracking_crop):
            _, qa = recipe.generate(locked, args)
        self.assertEqual(events, ["grade", "crop"] * 6)
        self.assertTrue(qa["color_applied_to_original_before_crop"])
        self.assertTrue(qa["color_correction_executed_for_all_steps"])
        self.assertTrue(qa["no_color_filters_after_typography"])
        self.assertEqual(len(qa["steps"]), 6)
        for step in qa["steps"]:
            self.assertEqual(step["grade_stage"], "original_before_crop")
            self.assertTrue(step["color_correction_executed"])
            self.assertGreater(step["grade_mean_abs_pixel_delta"], 0)
            self.assertEqual(step["caption_font_px"], 51)

    def test_disabled_color_correction_is_rejected(self):
        self.config["enable_color_correction"] = False
        self.save_config()
        args = argparse.Namespace(swap=None, set_label=None,
                                  set_step_saturation=None, save_config=None)
        with self.assertRaisesRegex(ValueError, "不得关闭"):
            recipe.generate(self.config_path, args)

    def test_real_fixed_font_identity_when_installed(self):
        try:
            fontpath, index = recipe.font_file()
        except FileNotFoundError:
            self.skipTest("Noto Sans CJK SC Bold is required for rendering")
        face = ImageFont.truetype(fontpath, recipe.CAPTION_FONT_PX, index=index)
        self.assertEqual(face.getname(), ("Noto Sans CJK SC", "Bold"))
        self.assertEqual(recipe.CAPTION_FONT_PX, 51)
        self.assertEqual(recipe.NUMBER_FONT_PX, 49)

    def test_render_keeps_typography_after_color_and_writes_qa(self):
        try:
            recipe.font_file()
        except FileNotFoundError:
            self.skipTest("Noto Sans CJK SC Bold is required for rendering")
        locked = recipe.write_locked_config(self.config_path)
        args = argparse.Namespace(output=str(self.root/"result1.png"), debug=False,
                                  save_qa=False, swap=None, set_label=None,
                                  set_step_saturation=None, save_config=None,
                                  saturation=None, make_calibration=False, strict=False)
        rim = dict(ok=True, source="auto_radial_outer_rim", score=1.0,
                   center=[0.5, 0.50], radius_fraction=0.29)
        with patch.object(recipe, "detect_circle", return_value=rim):
            p1, qa1 = recipe.generate(locked, args)
        self.assertTrue(p1.exists())
        self.assertTrue((self.root/"result1_QA.json").exists())
        self.assertTrue(qa1["typography_drawn_after_photo_grading"])
        self.assertTrue(qa1["source_hash_lock_enabled"])
        self.assertFalse(qa1["cooking_step_semantics_verified"])
        self.assertEqual((qa1["caption_font_px"], qa1["number_font_px"]), (51, 49))
        self.assertEqual(len(qa1["steps"]), 6)

        # Change colors only, re-render from the same sources, compare label/badge pixels.
        changed = json.loads(locked.read_text("utf-8"))
        changed["steps"][0]["color_override"] = {"saturation": 1.30}
        another = self.root/"config_changed.json"
        another.write_text(json.dumps(changed, ensure_ascii=False), encoding="utf-8")
        args.output = str(self.root/"result2.png")
        with patch.object(recipe, "detect_circle", return_value=rim):
            p2, qa2 = recipe.generate(another, args)
        self.assertEqual(qa2["font_sha256"], qa1["font_sha256"])
        with Image.open(p1) as a, Image.open(p2) as b:
            # Center of first step number and the center of caption background.
            for xy in ((72, 63), (250, 590), (400, 590)):
                self.assertEqual(a.getpixel(xy), b.getpixel(xy))


if __name__ == "__main__":
    unittest.main()
