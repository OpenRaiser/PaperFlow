from __future__ import annotations

import csv
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "scripts" / "human_eval" / "results" / "model_human_eval" / "summary.csv"
OUT_DIR = ROOT / "outputs" / "figures" / "art"

PNG_OUT = OUT_DIR / "model_auto_human_ggbench_minimal.png"
PDF_OUT = OUT_DIR / "model_auto_human_ggbench_minimal.pdf"
SVG_OUT = OUT_DIR / "model_auto_human_ggbench_minimal.svg"
CSV_OUT = OUT_DIR / "model_auto_human_ggbench_minimal_data.csv"

FONT = r"C:\Windows\Fonts\arial.ttf"
BOLD = r"C:\Windows\Fonts\arialbd.ttf"

W, H = 1450, 930
PLOT_L, PLOT_T = 150, 95
PLOT_R, PLOT_B = 1080, 760
X_MIN, X_MAX = 63.5, 65.1
Y_MIN, Y_MAX = 65.0, 96.0

TEXT = (35, 43, 54)
MUTED = (92, 102, 116)
GRID = (224, 229, 235)
AXIS = (64, 73, 88)
BLUE = (70, 137, 180)
BLUE_LIGHT = (148, 194, 225)
ORANGE = (241, 180, 94)
GREEN = (154, 190, 105)

DISPLAY_NAMES = {
    "gpt5_4": "GPT-5.4",
    "gemini_3_1_pro_preview": "Gemini 3.1",
    "grok_4_3": "Grok 4.3",
    "kimi_k2_6": "Kimi K2.6",
    "deepseek_v4_flash": "DeepSeek-V4-Flash",
    "claude_sonnet_4_6": "Claude Sonnet 4.6",
    "paperflow_default": "PaperFlow",
}

LABEL_KEYS = {
    "grok_4_3": (10, -28),
    "kimi_k2_6": (-78, -34),
    "deepseek_v4_flash": (10, -16),
    "claude_sonnet_4_6": (-148, 12),
    "paperflow_default": (10, 10),
    "gemini_3_1_pro_preview": (10, 14),
    "gpt5_4": (-86, 12),
}


def load_font(path: str, size: int) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype(path, size)
    except OSError:
        return ImageFont.load_default()


F_AXIS = load_font(BOLD, 28)
F_TICK = load_font(FONT, 23)
F_TEXT = load_font(BOLD, 22)
F_NOTE = load_font(FONT, 24)
F_LEGEND = load_font(FONT, 22)


def read_rows() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    with SOURCE.open("r", encoding="utf-8-sig", newline="") as fh:
        for row in csv.DictReader(fh):
            rows.append(
                {
                    "key": row["model_key"],
                    "group": "Closed" if row["group"].startswith("Closed") else "Open",
                    "auto": float(row["ModelAutoScore"]),
                    "human": float(row["ModelHumanScore"]),
                }
            )
    return rows


def x_pos(x: float) -> float:
    return PLOT_L + (x - X_MIN) / (X_MAX - X_MIN) * (PLOT_R - PLOT_L)


def y_pos(y: float) -> float:
    return PLOT_B - (y - Y_MIN) / (Y_MAX - Y_MIN) * (PLOT_B - PLOT_T)


def pearson(xs: list[float], ys: list[float]) -> float:
    x_bar, y_bar = sum(xs) / len(xs), sum(ys) / len(ys)
    num = sum((x - x_bar) * (y - y_bar) for x, y in zip(xs, ys))
    den_x = math.sqrt(sum((x - x_bar) ** 2 for x in xs))
    den_y = math.sqrt(sum((y - y_bar) ** 2 for y in ys))
    return num / (den_x * den_y)


def regression(xs: list[float], ys: list[float]) -> tuple[float, float]:
    x_bar, y_bar = sum(xs) / len(xs), sum(ys) / len(ys)
    slope = sum((x - x_bar) * (y - y_bar) for x, y in zip(xs, ys)) / sum((x - x_bar) ** 2 for x in xs)
    return slope, y_bar - slope * x_bar


def text_size(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont) -> tuple[int, int]:
    box = draw.textbbox((0, 0), text, font=font)
    return box[2] - box[0], box[3] - box[1]


def center_text(draw: ImageDraw.ImageDraw, x: float, y: float, text: str, font: ImageFont.FreeTypeFont, fill: tuple[int, int, int]) -> None:
    width, height = text_size(draw, text, font)
    draw.text((x - width / 2, y - height / 2), text, font=font, fill=fill)


def draw_vertical_label(image: Image.Image, text: str) -> None:
    layer = Image.new("RGBA", (460, 58), (255, 255, 255, 0))
    draw = ImageDraw.Draw(layer)
    center_text(draw, 230, 29, text, F_AXIS, TEXT)
    rotated = layer.rotate(90, expand=True, resample=Image.Resampling.BICUBIC)
    image.paste(rotated, (38, 285), rotated)


def draw_png(rows: list[dict[str, object]]) -> Image.Image:
    image = Image.new("RGB", (W, H), "white")
    draw = ImageDraw.Draw(image)

    draw.rectangle((PLOT_L, PLOT_T, PLOT_R, PLOT_B), outline=AXIS, width=2)

    for tick in [63.5, 64.0, 64.5, 65.0]:
        x = x_pos(tick)
        draw.line((x, PLOT_T, x, PLOT_B), fill=GRID, width=1)
        center_text(draw, x, PLOT_B + 31, f"{tick:.1f}", F_TICK, MUTED)

    for tick in [65, 70, 75, 80, 85, 90, 95]:
        y = y_pos(tick)
        draw.line((PLOT_L, y, PLOT_R, y), fill=GRID, width=1)
        center_text(draw, PLOT_L - 36, y, str(tick), F_TICK, MUTED)

    xs = [float(row["auto"]) for row in rows]
    ys = [float(row["human"]) for row in rows]
    slope, intercept = regression(xs, ys)
    x1, x2 = min(xs), max(xs)
    draw.line((x_pos(x1), y_pos(slope * x1 + intercept), x_pos(x2), y_pos(slope * x2 + intercept)), fill=BLUE_LIGHT, width=5)

    for row in rows:
        x, y = x_pos(float(row["auto"])), y_pos(float(row["human"]))
        fill = ORANGE if row["group"] == "Closed" else GREEN
        draw.ellipse((x - 11, y - 11, x + 11, y + 11), fill=fill, outline=AXIS, width=2)

    for row in rows:
        key = str(row["key"])
        if key not in LABEL_KEYS:
            continue
        x, y = x_pos(float(row["auto"])), y_pos(float(row["human"]))
        ox, oy = LABEL_KEYS[key]
        label = DISPLAY_NAMES[key]
        draw.text((x + ox, y + oy), label, font=F_TEXT, fill=TEXT)

    center_text(draw, (PLOT_L + PLOT_R) / 2, PLOT_B + 78, "ModelAutoScore", F_AXIS, TEXT)
    draw_vertical_label(image, "ModelHumanScore")

    r = pearson(xs, ys)
    draw.text((PLOT_L + 565, PLOT_B - 115), f"Pearson's r = {r:.4f}", font=F_NOTE, fill=TEXT)

    legend_x, legend_y = PLOT_R + 42, PLOT_T + 30
    draw.ellipse((legend_x, legend_y, legend_x + 22, legend_y + 22), fill=ORANGE, outline=AXIS, width=2)
    draw.text((legend_x + 32, legend_y - 2), "Closed API", font=F_LEGEND, fill=MUTED)
    draw.ellipse((legend_x, legend_y + 44, legend_x + 22, legend_y + 66), fill=GREEN, outline=AXIS, width=2)
    draw.text((legend_x + 32, legend_y + 42), "Open / open-access", font=F_LEGEND, fill=MUTED)

    return image


def write_svg(rows: list[dict[str, object]]) -> None:
    xs = [float(row["auto"]) for row in rows]
    ys = [float(row["human"]) for row in rows]
    slope, intercept = regression(xs, ys)
    x1, x2 = min(xs), max(xs)
    r = pearson(xs, ys)

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">',
        '<rect width="100%" height="100%" fill="white"/>',
        f'<rect x="{PLOT_L}" y="{PLOT_T}" width="{PLOT_R-PLOT_L}" height="{PLOT_B-PLOT_T}" fill="none" stroke="rgb{AXIS}" stroke-width="2"/>',
    ]
    for tick in [63.5, 64.0, 64.5, 65.0]:
        x = x_pos(tick)
        parts.append(f'<line x1="{x}" y1="{PLOT_T}" x2="{x}" y2="{PLOT_B}" stroke="rgb{GRID}" stroke-width="1"/>')
        parts.append(f'<text x="{x}" y="{PLOT_B+38}" font-size="23" text-anchor="middle" fill="rgb{MUTED}">{tick:.1f}</text>')
    for tick in [65, 70, 75, 80, 85, 90, 95]:
        y = y_pos(tick)
        parts.append(f'<line x1="{PLOT_L}" y1="{y}" x2="{PLOT_R}" y2="{y}" stroke="rgb{GRID}" stroke-width="1"/>')
        parts.append(f'<text x="{PLOT_L-35}" y="{y+8}" font-size="23" text-anchor="middle" fill="rgb{MUTED}">{tick}</text>')

    parts.append(
        f'<line x1="{x_pos(x1)}" y1="{y_pos(slope*x1+intercept)}" x2="{x_pos(x2)}" y2="{y_pos(slope*x2+intercept)}" '
        f'stroke="rgb{BLUE_LIGHT}" stroke-width="5"/>'
    )
    for row in rows:
        fill = ORANGE if row["group"] == "Closed" else GREEN
        parts.append(
            f'<circle cx="{x_pos(float(row["auto"]))}" cy="{y_pos(float(row["human"]))}" r="11" '
            f'fill="rgb{fill}" stroke="rgb{AXIS}" stroke-width="2"/>'
        )
    for row in rows:
        key = str(row["key"])
        if key not in LABEL_KEYS:
            continue
        x, y = x_pos(float(row["auto"])), y_pos(float(row["human"]))
        ox, oy = LABEL_KEYS[key]
        parts.append(
            f'<text x="{x+ox}" y="{y+oy+20}" font-size="22" font-weight="700" fill="rgb{TEXT}">{DISPLAY_NAMES[key]}</text>'
        )
    parts.append(f'<text x="{(PLOT_L+PLOT_R)/2}" y="{PLOT_B+86}" font-size="28" font-weight="700" text-anchor="middle" fill="rgb{TEXT}">ModelAutoScore</text>')
    parts.append(f'<text x="58" y="{(PLOT_T+PLOT_B)/2}" transform="rotate(-90 58 {(PLOT_T+PLOT_B)/2})" font-size="28" font-weight="700" text-anchor="middle" fill="rgb{TEXT}">ModelHumanScore</text>')
    parts.append(f'<text x="{PLOT_L+565}" y="{PLOT_B-96}" font-size="24" fill="rgb{TEXT}">Pearson&apos;s r = {r:.4f}</text>')
    legend_x, legend_y = PLOT_R + 42, PLOT_T + 30
    parts.append(f'<circle cx="{legend_x+11}" cy="{legend_y+11}" r="11" fill="rgb{ORANGE}" stroke="rgb{AXIS}" stroke-width="2"/>')
    parts.append(f'<text x="{legend_x+32}" y="{legend_y+18}" font-size="22" fill="rgb{MUTED}">Closed API</text>')
    parts.append(f'<circle cx="{legend_x+11}" cy="{legend_y+55}" r="11" fill="rgb{GREEN}" stroke="rgb{AXIS}" stroke-width="2"/>')
    parts.append(f'<text x="{legend_x+32}" y="{legend_y+62}" font-size="22" fill="rgb{MUTED}">Open / open-access</text>')
    parts.append("</svg>")
    SVG_OUT.write_text("\n".join(parts), encoding="utf-8")


def write_csv(rows: list[dict[str, object]]) -> None:
    with CSV_OUT.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=["model_key", "group", "ModelAutoScore", "ModelHumanScore"])
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "model_key": row["key"],
                    "group": row["group"],
                    "ModelAutoScore": f'{float(row["auto"]):.2f}',
                    "ModelHumanScore": f'{float(row["human"]):.2f}',
                }
            )


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    rows = read_rows()
    image = draw_png(rows)
    image.save(PNG_OUT, dpi=(300, 300))
    image.save(PDF_OUT, "PDF", resolution=300.0)
    write_svg(rows)
    write_csv(rows)
    print(PNG_OUT)
    print(PDF_OUT)
    print(SVG_OUT)


if __name__ == "__main__":
    main()

