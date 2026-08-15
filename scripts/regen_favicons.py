"""Regenerate Welcome to Trades favicons from logo.png (circular crop, no white matte)."""
from pathlib import Path

from PIL import Image, ImageDraw

STATIC = Path(__file__).resolve().parents[1] / "static"


def is_bg(c: tuple[int, int, int, int]) -> bool:
    r, g, b, a = c
    if a < 20:
        return True
    return r > 230 and g > 230 and b > 230


def circularize(img: Image.Image) -> Image.Image:
    n = img.size[0]
    mask = Image.new("L", (n, n), 0)
    ImageDraw.Draw(mask).ellipse((1, 1, n - 2, n - 2), fill=255)
    out = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    out.paste(img, (0, 0))
    r, g, b, a = out.split()
    out.putalpha(Image.composite(a, Image.new("L", (n, n), 0), mask))
    return out


def main() -> None:
    src = Image.open(STATIC / "logo.png").convert("RGBA")
    w, h = src.size
    px = src.load()
    xs, ys = [], []
    for y in range(h):
        for x in range(w):
            if not is_bg(px[x, y]):
                xs.append(x)
                ys.append(y)
    pad = 4
    left = max(0, min(xs) - pad)
    top = max(0, min(ys) - pad)
    right = min(w - 1, max(xs) + pad)
    bottom = min(h - 1, max(ys) + pad)
    cropped = src.crop((left, top, right + 1, bottom + 1))
    side = max(cropped.size)
    canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    canvas.paste(
        cropped,
        ((side - cropped.size[0]) // 2, (side - cropped.size[1]) // 2),
        cropped,
    )

    icon16 = circularize(canvas.resize((16, 16), Image.Resampling.LANCZOS))
    icon32 = circularize(canvas.resize((32, 32), Image.Resampling.LANCZOS))
    icon48 = circularize(canvas.resize((48, 48), Image.Resampling.LANCZOS))
    icon192 = circularize(canvas.resize((192, 192), Image.Resampling.LANCZOS))

    icon48.save(STATIC / "favicon-48.png", optimize=True)
    icon192.save(STATIC / "favicon-192.png", optimize=True)
    icon48.save(STATIC / "favicon.png", optimize=True)
    # New filenames force Chrome to drop the old localhost RJC cache entry
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
    print("ok", icon48.size, icon48.getpixel((24, 24)))


if __name__ == "__main__":
    main()
