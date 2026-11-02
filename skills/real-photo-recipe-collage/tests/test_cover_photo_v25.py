"""v2.5 cover regression tests: synthetic plate only, no user food photos."""
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from PIL import Image, ImageDraw

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from cover_photo import render

class TestCoverV25(unittest.TestCase):
    def make_case(self, root):
        img=Image.new("RGB",(600,900),"#32455F")
        d=ImageDraw.Draw(img)
        d.ellipse((120,275,540,625),fill="#F3F1E7")
        d.ellipse((240,390,420,540),fill="#AA7039")
        img.save(root/"source.png")
        return {"file":"source.png","output":"cover.png","canvas":[600,800],
            "mask":{"mode":"ellipse","center":[.55,.5],
                    "radius":[.35,175/900],"feather_px":1},
            "subject_center_on_canvas":[.5,.5],"subject_width_fraction":.86,
            "background":{"mode":"linen_botanical","base_color":"#D0D0CB",
                          "texture_strength":1.0,"pattern_opacity":.18},
            "color":{"brightness":1.035,"contrast":1.035,
                     "saturation":1.045,"sharpness":1.035}}

    def test_reproducible_linen_and_center(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            cfg=self.make_case(root)
            path=root/"config.json"
            path.write_text(json.dumps(cfg),encoding="utf-8")
            result,report=render(path)
            first_hash=hashlib.sha256(result.read_bytes()).hexdigest()
            with Image.open(result) as im:
                self.assertEqual(im.size,(600,800))
            self.assertEqual(report["background"]["mode"],"linen_botanical")
            self.assertLessEqual(max(map(abs,report["center_error_px"])),1)
            self.assertFalse(report["generative_redraw"])
            self.assertEqual(report["status"],"review_required")
            result2,_=render(path)
            self.assertEqual(first_hash,hashlib.sha256(result2.read_bytes()).hexdigest())

    def test_real_fabric_photo_is_supported(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            cfg=self.make_case(root)
            Image.new("RGB",(750,410),"#CBC7C5").save(root/"cloth.png")
            cfg["background"]={"mode":"image","file":"cloth.png"}
            path=root/"config.json"
            path.write_text(json.dumps(cfg),encoding="utf-8")
            _,report=render(path)
            self.assertEqual(report["background"]["mode"],"image")
            self.assertTrue(report["background"]["sha256"])

    def test_reject_cross_photo_masks(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            cfg=self.make_case(root)
            cfg["approved_source_sha256"]="0"*64
            path=root/"config.json"
            path.write_text(json.dumps(cfg),encoding="utf-8")
            with self.assertRaises(ValueError):
                render(path)

if __name__=="__main__":
    unittest.main()
