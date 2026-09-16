#!/usr/bin/env python3
"""
将日常照片转为带白边的贴纸 PNG（透明底）。

抠图优先级：macOS Vision 框架（原生、免模型） > rembg > 圆角矩形兜底。

用法:
  python3 make_sticker.py --input photo.jpg --output sticker.png [--border 12] [--shadow]
  python3 make_sticker.py --input already_cutout.png --output sticker.png --skip-cutout
"""
import argparse
import io
import json
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageFilter, ImageOps


# ---------------------------------------------------------------------------
# 抠图后端
# ---------------------------------------------------------------------------

def cutout_with_vision(input_path: str) -> Image.Image:
    """用 macOS Vision 框架做人物抠图。失败则抛出异常。"""
    import Vision  # noqa: WPS433
    import Quartz  # noqa: WPS433
    import Foundation  # noqa: WPS433

    img = ImageOps.exif_transpose(Image.open(input_path)).convert("RGB")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    ci_image = Vision.CIImage.imageWithData_(buf.getvalue())

    request = Vision.VNGeneratePersonSegmentationRequest.alloc().initWithCompletionHandler_(None)
    request.setQualityLevel_(Vision.VNGeneratePersonSegmentationRequestQualityLevelAccurate)
    handler = Vision.VNImageRequestHandler.alloc().initWithCIImage_options_(ci_image, None)
    success, error = handler.performRequests_error_([request], None)
    if not success:
        raise RuntimeError(f"Vision request failed: {error}")

    results = request.results()
    if not results:
        raise RuntimeError("No person detected by Vision")

    pixel_buffer = results[0].pixelBuffer()
    mask_ci = Vision.CIImage.imageWithCVPixelBuffer_(pixel_buffer)

    # 缩放 mask 到原图尺寸
    scale_x = ci_image.extent().size.width / mask_ci.extent().size.width
    scale_y = ci_image.extent().size.height / mask_ci.extent().size.height
    transform = Quartz.CGAffineTransformMakeScale(scale_x, scale_y)
    mask_ci = mask_ci.imageByApplyingTransform_(transform)
    mask_ci = mask_ci.imageByCroppingToRect_(ci_image.extent())

    # 渲染为 CGImage 后保存 PNG 临时文件
    context = Quartz.CIContext.contextWithOptions_(None)
    mask_cg = context.createCGImage_fromRect_(mask_ci, mask_ci.extent())
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        tmp_path = tmp.name
    tmp_url = Foundation.NSURL.fileURLWithPath_(tmp_path)
    dest = Quartz.CGImageDestinationCreateWithURL(tmp_url, "public.png", 1, None)
    Quartz.CGImageDestinationAddImage(dest, mask_cg, None)
    Quartz.CGImageDestinationFinalize(dest)

    mask = Image.open(tmp_path).convert("L")
    Path(tmp_path).unlink(missing_ok=True)
    mask = mask.resize(img.size, Image.BILINEAR)

    rgba = img.convert("RGBA")
    rgba.putalpha(mask)
    return rgba


def cutout_with_vision_foreground(input_path: str) -> Image.Image:
    """用 macOS Vision 通用前景分割抠图（适用于非人物的单个物件）。失败则抛出异常。"""
    import Vision  # noqa: WPS433
    import Quartz  # noqa: WPS433
    import Foundation  # noqa: WPS433

    img = ImageOps.exif_transpose(Image.open(input_path)).convert("RGB")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    ci_image = Vision.CIImage.imageWithData_(buf.getvalue())

    request = Vision.VNGenerateForegroundInstanceMaskRequest.alloc().initWithCompletionHandler_(None)
    handler = Vision.VNImageRequestHandler.alloc().initWithCIImage_options_(ci_image, None)
    success, error = handler.performRequests_error_([request], None)
    if not success:
        raise RuntimeError(f"Vision foreground request failed: {error}")

    results = request.results()
    if not results:
        raise RuntimeError("No foreground detected by Vision")

    obs = results[0]
    instances = obs.allInstances()
    masked_pb, err = obs.generateScaledMaskForImageForInstances_fromRequestHandler_error_(
        instances, handler, None
    )
    if err or not masked_pb:
        raise RuntimeError(f"Failed to generate masked image: {err}")

    masked_ci = Vision.CIImage.imageWithCVPixelBuffer_(masked_pb)
    context = Quartz.CIContext.contextWithOptions_(None)
    mask_cg = context.createCGImage_fromRect_(masked_ci, masked_ci.extent())

    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        tmp_path = tmp.name
    tmp_url = Foundation.NSURL.fileURLWithPath_(tmp_path)
    dest = Quartz.CGImageDestinationCreateWithURL(tmp_url, "public.png", 1, None)
    Quartz.CGImageDestinationAddImage(dest, mask_cg, None)
    Quartz.CGImageDestinationFinalize(dest)

    mask = Image.open(tmp_path).convert("L")
    Path(tmp_path).unlink(missing_ok=True)
    rgba = img.convert("RGBA")
    rgba.putalpha(mask.resize(img.size, Image.Resampling.LANCZOS))
    return rgba


def cutout_with_rembg(img: Image.Image) -> Image.Image:
    """用 rembg 抠图。失败则抛出异常。"""
    from rembg import remove  # noqa: WPS433
    result = remove(img)
    if result.mode != "RGBA":
        result = result.convert("RGBA")
    # Use only backend alpha; retain the original photograph RGB.
    rgba = img.convert("RGBA")
    rgba.putalpha(result.getchannel("A").resize(img.size, Image.Resampling.LANCZOS))
    return rgba


def fallback_rounded(img: Image.Image, radius_ratio: float = 0.04) -> Image.Image:
    """兜底：圆角矩形 + 透明四角。"""
    img = img.convert("RGBA")
    w, h = img.size
    radius = int(min(w, h) * radius_ratio)
    mask = Image.new("L", (w, h), 0)
    from PIL import ImageDraw
    draw = ImageDraw.Draw(mask)
    draw.rounded_rectangle([(0, 0), (w - 1, (h - 1))], radius=radius, fill=255)
    img.putalpha(mask)
    return img


# ---------------------------------------------------------------------------
# 贴纸效果
# ---------------------------------------------------------------------------

def add_white_border(img: Image.Image, border: int) -> Image.Image:
    """给透明底贴图加白色描边（贴纸感）。"""
    if border < 0:
        raise ValueError("border must be nonnegative")
    bbox = img.getchannel("A").getbbox()
    if not bbox:
        raise ValueError("Empty segmentation mask")
    img = ImageOps.expand(img.crop(bbox), border=border + 4, fill=(0, 0, 0, 0))
    if border == 0:
        return img
    alpha = img.getchannel("A")
    dilated = alpha.filter(ImageFilter.MaxFilter(3))
    for _ in range(max(1, border // 2)):
        dilated = dilated.filter(ImageFilter.MaxFilter(3))
    white_layer = Image.new("RGBA", img.size, (255, 255, 255, 255))
    white_layer.putalpha(dilated)
    composed = Image.alpha_composite(white_layer, img)
    bbox = composed.getbbox()
    if bbox:
        pad = border + 4
        l, t, r, b = bbox
        l = max(0, l - pad)
        t = max(0, t - pad)
        r = min(composed.width, r + pad)
        b = min(composed.height, b + pad)
        composed = composed.crop((l, t, r, b))
    return composed


def add_drop_shadow(img: Image.Image, offset: int = 8, blur: int = 12, opacity: int = 90) -> Image.Image:
    """在贴纸下方加柔和投影。"""
    w, h = img.size
    canvas = Image.new("RGBA", (w + offset * 4, h + offset * 4), (0, 0, 0, 0))
    shadow = Image.new("RGBA", img.size, (0, 0, 0, opacity))
    shadow.putalpha(img.getchannel("A").point(lambda p: int(p * opacity / 255)))
    shadow = shadow.filter(ImageFilter.GaussianBlur(blur))
    canvas.alpha_composite(shadow, (offset * 3, offset * 3))
    canvas.alpha_composite(img, (offset * 2, offset * 2))
    return canvas


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description="将照片转为带白边的贴纸 PNG")
    parser.add_argument("--input", required=True, help="输入照片路径")
    parser.add_argument("--output", required=True, help="输出 PNG 路径")
    parser.add_argument("--border", type=int, default=12, help="白边宽度（像素），默认 12")
    parser.add_argument("--shadow", action="store_true", help="是否加投影")
    parser.add_argument("--mode", choices=["person", "object", "auto"], default="auto",
                        help="抠图模式：person=人物分割, object=通用前景分割, auto=自动尝试（默认）")
    parser.add_argument("--no-cutout", action="store_true", help="跳过抠图，直接做圆角白边相框")
    parser.add_argument("--skip-cutout", action="store_true",
                        help="输入已是透明底 PNG，跳过所有抠图直接加白边")
    args = parser.parse_args()

    src = Path(args.input)
    if not src.exists():
        print(f"[ERROR] 输入文件不存在: {src}", file=sys.stderr)
        return 1

    img = ImageOps.exif_transpose(Image.open(src)).convert("RGBA")
    print(f"[INFO] 原图尺寸: {img.size}, mode={args.mode}")

    # 抠图
    if args.skip_cutout:
        print("[INFO] 输入已是透明底，跳过抠图")
        cut = img
    elif args.no_cutout:
        print("[INFO] 按要求使用圆角相框模式")
        cut = fallback_rounded(img)
    else:
        cut = None
        # 按 mode 选择 Vision 抠图方式
        vision_funcs = []
        if args.mode == "person":
            vision_funcs = [("Vision 人物分割", cutout_with_vision)]
        elif args.mode == "object":
            vision_funcs = [("Vision 前景分割", cutout_with_vision_foreground)]
        else:  # auto
            vision_funcs = [
                ("Vision 人物分割", cutout_with_vision),
                ("Vision 前景分割", cutout_with_vision_foreground),
            ]
        for label, func in vision_funcs:
            if cut is not None:
                break
            try:
                cut = func(str(src))
                print(f"[INFO] {label}成功")
            except Exception as exc:  # noqa: BLE001
                print(f"[WARN] {label}失败 ({exc})", file=sys.stderr)
        # rembg 兜底
        if cut is None:
            try:
                cut = cutout_with_rembg(img)
                print("[INFO] rembg 抠图成功")
            except Exception as exc:  # noqa: BLE001
                print(f"[WARN] rembg 失败 ({exc})，退化为圆角相框模式", file=sys.stderr)
                cut = fallback_rounded(img)

    bbox = cut.getchannel("A").getbbox()
    if not bbox:
        raise ValueError("Empty cutout; no visible foreground")
    quality = {"source": str(src.resolve()), "source_size": list(img.size),
               "cutout_size": list(cut.size), "visible_bbox": list(bbox),
               "visible_size": [bbox[2]-bbox[0], bbox[3]-bbox[1]]}

    # 白边
    sticker = add_white_border(cut, args.border)
    print(f"[INFO] 贴纸尺寸: {sticker.size}")

    # 投影
    if args.shadow:
        sticker = add_drop_shadow(sticker)
        print(f"[INFO] 加投影后尺寸: {sticker.size}")

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    sticker.save(out, "PNG")
    quality["sticker_size"] = list(sticker.size)
    out.with_suffix(".quality.json").write_text(json.dumps(quality, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[OK] 已保存贴纸: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
