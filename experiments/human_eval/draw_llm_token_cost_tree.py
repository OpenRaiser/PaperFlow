from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[2]


OUT_DIR = ROOT / "outputs" / "figures" / "art"
FIGURE_DIR = ROOT / "outputs" / "figures" / "pdf"

PNG_OUT = OUT_DIR / "llm_token_cost_tree.png"
PDF_OUT = OUT_DIR / "llm_token_cost_tree.pdf"
SVG_OUT = OUT_DIR / "llm_token_cost_tree.svg"
FIGURE_PDF_OUT = FIGURE_DIR / "llm_token_cost_tree.pdf"

FONT = r"C:\Windows\Fonts\times.ttf"
BOLD = r"C:\Windows\Fonts\timesbd.ttf"

W, H = 930, 960
ROOT_X = 33
GROUP_X = 190
LEAF_X = 305
VALUE_X = 805
MAX_BAR_W = 260

TEXT = (34, 34, 34)
MUTED = (106, 106, 106)
LINE = (170, 170, 170)
CLOSED = (54, 122, 84)
OPEN = (82, 132, 190)
PAPERFLOW = (36, 142, 73)
BAR_BG = (235, 235, 235)

CLOSED_ROWS = [
    ("Grok 4.3", 14_644_902),
    ("GPT-5.4", 16_132_608),
    ("PaperFlow", 17_413_607),
    ("Gemini 3.1 Pro", 20_195_805),
    ("Qwen3.6-Max", 22_051_712),
    ("Qwen3.6-Plus", 23_746_290),
    ("Qwen3.5-Plus", 25_149_755),
    ("Claude Sonnet 4.6", 36_522_181),
]

OPEN_ROWS = [
    ("Kimi K2.6", 13_039_358),
    ("MiniMax-M2.7", 14_709_207),
    ("MiMo-V2.5-Pro", 15_463_947),
    ("DeepSeek-V4-Flash", 15_954_997),
    ("GLM-5.1", 20_797_806),
    ("DeepSeek-V4-Pro", 23_851_830),
]

ALL_VALUES = [v for _, v in CLOSED_ROWS + OPEN_ROWS]
MAX_VALUE = max(ALL_VALUES)


def load_font(path: str, size: int) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype(path, size)
    except OSError:
        return ImageFont.truetype(r"C:\Windows\Fonts\arial.ttf", size)


F_ROOT = load_font(BOLD, 30)
F_GROUP = load_font(BOLD, 27)
F_MODEL = load_font(BOLD, 24)
F_VALUE = load_font(BOLD, 22)


def text_size(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont) -> tuple[int, int]:
    box = draw.textbbox((0, 0), text, font=font)
    return box[2] - box[0], box[3] - box[1]


def centered_node(
    draw: ImageDraw.ImageDraw,
    x: float,
    y: float,
    text: str,
    font: ImageFont.FreeTypeFont,
    fill: tuple[int, int, int],
) -> tuple[int, int, int, int]:
    tw, th = text_size(draw, text, font)
    pad_x, pad_y = 18, 8
    box = (
        round(x - tw / 2 - pad_x),
        round(y - th / 2 - pad_y),
        round(x + tw / 2 + pad_x),
        round(y + th / 2 + pad_y),
    )
    draw.rounded_rectangle(box, radius=8, outline=fill, width=2, fill="white")
    draw.text((x - tw / 2, y - th / 2 - 1), text, font=font, fill=fill)
    return box


def draw_leaf(
    draw: ImageDraw.ImageDraw,
    y: float,
    name: str,
    value: int,
    color: tuple[int, int, int],
    highlight: bool = False,
) -> None:
    label_color = PAPERFLOW if highlight else TEXT
    draw.text((LEAF_X, y - 14), name, font=F_MODEL, fill=label_color)

    bar_x = VALUE_X - MAX_BAR_W - 20
    bar_y = y - 9
    bar_w = round((value / MAX_VALUE) * MAX_BAR_W)
    draw.rounded_rectangle((bar_x, bar_y, bar_x + MAX_BAR_W, bar_y + 18), radius=5, fill=BAR_BG)
    draw.rounded_rectangle((bar_x, bar_y, bar_x + bar_w, bar_y + 18), radius=5, fill=color)

    value_text = f"{value / 1_000_000:.1f}M"
    draw.text((VALUE_X, y - 13), value_text, font=F_VALUE, fill=color)


def draw_branch(
    draw: ImageDraw.ImageDraw,
    group_y: float,
    leaf_ys: list[float],
    color: tuple[int, int, int],
) -> None:
    stem_x = GROUP_X + 84
    leaf_join_x = LEAF_X - 26
    draw.line((ROOT_X + 72, group_y, GROUP_X - 64, group_y), fill=LINE, width=2)
    draw.line((stem_x, min(leaf_ys), stem_x, max(leaf_ys)), fill=LINE, width=2)
    draw.line((GROUP_X + 72, group_y, stem_x, group_y), fill=LINE, width=2)
    for y in leaf_ys:
        draw.line((stem_x, y, leaf_join_x, y), fill=LINE, width=2)
        draw.ellipse((leaf_join_x - 5, y - 5, leaf_join_x + 5, y + 5), fill=color)


def draw_png() -> Image.Image:
    image = Image.new("RGB", (W, H), "white")
    draw = ImageDraw.Draw(image)

    root_y = 72
    closed_group_y = 170
    open_group_y = 610
    closed_ys = [220 + idx * 44 for idx in range(len(CLOSED_ROWS))]
    open_ys = [660 + idx * 44 for idx in range(len(OPEN_ROWS))]

    # Draw tree edges before nodes so node labels stay clean.
    draw.line((ROOT_X + 72, root_y + 27, ROOT_X + 72, open_group_y), fill=LINE, width=2)
    draw_branch(draw, closed_group_y, closed_ys, CLOSED)
    draw_branch(draw, open_group_y, open_ys, OPEN)

    centered_node(draw, ROOT_X + 72, root_y, "TokenCost", F_ROOT, TEXT)
    centered_node(draw, GROUP_X, closed_group_y, "Closed API", F_GROUP, CLOSED)
    centered_node(draw, GROUP_X, open_group_y, "Open / open-access", F_GROUP, OPEN)

    for y, (name, value) in zip(closed_ys, CLOSED_ROWS):
        draw_leaf(draw, y, name, value, PAPERFLOW if name == "PaperFlow" else CLOSED, name == "PaperFlow")

    for y, (name, value) in zip(open_ys, OPEN_ROWS):
        draw_leaf(draw, y, name, value, OPEN)

    return image


def rgb(c: tuple[int, int, int]) -> str:
    return f"rgb({c[0]},{c[1]},{c[2]})"


def svg_node(x: float, y: float, text: str, font_size: int, color: tuple[int, int, int]) -> list[str]:
    # Fixed-size nodes are sufficient here because all labels are known.
    widths = {"TokenCost": 150, "Closed API": 160, "Open / open-access": 245}
    w = widths[text]
    h = 44
    return [
        f'<rect x="{x - w / 2}" y="{y - h / 2}" width="{w}" height="{h}" rx="8" fill="white" stroke="{rgb(color)}" stroke-width="2"/>',
        f'<text x="{x}" y="{y + 8}" font-family="Times New Roman" font-size="{font_size}" font-weight="700" text-anchor="middle" fill="{rgb(color)}">{text}</text>',
    ]


def write_svg() -> None:
    root_y = 72
    closed_group_y = 170
    open_group_y = 610
    closed_ys = [220 + idx * 44 for idx in range(len(CLOSED_ROWS))]
    open_ys = [660 + idx * 44 for idx in range(len(OPEN_ROWS))]
    stem_x = GROUP_X + 84
    leaf_join_x = LEAF_X - 26
    bar_x = VALUE_X - MAX_BAR_W - 20

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">',
        '<rect width="100%" height="100%" fill="white"/>',
        f'<line x1="{ROOT_X + 72}" y1="{root_y + 27}" x2="{ROOT_X + 72}" y2="{open_group_y}" stroke="{rgb(LINE)}" stroke-width="2"/>',
    ]

    for group_y, leaf_ys, color in [(closed_group_y, closed_ys, CLOSED), (open_group_y, open_ys, OPEN)]:
        parts.append(f'<line x1="{ROOT_X + 72}" y1="{group_y}" x2="{GROUP_X - 64}" y2="{group_y}" stroke="{rgb(LINE)}" stroke-width="2"/>')
        parts.append(f'<line x1="{GROUP_X + 72}" y1="{group_y}" x2="{stem_x}" y2="{group_y}" stroke="{rgb(LINE)}" stroke-width="2"/>')
        parts.append(f'<line x1="{stem_x}" y1="{min(leaf_ys)}" x2="{stem_x}" y2="{max(leaf_ys)}" stroke="{rgb(LINE)}" stroke-width="2"/>')
        for y in leaf_ys:
            parts.append(f'<line x1="{stem_x}" y1="{y}" x2="{leaf_join_x}" y2="{y}" stroke="{rgb(LINE)}" stroke-width="2"/>')
            parts.append(f'<circle cx="{leaf_join_x}" cy="{y}" r="5" fill="{rgb(color)}"/>')

    parts.extend(svg_node(ROOT_X + 72, root_y, "TokenCost", 30, TEXT))
    parts.extend(svg_node(GROUP_X, closed_group_y, "Closed API", 27, CLOSED))
    parts.extend(svg_node(GROUP_X, open_group_y, "Open / open-access", 27, OPEN))

    for y, (name, value) in zip(closed_ys, CLOSED_ROWS):
        color = PAPERFLOW if name == "PaperFlow" else CLOSED
        label_color = PAPERFLOW if name == "PaperFlow" else TEXT
        bar_w = round((value / MAX_VALUE) * MAX_BAR_W)
        parts.append(f'<text x="{LEAF_X}" y="{y + 8}" font-family="Times New Roman" font-size="24" font-weight="700" fill="{rgb(label_color)}">{name}</text>')
        parts.append(f'<rect x="{bar_x}" y="{y - 9}" width="{MAX_BAR_W}" height="18" rx="5" fill="{rgb(BAR_BG)}"/>')
        parts.append(f'<rect x="{bar_x}" y="{y - 9}" width="{bar_w}" height="18" rx="5" fill="{rgb(color)}"/>')
        parts.append(f'<text x="{VALUE_X}" y="{y + 8}" font-family="Times New Roman" font-size="22" font-weight="700" fill="{rgb(color)}">{value / 1_000_000:.1f}M</text>')

    for y, (name, value) in zip(open_ys, OPEN_ROWS):
        bar_w = round((value / MAX_VALUE) * MAX_BAR_W)
        parts.append(f'<text x="{LEAF_X}" y="{y + 8}" font-family="Times New Roman" font-size="24" font-weight="700" fill="{rgb(TEXT)}">{name}</text>')
        parts.append(f'<rect x="{bar_x}" y="{y - 9}" width="{MAX_BAR_W}" height="18" rx="5" fill="{rgb(BAR_BG)}"/>')
        parts.append(f'<rect x="{bar_x}" y="{y - 9}" width="{bar_w}" height="18" rx="5" fill="{rgb(OPEN)}"/>')
        parts.append(f'<text x="{VALUE_X}" y="{y + 8}" font-family="Times New Roman" font-size="22" font-weight="700" fill="{rgb(OPEN)}">{value / 1_000_000:.1f}M</text>')

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

