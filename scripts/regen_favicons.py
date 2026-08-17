"""Regenerate Welcome to Trades favicons from logo.png (transparent matte, circular)."""
from __future__ import annotations

import base64
from pathlib import Path

from PIL import Image, ImageDraw

STATIC = Path(__file__).resolve().parents[1] / "static"


def is_white_matte(c: tuple[int, int, int, int], *, threshold: int = 245) -> bool:
    r, g, b, a = c
    if a < 20:
        return True
    return r >= threshold and g >= threshold and b >= threshold


def strip_white_matte(img: Image.Image, *, threshold: int = 245) -> Image.Image:
    """Turn white / near-white pixels transparent (drop shadow matte, etc.)."""
    rgba = img.convert("RGBA")
    px = rgba.load()
    w, h = rgba.size
    for y in range(h):
        for x in range(w):
            if is_white_matte(px[x, y], threshold=threshold):
                px[x, y] = (255, 255, 255, 0)
    return rgba


def circularize(img: Image.Image) -> Image.Image:
    n = img.size[0]
    mask = Image.new("L", (n, n), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, n - 1, n - 1), fill=255)
    out = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    out.paste(img, (0, 0))
    r, g, b, a = out.split()
    out.putalpha(Image.composite(a, Image.new("L", (n, n), 0), mask))
    return out


def tight_crop(img: Image.Image, *, pad: int = 2) -> Image.Image:
    px = img.load()
    w, h = img.size
    xs, ys = [], []
    for y in range(h):
        for x in range(w):
            if px[x, y][3] > 20:
                xs.append(x)
                ys.append(y)
    if not xs:
        return img
    left = max(0, min(xs) - pad)
    top = max(0, min(ys) - pad)
    right = min(w - 1, max(xs) + pad)
    bottom = min(h - 1, max(ys) + pad)
    cropped = img.crop((left, top, right + 1, bottom + 1))
    side = max(cropped.size)
    canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    canvas.paste(
        cropped,
        ((side - cropped.size[0]) // 2, (side - cropped.size[1]) // 2),
        cropped,
    )
    return canvas


def write_embedded_svg(png_path: Path, svg_path: Path) -> None:
    b64 = base64.b64encode(png_path.read_bytes()).decode("ascii")
    svg_path.write_text(
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512" role="img" aria-label="Welcome to Trades">\n'
        f'  <image width="512" height="512" href="data:image/png;base64,{b64}"/>\n'
        f"</svg>\n",
        encoding="utf-8",
    )


def main() -> None:
    src_path = STATIC / "logo.png"
    src = Image.open(src_path).convert("RGBA")
    cleaned = tight_crop(strip_white_matte(src))
    cleaned512 = cleaned.resize((512, 512), Image.Resampling.LANCZOS)
    cleaned512.save(src_path, optimize=True)

    icon16 = circularize(cleaned512.resize((16, 16), Image.Resampling.LANCZOS))
    icon32 = circularize(cleaned512.resize((32, 32), Image.Resampling.LANCZOS))
    icon48 = circularize(cleaned512.resize((48, 48), Image.Resampling.LANCZOS))
    icon192 = circularize(cleaned512.resize((192, 192), Image.Resampling.LANCZOS))

    icon48.save(STATIC / "favicon-48.png", optimize=True)
    icon192.save(STATIC / "favicon-192.png", optimize=True)
    icon48.save(STATIC / "favicon.png", optimize=True)
    icon48.save(STATIC / "wtt-favicon-48.png", optimize=True)
    icon192.save(STATIC / "wtt-favicon-192.png", optimize=True)
    icon16.save(
        STATIC / "favicon.ico",
        format="ICO",
        sizes=[(16, 16), (32, 32), (48, 48)],
        append_images=[icon32, icon48],
    )
    icon16.save(
        STATIC / "wtt-favicon.ico",
        format="ICO",
        sizes=[(16, 16), (32, 32), (48, 48)],
        append_images=[icon32, icon48],
    )
    write_embedded_svg(src_path, STATIC / "logo.svg")
    corner = cleaned512.getpixel((0, 0))
    print("ok", icon48.size, "corner", corner)


if __name__ == "__main__":
    main()
