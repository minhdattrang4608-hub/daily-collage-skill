#!/usr/bin/env python3
"""
按 JSON 布局配置合成拼贴图。

布局 JSON 格式（通过 --config 传入文件路径，或 --json 直接传入字符串）:
{
  "canvas": {"width": 1080, "height": 1440},
  "background": "#1A1A1A",
  "elements": [
    {
      "path": "subject.png",   // 图片路径（相对配置文件目录或绝对路径）
      "x": 540,                 // 中心点 x（画布坐标）
      "y": 600,                 // 中心点 y
      "width": 520,             // 目标宽度（高度按比例自动算）
      "rotation": -3,           // 旋转角度（度，逆时针为正）
      "shadow": true,           // 是否加投影
      "z": 10                   // 层级，越大越在上
    },
    ...
  ]
}

用法:
  python3 compose_collage.py --config layout.json --output collage.png
  python3 compose_collage.py --json '{"canvas":...}' --output collage.png
"""
import argparse
import json
import sys
from pathlib import Path

from PIL import Image, ImageFilter, ImageOps


def load_config(args) -> dict:
    if args.json:
        return json.loads(args.json)
    with open(args.config, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    # 相对路径基于配置文件所在目录解析
    cfg["_base_dir"] = str(Path(args.config).resolve().parent)
    return cfg


def resolve_path(cfg: dict, p: str) -> str:
    path = Path(p)
    if path.is_absolute():
        return str(path)
    base = cfg.get("_base_dir", ".")
    return str(Path(base) / path)


def make_shadow(elem_img: Image.Image, offset: int = 6, blur: int = 10, opacity: int = 80) -> Image.Image:
    """生成带投影的合成图（投影在下方）。"""
    w, h = elem_img.size
    pad = offset * 4 + blur * 2
    canvas = Image.new("RGBA", (w + pad, h + pad), (0, 0, 0, 0))
    alpha = elem_img.getchannel("A")
    shadow = Image.new("RGBA", elem_img.size, (0, 0, 0, opacity))
    shadow.putalpha(alpha.point(lambda v: int(v * opacity / 255)))
    shadow = shadow.filter(ImageFilter.GaussianBlur(blur))
    sx = pad // 2 + offset
    sy = pad // 2 + offset
    canvas.alpha_composite(shadow, (sx, sy))
    canvas.alpha_composite(elem_img, (pad // 2, pad // 2))
    return canvas


def place_element(canvas: Image.Image, elem: dict, cfg: dict) -> None:
    path = resolve_path(cfg, elem["path"])
    img = ImageOps.exif_transpose(Image.open(path)).convert("RGBA")

    # Remove transparent margins before calculating effective resolution.
    bbox = img.getchannel("A").getbbox()
    if not bbox:
        raise ValueError(f"Empty transparent image: {path}")
    img = img.crop(bbox)

    # 按目标宽度缩放
    target_w = int(elem.get("width", 300))
    ratio = target_w / img.width
    check_scale(cfg, path, img.size, ratio, elem.get("allow_upscale", False))
    target_h = max(1, round(img.height * ratio))
    if img.size != (target_w, target_h):
        img = img.resize((target_w, target_h), Image.LANCZOS)

    # 旋转（expand=True 保留完整内容）
    rot = elem.get("rotation", 0)
    if rot:
        img = img.rotate(rot, expand=True, resample=Image.BICUBIC)

    # 投影
    if elem.get("shadow", False):
        img = make_shadow(img)

    # 居中粘贴
    cx = int(elem["x"])
    cy = int(elem["y"])
    px = cx - img.width // 2
    py = cy - img.height // 2
    canvas.alpha_composite(img, (px, py))


def check_scale(cfg, path, size, ratio, allow_upscale=False):
    record = {"path": str(path), "source_size": list(size), "scale": round(ratio, 4)}
    cfg.setdefault("_quality_records", []).append(record)
    print(f"[QUALITY] {path}: {size[0]}x{size[1]}, scale={ratio:.3f}")
    if ratio <= 0:
        raise ValueError("Target dimensions must be positive")
    if ratio > 1.0:
        message = f"Upscaling {path} by {ratio:.3f}x; use a larger source or reduce placement size"
        if not allow_upscale:
            raise ValueError(message + "; intentional decorative upscaling requires allow_upscale=true")
        print(f"[WARN] {message}", file=sys.stderr)


def hex_to_rgb(hex_color: str) -> tuple:
    hex_color = hex_color.lstrip("#")
    if len(hex_color) == 3:
        hex_color = "".join(c * 2 for c in hex_color)
    return tuple(int(hex_color[i:i + 2], 16) for i in (0, 2, 4))


def main() -> int:
    parser = argparse.ArgumentParser(description="按布局配置合成拼贴图")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--config", help="布局 JSON 文件路径")
    group.add_argument("--json", help="布局 JSON 字符串")
    parser.add_argument("--output", required=True, help="输出图片路径")
    args = parser.parse_args()

    cfg = load_config(args)

    canvas_w = int(cfg.get("canvas", {}).get("width", 2160))
    canvas_h = int(cfg.get("canvas", {}).get("height", 2880))
    bg = cfg.get("background", "#FFFFFF")

    canvas = Image.new("RGBA", (canvas_w, canvas_h), (*hex_to_rgb(bg), 255))
    print(f"[INFO] 画布: {canvas_w}x{canvas_h}, 背景色: {bg}")

    # 背景图（cover 铺满，居中裁剪）
    bg_image_path = cfg.get("background_image")
    if bg_image_path:
        bg_path = resolve_path(cfg, bg_image_path)
        bg_img = ImageOps.exif_transpose(Image.open(bg_path)).convert("RGBA")
        ratio = max(canvas_w / bg_img.width, canvas_h / bg_img.height)
        check_scale(cfg, bg_path, bg_img.size, ratio, cfg.get("background_allow_upscale", False))
        bg_img = bg_img.resize(
            (int(bg_img.width * ratio), int(bg_img.height * ratio)), Image.LANCZOS
        )
        left = (bg_img.width - canvas_w) // 2
        top = (bg_img.height - canvas_h) // 2
        bg_img = bg_img.crop((left, top, left + canvas_w, top + canvas_h))
        canvas.alpha_composite(bg_img)
        print(f"[INFO] 背景图: {bg_image_path} (cover 铺满)")

    elements = cfg.get("elements", [])
    # 按 z 排序，小的先画（在底层）
    elements.sort(key=lambda e: e.get("z", 0))

    for i, elem in enumerate(elements):
        try:
            place_element(canvas, elem, cfg)
            print(f"[INFO] 放置元素 {i + 1}/{len(elements)}: {elem.get('path', '?')} "
                  f"@({elem['x']},{elem['y']}) w={elem.get('width')} rot={elem.get('rotation', 0)}")
        except Exception as exc:  # noqa: BLE001
            print(f"[ERROR] 元素 {elem.get('path')} 放置失败: {exc}", file=sys.stderr)
            return 1

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    # 转 RGB 保存为 JPG/PNG 均可，这里按扩展名
    if out.suffix.lower() in (".jpg", ".jpeg"):
        canvas.convert("RGB").save(out, "JPEG", quality=92)
    else:
        canvas.save(out, "PNG")
    out.with_suffix(".quality.json").write_text(json.dumps({"canvas": [canvas_w, canvas_h], "assets": cfg.get("_quality_records", [])}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[OK] 拼贴图已保存: {out} ({canvas_w}x{canvas_h})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
