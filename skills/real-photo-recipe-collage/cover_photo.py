#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Deterministic cover photo: original pixels only; no inpainting or generative redraw."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageOps
import cv2
import math

VERSION = "2.6.0"
LIMITS = {"brightness":(.90,1.10),"contrast":(.90,1.10),
          "saturation":(.88,1.12),"sharpness":(.88,1.12)}
DEFAULT_COLORS = {"brightness":1.035,"contrast":1.035,
                  "saturation":1.045,"sharpness":1.035}
DEFAULT_BACKGROUND = {"mode":"linen_botanical","base_color":"#D0D0CB",
                      "texture_strength":1.0,"pattern_opacity":0.18}

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


def _ellipse_mask(size, ellipse, feather):
    """Use the actual rim ellipse. Crop geometry never includes the arm in centering."""
    w,h=size
    cx,cy,rx,ry,angle=map(float,ellipse)
    if not (0<rx and 0<ry and cx-rx>=-max(rx,ry)*.15 and
            cy-ry>=-max(rx,ry)*.15):
        raise ValueError("检测到的碗盘几何不合理")
    scale=2
    pts=[]
    phi=math.radians(angle)
    for k in range(360):
        theta=math.radians(k)
        u,v=rx*math.cos(theta),ry*math.sin(theta)
        px=cx+u*math.cos(phi)-v*math.sin(phi)
        py=cy+u*math.sin(phi)+v*math.cos(phi)
        pts.append((round(px*scale),round(py*scale)))
    if min(x for x,_ in pts)<0 or max(x for x,_ in pts)>=w*scale or min(y for _,y in pts)<0 or max(y for _,y in pts)>=h*scale:
        raise ValueError("碗盘外沿超出照片边缘，需要人工轮廓蒙版")
    mask=Image.new("L",(w*scale,h*scale),0)
    ImageDraw.Draw(mask).polygon(pts,fill=255)
    mask=mask.resize((w,h),Image.Resampling.LANCZOS)
    if feather:
        mask=mask.filter(ImageFilter.GaussianBlur(feather))
    return mask

def detect_dish_rim(original, confidence_min=0.72):
    """Detect external white plate/bowl rim; never use food saliency or hand centroid.
    Conservative detector: ambiguous objects are rejected, not silently re-centered.
    """
    if not (0.45<=confidence_min<=0.95):
        raise ValueError("confidence_min 范围为 0.45-0.95")
    w,h=original.size
    scale=min(1.,950/max(w,h))
    sw,sh=max(60,int(round(w*scale))),max(60,int(round(h*scale)))
    rgb=np.asarray(original.resize((sw,sh),Image.Resampling.LANCZOS))
    hsv=cv2.cvtColor(rgb,cv2.COLOR_RGB2HSV)
    # Plate and bowl are generally light neutral/white; hand is usually chromatic.
    bright=cv2.inRange(hsv,np.array([0,0,155],dtype=np.uint8),
                             np.array([179,80,255],dtype=np.uint8))
    bright=cv2.morphologyEx(bright,cv2.MORPH_CLOSE,
                           cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(9,9)))
    contours,_=cv2.findContours(bright,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
    found=[]
    for c in contours:
        if len(c)<5: continue
        area=cv2.contourArea(c)
        if area<sw*sh*.095: continue
        x,y,cw,ch=cv2.boundingRect(c)
        if cw<sw*.43 or cw>sw*.995 or ch<sh*.26 or ch>sh*.90:continue
        if min(x,y)<3 or x+cw>sw-3 or y+ch>sh-3:continue
        (cx,cy),(major,minor),angle=cv2.fitEllipse(c)
        # cv2.fitEllipse always returns the center and two orthogonal diameters.
        rx,ry=major/2,minor/2
        if not (.20*sw<cx<.80*sw and .19*sh<cy<.84*sh):continue
        if min(rx,ry)<sw*.13:continue
        shape_ratio=max(rx,ry)/min(rx,ry)
        if shape_ratio>1.95:continue
        ellipse_area=math.pi*rx*ry
        fill_ratio=area/max(1,ellipse_area)
        if not .70<=fill_ratio<=1.22:continue
        boundary=c.reshape(-1,2).astype(float)
        # Ellipse fit quality (normalized implicit ellipse-distance residual).
        p=math.radians(angle)
        dx,dy=boundary[:,0]-cx,boundary[:,1]-cy
        u=dx*math.cos(p)+dy*math.sin(p)
        v=-dx*math.sin(p)+dy*math.cos(p)
        radial=np.sqrt((u/max(rx,1))**2+(v/max(ry,1))**2)
        residual=float(np.quantile(np.abs(radial-1),.75))
        contour_fit=max(0.,1.-residual/.14)
        central=max(0.,1.-abs(cx/sw-.5)-abs(cy/sh-.5))
        strength=min(1.,(cw/sw)/.75)
        quality=.66*contour_fit+.20*min(1.,fill_ratio)+.09*strength+.05*central
        found.append((quality,(cx,cy,rx,ry,angle),area,contour_fit))
    if not found:
        raise ValueError("自动定位失败：无法可靠识别完整白色盘/碗外沿；请使用人工确认的 alpha_file 蒙版，不得套用旧图中心")
    quality,ellipse,area,fit=max(found,key=lambda t:t[0])
    if quality<confidence_min:
        raise ValueError(f"碗盘轮廓检测置信度不足（{quality:.3f}），需要人工蒙版或校准，禁止自动输出错误居中图")
    center_x,center_y,rad_x,rad_y,angle=ellipse
    geometry=[center_x/scale,center_y/scale,rad_x/scale,rad_y/scale,angle]
    return geometry,{"method":"white_rim_external_contour_fitEllipse",
                     "confidence":round(quality,4),
                     "fit_quality":round(fit,4),
                     "center_source_px":[round(geometry[0],2),round(geometry[1],2)],
                     "ellipse_source_px":[round(v,2) for v in geometry],
                     "hand_used_for_center":False,
                     "warning":"仅适用外沿明亮、轮廓完整的盘/碗；输出必须目视确认，不能保证无损去手"}

def make_mask(size, data, parent, original=None):
    w,h=size
    if data.get("mode")=="auto_plate":
        if original is None: raise ValueError("auto_plate 需要真实原片输入")
        ellipse,meta=detect_dish_rim(original,float(data.get("confidence_min",.72)))
        mask=_ellipse_mask(size,ellipse,float(data.get("feather_px",1.0)))
        return mask, {"mode":"auto_plate",**meta}
    if data.get("mode")=="alpha_file":
        p=resolve(parent,data["file"])
        with Image.open(p) as im: mask=im.convert("L")
        if mask.size!=size: raise ValueError("蒙版尺寸必须等于原图尺寸；不可自动拉伸")
        return mask, {"mode":"alpha_file","sha256":digest(p),"source":str(p)}
    if data.get("mode")!="ellipse":
        raise ValueError("mask.mode 必须为 auto_plate、ellipse 或 alpha_file")
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


def rgb(code):
    if not isinstance(code,str) or len(code)!=7 or not code.startswith("#"):
        raise ValueError("颜色必须为 #RRGGBB")
    try: return tuple(int(code[k:k+2],16) for k in (1,3,5))
    except ValueError as exc: raise ValueError("背景颜色无效") from exc

def botanical_background(size, options):
    """Reproducible gray-linen approximation with very faint printed corner leaves.
    The texture and print are background-only and never redraw the source subject.
    """
    w,h=size
    base_color=options.get("base_color","#D0D0CB")
    base=np.asarray(rgb(base_color),dtype=np.float32)
    texture=float(options.get("texture_strength",1.0))
    opacity=float(options.get("pattern_opacity",.18))
    if not (0 <= texture <= 1.8 and 0 <= opacity <= .32):
        raise ValueError("桌布纹理强度或植物纹透明度超出允许范围")
    rng=np.random.default_rng(20261102)
    yy,xx=np.ogrid[:h,:w]
    weave=.75*np.sin(xx*.84)+.65*np.sin(yy*.81)
    noise=rng.normal(0,1.15,(h,w))
    arr=np.clip(base[None,None,:]+((weave+noise)*texture)[:,:,None],0,255).astype(np.uint8)
    bg=Image.fromarray(arr,"RGB")
    if opacity:
        print_layer=Image.new("RGBA",size,(0,0,0,0))
        draw=ImageDraw.Draw(print_layer)
        for corner in ("TL","TR","BL","BR"):
            sx=-1 if corner in ("TR","BR") else 1
            sy=-1 if corner in ("BL","BR") else 1
            bx=w-1 if sx<0 else 0
            by=h-1 if sy<0 else 0
            def at(x,y): return (round(bx+sx*x*w),round(by+sy*y*h))
            color=(94,111,99,round(44*opacity))
            draw.line([at(.018,.030),at(.037,.083),at(.067,.120),
                       at(.097,.166),at(.130,.207)],
                      fill=color,width=max(1,round(w*.002)))
            for x,y,side in ((.040,.085,-1),(.057,.112,1),(.079,.140,-1),
                             (.101,.171,1),(.120,.190,-1)):
                draw.polygon([at(x,y),at(x+side*.028,y-.014),
                              at(x+side*.011,y+.014)],fill=color)
        print_layer=print_layer.filter(ImageFilter.GaussianBlur(.6))
        bg=Image.alpha_composite(bg.convert("RGBA"),print_layer).convert("RGB")
    return bg,{"mode":"linen_botanical","base_color":base_color,
               "texture_strength":texture,"pattern_opacity":opacity,
               "seed":20261102,
               "note":"为可复现的浅灰植物纹桌布模拟；真实桌布可用 background.mode=image"}

def make_background(size,settings,parent):
    """Supports old solid-color configs, a deterministic linen design, or a real cloth photo."""
    if isinstance(settings,str):
        return Image.new("RGB",size,rgb(settings)),{"mode":"solid","color":settings}
    config={**DEFAULT_BACKGROUND,**(settings or {})}
    mode=config.get("mode")
    if mode=="linen_botanical": return botanical_background(size,config)
    if mode=="solid":
        color=config.get("color","#D0D0CB")
        return Image.new("RGB",size,rgb(color)),{"mode":"solid","color":color}
    if mode=="image":
        image_path=resolve(parent,config["file"])
        with Image.open(image_path) as im:
            bg=ImageOps.fit(ImageOps.exif_transpose(im).convert("RGB"),size,
                            method=Image.Resampling.LANCZOS,
                            centering=pair(config.get("crop_center",[.5,.5]),
                                           "background.crop_center"))
        return bg,{"mode":"image","source":str(image_path),"sha256":digest(image_path)}
    raise ValueError("background.mode 仅支持 linen_botanical、image、solid")

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
    mask,mask_meta=make_mask(original.size,data["mask"],config.parent,original)
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
    output,bg_meta=make_background((cw,ch),data.get("background"),config.parent)
    shadow_strength=float(data.get("contact_shadow",.10))
    if not 0 <= shadow_strength <= .20:
        raise ValueError("contact_shadow 超出保真范围")
    if shadow_strength:
        shadow=Image.new("RGBA",(cw,ch),(0,0,0,0))
        shadow_stamp=Image.new("RGBA",size,(51,49,46,0))
        alpha=fg.getchannel("A").point(lambda p:round(p*shadow_strength))
        shadow_stamp.putalpha(alpha)
        shadow.paste(shadow_stamp,(x,min(ch-size[1],y+max(1,round(ch*.006)))))
        shadow=shadow.filter(ImageFilter.GaussianBlur(max(2,round(cw*.013))))
        output=Image.alpha_composite(output.convert("RGBA"),shadow).convert("RGB")
    output.paste(fg,(x,y),fg.getchannel("A"))
    out=resolve(config.parent,data.get("output","output/封面图.png"))
    out.parent.mkdir(parents=True,exist_ok=True)
    output.save(out)
    center_px=[x+size[0]/2,y+size[1]/2]
    center_target_px=[cw*center[0],ch*center[1]]
    qa={"version":VERSION,"status":"review_required",
        "source":str(origin),"source_sha256":sha,
        "source_size":list(original.size),"only_original_subject_pixels":True,
        "generative_redraw":False,"hand_removal_verified":False,
        "mask":mask_meta,"source_bbox_px":list(bbox),
        "subject_bbox_canvas_px":[x,y,x+size[0],y+size[1]],
        "canvas":canvas,"background":bg_meta,"color":color,
        "center_px":center_px,"center_target_px":center_target_px,
        "center_error_px":[center_px[0]-center_target_px[0],center_px[1]-center_target_px[1]],
        "contact_shadow":shadow_strength,
        "note":"必须目视确认真实蒙版贴合盘沿、手部移除、碗盘居中、轻调色；遮挡盘沿处禁止凭空修复。"}
    # Diagnostic overlay is generated from the unmodified original and excluded from final cover.
    preview=original.copy()
    d=ImageDraw.Draw(preview)
    width=max(3,round(min(original.size)/240))
    if mask_meta.get("mode")=="auto_plate":
        cx,cy,rx,ry,angle=mask_meta["ellipse_source_px"]
        phi=math.radians(angle)
        boundary=[]
        for k in range(241):
            t=2*math.pi*k/240
            u,v=rx*math.cos(t),ry*math.sin(t)
            boundary.append((cx+u*math.cos(phi)-v*math.sin(phi),
                             cy+u*math.sin(phi)+v*math.cos(phi)))
        d.line(boundary,fill=(255,60,40),width=width,joint="curve")
        d.line((cx-18,cy,cx+18,cy),fill=(10,130,250),width=width)
        d.line((cx,cy-18,cx,cy+18),fill=(10,130,250),width=width)
    else:
        d.rectangle(bbox,outline=(255,60,40),width=width)
    preview_path=out.with_name(out.stem+"_QA_rim_preview.png")
    preview.save(preview_path)
    qa["rim_preview"]=str(preview_path)
    qa["placement_basis"]="plate_bowl_outer_rim_mask_not_food_or_hand"
    qa["hand_removal_method"]="mask_exclusion_of_pixels_outside_plate"
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
