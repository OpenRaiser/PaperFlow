from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[2]


OUT_DIR = ROOT / "outputs" / "figures" / "art"
PNG_OUT = OUT_DIR / "interest_drift_analysis_panel.png"
PDF_OUT = OUT_DIR / "interest_drift_analysis_panel.pdf"
SVG_OUT = OUT_DIR / "interest_drift_analysis_panel.svg"

FONT = r"C:\Windows\Fonts\arial.ttf"
BOLD = r"C:\Windows\Fonts\arialbd.ttf"

W, H = 2200, 1420
PLOT_L, PLOT_R = 720, 1840
ROW_START = 250
ROW_GAP = 108

TEXT = (42, 50, 62)
MUTED = (104, 113, 126)
LIGHT = (225, 231, 238)
GRID = (236, 240, 245)
FULL = (235, 91, 79)
WODRIFT = (104, 158, 204)
FIXED = (137, 183, 118)

METHODS = [
    ("Full PaperFlow", FULL),
    ("w/o Drift", WODRIFT),
    ("Fixed Profile", FIXED),
]

ROWS = [
    ("Static oracle", "PostDrift gNDCG@20", "up", {"Full PaperFlow": 0.6817, "w/o Drift": 0.6898, "Fixed Profile": 0.6883}),
    ("Static oracle", "PostDrift Useful@20", "up", {"Full PaperFlow": 0.2568, "w/o Drift": 0.2635, "Fixed Profile": 0.2641}),
    ("Static oracle", "PostDrift OracleR@20", "up", {"Full PaperFlow": 0.2684, "w/o Drift": 0.2807, "Fixed Profile": 0.2849}),
    ("Adaptation", "PostDrift SelNDCG@20", "up", {"Full PaperFlow": 0.7946, "w/o Drift": 0.7828, "Fixed Profile": 0.7563}),
    ("Adaptation", "NewTopicRecall@20", "up", {"Full PaperFlow": 0.8254, "w/o Drift": 0.7602, "Fixed Profile": 0.7470}),
    ("Adaptation", "OldTopicRate@20", "down", {"Full PaperFlow": 0.0557, "w/o Drift": 0.0984, "Fixed Profile": 0.0995}),
    ("Adaptation", "Adapt. Delay (days)", "down", {"Full PaperFlow": 0.1667, "w/o Drift": 0.3333, "Fixed Profile": 0.5000}),
    ("Composite", "DriftAutoScore", "up", {"Full PaperFlow": 72.76, "w/o Drift": 65.53, "Fixed Profile": 59.68}),
    ("Composite", "AdaptHumanScore", "up", {"Full PaperFlow": 68.75, "w/o Drift": 67.78, "Fixed Profile": 68.19}),
]


def load_font(path: str, size: int) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype(path, size)
    except OSError:
        return ImageFont.load_default()


F_TITLE = load_font(BOLD, 44)
F_SUB = load_font(FONT, 26)
F_GROUP = load_font(BOLD, 28)
F_LABEL = load_font(BOLD, 28)
F_SMALL = load_font(FONT, 23)
F_SMALL_BOLD = load_font(BOLD, 23)
F_VALUE = load_font(BOLD, 22)


def text_size(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont) -> tuple[int, int]:
    box = draw.textbbox((0, 0), text, font=font)
    return box[2] - box[0], box[3] - box[1]


def centered_text(draw: ImageDraw.ImageDraw, x: float, y: float, text: str, font: ImageFont.FreeTypeFont, fill: tuple[int, int, int]) -> None:
    w, h = text_size(draw, text, font)
    draw.text((x - w / 2, y - h / 2), text, font=font, fill=fill)


def norm_x(values: dict[str, float], method: str, direction: str) -> float:
    vals = list(values.values())
    lo, hi = min(vals), max(vals)
    if hi == lo:
        score = 0.5
    else:
        score = (values[method] - lo) / (hi - lo)
    if direction == "down":
        score = 1 - score
    return PLOT_L + score * (PLOT_R - PLOT_L)


def fmt_value(value: float) -> str:
    if value >= 10:
        return f"{value:.2f}"
    return f"{value:.4f}".rstrip("0").rstrip(".")


def best_method(values: dict[str, float], direction: str) -> str:
    if direction == "down":
        return min(values, key=lambda key: values[key])
    return max(values, key=lambda key: values[key])


def draw_chip(draw: ImageDraw.ImageDraw, x: int, y: int, label: str, color: tuple[int, int, int]) -> None:
    draw.rounded_rectangle((x, y - 18, x + 42, y + 18), radius=9, fill=color)
    draw.text((x + 56, y - 16), label, font=F_SMALL_BOLD, fill=TEXT)


def draw_png() -> Image.Image:
    image = Image.new("RGB", (W, H), "white")
    draw = ImageDraw.Draw(image)

    draw.text((120, 58), "Interest-Drift Analysis", font=F_TITLE, fill=TEXT)
    draw.text(
        (120, 113),
        "Each row normalizes one metric so that the right side is better; labels show raw values.",
        font=F_SUB,
        fill=MUTED,
    )

    legend_x = 1240
    for idx, (method, color) in enumerate(METHODS):
        draw_chip(draw, legend_x + idx * 290, 82, method, color)

    draw.text((PLOT_L, 168), "worse", font=F_SMALL, fill=MUTED)
    draw.text((PLOT_R - 50, 168), "better", font=F_SMALL, fill=MUTED)
    draw.line((PLOT_L + 95, 181, PLOT_R - 75, 181), fill=LIGHT, width=3)
    draw.polygon([(PLOT_R - 75, 181), (PLOT_R - 93, 171), (PLOT_R - 93, 191)], fill=LIGHT)

    last_group = None
    for idx, (group, label, direction, values) in enumerate(ROWS):
        y = ROW_START + idx * ROW_GAP
        if group != last_group:
            if idx:
                draw.line((100, y - 54, W - 110, y - 54), fill=GRID, width=2)
            draw.text((100, y - 64), group, font=F_GROUP, fill=MUTED)
            last_group = group

        if idx % 2 == 0:
            draw.rounded_rectangle((82, y - 33, W - 92, y + 34), radius=12, fill=(250, 252, 254))

        arrow = "lower" if direction == "down" else "higher"
        draw.text((140, y - 18), f"{label} {arrow}", font=F_LABEL, fill=TEXT)
        draw.line((PLOT_L, y, PLOT_R, y), fill=LIGHT, width=5)
        for tick in [0.0, 0.5, 1.0]:
            x = PLOT_L + tick * (PLOT_R - PLOT_L)
            draw.line((x, y - 9, x, y + 9), fill=(198, 207, 218), width=2)

        winner = best_method(values, direction)
        for method, color in METHODS:
            x = norm_x(values, method, direction)
            radius = 15 if method == winner else 12
            draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=color, outline="white", width=3)

        # Value labels are staggered to avoid collisions when methods are close.
        offsets = {"Full PaperFlow": -34, "w/o Drift": 11, "Fixed Profile": 44}
        for method, color in METHODS:
            x = norm_x(values, method, direction)
            y_text = y + offsets[method]
            value_text = fmt_value(values[method])
            tw, _ = text_size(draw, value_text, F_VALUE)
            draw.text((x - tw / 2, y_text - 11), value_text, font=F_VALUE, fill=color)

    note = "Full PaperFlow leads on adaptation metrics and both composite scores; static baselines remain competitive on oracle-only metrics."
    centered_text(draw, W / 2, H - 68, note, F_SUB, MUTED)
    return image


def rgb(color: tuple[int, int, int]) -> str:
    return f"rgb({color[0]},{color[1]},{color[2]})"


def write_svg() -> None:
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">',
        '<rect width="100%" height="100%" fill="white"/>',
        f'<text x="120" y="96" font-family="Arial" font-size="44" font-weight="700" fill="{rgb(TEXT)}">Interest-Drift Analysis</text>',
        f'<text x="120" y="140" font-family="Arial" font-size="26" fill="{rgb(MUTED)}">Each row normalizes one metric so that the right side is better; labels show raw values.</text>',
    ]
    legend_x = 1240
    for idx, (method, color) in enumerate(METHODS):
        x = legend_x + idx * 290
        parts.append(f'<rect x="{x}" y="64" width="42" height="36" rx="9" fill="{rgb(color)}"/>')
        parts.append(f'<text x="{x+56}" y="91" font-family="Arial" font-size="23" font-weight="700" fill="{rgb(TEXT)}">{method}</text>')
    parts.append(f'<text x="{PLOT_L}" y="176" font-family="Arial" font-size="23" fill="{rgb(MUTED)}">worse</text>')
    parts.append(f'<text x="{PLOT_R-50}" y="176" font-family="Arial" font-size="23" fill="{rgb(MUTED)}">better</text>')
    parts.append(f'<line x1="{PLOT_L+95}" y1="181" x2="{PLOT_R-75}" y2="181" stroke="{rgb(LIGHT)}" stroke-width="3"/>')

    last_group = None
    for idx, (group, label, direction, values) in enumerate(ROWS):
        y = ROW_START + idx * ROW_GAP
        if group != last_group:
            if idx:
                parts.append(f'<line x1="100" y1="{y-54}" x2="{W-110}" y2="{y-54}" stroke="{rgb(GRID)}" stroke-width="2"/>')
            parts.append(f'<text x="100" y="{y-34}" font-family="Arial" font-size="28" font-weight="700" fill="{rgb(MUTED)}">{group}</text>')
            last_group = group
        if idx % 2 == 0:
            parts.append(f'<rect x="82" y="{y-33}" width="{W-174}" height="67" rx="12" fill="rgb(250,252,254)"/>')
        arrow = "lower" if direction == "down" else "higher"
        parts.append(f'<text x="140" y="{y+10}" font-family="Arial" font-size="28" font-weight="700" fill="{rgb(TEXT)}">{label} {arrow}</text>')
        parts.append(f'<line x1="{PLOT_L}" y1="{y}" x2="{PLOT_R}" y2="{y}" stroke="{rgb(LIGHT)}" stroke-width="5"/>')
        winner = best_method(values, direction)
        for method, color in METHODS:
            x = norm_x(values, method, direction)
            radius = 15 if method == winner else 12
            parts.append(f'<circle cx="{x}" cy="{y}" r="{radius}" fill="{rgb(color)}" stroke="white" stroke-width="3"/>')
        offsets = {"Full PaperFlow": -34, "w/o Drift": 11, "Fixed Profile": 44}
        for method, color in METHODS:
            x = norm_x(values, method, direction)
            y_text = y + offsets[method]
            parts.append(
                f'<text x="{x}" y="{y_text+8}" font-family="Arial" font-size="22" font-weight="700" '
                f'text-anchor="middle" fill="{rgb(color)}">{fmt_value(values[method])}</text>'
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


