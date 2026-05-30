from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[2]


OUT_DIR = ROOT / "outputs" / "figures" / "art"
FIGURE_DIR = ROOT / "outputs" / "figures" / "pdf"

PNG_OUT = OUT_DIR / "llm_token_cost_bar.png"
PDF_OUT = OUT_DIR / "llm_token_cost_bar.pdf"
SVG_OUT = OUT_DIR / "llm_token_cost_bar.svg"
FIGURE_PDF_OUT = FIGURE_DIR / "llm_token_cost_bar.pdf"

FONT = r"C:\Windows\Fonts\times.ttf"
BOLD = r"C:\Windows\Fonts\timesbd.ttf"

W, H = 980, 850
LEFT = 300
RIGHT = 875
TOP = 62
ROW_H = 52
BAR_H = 18
X_MAX = 38.0

TEXT = (34, 34, 34)
MUTED = (112, 112, 112)
GRID = (224, 224, 224)
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
    ("Gemini 3.1 Pro", "Closed", 20_195_805),
    ("GLM-5.1", "Open", 20_797_806),
    ("Qwen3.6-Max", "Closed", 22_051_712),
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


F_MODEL = load_font(BOLD, 24)
F_VALUE = load_font(BOLD, 22)
F_AXIS = load_font(FONT, 19)
F_LEGEND = load_font(FONT, 21)


def text_size(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont) -> tuple[int, int]:
    box = draw.textbbox((0, 0), text, font=font)
    return box[2] - box[0], box[3] - box[1]


def draw_right_text(
    draw: ImageDraw.ImageDraw,
    x: float,
    y: float,
    text: str,
    font: ImageFont.FreeTypeFont,
    fill: tuple[int, int, int],
) -> None:
    tw, th = text_size(draw, text, font)
    draw.text((x - tw, y - th / 2), text, font=font, fill=fill)


def color_for(group: str, name: str) -> tuple[int, int, int]:
    if name == "PaperFlow":
        return PAPERFLOW
    return CLOSED if group == "Closed" else OPEN


def x_pos(million_tokens: float) -> float:
    return LEFT + (million_tokens / X_MAX) * (RIGHT - LEFT)


def draw_png() -> Image.Image:
    image = Image.new("RGB", (W, H), "white")
    draw = ImageDraw.Draw(image)

    # Legend.
    draw.ellipse((LEFT, 18, LEFT + 16, 34), fill=CLOSED)
    draw.text((LEFT + 24, 15), "Closed", font=F_LEGEND, fill=TEXT)
    draw.ellipse((LEFT + 126, 18, LEFT + 142, 34), fill=OPEN)
    draw.text((LEFT + 150, 15), "Open", font=F_LEGEND, fill=TEXT)

    # Vertical reference ticks.
    chart_bottom = TOP + (len(ROWS) - 1) * ROW_H + 40
    for tick in [10, 20, 30]:
        x = x_pos(tick)
        draw.line((x, TOP - 18, x, chart_bottom), fill=GRID, width=1)
        label = f"{tick}M"
        tw, _ = text_size(draw, label, F_AXIS)
        draw.text((x - tw / 2, chart_bottom + 10), label, font=F_AXIS, fill=MUTED)

    draw.text((LEFT, chart_bottom + 45), "TokenCost (million tokens, lower is better)", font=F_AXIS, fill=TEXT)

    for idx, (name, group, tokens) in enumerate(ROWS):
        y = TOP + idx * ROW_H
        value = tokens / 1_000_000
        color = color_for(group, name)
        label_color = PAPERFLOW if name == "PaperFlow" else TEXT
        draw_right_text(draw, LEFT - 22, y, name, F_MODEL, label_color)
        draw.line((LEFT, y + 24, RIGHT, y + 24), fill=(244, 244, 244), width=1)
        draw.rounded_rectangle(
            (LEFT, y - BAR_H / 2, x_pos(value), y + BAR_H / 2),
            radius=5,
            fill=color,
        )
        draw.text((x_pos(value) + 12, y - 13), f"{value:.1f}M", font=F_VALUE, fill=color)

    return image


def rgb(c: tuple[int, int, int]) -> str:
    return f"rgb({c[0]},{c[1]},{c[2]})"


def write_svg() -> None:
    chart_bottom = TOP + (len(ROWS) - 1) * ROW_H + 40
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">',
        '<rect width="100%" height="100%" fill="white"/>',
        f'<circle cx="{LEFT + 8}" cy="26" r="8" fill="{rgb(CLOSED)}"/>',
        f'<text x="{LEFT + 24}" y="32" font-family="Times New Roman" font-size="21" fill="{rgb(TEXT)}">Closed</text>',
        f'<circle cx="{LEFT + 134}" cy="26" r="8" fill="{rgb(OPEN)}"/>',
        f'<text x="{LEFT + 150}" y="32" font-family="Times New Roman" font-size="21" fill="{rgb(TEXT)}">Open</text>',
    ]

    for tick in [10, 20, 30]:
        x = x_pos(tick)
        parts.append(f'<line x1="{x}" y1="{TOP - 18}" x2="{x}" y2="{chart_bottom}" stroke="{rgb(GRID)}" stroke-width="1"/>')
        parts.append(
            f'<text x="{x}" y="{chart_bottom + 28}" font-family="Times New Roman" '
            f'font-size="19" text-anchor="middle" fill="{rgb(MUTED)}">{tick}M</text>'
        )
    parts.append(
        f'<text x="{LEFT}" y="{chart_bottom + 68}" font-family="Times New Roman" '
        f'font-size="19" fill="{rgb(TEXT)}">TokenCost (million tokens, lower is better)</text>'
    )

    for idx, (name, group, tokens) in enumerate(ROWS):
        y = TOP + idx * ROW_H
        value = tokens / 1_000_000
        color = color_for(group, name)
        label_color = PAPERFLOW if name == "PaperFlow" else TEXT
        x_end = x_pos(value)
        parts.append(f'<line x1="{LEFT}" y1="{y + 24}" x2="{RIGHT}" y2="{y + 24}" stroke="rgb(244,244,244)" stroke-width="1"/>')
        parts.append(
            f'<text x="{LEFT - 22}" y="{y + 8}" font-family="Times New Roman" '
            f'font-size="24" font-weight="700" text-anchor="end" fill="{rgb(label_color)}">{name}</text>'
        )
        parts.append(
            f'<rect x="{LEFT}" y="{y - BAR_H / 2}" width="{x_end - LEFT}" height="{BAR_H}" '
            f'rx="5" fill="{rgb(color)}"/>'
        )
        parts.append(
            f'<text x="{x_end + 12}" y="{y + 8}" font-family="Times New Roman" '
            f'font-size="22" font-weight="700" fill="{rgb(color)}">{value:.1f}M</text>'
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

