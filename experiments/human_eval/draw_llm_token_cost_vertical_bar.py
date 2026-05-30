from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[2]


OUT_DIR = ROOT / "outputs" / "figures" / "art"
FIGURE_DIR = ROOT / "outputs" / "figures" / "pdf"

PNG_OUT = OUT_DIR / "llm_token_cost_vertical_bar.png"
PDF_OUT = OUT_DIR / "llm_token_cost_vertical_bar.pdf"
SVG_OUT = OUT_DIR / "llm_token_cost_vertical_bar.svg"
FIGURE_PDF_OUT = FIGURE_DIR / "llm_token_cost_vertical_bar.pdf"

FONT = r"C:\Windows\Fonts\times.ttf"
BOLD = r"C:\Windows\Fonts\timesbd.ttf"

W, H = 1120, 820
PLOT_L = 92
PLOT_R = 1045
PLOT_T = 55
PLOT_B = 520
Y_MAX = 38.0
BAR_W = 42

TEXT = (34, 34, 34)
MUTED = (112, 112, 112)
GRID = (226, 226, 226)
AXIS = (76, 76, 76)
CLOSED = (54, 122, 84)
OPEN = (82, 132, 190)
PAPERFLOW = (36, 142, 73)

ROWS = [
    ("Kimi K2.6", "Open", 13_039_358),
    ("Grok 4.3", "Closed", 14_644_902),
    ("MiniMax-M2.7", "Open", 14_709_207),
    ("MiMo-V2.5-Pro", "Open", 15_463_947),
    ("DeepSeek-V4-Flash", "Open", 15_954_997),
    ("GPT-5.4", "Closed", 16_132_608),
    ("PaperFlow", "Closed", 17_413_607),
    ("Gemini 3.1 Pro Preview", "Closed", 20_195_805),
    ("GLM-5.1", "Open", 20_797_806),
    ("Qwen3.6-Max-Preview", "Closed", 22_051_712),
    ("Qwen3.6-Plus", "Closed", 23_746_290),
    ("DeepSeek-V4-Pro", "Open", 23_851_830),
    ("Qwen3.5-Plus", "Closed", 25_149_755),
    ("Claude Sonnet 4.6", "Closed", 36_522_181),
]


def load_font(path: str, size: int) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype(path, size)
    except OSError:
        return ImageFont.truetype(r"C:\Windows\Fonts\arial.ttf", size)


F_TICK = load_font(FONT, 22)
F_AXIS = load_font(FONT, 23)
F_VALUE = load_font(BOLD, 19)
F_LABEL = load_font(BOLD, 19)
F_LEGEND = load_font(FONT, 24)


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
    pad = 10
    layer = Image.new("RGBA", (tw + 2 * pad, th + 2 * pad), (255, 255, 255, 0))
    layer_draw = ImageDraw.Draw(layer)
    layer_draw.text((pad, pad), text, font=font, fill=fill)
    rotated = layer.rotate(angle, expand=True, resample=Image.Resampling.BICUBIC)
    base.paste(rotated, (round(x - rotated.width / 2), round(y - rotated.height / 2)), rotated)


def x_pos(idx: int) -> float:
    step = (PLOT_R - PLOT_L) / len(ROWS)
    return PLOT_L + step * (idx + 0.5)


def y_pos(million_tokens: float) -> float:
    return PLOT_B - (million_tokens / Y_MAX) * (PLOT_B - PLOT_T)


def color_for(group: str, name: str) -> tuple[int, int, int]:
    if name == "PaperFlow":
        return PAPERFLOW
    return CLOSED if group == "Closed" else OPEN


def draw_png() -> Image.Image:
    image = Image.new("RGB", (W, H), "white")
    draw = ImageDraw.Draw(image)

    for tick in [0, 10, 20, 30]:
        y = y_pos(tick)
        draw.line((PLOT_L, y, PLOT_R, y), fill=GRID, width=1)
        draw.line((PLOT_L - 8, y, PLOT_L, y), fill=AXIS, width=2)
        draw.text((PLOT_L - 58, y - 13), f"{tick}M", font=F_TICK, fill=TEXT)

    draw.line((PLOT_L, PLOT_T, PLOT_L, PLOT_B), fill=AXIS, width=2)
    draw.line((PLOT_L, PLOT_B, PLOT_R, PLOT_B), fill=AXIS, width=2)

    draw.ellipse((PLOT_L + 4, 18, PLOT_L + 20, 34), fill=CLOSED)
    draw.text((PLOT_L + 28, 15), "Closed", font=F_LEGEND, fill=TEXT)
    draw.ellipse((PLOT_L + 138, 18, PLOT_L + 154, 34), fill=OPEN)
    draw.text((PLOT_L + 162, 15), "Open", font=F_LEGEND, fill=TEXT)

    for idx, (name, group, tokens) in enumerate(ROWS):
        value = tokens / 1_000_000
        x = x_pos(idx)
        y = y_pos(value)
        color = color_for(group, name)
        draw.rounded_rectangle(
            (x - BAR_W / 2, y, x + BAR_W / 2, PLOT_B),
            radius=5,
            fill=color,
        )
        centered_text(draw, x, y - 16, f"{value:.1f}", F_VALUE, color)
        label_color = PAPERFLOW if name == "PaperFlow" else TEXT
        draw_rotated_text(image, name, x, PLOT_B + 114, -58, F_LABEL, label_color)

    centered_text(draw, (PLOT_L + PLOT_R) / 2, H - 32, "TokenCost (million tokens, lower is better)", F_AXIS, TEXT)
    return image


def rgb(c: tuple[int, int, int]) -> str:
    return f"rgb({c[0]},{c[1]},{c[2]})"


def write_svg() -> None:
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">',
        '<rect width="100%" height="100%" fill="white"/>',
    ]

    for tick in [0, 10, 20, 30]:
        y = y_pos(tick)
        parts.append(f'<line x1="{PLOT_L}" y1="{y}" x2="{PLOT_R}" y2="{y}" stroke="{rgb(GRID)}" stroke-width="1"/>')
        parts.append(f'<line x1="{PLOT_L - 8}" y1="{y}" x2="{PLOT_L}" y2="{y}" stroke="{rgb(AXIS)}" stroke-width="2"/>')
        parts.append(
            f'<text x="{PLOT_L - 58}" y="{y + 7}" font-family="Times New Roman" '
            f'font-size="22" fill="{rgb(TEXT)}">{tick}M</text>'
        )

    parts.append(f'<line x1="{PLOT_L}" y1="{PLOT_T}" x2="{PLOT_L}" y2="{PLOT_B}" stroke="{rgb(AXIS)}" stroke-width="2"/>')
    parts.append(f'<line x1="{PLOT_L}" y1="{PLOT_B}" x2="{PLOT_R}" y2="{PLOT_B}" stroke="{rgb(AXIS)}" stroke-width="2"/>')
    parts.append(f'<circle cx="{PLOT_L + 12}" cy="26" r="8" fill="{rgb(CLOSED)}"/>')
    parts.append(f'<text x="{PLOT_L + 28}" y="33" font-family="Times New Roman" font-size="24" fill="{rgb(TEXT)}">Closed</text>')
    parts.append(f'<circle cx="{PLOT_L + 146}" cy="26" r="8" fill="{rgb(OPEN)}"/>')
    parts.append(f'<text x="{PLOT_L + 162}" y="33" font-family="Times New Roman" font-size="24" fill="{rgb(TEXT)}">Open</text>')

    for idx, (name, group, tokens) in enumerate(ROWS):
        value = tokens / 1_000_000
        x = x_pos(idx)
        y = y_pos(value)
        color = color_for(group, name)
        label_color = PAPERFLOW if name == "PaperFlow" else TEXT
        parts.append(
            f'<rect x="{x - BAR_W / 2}" y="{y}" width="{BAR_W}" height="{PLOT_B - y}" '
            f'rx="5" fill="{rgb(color)}"/>'
        )
        parts.append(
            f'<text x="{x}" y="{y - 9}" font-family="Times New Roman" font-size="19" '
            f'font-weight="700" text-anchor="middle" fill="{rgb(color)}">{value:.1f}</text>'
        )
        parts.append(
            f'<text x="{x}" y="{PLOT_B + 114}" transform="rotate(-58 {x} {PLOT_B + 114})" '
            f'font-family="Times New Roman" font-size="19" font-weight="700" '
            f'text-anchor="middle" fill="{rgb(label_color)}">{name}</text>'
        )

    parts.append(
        f'<text x="{(PLOT_L + PLOT_R) / 2}" y="{H - 25}" font-family="Times New Roman" '
        f'font-size="23" text-anchor="middle" fill="{rgb(TEXT)}">TokenCost (million tokens, lower is better)</text>'
    )
    parts.append("</svg>")
    SVG_OUT.write_text("\n".join(parts), encoding="utf-8")


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    FIGURE_DIR.mkdir(parents=True, exist_ok=True)
    image = draw_png()
    image.save(PNG_OUT, dpi=(300, 300))
    image.save(PDF_OUT, "PDF", resolution=300.0)
    image.save(FIGURE_PDF_OUT, "PDF", resolution=300.0)
    write_svg()
    print(PNG_OUT)
    print(PDF_OUT)
    print(SVG_OUT)
    print(FIGURE_PDF_OUT)


if __name__ == "__main__":
    main()

