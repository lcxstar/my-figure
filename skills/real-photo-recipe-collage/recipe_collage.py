#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Real-photo recipe collage, v2.2 community edition.
No generative image editing. Pillow/OpenCV only.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageFont, ImageOps

VERSION = "2.2-community"
PRESETS = {
    "natural_appetizing_v2": dict(brightness=1.035, contrast=1.055,
                                 saturation=1.155, warmth=.004, sharpness=1.09),
    "neutral_documentary_v2": dict(brightness=1.025, contrast=1.035,
                                   saturation=1.065, warmth=0, sharpness=1.065),
}
COLORS = dict(background="#F6F5F0", green="#286B49", cream="#F8F8F0",
              ink="#214A36", yellow="#FFD455")

def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def font_file(provided=None):
    locations = [provided, "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
                 "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
                 "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
                 "C:/Windows/Fonts/msyhbd.ttc", "C:/Windows/Fonts/msyh.ttc",
                 "C:/Windows/Fonts/simhei.ttf"]
    for x in locations:
        if x and Path(x).is_file():
            return str(x)
    raise FileNotFoundError("请在配置 font_path 指定已安装的中文字体")

def read_image(path):
    with Image.open(path) as original:
        return ImageOps.exif_transpose(original).convert("RGB")

def detect_circle(im, kind="pot"):
    """Circle geometry is only a candidate, never a semantic ground truth."""
    w, h = im.size
    scale = min(1., 640. / w)
    small = im.resize((round(w * scale), round(h * scale)))
    gray = cv2.cvtColor(np.asarray(small), cv2.COLOR_RGB2GRAY)
    gray = cv2.GaussianBlur(gray, (7, 7), 1.8)
    sw, sh = gray.shape[1], gray.shape[0]
    rmin = round(sw * (.23 if kind == "plate" else .30))
    rmax = round(sw * .52)
    candidates = []
    for threshold in (48, 41, 34):
        hits = cv2.HoughCircles(gray, cv2.HOUGH_GRADIENT, dp=1.25,
                               minDist=.34 * sw, param1=135, param2=threshold,
                               minRadius=rmin, maxRadius=rmax)
        if hits is not None:
            for cx, cy, radius in hits[0]:
                score = float(radius / sw * 1.8
                              - abs(cx / sw - .5) * .9
                              - abs(cy / sh - .51) * .45 + threshold / 1000)
                candidates.append((score, cx, cy, radius))
        if candidates:
            break
    if not candidates:
        return dict(ok=False, source="auto_unverified", score=0.,
                    center=[.5, .52], radius_fraction=.42,
                    reason="未找到可靠锅盘圆，请手工校准")
    score, cx, cy, radius = max(candidates, key=lambda item: item[0])
    return dict(ok=bool(score >= .60 and radius / sw >= .34),
                source="auto_unverified", score=round(score, 4),
                center=[round(cx / sw, 6), round(cy / sh, 6)],
                radius_fraction=round(radius / sw, 6),
                reason="仅供目视校准")

def crop_original(im, circle, ratio, framing, target_y):
    w, h = im.size
    if not 1 < ratio < 1.6 or not .8 <= framing <= 1:
        raise ValueError("面板比例或裁剪放大系数不合理")
    if not .38 <= target_y <= .50:
        raise ValueError("subject_y_in_tile 必须在 0.38~0.50 内")
    cx = float(circle["center"][0]) * w
    cy = float(circle["center"][1]) * h
    radius = float(circle["radius_fraction"]) * w
    cw = min(2 * radius / framing, float(w), 2 * cx, 2 * (w - cx))
    ch = cw / ratio
    if ch > h:
        ch = float(h)
        cw = ch * ratio
    left = max(0., min(w - cw, cx - cw / 2))
    top = max(0., min(h - ch, cy - target_y * ch))
    rect = [round(left), round(top), round(left + cw), round(top + ch)]
    image = im.crop(tuple(rect))
    center_err_x = (cx - (rect[0] + rect[2]) / 2) / image.width
    center_y = (cy - rect[1]) / image.height
    return image, rect, dict(center_error_x=round(center_err_x, 5),
                             center_y=round(center_y, 5),
                             expected_center_y=target_y,
                             estimated_rim_width=round(2 * radius / image.width, 5),
                             source_crop_ratio=round(image.width / image.height, 6),
                             no_stretch=True)

def natural_grade(im, settings):
    ranges = {"brightness":(.92,1.12), "contrast":(.92,1.15),
              "saturation":(.90,1.25), "warmth":(-.03,.03),
              "sharpness":(1.,1.22)}
    for k,(low,high) in ranges.items():
        if not low <= float(settings[k]) <= high:
            raise ValueError("调色参数 {}={} 超出允许范围".format(k,settings[k]))
    im = ImageEnhance.Brightness(im).enhance(float(settings["brightness"]))
    im = ImageEnhance.Contrast(im).enhance(float(settings["contrast"]))
    im = ImageEnhance.Color(im).enhance(float(settings["saturation"]))
    warmth = float(settings["warmth"])
    if warmth:
        red, green, blue = im.split()
        red = red.point([min(255,round(v * (1 + warmth))) for v in range(256)])
        blue = blue.point([min(255,round(v * (1 - warmth))) for v in range(256)])
        im = Image.merge("RGB",(red,green,blue))
    return ImageEnhance.Sharpness(im).enhance(float(settings["sharpness"]))

def modify(cfg, args):
    for a,b in getattr(args,"swap",[]) or []:
        if not 1 <= a <= 6 or not 1 <= b <= 6:
            raise ValueError("交换序号必须是1~6")
        s,t = cfg["steps"][a-1],cfg["steps"][b-1]
        s["file"],t["file"]=t["file"],s["file"]
        for key in ("subject","framing","subject_y_in_tile","color_override",
                    "approved_source_sha256"):
            sv,tv=s.pop(key,None),t.pop(key,None)
            if tv is not None: s[key]=tv
            if sv is not None: t[key]=sv
    for pair in getattr(args,"set_label",[]) or []:
        n,sep,label=pair.partition("=")
        if not sep or not n.isdecimal() or not 1 <= int(n) <= 6:
            raise ValueError("标签格式应为3=文字")
        cfg["steps"][int(n)-1]["label"]=label
    for pair in getattr(args,"set_step_saturation",[]) or []:
        n,sep,sat=pair.partition("=")
        if not sep or not n.isdecimal() or not 1 <= int(n) <= 6:
            raise ValueError("饱和度格式应为3=1.03")
        cfg["steps"][int(n)-1].setdefault("color_override",{})["saturation"]=float(sat)
    return cfg

def generate(config, args):
    config=Path(config).resolve()
    cfg=modify(json.loads(config.read_text("utf-8")),args)
    steps=cfg["steps"]
    if len(steps) != 6:
        raise ValueError("只支持六张原片")
    files=[str(s["file"]) for s in steps]
    if len(set(files))!=6 and not cfg.get("allow_repeated_files",False):
        raise ValueError("发现重复源图，默认禁止")
    nums=[str(s.get("number","")).zfill(2) for s in steps]
    if nums != [str(i).zfill(2) for i in range(int(nums[0]),int(nums[0])+6)]:
        raise ValueError("步骤编号必须为连续两位数字")
    if getattr(args,"save_config",None):
        dst=Path(args.save_config).resolve()
        dst.parent.mkdir(parents=True,exist_ok=True)
        if dst.parent != config.parent:
            for s in steps:
                s["file"]=str((config.parent/s["file"]).resolve())
        dst.write_text(json.dumps(cfg,ensure_ascii=False,indent=2),"utf-8")
    ww,hh=int(cfg.get("width",1500)),int(cfg.get("height",2000))
    if ww*4!=hh*3: raise ValueError("整体比例必须为3:4")
    gap,margin=int(cfg.get("gap",10)),int(cfg.get("margin",5))
    pw=(ww-2*margin-gap)//2
    ph=(hh-2*margin-2*gap)//3
    if pw<100 or ph<100:raise ValueError("画布尺寸不足")
    fontpath=font_file(cfg.get("font_path"))
    fhash=digest(fontpath)
    if cfg.get("required_font_sha256") and cfg["required_font_sha256"]!=fhash:
        raise ValueError("字体SHA256不匹配")
    preset=cfg.get("preset","natural_appetizing_v2")
    if preset not in PRESETS: raise ValueError("未知预设")
    color=PRESETS[preset].copy()
    color.update(cfg.get("color_override",{}))
    if getattr(args,"saturation",None) is not None:
        color["saturation"]=args.saturation
    palette=COLORS.copy()
    palette.update(cfg.get("palette",{}))
    output=Image.new("RGB",(ww,hh),palette["background"])
    canvas=ImageDraw.Draw(output)
    sources=[]
    for s in steps:
        p=(config.parent/s["file"]).resolve()
        if not p.is_file():raise FileNotFoundError(p)
        im=read_image(p)
        auto=detect_circle(im,cfg.get("subject_type","pot"))
        if "subject" in s:
            sub=copy.deepcopy(s["subject"])
            correct_hash=s.get("approved_source_sha256")==digest(p)
            x,y=sub["center"]
            rad=sub["radius_fraction"]
            ok=(.07<=x<=.93 and .07<=y<=.93 and .20<=rad<=.52
                and sub.get("verified") is True and correct_hash)
            sub["ok"]=bool(ok)
            sub["source"]="manual_anchor_approved" if ok else "manual_anchor_review_required"
            sub["auto_candidate"]=auto
        else:
            sub=auto
        sources.append((p,im,s,sub))
    # One font size for all six, determined by the longest caption.
    fsize=round(pw*.069)
    while fsize>14:
        capfont=ImageFont.truetype(fontpath,fsize)
        if max(canvas.textbbox((0,0),str(s["label"]),font=capfont)[2] for s in steps) < pw*.75:
            break
        fsize-=1
    capfont=ImageFont.truetype(fontpath,fsize)
    numfont=ImageFont.truetype(fontpath,round(ph*.074))
    manifest=[]
    warnings=[]
    debug=[]
    for i,(p,im,s,sub) in enumerate(sources):
        x=margin+(i%2)*(pw+gap)
        y=margin+(i//2)*(ph+gap)
        target_y=float(s.get("subject_y_in_tile",cfg.get("subject_y_in_tile",.445)))
        crop,rect,geometry=crop_original(im,sub,pw/ph,
                   float(s.get("framing",cfg.get("framing",.975))),target_y)
        flags=[]
        if not sub.get("ok"): flags.append("SUBJECT_UNCONFIRMED")
        if sub["source"]=="auto_unverified":flags.append("AUTO_NEEDS_VISUAL_CONFIRMATION")
        if abs(geometry["center_error_x"])>.025:flags.append("CENTER_X_OUT_OF_TARGET")
        if abs(geometry["center_y"]-target_y)>.045:flags.append("CENTER_Y_OUT_OF_TARGET")
        if geometry["estimated_rim_width"]>1.035:flags.append("POSSIBLE_RIM_CROP")
        if flags:warnings.append({"step":nums[i],"flags":flags})
        local=color.copy()
        local.update(s.get("color_override",{}))
        tile=natural_grade(crop,local).resize((pw,ph),Image.Resampling.LANCZOS)
        mask=Image.new("L",(pw,ph),0)
        ImageDraw.Draw(mask).rounded_rectangle((0,0,pw-1,ph-1),radius=int(cfg.get("corner_radius",14)),fill=255)
        output.paste(tile,(x,y),mask)
        # Top-left numbered circle.
        nx=x+round(pw*.091)
        ny=y+round(ph*.090)
        nr=round(ph*.073)
        canvas.ellipse((nx-nr,ny-nr,nx+nr,ny+nr),fill=palette["green"],
                       outline="white",width=4)
        canvas.text((nx,ny+1),str(int(nums[i])),font=numfont,anchor="mm",fill="white")
        # The caption label has one fixed size and shared baseline.
        th=round(ph*.149)
        ty=y+ph-th-round(ph*.028)
        label=str(s["label"])
        textw=canvas.textbbox((0,0),label,font=capfont)[2]
        tw=round(max(pw*.53,min(pw*.84,textw+pw*.092)))
        tx=x+(pw-tw)//2
        canvas.rounded_rectangle((tx,ty,tx+tw,ty+th),radius=th//2,fill=palette["cream"])
        canvas.text((x+pw//2,ty+th//2+1),label,anchor="mm",font=capfont,fill=palette["ink"])
        if cfg.get("accent_rays",True):
            scale=pw/740.
            for side in (-1,1):
                base_x=(tx-14*scale) if side<0 else (tx+tw+14*scale)
                base_y=ty+th/2
                for (ax,ay),(bx,by) in (((2,-23),(17,-38)),((3,-4),(24,-8)),((2,18),(19,27))):
                    a=(round(base_x+side*ax*scale),round(base_y+ay*scale))
                    b=(round(base_x+side*bx*scale),round(base_y+by*scale))
                    canvas.line((a,b),fill=palette["yellow"],width=max(3,round(7*scale)))
        manifest.append(dict(step=nums[i],label=label,source=p.name,
                   source_sha256=digest(p),subject=sub,crop_px=rect,
                   geometry=geometry,caption_rect=[tx,ty,tx+tw,ty+th],
                   caption_font_px=fsize,color=local,flags=flags))
        if getattr(args,"debug",False):
            v=im.copy()
            dd=ImageDraw.Draw(v)
            cx=sub["center"][0]*im.width
            cy=sub["center"][1]*im.height
            rr=sub["radius_fraction"]*im.width
            dd.ellipse((cx-rr,cy-rr,cx+rr,cy+rr),outline="#12E14F",width=8)
            dd.rectangle(rect,outline="#FC3549",width=8)
            debug.append(v)
    out=(Path(args.output).resolve() if getattr(args,"output",None)
         else (config.parent/cfg.get("output","../output/recipe.png")).resolve())
    out.parent.mkdir(parents=True,exist_ok=True)
    if getattr(args,"make_calibration",False):
        new=copy.deepcopy(cfg)
        for s,(_,_,_,sub) in zip(new["steps"],sources):
            s["subject"]=dict(center=sub["center"],
                              radius_fraction=sub["radius_fraction"],verified=False)
        config.with_name(config.stem+"_待确认定位.json").write_text(
            json.dumps(new,ensure_ascii=False,indent=2),"utf-8")
    if getattr(args,"strict",False) and warnings:
        raise RuntimeError("仍有未校准照片，请先人工检查预览")
    output.save(out,format="PNG",optimize=True)
    if debug:
        # One overview showing crop rectangle and detected circle for each original.
        preview=Image.new("RGB",(3*340,2*500),"#EFEFEF")
        for j,v in enumerate(debug):
            v.thumbnail((340,470))
            preview.paste(v,((j%3)*340+(340-v.width)//2,(j//3)*500))
        preview.save(out.with_name(out.stem+"_校准预览.jpg"),quality=90)
    qa=dict(version=VERSION,status="review_required" if warnings else "pass",
            no_ai_generation=True,no_geometric_warp=True,only_user_originals=True,
            canvas=[ww,hh],panel=[pw,ph],font=fontpath,font_sha256=fhash,
            output_sha256=digest(out),warnings=warnings,steps=manifest)
    qa_file=out.with_name(out.stem+"_QA.json")
    qa_file.write_text(json.dumps(qa,ensure_ascii=False,indent=2),"utf-8")
    print("成品:",out)
    print("校验:",qa_file,qa["status"])
    return out,qa

def main():
    parser=argparse.ArgumentParser(description="真实照片菜谱六联图 v2.2")
    parser.add_argument("--config",required=True)
    parser.add_argument("--output")
    parser.add_argument("--saturation",type=float)
    parser.add_argument("--swap",action="append",nargs=2,type=int)
    parser.add_argument("--set-label",action="append")
    parser.add_argument("--set-step-saturation",action="append")
    parser.add_argument("--save-config")
    parser.add_argument("--make-calibration",action="store_true")
    parser.add_argument("--debug",action="store_true")
    parser.add_argument("--strict",action="store_true")
    args=parser.parse_args()
    generate(args.config,args)

if __name__=="__main__":
    main()
