#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Final cover-image gate for both hybrid_natural_cover and strict_original_cover.

This script validates what code can reliably measure; it does not claim to
understand shadows, whether food was AI-redrawn, or natural photography.
Those checks require explicit visual review tied to the file's SHA256.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from PIL import Image, ImageOps

VERSION = "3.8-cover-final-gate"
VISUAL_CHECKS = (
    "plate_rim_complete",
    "food_structure_preserved",
    "no_hand_or_clutter",
    "natural_table_contact",
    "consistent_light_and_white_balance",
    "natural_color_no_plastic_look",
    "background_appropriate_no_extra_props",
    "no_destructive_edit_after_final",
)


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def review_template(image_sha, source_sha):
    return {
        "image_sha256": image_sha,
        "source_image_sha256": source_sha,
        "reviewer_note": "请逐项目视核对，只有确认后才把对应 false 改成 true；不能批量假设通过",
        "checks": {key: False for key in VISUAL_CHECKS},
    }


def inspect(image_path, source_path, mask_path=None, review_path=None):
    """Measure final image, optionally verify a subject mask and signed-off checks.

    Status is pass_manual_checked only if measurements pass and explicit,
    SHA-bound human visual checks are all true. Missing reviews never pass.
    """
    image_path, source_path = Path(image_path), Path(source_path)
    if not image_path.is_file():
        raise FileNotFoundError(image_path)
    if not source_path.is_file():
        raise FileNotFoundError(source_path)

    img_hash, src_hash = sha256(image_path), sha256(source_path)
    with Image.open(image_path) as image:
        image.load()
        width, height = image.size
        fmt = image.format
    with Image.open(source_path) as source:
        source_size = list(ImageOps.exif_transpose(source).size)

    ratio_ok = (width * 4 == height * 3 and width < height)
    png_ok = fmt == "PNG" and image_path.suffix.lower() == ".png"
    hard_failures, warnings = [], []
    if not ratio_ok:
        hard_failures.append("FINAL_RATIO_NOT_EXACT_3_4")
    if not png_ok:
        hard_failures.append("FINAL_IMAGE_NOT_PNG")

    margins = None
    mask_sha = None
    if mask_path is not None:
        mask_path = Path(mask_path)
        if not mask_path.is_file():
            raise FileNotFoundError(mask_path)
        mask_sha = sha256(mask_path)
        with Image.open(mask_path) as raw_mask:
            if raw_mask.size != (width, height):
                hard_failures.append("SUBJECT_MASK_SIZE_MISMATCH")
            else:
                mask = raw_mask.convert("L").point(lambda p: 255 if p >= 128 else 0)
                box = mask.getbbox()
                if box is None:
                    hard_failures.append("SUBJECT_MASK_EMPTY")
                else:
                    left, top, right, bottom = box
                    margins = {
                        "left": round(left / width, 5),
                        "right": round((width - right) / width, 5),
                        "top": round(top / height, 5),
                        "bottom": round((height - bottom) / height, 5),
                        "subject_bbox_px": [left, top, right, bottom],
                    }
                    if min(margins[k] for k in ("left", "right", "top", "bottom")) <= 0:
                        hard_failures.append("SUBJECT_TOUCHES_CANVAS_EDGE")
                    if margins["left"] < 0.03 or margins["right"] < 0.03:
                        hard_failures.append("SIDE_MARGIN_BELOW_3_PERCENT")
                    if margins["left"] > 0.06 or margins["right"] > 0.06:
                        warnings.append("SIDE_MARGIN_ABOVE_PREFERRED_6_PERCENT")
                    if margins["top"] < 0.04 or margins["bottom"] < 0.04:
                        warnings.append("TOP_BOTTOM_MARGIN_BELOW_PREFERRED_4_PERCENT")
    else:
        warnings.append("PLATE_RIM_BBOX_NOT_MACHINE_VERIFIED")

    review_checks = {}
    if review_path is not None:
        data = json.loads(Path(review_path).read_text(encoding="utf-8"))
        if (data.get("image_sha256") != img_hash
                or data.get("source_image_sha256") != src_hash):
            hard_failures.append("VISUAL_REVIEW_HASH_MISMATCH")
        review_checks = {
            key: data.get("checks", {}).get(key) is True
            for key in VISUAL_CHECKS
        }
        if not all(review_checks.values()):
            warnings.append("VISUAL_REVIEW_INCOMPLETE")
    else:
        warnings.append("VISUAL_REVIEW_MISSING")

    # A too-wide subject margin needs a new composition, not an assertion
    # that the original plate shape has changed. Never auto-crop a plate.
    if hard_failures:
        status = "fail"
    elif any(item in warnings for item in (
        "VISUAL_REVIEW_INCOMPLETE",
        "VISUAL_REVIEW_MISSING",
        "SIDE_MARGIN_ABOVE_PREFERRED_6_PERCENT",
    )):
        status = "review_required"
    else:
        status = "pass_manual_checked"

    return {
        "validator_version": VERSION,
        "mode": "hybrid_natural_cover_or_strict_original_cover",
        "status": status,
        "actual_size": [width, height],
        "target_default_size": [1200, 1600],
        "actual_format": fmt,
        "exact_ratio_3_4": ratio_ok,
        "format_png": png_ok,
        "image_sha256": img_hash,
        "source_image_sha256": src_hash,
        "source_size": source_size,
        "subject_mask_sha256": mask_sha,
        "subject_margins": margins,
        "visual_review_checks": review_checks,
        "manual_review_confirmed": bool(review_checks) and all(review_checks.values()),
        "hard_failures": hard_failures,
        "warnings": warnings,
        "safe_repair_policy": (
            "If ratio fails, expand ONLY the scene-aware cloth background with "
            "image editing, preserve full plate/food pixels and perspective, "
            "then re-run QA. Never stretch, crop through the rim, or rescale "
            "a labelled finished collage. This checker never edits pixels."
        ),
        "limit": (
            "Mask bbox is geometric only: it cannot prove a complete rim or "
            "natural shadows. Visual review is required for those claims."
        ),
    }


def main():
    parser = argparse.ArgumentParser(
        description="封面图 3:4 强制验收：比例/PNG/可选主体边距/与图片哈希绑定的目视检查")
    parser.add_argument("--image", required=True, help="最终待验收 PNG")
    parser.add_argument("--source", required=True, help="用户原始照片（不上传公开仓库）")
    parser.add_argument("--subject-mask", help="最终画布同尺寸的盘/碗主体蒙版（可选）")
    parser.add_argument("--review", help="与图片 SHA256 绑定的目视复核 JSON（可选）")
    parser.add_argument("--init-review", action="store_true",
                        help="生成全部为 false 的人工复核表，不会自动宣称通过")
    parser.add_argument("--output", help="QA JSON 输出路径")
    parser.add_argument("--strict", action="store_true",
                        help="状态不等于 pass_manual_checked 时返回非零退出码")
    args = parser.parse_args()

    output = Path(args.output) if args.output else Path(args.image).with_name(
        Path(args.image).stem + "_cover_QA.json")
    output.parent.mkdir(parents=True, exist_ok=True)

    if args.init_review:
        review = review_template(sha256(args.image), sha256(args.source))
        target = output.with_name(Path(args.image).stem + "_review_template.json")
        target.write_text(json.dumps(review, ensure_ascii=False, indent=2) + "\n",
                          encoding="utf-8")
        print("待人工核验:", target)
        return

    result = inspect(args.image, args.source, args.subject_mask, args.review)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8")
    print("封面 QA:", output)
    print("状态:", result["status"], "尺寸:", result["actual_size"])
    if args.strict and result["status"] != "pass_manual_checked":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
