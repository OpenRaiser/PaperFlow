from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[2]


OUT_DIR = ROOT / "outputs" / "figures" / "art"
PNG_OUT = OUT_DIR / "interest_drift_heatmap.png"
PDF_OUT = OUT_DIR / "interest_drift_heatmap.pdf"
SVG_OUT = OUT_DIR / "interest_drift_heatmap.svg"

FONT = r"C:\Windows\Fonts\times.ttf"
BOLD = r"C:\Windows\Fonts\timesbd.ttf"

W, H = 1375, 306
LEFT = 190
TOP = 42
CELL_W = 118
CELL_H = 48
GAP = 2

TEXT = (30, 30, 30)
GREEN_DARK = (35, 139, 62)
GREEN_LIGHT = (235, 246, 230)

METHODS = ["Full PaperFlow", "w/o Drift", "Fixed Profile"]
METRICS = [
    ("PD-gNDCG", "up", [0.6817, 0.6898, 0.6883]),
    ("PD-Useful", "up", [0.2568, 0.2635, 0.2641]),
    ("PD-OracleR", "up", [0.2684, 0.2807, 0.2849]),
    ("PD-SelNDCG", "up", [0.7946, 0.7828, 0.7563]),
    ("NewTopicR", "up", [0.8254, 0.7602, 0.7470]),
    ("OldTopicR", "down", [0.0557, 0.0984, 0.0995]),
    ("AdaptDelay", "down", [0.1667, 0.3333, 0.5000]),
    ("DriftAuto", "up", [72.76, 65.53, 59.68]),
    ("AdaptHuman", "up", [68.75, 67.78, 68.19]),
]


def load_font(path: str, size: int) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype(path, size)
    except OSError:
        return ImageFont.truetype(r"C:\Windows\Fonts\arial.ttf", size)


F_ROW = load_font(BOLD, 23)
F_CELL = load_font(BOLD, 20)
F_COL = load_font(BOLD, 18)
F_SMALL = load_font(FONT, 17)


def blend(c1: tuple[int, int, int], c2: tuple[int, int, int], t: float) -> tuple[int, int, int]:
    return tuple(round(c1[i] * (1 - t) + c2[i] * t) for i in range(3))


def score_for_metric(values: list[float], idx: int, direction: str) -> float:
    lo, hi = min(values), max(values)
    score = 0.5 if hi == lo else (values[idx] - lo) / (hi - lo)
    return 1 - score if direction == "down" else score


def color_for_score(score: float) -> tuple[int, int, int]:
    return blend(GREEN_LIGHT, GREEN_DARK, 0.04 + 0.96 * score)


def text_size(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont) -> tuple[int, int]:
    box = draw.textbbox((0, 0), text, font=font)
    return box[2] - box[0], box[3] - box[1]


def centered_text(
    draw: ImageDraw.ImageDraw,
    x: float,
    y: float,
    text: str,
    font: ImageFont.FreeTypeFont,
    fill: tuple[int, int, int],
) -> None:
    tw, th = text_size(draw, text, font)
    draw.text((x - tw / 2, y - th / 2), text, font=font, fill=fill)


def draw_rotated_text(
    base: Image.Image,
    text: str,
    x: float,
    y: float,
    angle: float,
    font: ImageFont.FreeTypeFont,
    fill: tuple[int, int, int],
) -> None:
    dummy = ImageDraw.Draw(base)
    tw, th = text_size(dummy, text, font)
    pad = 18
    layer = Image.new("RGBA", (tw + 2 * pad, th + 2 * pad), (255, 255, 255, 0))
    layer_draw = ImageDraw.Draw(layer)
    layer_draw.text((pad, pad), text, font=font, fill=fill)
    rotated = layer.rotate(angle, expand=True, resample=Image.Resampling.BICUBIC)
    base.paste(rotated, (round(x - rotated.width / 2), round(y - rotated.height / 2)), rotated)


def fmt(value: float) -> str:
    if value >= 10:
        return f"{value:.2f}"
    return f"{value:.4f}"


def is_best(values: list[float], row_idx: int, direction: str) -> bool:
    score = score_for_metric(values, row_idx, direction)
    best = max(score_for_metric(values, idx, direction) for idx in range(len(values)))
    return abs(score - best) < 1e-12


def draw_png() -> Image.Image:
    image = Image.new("RGB", (W, H), "white")
    draw = ImageDraw.Draw(image)

    for r, method in enumerate(METHODS):
        y = TOP + r * CELL_H
        method_w, method_h = text_size(draw, method, F_ROW)
        draw.text(
            (LEFT - 22 - method_w, y + (CELL_H - GAP - method_h) / 2 - 1),
            method,
            font=F_ROW,
            fill=TEXT,
        )

        for c, (_metric, direction, values) in enumerate(METRICS):
            x = LEFT + c * CELL_W
            score = score_for_metric(values, r, direction)
            draw.rectangle(
                (x, y, x + CELL_W - GAP, y + CELL_H - GAP),
                fill=color_for_score(score),
            )
            centered_text(draw, x + CELL_W / 2, y + CELL_H / 2, fmt(values[r]), F_CELL, (0, 0, 0))

    label_y = TOP + len(METHODS) * CELL_H + 49
    for c, (metric, direction, _values) in enumerate(METRICS):
        x = LEFT + c * CELL_W + CELL_W / 2
        draw_rotated_text(
            image,
            metric + (" \u2193" if direction == "down" else " \u2191"),
            x,
            label_y,
            -21,
            F_COL,
            TEXT,
        )

    bar_x = LEFT + len(METRICS) * CELL_W + 32
    bar_y = TOP + 4
    bar_h = len(METHODS) * CELL_H - GAP
    for i in range(bar_h):
        score = 1 - i / max(1, bar_h - 1)
        draw.line((bar_x, bar_y + i, bar_x + 14, bar_y + i), fill=color_for_score(score))
    draw.text((bar_x + 23, bar_y - 6), "better", font=F_SMALL, fill=TEXT)
    draw.text((bar_x + 23, bar_y + bar_h - 14), "worse", font=F_SMALL, fill=TEXT)
    return image


def rgb(c: tuple[int, int, int]) -> str:
    return f"rgb({c[0]},{c[1]},{c[2]})"


def write_svg() -> None:
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">',
        '<rect width="100%" height="100%" fill="white"/>',
        "<defs>",
        '<linearGradient id="driftbar" x1="0" x2="0" y1="0" y2="1">',
        f'<stop offset="0%" stop-color="{rgb(color_for_score(1))}"/>',
        f'<stop offset="100%" stop-color="{rgb(color_for_score(0))}"/>',
        "</linearGradient>",
        "</defs>",
    ]

    for r, method in enumerate(METHODS):
        y = TOP + r * CELL_H
        parts.append(
            f'<text x="{LEFT - 28}" y="{y + CELL_H / 2 + 9}" '
            f'font-family="Times New Roman" font-size="23" font-weight="700" '
            f'text-anchor="end" fill="{rgb(TEXT)}">{method}</text>'
        )

        for c, (_metric, direction, values) in enumerate(METRICS):
            x = LEFT + c * CELL_W
            score = score_for_metric(values, r, direction)
            parts.append(
                f'<rect x="{x}" y="{y}" width="{CELL_W - GAP}" height="{CELL_H - GAP}" '
                f'fill="{rgb(color_for_score(score))}"/>'
            )
            parts.append(
                f'<text x="{x + CELL_W / 2}" y="{y + CELL_H / 2 + 8}" '
                f'font-family="Times New Roman" font-size="20" font-weight="700" '
                f'text-anchor="middle" fill="rgb(0,0,0)">{fmt(values[r])}</text>'
            )

    label_y = TOP + len(METHODS) * CELL_H + 49
    for c, (metric, direction, _values) in enumerate(METRICS):
        x = LEFT + c * CELL_W + CELL_W / 2
        label = metric + (" \u2193" if direction == "down" else " \u2191")
        parts.append(
            f'<text x="{x}" y="{label_y}" transform="rotate(-21 {x} {label_y})" '
            f'font-family="Times New Roman" font-size="18" font-weight="700" '
            f'text-anchor="middle" fill="{rgb(TEXT)}">{label}</text>'
        )

    bar_x = LEFT + len(METRICS) * CELL_W + 32
    bar_y = TOP + 4
    bar_h = len(METHODS) * CELL_H - GAP
    parts.append(
        f'<rect x="{bar_x}" y="{bar_y}" width="14" height="{bar_h}" fill="url(#driftbar)"/>'
    )
    parts.append(
        f'<text x="{bar_x + 23}" y="{bar_y + 11}" font-family="Times New Roman" '
        f'font-size="17" fill="{rgb(TEXT)}">better</text>'
    )
    parts.append(
        f'<text x="{bar_x + 23}" y="{bar_y + bar_h}" font-family="Times New Roman" '
        f'font-size="17" fill="{rgb(TEXT)}">worse</text>'
    )
    parts.append("</svg>")
    SVG_OUT.write_text("\n".join(parts), encoding="utf-8")


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    image = draw_png()
    image.save(PNG_OUT, dpi=(300, 300))
    image.save(PDF_OUT, "PDF", resolution=300.0)
    write_svg()
    print(PNG_OUT)
    print(PDF_OUT)
    print(SVG_OUT)


if __name__ == "__main__":
    main()

