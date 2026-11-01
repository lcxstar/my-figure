"""Regression tests for cover photo mode. Generated test geometry, no private user photos."""
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from PIL import Image, ImageDraw

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from cover_photo import render

class CoverTests(unittest.TestCase):
    def test_repeatable_no_redraw_and_gray_background(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            photo=Image.new("RGB",(500,700),"#254466")
            draw=ImageDraw.Draw(photo)
            draw.ellipse((75,175,425,525),fill="#ECE9DF")
            draw.ellipse((160,260,340,440),fill="#A96737")
            photo.save(root/"source.png")
            cfg={
                "file":"source.png","output":"cover.png",
                "canvas":[1200,1600],"background":"#C8C8C3",
                "mask":{"mode":"ellipse","center":[.5,.5],"radius":[.35,.25],"feather_px":1},
                "subject_center_on_canvas":[.5,.5],"subject_width_fraction":.86,
                "color":{"brightness":1,"contrast":1,"saturation":1,"sharpness":1}
            }
            config=root/"config.json"
            config.write_text(json.dumps(cfg),encoding="utf-8")
            out,qa=render(config)
            h1=hashlib.sha256(out.read_bytes()).hexdigest()
            with Image.open(out) as result:
                self.assertEqual(result.size,(1200,1600))
                self.assertEqual(result.getpixel((0,0)),(200,200,195))
            out2,qa2=render(config)
            self.assertEqual(h1,hashlib.sha256(out2.read_bytes()).hexdigest())
            self.assertTrue(qa["only_original_subject_pixels"])
            self.assertFalse(qa["generative_redraw"])
            self.assertEqual(qa["status"],"review_required")
    def test_no_invalid_rim_reconstruction(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            Image.new("RGB",(50,50),"white").save(root/"source.png")
            cfg={"file":"source.png","mask":{"mode":"ellipse","center":[.95,.95],"radius":[.2,.2]}}
            config=root/"config.json"
            config.write_text(json.dumps(cfg),encoding="utf-8")
            with self.assertRaises(ValueError):render(config)

if __name__=="__main__":unittest.main()
