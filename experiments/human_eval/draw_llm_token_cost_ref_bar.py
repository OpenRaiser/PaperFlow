from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[2]


OUT_DIR = ROOT / "outputs" / "figures" / "art"
FIGURE_DIR = ROOT / "outputs" / "figures" / "pdf"

PNG_OUT = OUT_DIR / "llm_token_cost_ref_bar.png"
PDF_OUT = OUT_DIR / "llm_token_cost_ref_bar.pdf"
SVG_OUT = OUT_DIR / "llm_token_cost_ref_bar.svg"
FIGURE_PDF_OUT = FIGURE_DIR / "llm_token_cost_ref_bar.pdf"
DESKTOP_PDF_OUT = OUT_DIR / "llm_token_cost_ref_bar.pdf"

FONT = r"C:\Windows\Fonts\times.ttf"
BOLD = r"C:\Windows\Fonts\timesbd.ttf"

W, H = 1320, 860
PLOT_L = 145
PLOT_R = 1190
PLOT_T = 118
PLOT_B = 600
Y_MAX = 40.0
BAR_W = 46

TEXT = (72, 72, 78)
GRID = (234, 234, 234)
AXIS = (96, 96, 96)
CLOSED = (197, 211, 231)
OPEN = (149, 181, 216)

# Sorted by token cost.
ROWS = [
    ("M1", "Kimi K2.6", "Open", 13_039_358),
    ("M2", "Grok 4.3", "Closed", 14_644_902),
    ("M3", "MiniMax-M2.7", "Open", 14_709_207),
    ("M4", "MiMo-V2.5-Pro", "Open", 15_463_947),
    ("M5", "DeepSeek-V4-Flash", "Open", 15_954_997),
    ("M6", "GPT-5.4", "Closed", 16_132_608),
    ("M7", "Gemini 3 Flash", "Closed", 17_413_607),
    ("M8", "Gemini 3.1 Pro", "Closed", 20_195_805),
    ("M9", "GLM-5.1", "Open", 20_797_806),
    ("M10", "Qwen3.6-Max", "Closed", 22_051_712),
    ("M11", "Qwen3.6-Plus", "Closed", 23_746_290),
    ("M12", "DeepSeek-V4-Pro", "Open", 23_851_830),
    ("M13", "Qwen3.5-Plus", "Closed", 25_149_755),
    ("M14", "Claude Sonnet 4.6", "Closed", 36_522_181),
]


def load_font(path: str, size: int) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype(path, size)
    except OSError:
        return ImageFont.truetype(r"C:\Windows\Fonts\arial.ttf", size)


F_TITLE = load_font(BOLD, 43)
F_TICK = load_font(BOLD, 38)
F_LEGEND = load_font(BOLD, 38)
F_VALUE = load_font(BOLD, 32)
F_LABEL = load_font(BOLD, 35)
F_AXIS = load_font(FONT, 30)


def text_size(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont) -> tuple[int, int]:
    box = draw.textbbox((0, 0), text, font=font)
    return box[2] - box[0], box[3] - box[1]


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


def x_pos(idx: int) -> float:
    step = (PLOT_R - PLOT_L) / len(ROWS)
    return PLOT_L + step * (idx + 0.5)


def y_pos(value: float) -> float:
    return PLOT_B - (value / Y_MAX) * (PLOT_B - PLOT_T)


def color_for(group: str, name: str) -> tuple[int, int, int]:
    return CLOSED if group == "Closed" else OPEN


def draw_legend(draw: ImageDraw.ImageDraw) -> None:
    legend = [("Closed-source Model", CLOSED), ("Open-source Model", OPEN)]
    x = 565
    for row_idx, (label, color) in enumerate(legend):
        y = 13 + row_idx * 38
        draw.rounded_rectangle((x, y + 11, x + 24, y + 27), radius=4, fill=color)
        draw.text((x + 34, y), label, font=F_LEGEND, fill=TEXT)


def draw_png() -> Image.Image:
    image = Image.new("RGB", (W, H), "white")
    draw = ImageDraw.Draw(image)

    draw.text((PLOT_L - 34, 12), "TokenCost", font=F_TITLE, fill=TEXT)
    draw_legend(draw)

    for tick in [0, 10, 20, 30, 40]:
        y = y_pos(tick)
        draw.line((PLOT_L, y, PLOT_R, y), fill=GRID, width=1)
        label = f"{tick:.2f}"
        tw, th = text_size(draw, label, F_TICK)
        draw.text((PLOT_L - 12 - tw, y - th / 2), label, font=F_TICK, fill=TEXT)

    draw.line((PLOT_L, PLOT_B, PLOT_R, PLOT_B), fill=AXIS, width=2)

    for idx, (code, name, group, tokens) in enumerate(ROWS):
        value = tokens / 1_000_000
        x = x_pos(idx)
        y = y_pos(value)
        color = color_for(group, name)
        draw.rectangle((x - BAR_W / 2, y, x + BAR_W / 2, PLOT_B), fill=color)
        value_label = f"{value:.1f}"
        tw, th = text_size(draw, value_label, F_VALUE)
        draw.text((x - tw / 2, y - th - 16), value_label, font=F_VALUE, fill=TEXT)
        draw_rotated_text(image, name, x, PLOT_B + 112, 44, F_LABEL, TEXT)

    return image


def rgb(c: tuple[int, int, int]) -> str:
    return f"rgb({c[0]},{c[1]},{c[2]})"


def write_svg() -> None:
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">',
        '<rect width="100%" height="100%" fill="white"/>',
        f'<text x="{PLOT_L - 34}" y="50" font-family="Times New Roman" font-size="43" font-weight="700" fill="{rgb(TEXT)}">TokenCost</text>',
    ]
    x = 565
    for label, color in [("Closed-source Model", CLOSED), ("Open-source Model", OPEN)]:
        y = 24 if label.startswith("Closed") else 62
        parts.append(f'<rect x="{x}" y="{y}" width="24" height="16" rx="4" fill="{rgb(color)}"/>')
        parts.append(f'<text x="{x + 34}" y="{y + 26}" font-family="Times New Roman" font-size="38" font-weight="700" fill="{rgb(TEXT)}">{label}</text>')

    for tick in [0, 10, 20, 30, 40]:
        y = y_pos(tick)
        parts.append(f'<line x1="{PLOT_L}" y1="{y}" x2="{PLOT_R}" y2="{y}" stroke="{rgb(GRID)}" stroke-width="1"/>')
        parts.append(f'<text x="{PLOT_L - 12}" y="{y + 10}" font-family="Times New Roman" font-size="38" font-weight="700" text-anchor="end" fill="{rgb(TEXT)}">{tick:.2f}</text>')

    parts.append(f'<line x1="{PLOT_L}" y1="{PLOT_B}" x2="{PLOT_R}" y2="{PLOT_B}" stroke="{rgb(AXIS)}" stroke-width="2"/>')

    for idx, (code, name, group, tokens) in enumerate(ROWS):
        value = tokens / 1_000_000
        x = x_pos(idx)
        y = y_pos(value)
        color = color_for(group, name)
        parts.append(f'<rect x="{x - BAR_W / 2}" y="{y}" width="{BAR_W}" height="{PLOT_B - y}" fill="{rgb(color)}"/>')
        parts.append(f'<text x="{x}" y="{y - 20}" font-family="Times New Roman" font-size="32" font-weight="700" text-anchor="middle" fill="{rgb(TEXT)}">{value:.1f}</text>')
        parts.append(f'<text x="{x}" y="{PLOT_B + 112}" transform="rotate(44 {x} {PLOT_B + 112})" font-family="Times New Roman" font-size="35" font-weight="700" text-anchor="middle" fill="{rgb(TEXT)}">{name}</text>')

    parts.append("</svg>")
    SVG_OUT.write_text("\n".join(parts), encoding="utf-8")


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    FIGURE_DIR.mkdir(parents=True, exist_ok=True)
    image = draw_png()
    image.save(PNG_OUT, dpi=(300, 300))
    image.save(PDF_OUT, "PDF", resolution=300.0)
    image.save(FIGURE_PDF_OUT, "PDF", resolution=300.0)
    image.save(DESKTOP_PDF_OUT, "PDF", resolution=300.0)
    write_svg()
    print(PNG_OUT)
    print(PDF_OUT)
    print(SVG_OUT)
    print(FIGURE_PDF_OUT)
    print(DESKTOP_PDF_OUT)


if __name__ == "__main__":
    main()

