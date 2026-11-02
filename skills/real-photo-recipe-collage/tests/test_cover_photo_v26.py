"""v2.6: rim-first detection, no re-used center, arm ignored, synthetic tests only."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from PIL import Image, ImageDraw
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from cover_photo import detect_dish_rim, render

class RimFirst(unittest.TestCase):
    def make_photo(self,root):
        w,h=600,900
        im=Image.new("RGB",(w,h),(61,67,73))
        d=ImageDraw.Draw(im)
        # The hand and arm reach the plate from the bottom, but cannot locate plate.
        d.polygon([(240,630),(382,630),(300,900),(55,900)],fill=(195,128,98))
        d.ellipse((115,286,525,656),fill=(241,236,220))
        d.ellipse((190,378,450,570),fill=(187,108,42))
        d.ellipse((236,414,282,456),fill=(68,123,60))
        im.save(root/"food.png")
        return im

    def test_auto_ignores_hand_and_centers_rim(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            im=self.make_photo(root)
            ellipse,qa=detect_dish_rim(im)
            self.assertLess(abs(ellipse[0]-320),12)
            self.assertLess(abs(ellipse[1]-471),12)
            self.assertFalse(qa["hand_used_for_center"])
            cfg={"file":"food.png","output":"cover.png",
                 "mask":{"mode":"auto_plate","confidence_min":.72},
                 "canvas":[600,800],
                 "subject_width_fraction":.86,
                 "subject_center_on_canvas":[.5,.5],
                 "contact_shadow":.1}
            p=root/"cfg.json"
            p.write_text(json.dumps(cfg),encoding="utf-8")
            out,result=render(p)
            self.assertEqual(result["mask"]["mode"],"auto_plate")
            self.assertEqual(result["placement_basis"],"plate_bowl_outer_rim_mask_not_food_or_hand")
            self.assertLessEqual(max(abs(v) for v in result["center_error_px"]),1)
            self.assertTrue((root/"cover_QA_rim_preview.png").exists())
            self.assertFalse(result["hand_removal_verified"])
            self.assertEqual(result["status"],"review_required")
            with Image.open(out) as cover:
                self.assertEqual(cover.size,(600,800))

    def test_no_bowl_must_fail_instead_of_guess(self):
        with tempfile.TemporaryDirectory() as tmp:
            im=Image.new("RGB",(600,900),(80,80,80))
            with self.assertRaisesRegex(ValueError,"自动定位失败"):
                detect_dish_rim(im)

    def test_missing_edge_must_fail(self):
        with tempfile.TemporaryDirectory() as tmp:
            im=Image.new("RGB",(600,900),(70,70,70))
            ImageDraw.Draw(im).ellipse((-170,185,500,855),fill=(230,225,214))
            with self.assertRaises(ValueError):
                detect_dish_rim(im)

if __name__=="__main__":unittest.main()
