#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Deterministic cover photo: original pixels only; no inpainting or generative redraw."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageOps

VERSION = "2.4.0"
LIMITS = {"brightness":(.90,1.10),"contrast":(.90,1.10),
          "saturation":(.88,1.12),"sharpness":(.88,1.12)}
DEFAULT_COLORS = {"brightness":1.025,"contrast":1.025,
                  "saturation":1.025,"sharpness":1.03}

def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def resolve(parent, name):
    p=Path(name)
    return p if p.is_absolute() else (parent/p).resolve()

def pair(x, title):
    if not isinstance(x,(list,tuple)) or len(x)!=2:
        raise ValueError(f"{title} 必须是包含两个数值的数组")
    a,b=map(float,x)
    if not 0<=a<=1 or not 0<=b<=1:
        raise ValueError(f"{title} 必须在 0~1 范围内")
    return a,b

def make_mask(size, data, parent):
    w,h=size
    if data.get("mode")=="alpha_file":
        p=resolve(parent,data["file"])
        with Image.open(p) as im: mask=im.convert("L")
        if mask.size!=size: raise ValueError("蒙版尺寸必须等于原图尺寸；不可自动拉伸")
        return mask, {"mode":"alpha_file","sha256":digest(p),"source":str(p)}
    if data.get("mode")!="ellipse":
        raise ValueError("mask.mode 必须为 ellipse 或 alpha_file")
    cx,cy=pair(data["center"],"mask.center")
    rx,ry=pair(data["radius"],"mask.radius")
    if rx<=0 or ry<=0 or cx-rx<0 or cy-ry<0 or cx+rx>1 or cy+ry>1:
        raise ValueError("主体标注超出原图范围，拒绝补画盘沿")
    feather=float(data.get("feather_px",1.25))
    if feather<0 or feather>3: raise ValueError("feather_px 允许 0~3")
    supersample=3
    m=Image.new("L",(w*supersample,h*supersample),0)
    ImageDraw.Draw(m).ellipse((round((cx-rx)*w*supersample),
                               round((cy-ry)*h*supersample),
                               round((cx+rx)*w*supersample),
                               round((cy+ry)*h*supersample)),fill=255)
    m=m.resize(size,Image.Resampling.LANCZOS)
    if feather: m=m.filter(ImageFilter.GaussianBlur(feather))
    return m, {"mode":"ellipse","warning":"椭圆只是近似，需人工检查真实盘沿和手的残留"}

def render(config):
    config=Path(config).resolve()
    data=json.loads(config.read_text(encoding="utf-8"))
    origin=resolve(config.parent,data["file"])
    if not origin.is_file(): raise FileNotFoundError(f"找不到原图: {origin}")
    sha=digest(origin)
    if data.get("approved_source_sha256") and data["approved_source_sha256"]!=sha:
        raise ValueError("原图已更换，旧的裁剪与蒙版参数不可复用")
    with Image.open(origin) as im:
        original=ImageOps.exif_transpose(im).convert("RGB")
    mask,mask_meta=make_mask(original.size,data["mask"],config.parent)
    bbox=mask.point(lambda x:255 if x>=128 else 0).getbbox()
    if not bbox: raise ValueError("蒙版无前景")
    left,top,right,bottom=bbox
    canvas=list(map(int,data.get("canvas",[1200,1600])))
    cw,ch=canvas
    if cw*4!=ch*3: raise ValueError("封面比例必须是 3:4")
    fraction=float(data.get("subject_width_fraction",.86))
    if not .65<=fraction<=.92: raise ValueError("主体宽度比例不合理")
    center=pair(data.get("subject_center_on_canvas",[.5,.5]),"subject_center_on_canvas")
    factor=min(cw*fraction/(right-left), ch*.92/(bottom-top))
    size=(max(1,round((right-left)*factor)),max(1,round((bottom-top)*factor)))
    x=round(cw*center[0]-size[0]/2)
    y=round(ch*center[1]-size[1]/2)
    if x<0 or y<0 or x+size[0]>cw or y+size[1]>ch:
        raise ValueError("主体超出画布，请校正中心/大小，不进行缺失补画")
    bg=data.get("background","#C8C8C3")
    if not isinstance(bg,str) or len(bg)!=7 or not bg.startswith("#"):
        raise ValueError("背景仅支持固定的 #RRGGBB 纯色")
    int(bg[1:],16)
    color={**DEFAULT_COLORS,**data.get("color",{})}
    if any(k not in LIMITS for k in color): raise ValueError("不支持的调色参数")
    for k,v in color.items():
        lo,hi=LIMITS[k]
        if not lo<=float(v)<=hi: raise ValueError(f"{k} 超出保真范围")
    fg=original.crop(bbox)
    for k,enh in (("brightness",ImageEnhance.Brightness),
                  ("contrast",ImageEnhance.Contrast),
                  ("saturation",ImageEnhance.Color),
                  ("sharpness",ImageEnhance.Sharpness)):
        fg=enh(fg).enhance(float(color[k]))
    fg=fg.convert("RGBA")
    fg.putalpha(mask.crop(bbox))
    fg=fg.resize(size,Image.Resampling.LANCZOS)
    output=Image.new("RGB",(cw,ch),bg)
    output.paste(fg,(x,y),fg.getchannel("A"))
    out=resolve(config.parent,data.get("output","output/封面图.png"))
    out.parent.mkdir(parents=True,exist_ok=True)
    output.save(out)
    qa={"version":VERSION,"status":"review_required",
        "source":str(origin),"source_sha256":sha,
        "source_size":list(original.size),"only_original_subject_pixels":True,
        "generative_redraw":False,"hand_removal_verified":False,
        "mask":mask_meta,"source_bbox_px":list(bbox),
        "subject_bbox_canvas_px":[x,y,x+size[0],y+size[1]],
        "canvas":canvas,"background":bg,"color":color,
        "note":"必须目视验证原图盘沿完整和手是否去净；遮挡处禁止补画。"}
    out.with_name(out.stem+"_QA.json").write_text(
        json.dumps(qa,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    return out,qa

def main():
    ap=argparse.ArgumentParser(description="真实原图美食封面：禁止 AI 重绘")
    ap.add_argument("--config",required=True)
    args=ap.parse_args()
    out,qa=render(args.config)
    print(f"{out}\nQA: {out.with_name(out.stem+'_QA.json')}\n{qa['status']}")

if __name__=="__main__":
    main()
