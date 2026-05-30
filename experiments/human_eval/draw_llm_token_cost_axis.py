from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[2]


OUT_DIR = ROOT / "outputs" / "figures" / "art"
FIGURE_DIR = ROOT / "outputs" / "figures" / "pdf"

PNG_OUT = OUT_DIR / "llm_token_cost_axis.png"
PDF_OUT = OUT_DIR / "llm_token_cost_axis.pdf"
SVG_OUT = OUT_DIR / "llm_token_cost_axis.svg"
FIGURE_PDF_OUT = FIGURE_DIR / "llm_token_cost_axis.pdf"

FONT = r"C:\Windows\Fonts\times.ttf"
BOLD = r"C:\Windows\Fonts\timesbd.ttf"

W, H = 960, 820
LEFT, RIGHT = 315, 870
TOP, BOTTOM = 70, 700
X_MIN, X_MAX = 12.0, 38.0

TEXT = (34, 34, 34)
MUTED = (108, 108, 108)
GRID = (222, 222, 222)
AXIS = (70, 70, 70)
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
F_AXIS = load_font(BOLD, 22)
F_TICK = load_font(FONT, 20)
F_LEGEND = load_font(FONT, 21)


def x_pos(tokens: int) -> float:
    value = tokens / 1_000_000
    return LEFT + (value - X_MIN) / (X_MAX - X_MIN) * (RIGHT - LEFT)


def y_pos(idx: int) -> float:
    if len(ROWS) == 1:
        return (TOP + BOTTOM) / 2
    return TOP + idx * ((BOTTOM - TOP) / (len(ROWS) - 1))


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


def draw_png() -> Image.Image:
    image = Image.new("RGB", (W, H), "white")
    draw = ImageDraw.Draw(image)

    for tick in [12, 16, 20, 24, 28, 32, 36]:
        x = LEFT + (tick - X_MIN) / (X_MAX - X_MIN) * (RIGHT - LEFT)
        draw.line((x, TOP - 25, x, BOTTOM + 15), fill=GRID, width=1)
        label = f"{tick}M"
        tw, th = text_size(draw, label, F_TICK)
        draw.text((x - tw / 2, BOTTOM + 28), label, font=F_TICK, fill=TEXT)

    draw.line((LEFT, BOTTOM + 15, RIGHT, BOTTOM + 15), fill=AXIS, width=2)
    draw.text((LEFT, BOTTOM + 61), "TokenCost (million tokens, lower is better)", font=F_AXIS, fill=TEXT)

    # Small legend, kept inside the one-column figure.
    lx = LEFT
    ly = 24
    draw.ellipse((lx, ly, lx + 16, ly + 16), fill=CLOSED)
    draw.text((lx + 24, ly - 3), "Closed", font=F_LEGEND, fill=TEXT)
    draw.ellipse((lx + 120, ly, lx + 136, ly + 16), fill=OPEN)
    draw.text((lx + 144, ly - 3), "Open", font=F_LEGEND, fill=TEXT)

    for idx, (name, group, tokens) in enumerate(ROWS):
        y = y_pos(idx)
        x = x_pos(tokens)
        color = color_for(group, name)
        label_color = TEXT if name != "PaperFlow" else PAPERFLOW
        draw_right_text(draw, LEFT - 22, y, name, F_MODEL, label_color)
        draw.line((LEFT, y, RIGHT, y), fill=(242, 242, 242), width=1)
        draw.ellipse((x - 9, y - 9, x + 9, y + 9), fill=color, outline=color)
        value = f"{tokens / 1_000_000:.1f}M"
        draw.text((x + 15, y - 12), value, font=F_VALUE, fill=color)

    return image


def rgb(c: tuple[int, int, int]) -> str:
    return f"rgb({c[0]},{c[1]},{c[2]})"


def write_svg() -> None:
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">',
        '<rect width="100%" height="100%" fill="white"/>',
    ]
    for tick in [12, 16, 20, 24, 28, 32, 36]:
        x = LEFT + (tick - X_MIN) / (X_MAX - X_MIN) * (RIGHT - LEFT)
        parts.append(f'<line x1="{x}" y1="{TOP - 25}" x2="{x}" y2="{BOTTOM + 15}" stroke="{rgb(GRID)}" stroke-width="1"/>')
        parts.append(
            f'<text x="{x}" y="{BOTTOM + 50}" font-family="Times New Roman" '
            f'font-size="20" text-anchor="middle" fill="{rgb(TEXT)}">{tick}M</text>'
        )

    parts.append(f'<line x1="{LEFT}" y1="{BOTTOM + 15}" x2="{RIGHT}" y2="{BOTTOM + 15}" stroke="{rgb(AXIS)}" stroke-width="2"/>')
    parts.append(
        f'<text x="{LEFT}" y="{BOTTOM + 84}" font-family="Times New Roman" '
        f'font-size="22" font-weight="700" fill="{rgb(TEXT)}">TokenCost (million tokens, lower is better)</text>'
    )
    parts.append(f'<circle cx="{LEFT + 8}" cy="32" r="8" fill="{rgb(CLOSED)}"/>')
    parts.append(f'<text x="{LEFT + 24}" y="39" font-family="Times New Roman" font-size="21" fill="{rgb(TEXT)}">Closed</text>')
    parts.append(f'<circle cx="{LEFT + 128}" cy="32" r="8" fill="{rgb(OPEN)}"/>')
    parts.append(f'<text x="{LEFT + 144}" y="39" font-family="Times New Roman" font-size="21" fill="{rgb(TEXT)}">Open</text>')

    for idx, (name, group, tokens) in enumerate(ROWS):
        y = y_pos(idx)
        x = x_pos(tokens)
        color = color_for(group, name)
        label_color = TEXT if name != "PaperFlow" else PAPERFLOW
        parts.append(f'<line x1="{LEFT}" y1="{y}" x2="{RIGHT}" y2="{y}" stroke="rgb(242,242,242)" stroke-width="1"/>')
        parts.append(
            f'<text x="{LEFT - 22}" y="{y + 8}" font-family="Times New Roman" '
            f'font-size="24" font-weight="700" text-anchor="end" fill="{rgb(label_color)}">{name}</text>'
        )
        parts.append(f'<circle cx="{x}" cy="{y}" r="9" fill="{rgb(color)}"/>')
        parts.append(
            f'<text x="{x + 15}" y="{y + 8}" font-family="Times New Roman" '
            f'font-size="22" font-weight="700" fill="{rgb(color)}">{tokens / 1_000_000:.1f}M</text>'
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

