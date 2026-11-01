"""Synthetic fixtures, no private recipe photos."""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from recipe_collage import generate, digest
from PIL import Image,ImageDraw

def make_fixture(root):
    photos=root/"originals"
    photos.mkdir()
    steps=[]
    for i in range(6):
        im=Image.new("RGB",(960,1280),"#C7B9A6")
        d=ImageDraw.Draw(im)
        cx=480+(-12 if i%2 else 12)
        cy=615+i*9
        radius=390
        d.ellipse((cx-radius,cy-radius,cx+radius,cy+radius),
                  fill="#202427",outline="#08090B",width=16)
        d.ellipse((cx-260,cy-260,cx+260,cy+260),
                  fill=("#AB8B58","#899664","#B57E4E")[i%3])
        p=photos/("%02d.png"%(i+1))
        im.save(p)
        steps.append(dict(file="originals/"+p.name,
                          number="%02d"%(i+1),label="步骤%d"%(i+1),
                          subject=dict(center=[cx/960,cy/1280],
                                       radius_fraction=radius/960,
                                       verified=True),
                          approved_source_sha256=digest(p)))
    cfg=dict(recipe="合成几何测试图",preset="neutral_documentary_v2",
             subject_type="pot",width=1500,height=2000,margin=5,
             gap=10,framing=.975,output="out.png",steps=steps)
    conf=root/"config.json"
    conf.write_text(json.dumps(cfg,ensure_ascii=False,indent=2),"utf-8")
    return conf

def args(**kw):
    defaults=dict(output=None,saturation=None,swap=None,set_label=None,
                  set_step_saturation=None,save_config=None,
                  debug=False,strict=False,make_calibration=False)
    defaults.update(kw)
    return SimpleNamespace(**defaults)

class Smoke(unittest.TestCase):
    def test_repeatable_original_crop_and_layout(self):
        with tempfile.TemporaryDirectory() as td:
            config=make_fixture(Path(td))
            p,q=generate(config,args())
            first=hashlib.sha256(p.read_bytes()).hexdigest()
            p,q=generate(config,args())
            self.assertEqual(hashlib.sha256(p.read_bytes()).hexdigest(),first)
            with Image.open(p) as im:
                self.assertEqual(im.size,(1500,2000))
            self.assertEqual(len(q["steps"]),6)
            self.assertEqual(len({x["source_sha256"] for x in q["steps"]}),6)
            self.assertTrue(all(abs(x["geometry"]["center_error_x"])<.025 for x in q["steps"]))
            self.assertTrue(q["no_ai_generation"])
    def test_swap_relabel_and_one_tile_saturation(self):
        with tempfile.TemporaryDirectory() as td:
            config=make_fixture(Path(td))
            before=config.read_bytes()
            p,q=generate(config,args(swap=[(2,3)],
                 set_label=["4=改成新说明"],
                 set_step_saturation=["2=1.04"]))
            self.assertEqual(q["steps"][3]["label"],"改成新说明")
            self.assertEqual(q["steps"][1]["color"]["saturation"],1.04)
            self.assertEqual(config.read_bytes(),before)
    def test_duplicate_step_photo_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            config=make_fixture(Path(td))
            cfg=json.loads(config.read_text("utf-8"))
            cfg["steps"][1]["file"]=cfg["steps"][0]["file"]
            config.write_text(json.dumps(cfg,ensure_ascii=False),"utf-8")
            with self.assertRaises(ValueError):
                generate(config,args())

if __name__=="__main__":
    unittest.main()
