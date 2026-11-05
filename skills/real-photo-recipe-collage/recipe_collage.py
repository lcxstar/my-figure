#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Real-photo recipe collage, v3.0 font-locked.
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

VERSION = "3.4-source-locked-color-first"
PRESETS = {
    "natural_appetizing_v2": dict(brightness=1.035, contrast=1.055,
                                 saturation=1.155, warmth=.004, sharpness=1.09),
    "neutral_documentary_v2": dict(brightness=1.025, contrast=1.035,
                                   saturation=1.065, warmth=0, sharpness=1.065),
    # v3: appetizing yet restrained; applies only to original PHOTOS before typography.
    "natural_appetizing_v3": dict(brightness=1.040, contrast=1.080,
                                 saturation=1.165, warmth=.007, sharpness=1.095),
    # Natural but richer food colors. Not AI; strictly applied to photo pixels before drawing text.
    "natural_appetizing_v4": dict(brightness=1.045, contrast=1.090,
                                 saturation=1.210, warmth=.010, sharpness=1.100),
}
COLORS = dict(background="#F6F5F0", green="#286B49", cream="#F8F8F0",
              ink="#214A36", yellow="#FFD455")

def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

REQUIRED_FONT_FAMILY = "Noto Sans CJK SC"
REQUIRED_FONT_WEIGHT = "Bold"
CAPTION_FONT_PX = 51
NUMBER_FONT_PX = 49


def font_file(provided=None):
    """Select the precise SC Bold face by embedded metadata, no substitution."""
    defaults = [
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
        "C:/Windows/Fonts/NotoSansCJK-Bold.ttc",
        "/Library/Fonts/NotoSansCJK-Bold.ttc",
        "/usr/local/share/fonts/NotoSansCJK-Bold.ttc",
    ]
    locations = [provided] if provided else defaults
    for location in locations:
        if not location:
            continue
        p = Path(location)
        if not p.is_file():
            continue
        collection = p.suffix.lower() in (".ttc", ".otc")
        for index in range(20 if collection else 1):
            try:
                face = ImageFont.truetype(str(p), 20, index=index)
                family, weight = face.getname()
            except OSError:
                break
            if (family, weight) == (REQUIRED_FONT_FAMILY, REQUIRED_FONT_WEIGHT):
                return str(p), index
    if provided:
        raise ValueError(
            "font_path 不是 Noto Sans CJK SC Bold 简体中文粗体，"
            "或字体文件不存在；禁止退回其他字体。"
        )
    raise FileNotFoundError(
        "缺少 Noto Sans CJK SC Bold 简体中文粗体。请合法安装 "
        "NotoSansCJK-Bold.ttc 并在 config.json 中配置 font_path；"
        "不会自动替换其他字体。"
    )

def read_image(path):
    with Image.open(path) as original:
        return ImageOps.exif_transpose(original).convert("RGB")


def detect_circle(im, kind="auto"):
    """Auto-search observed outer rims by radial image contrast, not Hough alone."""
    w, h = im.size
    sw = min(640, w)
    sh = max(1, round(h * sw / w))
    photo = np.asarray(im.resize((sw, sh)))
    gray = cv2.cvtColor(photo, cv2.COLOR_RGB2GRAY)
    gray = cv2.GaussianBlur(gray, (5, 5), 2.1)
    theta = np.linspace(0, 2 * np.pi, 120, endpoint=False)
    cs, ss = np.cos(theta), np.sin(theta)
    centers_x = np.arange(.36, .671, .025)
    centers_y = np.arange(.35, .731, .025)
    radii = np.arange(.27, .531, .016)
    aspect = np.arange(.79, 1.021, .06)
    grid = np.stack(np.meshgrid(centers_x, centers_y, radii,
                                aspect, indexing="ij"), axis=-1).reshape(-1, 4)
    cx = grid[:, 0] * sw
    cy = grid[:, 1] * sh
    rx = grid[:, 2] * sw
    ry = grid[:, 3] * rx
    scores = np.zeros(len(grid), dtype=float)
    batch_size = 1000
    for i in range(0, len(grid), batch_size):
        sl = slice(i, min(i + batch_size, len(grid)))
        xi = np.rint(cx[sl, None] + (rx[sl, None] - 8) * cs).astype(int)
        yi = np.rint(cy[sl, None] + (ry[sl, None] - 8) * ss).astype(int)
        xo = np.rint(cx[sl, None] + (rx[sl, None] + 8) * cs).astype(int)
        yo = np.rint(cy[sl, None] + (ry[sl, None] + 8) * ss).astype(int)
        valid = ((xi >= 0) & (xi < sw) & (xo >= 0) & (xo < sw)
                 & (yi >= 0) & (yi < sh) & (yo >= 0) & (yo < sh))
        xi = np.clip(xi, 0, sw - 1)
        xo = np.clip(xo, 0, sw - 1)
        yi = np.clip(yi, 0, sh - 1)
        yo = np.clip(yo, 0, sh - 1)
        diff = np.abs(gray[yi, xi].astype(float)
                      - gray[yo, xo].astype(float))
        diff[~valid] = 0
        strength = np.minimum(diff, 75) / 75
        support = diff > 22
        sectors = support.reshape(-1, 12, 10).any(axis=2).mean(axis=1)
        scores[sl] = (.63 * strength.mean(axis=1)
                      + .25 * support.mean(axis=1) + .12 * sectors)
        scores[sl] -= .5 * (1 - valid.mean(axis=1))
    scores += (.04 * np.minimum(1., grid[:, 2] / .42)
               - .08 * np.hypot(grid[:, 0] - .50, grid[:, 1] - .52))
    top = int(np.argmax(scores))
    # A bright food/rim interior may look stronger than the real outer rim.
    # When a comparably supported, larger ellipse is nearby, prefer its edge.
    larger = np.where(
        (scores >= scores[top] - .11)
        & (grid[:, 2] > grid[top, 2] + .045)
        & (grid[:, 2] <= .49)
        & (np.abs(grid[:, 0] - grid[top, 0]) < .09)
        & (np.abs(grid[:, 1] - grid[top, 1]) < .09)
    )[0]
    if len(larger):
        top = int(larger[np.argmax(scores[larger])])
    score = float(scores[top])
    x, y, radius, ellipse_aspect = (float(v) for v in grid[top])
    return dict(
        ok=score >= .55, source="auto_radial_outer_rim",
        score=round(score, 4), candidate_count=len(grid),
        center=[round(x, 6), round(y, 6)],
        radius_fraction=round(radius, 6),
        ellipse_aspect_yx=round(ellipse_aspect, 4),
        reason="原图边缘的多尺度椭圆搜索；未经人工逐格复核"
    )


def crop_original(im, circle, ratio, framing, target_y):
    w,h=im.size
    if not 1<ratio<1.6 or not .8<=framing<=1:
        raise ValueError("面板比例或裁剪放大系数不合理")
    if not .38<=target_y<=.52:
        raise ValueError("subject_y_in_tile 必须在0.38~0.52")
    cx=float(circle["center"][0])*w
    cy=float(circle["center"][1])*h
    r=float(circle["radius_fraction"])*w
    # Keep the round rim: its max complete horizontal fill is 1/ratio.
    cw=min(max(2*r/framing,2*r*ratio*1.025),float(w),float(h)*ratio)
    ch=cw/ratio
    left=max(0.,min(w-cw,cx-cw/2))
    top=max(0.,min(h-ch,cy-target_y*ch))
    if 2*r<=ch:
        lo=max(0.,cy+r-ch)
        hi=min(h-ch,cy-r)
        if lo<=hi:top=max(lo,min(hi,top))
    rect=[round(left),round(top),round(left+cw),round(top+ch)]
    crop=im.crop(tuple(rect))
    err_x=(cx-(rect[0]+rect[2])/2)/crop.width
    pos_y=(cy-rect[1])/crop.height
    rim_cut=max(0.,(rect[0]-cx+r)/(2*r), (cx+r-rect[2])/(2*r),
                (rect[1]-cy+r)/(2*r),(cy+r-rect[3])/(2*r))
    return crop,rect,dict(center_error_x=round(err_x,5),
         center_y=round(pos_y,5),expected_center_y=target_y,
         estimated_rim_width=round(2*r/crop.width,5),
         estimated_rim_cut_fraction=round(rim_cut,5),
         source_crop_ratio=round(crop.width/crop.height,6),
         no_stretch=True)

def natural_grade(im, settings):
    ranges = {"brightness":(.92,1.12), "contrast":(.92,1.15),
              "saturation":(.90,1.32), "warmth":(-.03,.03),
              "sharpness":(1.,1.22)}
    if set(settings) != set(ranges):
        raise ValueError("调色字段必须恰好为 " + ", ".join(ranges))
    for k,(low,high) in ranges.items():
        value=float(settings[k])
        if not np.isfinite(value) or not low <= value <= high:
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


def validate_source_mapping(config, steps, parent):
    """Bind every user-assigned cooking step to an unambiguous original file and optional SHA256."""
    if len(steps) != 6:
        raise ValueError("六联图必须提供六张真实步骤照片")
    require_hash=bool(config.get("require_source_sha256",False))
    seen=set()
    sources=[]
    for i,step in enumerate(steps,1):
        number=str(step.get("number","")).zfill(2)
        if number!=f"{i:02d}":
            raise ValueError(f"第{i}格编号应为 {i:02d}，当前为 {number}；请先确认步骤顺序")
        label=str(step.get("label","")).strip()
        if not label:
            raise ValueError(f"第{i}格缺少标签文字")
        path=(parent/str(step["file"])).resolve()
        if path in seen:
            raise ValueError(f"第{i}格源图重复：{path}；六联图不得复制同一张照片")
        if not path.is_file():
            raise FileNotFoundError(path)
        seen.add(path)
        actual_sha=digest(path)
        expected=step.get("expected_source_sha256")
        if require_hash and not expected:
            raise ValueError(f"第{i}格缺少 expected_source_sha256；先运行 --lock-inputs 生成锁定配置")
        if expected and (len(str(expected))!=64 or str(expected).lower()!=actual_sha):
            raise ValueError(f"第{i}格照片与记录的 SHA256 不匹配，请检查是否选错或更换了原图：{path.name}")
        sources.append(dict(number=number,label=label,file=path,
                            role=str(step.get("role","")).strip(),
                            sha256=actual_sha))
    return sources


def write_locked_config(config_path, output_path=None):
    """Hash the explicitly selected six photos without changing their order or captions."""
    config_path=Path(config_path).resolve()
    data=json.loads(config_path.read_text(encoding="utf-8"))
    steps=data["steps"]
    # Validate original paths before locking, but do not require pre-existing hashes.
    verify=dict(data,require_source_sha256=False)
    source_info=validate_source_mapping(verify,steps,config_path.parent)
    for step,source in zip(steps,source_info):
        step["expected_source_sha256"]=source["sha256"]
    data["require_source_sha256"]=True
    out=(Path(output_path).resolve() if output_path else
         config_path.with_name(config_path.stem+"_locked.json"))
    if out==config_path:
        raise ValueError("锁定配置不能覆盖输入配置，请另存为新文件")
    out.parent.mkdir(parents=True,exist_ok=True)
    # Paths in an external directory must be made absolute to stay valid.
    if out.parent!=config_path.parent:
        for step,source in zip(steps,source_info):
            step["file"]=str(source["file"])
    out.write_text(json.dumps(data,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    return out

def modify(cfg, args):
    for a,b in getattr(args,"swap",[]) or []:
        if not 1 <= a <= 6 or not 1 <= b <= 6:
            raise ValueError("交换序号必须是1~6")
        s,t = cfg["steps"][a-1],cfg["steps"][b-1]
        s["file"],t["file"]=t["file"],s["file"]
        for key in ("subject","framing","subject_y_in_tile","color_override",
                    "approved_source_sha256","expected_source_sha256","role"):
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
    source_mapping=validate_source_mapping(cfg,steps,config.parent)
    nums=[s["number"] for s in source_mapping]
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
    if cfg.get("font_family",REQUIRED_FONT_FAMILY)!=REQUIRED_FONT_FAMILY:
        raise ValueError("六联图字体必须为 Noto Sans CJK SC")
    if cfg.get("font_weight",REQUIRED_FONT_WEIGHT)!=REQUIRED_FONT_WEIGHT:
        raise ValueError("六联图字重必须为 Bold")
    if int(cfg.get("font_size_px",CAPTION_FONT_PX))!=CAPTION_FONT_PX:
        raise ValueError("六联图步骤标签字号固定为 51px，禁止逐次缩放")
    if int(cfg.get("number_font_size_px",NUMBER_FONT_PX))!=NUMBER_FONT_PX:
        raise ValueError("六联图编号字号固定为 49px")
    fontpath,fontindex=font_file(cfg.get("font_path"))
    fhash=digest(fontpath)
    if cfg.get("required_font_sha256") and cfg["required_font_sha256"]!=fhash:
        raise ValueError("字体SHA256不匹配")
    preset=cfg.get("preset","natural_appetizing_v4")
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
    for s,source in zip(steps,source_mapping):
        p=source["file"]
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
    # Color is applied to cropped original photos, and all labels/numbers are drawn only afterwards.
    # Do not run generative editing or color filters over the already labeled collage.
    # One exact font and size for all six. Never silently resize labels.
    fsize=CAPTION_FONT_PX
    capfont=ImageFont.truetype(fontpath,fsize,index=fontindex)
    numfont=ImageFont.truetype(fontpath,NUMBER_FONT_PX,index=fontindex)
    if capfont.getname()!=(REQUIRED_FONT_FAMILY,REQUIRED_FONT_WEIGHT):
        raise RuntimeError("步骤文字字体身份校验失败")
    if numfont.getname()!=(REQUIRED_FONT_FAMILY,REQUIRED_FONT_WEIGHT):
        raise RuntimeError("数字字体身份校验失败")
    max_label_width=int(pw*.84-pw*.092)
    for s in steps:
        label=str(s["label"])
        bounds=canvas.textbbox((0,0),label,font=capfont)
        if bounds[2]-bounds[0]>max_label_width:
            raise ValueError(
                f"步骤 {s['number']} 的文字过长：{label!r}；"
                "请缩短文案，不能自动减小字号或换字体。"
            )
    manifest=[]
    warnings=[]
    debug=[]
    for i,(p,im,s,sub) in enumerate(sources):
        x=margin+(i%2)*(pw+gap)
        y=margin+(i//2)*(ph+gap)
        target_y=float(s.get("subject_y_in_tile",cfg.get("subject_y_in_tile",.48)))
        crop,rect,geometry=crop_original(im,sub,pw/ph,
                   float(s.get("framing",cfg.get("framing",.975))),target_y)
        flags=[]
        if not sub.get("ok"): flags.append("SUBJECT_UNCONFIRMED")
        if sub["source"]=="auto_radial_outer_rim" and not sub.get("ok"):flags.append("LOW_RIM_CONFIDENCE")
        if abs(geometry["center_error_x"])>.025:flags.append("CENTER_X_OUT_OF_TARGET")
        if abs(geometry["center_y"]-target_y)>.045:flags.append("CENTER_Y_OUT_OF_TARGET")
        if geometry["estimated_rim_cut_fraction"]>.015:flags.append("POSSIBLE_RIM_CROP")
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
        bounds=canvas.textbbox((0,0),label,font=capfont)
        textw=bounds[2]-bounds[0]
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
        manifest.append(dict(step=nums[i],label=label,role=source_mapping[i]["role"],
                   source=p.name,source_sha256=source_mapping[i]["sha256"],
                   subject=sub,crop_px=rect,
                   geometry=geometry,caption_rect=[tx,ty,tx+tw,ty+th],
                   caption_font_px=fsize,number_font_px=NUMBER_FONT_PX,
                   font_family=REQUIRED_FONT_FAMILY,font_weight=REQUIRED_FONT_WEIGHT,
                   font_collection_index=fontindex,color=local,flags=flags))
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
    qa=dict(version=VERSION,color_applied_before_typography=True,
            typography_drawn_after_photo_grading=True,
            source_file_uniqueness_checked=True,
            source_hash_lock_enabled=bool(cfg.get("require_source_sha256",False)),
            source_hashes_checked=bool(cfg.get("require_source_sha256",False)),
            cooking_step_semantics_verified=False,  # requires human inspection

            preset=preset,status="auto_warning" if warnings else "auto_complete",
            no_ai_generation=True,no_geometric_warp=True,only_user_originals=True,
            canvas=[ww,hh],panel=[pw,ph],font=fontpath,font_sha256=fhash,
            font_family=REQUIRED_FONT_FAMILY,font_weight=REQUIRED_FONT_WEIGHT,
            font_collection_index=fontindex,caption_font_px=fsize,
            number_font_px=NUMBER_FONT_PX,
            output_sha256=digest(out),warnings=warnings,steps=manifest)
    # Always write a reproducible local QA JSON, while showing only the final collage by default.
    # Annotated previews remain opt-in, not user checkpoints.
    qa_file=out.with_name(out.stem+"_QA.json")
    qa_file.write_text(json.dumps(qa,ensure_ascii=False,indent=2),"utf-8")
    if getattr(args,"debug",False) or getattr(args,"save_qa",False):
        print("校验:",qa_file,qa["status"])
    print("成品:",out)
    return out,qa

def main():
    parser=argparse.ArgumentParser(description="真实照片菜谱六联图 v3.4 先调色后上字＋原图校验")
    parser.add_argument("--config")
    parser.add_argument("--output")
    parser.add_argument("--saturation",type=float)
    parser.add_argument("--swap",action="append",nargs=2,type=int)
    parser.add_argument("--set-label",action="append")
    parser.add_argument("--set-step-saturation",action="append")
    parser.add_argument("--save-config")
    parser.add_argument("--make-calibration",action="store_true")
    parser.add_argument("--debug",action="store_true")
    parser.add_argument("--save-qa",action="store_true")
    parser.add_argument("--strict",action="store_true")
    parser.add_argument("--lock-inputs",action="store_true",
                        help="校验六张照片顺序并写出含 SHA256 的锁定配置，不制作图")
    parser.add_argument("--lock-output",help="--lock-inputs 的输出路径")
    parser.add_argument("--check-font",action="store_true",
                        help="不需要六张照片，检查字体族、字重、TTC索引和锁定字号")
    args=parser.parse_args()
    if args.check_font:
        cfg={}
        if args.config:
            cfg=json.loads(Path(args.config).read_text("utf-8"))
        path,index=font_file(cfg.get("font_path"))
        face=ImageFont.truetype(path,CAPTION_FONT_PX,index=index)
        print(json.dumps(dict(
            font_family=face.getname()[0],font_weight=face.getname()[1],
            font_path=path,font_collection_index=index,
            font_sha256=digest(path),caption_font_px=CAPTION_FONT_PX,
            number_font_px=NUMBER_FONT_PX,verified=face.getname()==(
                REQUIRED_FONT_FAMILY,REQUIRED_FONT_WEIGHT)
        ),ensure_ascii=False,indent=2))
        return
    if not args.config:
        parser.error("制作六联图需要 --config；仅检查字体可使用 --check-font")
    if args.lock_inputs:
        print("已锁定六张原图:",write_locked_config(args.config,args.lock_output))
        return
    generate(args.config,args)

if __name__=="__main__":
    main()
