from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[2]


OUT_DIR = ROOT / "outputs" / "figures" / "art"
PNG_OUT = OUT_DIR / "interest_drift_paperflow_style.png"
PDF_OUT = OUT_DIR / "interest_drift_paperflow_style.pdf"
SVG_OUT = OUT_DIR / "interest_drift_paperflow_style.svg"

FONT = r"C:\Windows\Fonts\times.ttf"
BOLD = r"C:\Windows\Fonts\timesbd.ttf"

W, H = 1780, 1040
LEFT = 120
RIGHT = 1620
LABEL_W = 430
TRACK_L = LEFT + LABEL_W
TRACK_R = RIGHT - 150
ROW_TOP = 145
ROW_GAP = 82

TEXT = (35, 35, 35)
MUTED = (100, 105, 112)
LINE = (198, 205, 215)
LIGHT = (245, 247, 250)
FULL = (221, 73, 61)
WODRIFT = (91, 145, 197)
FIXED = (123, 171, 105)

METHODS = [
    ("Full PaperFlow", FULL, "F"),
    ("w/o Drift", WODRIFT, "D"),
    ("Fixed Profile", FIXED, "P"),
]

ROWS = [
    ("Static oracle", "PostDrift gNDCG@20", "up", {"Full PaperFlow": 0.6817, "w/o Drift": 0.6898, "Fixed Profile": 0.6883}),
    ("Static oracle", "PostDrift Useful@20", "up", {"Full PaperFlow": 0.2568, "w/o Drift": 0.2635, "Fixed Profile": 0.2641}),
    ("Static oracle", "PostDrift OracleR@20", "up", {"Full PaperFlow": 0.2684, "w/o Drift": 0.2807, "Fixed Profile": 0.2849}),
    ("Adaptation", "PostDrift SelNDCG@20", "up", {"Full PaperFlow": 0.7946, "w/o Drift": 0.7828, "Fixed Profile": 0.7563}),
    ("Adaptation", "NewTopicRecall@20", "up", {"Full PaperFlow": 0.8254, "w/o Drift": 0.7602, "Fixed Profile": 0.7470}),
    ("Adaptation", "OldTopicRate@20", "down", {"Full PaperFlow": 0.0557, "w/o Drift": 0.0984, "Fixed Profile": 0.0995}),
    ("Adaptation", "AdaptationDelayDays", "down", {"Full PaperFlow": 0.1667, "w/o Drift": 0.3333, "Fixed Profile": 0.5000}),
    ("Composite", "DriftAutoScore", "up", {"Full PaperFlow": 72.76, "w/o Drift": 65.53, "Fixed Profile": 59.68}),
    ("Composite", "AdaptationHumanScore", "up", {"Full PaperFlow": 68.75, "w/o Drift": 67.78, "Fixed Profile": 68.19}),
]


def load_font(path: str, size: int) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype(path, size)
    except OSError:
        return ImageFont.truetype(r"C:\Windows\Fonts\arial.ttf", size)


F_TITLE = load_font(BOLD, 36)
F_SUB = load_font(FONT, 24)
F_GROUP = load_font(BOLD, 25)
F_LABEL = load_font(BOLD, 24)
F_SMALL = load_font(FONT, 21)
F_SMALL_BOLD = load_font(BOLD, 21)
F_VALUE = load_font(BOLD, 19)


def text_size(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont) -> tuple[int, int]:
    box = draw.textbbox((0, 0), text, font=font)
    return box[2] - box[0], box[3] - box[1]


def centered_text(draw: ImageDraw.ImageDraw, x: float, y: float, text: str, font: ImageFont.FreeTypeFont, fill: tuple[int, int, int]) -> None:
    w, h = text_size(draw, text, font)
    draw.text((x - w / 2, y - h / 2), text, font=font, fill=fill)


def norm(values: dict[str, float], method: str, direction: str) -> float:
    vals = list(values.values())
    lo, hi = min(vals), max(vals)
    if hi == lo:
        score = 0.5
    else:
        score = (values[method] - lo) / (hi - lo)
    if direction == "down":
        score = 1 - score
    return score


def x_pos(score: float) -> float:
    return TRACK_L + score * (TRACK_R - TRACK_L)


def best(values: dict[str, float], direction: str) -> str:
    return min(values, key=values.get) if direction == "down" else max(values, key=values.get)


def fmt(value: float) -> str:
    if value >= 10:
        return f"{value:.2f}"
    return f"{value:.4f}".rstrip("0").rstrip(".")


def draw_legend(draw: ImageDraw.ImageDraw) -> None:
    x = 930
    y = 52
    for name, color, short in METHODS:
        draw.ellipse((x, y - 11, x + 22, y + 11), fill=color)
        draw.text((x + 32, y - 14), f"{short}: {name}", font=F_SMALL_BOLD, fill=TEXT)
        x += 240


def draw_png() -> Image.Image:
    image = Image.new("RGB", (W, H), "white")
    draw = ImageDraw.Draw(image)

    draw.text((LEFT, 34), "Interest-drift analysis", font=F_TITLE, fill=TEXT)
    draw.text((LEFT, 78), "Metrics are row-normalized so that right is better; numbers are raw metric values.", font=F_SUB, fill=MUTED)
    draw_legend(draw)

    draw.line((LEFT, 118, RIGHT, 118), fill=TEXT, width=2)
    draw.text((TRACK_L, 124), "worse", font=F_SMALL, fill=MUTED)
    draw.text((TRACK_R - 42, 124), "better", font=F_SMALL, fill=MUTED)

    last_group = None
    for idx, (group, metric, direction, values) in enumerate(ROWS):
        y = ROW_TOP + idx * ROW_GAP
        if group != last_group:
            draw.text((LEFT, y - 33), group, font=F_GROUP, fill=TEXT)
            last_group = group
        if idx % 2 == 0:
            draw.rectangle((LEFT, y - 24, RIGHT, y + 25), fill=LIGHT)

        arrow = "lower" if direction == "down" else "higher"
        draw.text((LEFT + 30, y - 14), f"{metric} {arrow}", font=F_LABEL, fill=TEXT)
        draw.line((TRACK_L, y, TRACK_R, y), fill=LINE, width=3)
        for tick in (0.0, 0.5, 1.0):
            x = x_pos(tick)
            draw.line((x, y - 7, x, y + 7), fill=LINE, width=2)

        winner = best(values, direction)
        used_positions: list[float] = []
        for name, color, short in METHODS:
            score = norm(values, name, direction)
            x = x_pos(score)
            r = 12 if name == winner else 9
            draw.ellipse((x - r, y - r, x + r, y + r), fill=color, outline="white", width=2)
            centered_text(draw, x, y + 1, short, F_SMALL_BOLD, (255, 255, 255))
            used_positions.append(x)

        for name, color, _short in METHODS:
            score = norm(values, name, direction)
            x = x_pos(score)
            label_y = y - 26 if name == "Full PaperFlow" else (y + 24 if name == "Fixed Profile" else y + 3)
            if name == "w/o Drift" and any(abs(x - x_pos(norm(values, other, direction))) < 45 for other in ("Full PaperFlow", "Fixed Profile")):
                label_y = y + 4
            centered_text(draw, x, label_y, fmt(values[name]), F_VALUE, color)

    draw.line((LEFT, ROW_TOP + len(ROWS) * ROW_GAP - 35, RIGHT, ROW_TOP + len(ROWS) * ROW_GAP - 35), fill=TEXT, width=2)
    note = "Full PaperFlow wins adaptation-oriented metrics and both composite scores, while static baselines remain strong on oracle-only ranking."
    centered_text(draw, W / 2, H - 55, note, F_SUB, MUTED)
    return image


def rgb(color: tuple[int, int, int]) -> str:
    return f"rgb({color[0]},{color[1]},{color[2]})"


def write_svg() -> None:
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">',
        '<rect width="100%" height="100%" fill="white"/>',
        f'<text x="{LEFT}" y="64" font-family="Times New Roman" font-size="36" font-weight="700" fill="{rgb(TEXT)}">Interest-drift analysis</text>',
        f'<text x="{LEFT}" y="101" font-family="Times New Roman" font-size="24" fill="{rgb(MUTED)}">Metrics are row-normalized so that right is better; numbers are raw metric values.</text>',
        f'<line x1="{LEFT}" y1="118" x2="{RIGHT}" y2="118" stroke="{rgb(TEXT)}" stroke-width="2"/>',
    ]
    x = 930
    for name, color, short in METHODS:
        parts.append(f'<circle cx="{x+11}" cy="52" r="11" fill="{rgb(color)}"/>')
        parts.append(f'<text x="{x+32}" y="60" font-family="Times New Roman" font-size="21" font-weight="700" fill="{rgb(TEXT)}">{short}: {name}</text>')
        x += 240

    last_group = None
    for idx, (group, metric, direction, values) in enumerate(ROWS):
        y = ROW_TOP + idx * ROW_GAP
        if group != last_group:
            parts.append(f'<text x="{LEFT}" y="{y-12}" font-family="Times New Roman" font-size="25" font-weight="700" fill="{rgb(TEXT)}">{group}</text>')
            last_group = group
        if idx % 2 == 0:
            parts.append(f'<rect x="{LEFT}" y="{y-24}" width="{RIGHT-LEFT}" height="49" fill="{rgb(LIGHT)}"/>')
        arrow = "lower" if direction == "down" else "higher"
        parts.append(f'<text x="{LEFT+30}" y="{y+9}" font-family="Times New Roman" font-size="24" font-weight="700" fill="{rgb(TEXT)}">{metric} {arrow}</text>')
        parts.append(f'<line x1="{TRACK_L}" y1="{y}" x2="{TRACK_R}" y2="{y}" stroke="{rgb(LINE)}" stroke-width="3"/>')
        winner = best(values, direction)
        for name, color, short in METHODS:
            score = norm(values, name, direction)
            x = x_pos(score)
            r = 12 if name == winner else 9
            parts.append(f'<circle cx="{x}" cy="{y}" r="{r}" fill="{rgb(color)}" stroke="white" stroke-width="2"/>')
            parts.append(f'<text x="{x}" y="{y+7}" font-family="Times New Roman" font-size="21" font-weight="700" text-anchor="middle" fill="white">{short}</text>')
        for name, color, _short in METHODS:
            score = norm(values, name, direction)
            x = x_pos(score)
            label_y = y - 26 if name == "Full PaperFlow" else (y + 24 if name == "Fixed Profile" else y + 3)
            parts.append(f'<text x="{x}" y="{label_y+7}" font-family="Times New Roman" font-size="19" font-weight="700" text-anchor="middle" fill="{rgb(color)}">{fmt(values[name])}</text>')

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


