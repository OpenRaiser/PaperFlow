from __future__ import annotations

import csv
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "scripts" / "human_eval" / "results" / "model_human_eval" / "summary.csv"
OUT_DIR = ROOT / "outputs" / "figures" / "art"
PNG_OUT = OUT_DIR / "model_auto_human_ggbench_style.png"
PDF_OUT = OUT_DIR / "model_auto_human_ggbench_style.pdf"
CSV_OUT = OUT_DIR / "model_auto_human_ggbench_style_data.csv"

FONT = r"C:\Windows\Fonts\arial.ttf"
BOLD = r"C:\Windows\Fonts\arialbd.ttf"

W, H = 2100, 1500
PLOT_L, PLOT_T = 300, 185
PLOT_R, PLOT_B = 1540, 1230
X_MIN, X_MAX = 63.5, 65.1
Y_MIN, Y_MAX = 65.0, 96.0

COLORS = {
    "text": (38, 46, 58),
    "muted": (105, 113, 126),
    "grid": (225, 230, 236),
    "axis": (140, 150, 164),
    "closed": (248, 211, 160),
    "closed_edge": (190, 127, 47),
    "open": (220, 235, 192),
    "open_edge": (109, 145, 67),
    "line": (128, 173, 205),
    "line_soft": (128, 173, 205, 90),
}

DISPLAY_NAMES = {
    "gpt5_4": "GPT-5.4",
    "qwen3_5_plus": "Qwen3.5-Plus",
    "gemini_3_1_pro_preview": "Gemini 3.1 Pro Preview",
    "claude_sonnet_4_6": "Claude Sonnet 4.6",
    "qwen3_6_plus": "Qwen3.6-Plus",
    "qwen3_6_max_preview": "Qwen3.6-Max-Preview",
    "grok_4_3": "Grok 4.3",
    "paperflow_default": "PaperFlow",
    "mimo2_5pro": "MiMo-V2.5-Pro",
    "deepseek_v4_pro": "DeepSeek-V4-Pro",
    "deepseek_v4_flash": "DeepSeek-V4-Flash",
    "kimi_k2_6": "Kimi K2.6",
    "glm_5_1": "GLM-5.1",
    "minimax_m2_7": "MiniMax-M2.7",
}

LABEL_OFFSETS = {
    "grok_4_3": (18, -26),
    "kimi_k2_6": (-110, -48),
    "deepseek_v4_flash": (16, -16),
    "claude_sonnet_4_6": (-174, 18),
    "minimax_m2_7": (20, 20),
    "qwen3_6_plus": (-118, 18),
    "paperflow_default": (18, 24),
    "deepseek_v4_pro": (-196, 22),
    "glm_5_1": (-104, 30),
    "qwen3_6_max_preview": (20, -38),
    "qwen3_5_plus": (-174, -44),
    "mimo2_5pro": (22, 8),
    "gemini_3_1_pro_preview": (24, 20),
    "gpt5_4": (-110, 22),
}


def font(path: str, size: int) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype(path, size)
    except OSError:
        return ImageFont.load_default()


F_TITLE = font(BOLD, 42)
F_AXIS = font(BOLD, 30)
F_TICK = font(FONT, 25)
F_LABEL = font(BOLD, 22)
F_NOTE = font(FONT, 27)
F_NOTE_BOLD = font(BOLD, 29)
F_LEGEND = font(BOLD, 26)


def text_size(draw: ImageDraw.ImageDraw, text: str, fnt: ImageFont.FreeTypeFont) -> tuple[int, int]:
    box = draw.textbbox((0, 0), text, font=fnt)
    return box[2] - box[0], box[3] - box[1]


def centered_text(
    draw: ImageDraw.ImageDraw,
    x: float,
    y: float,
    text: str,
    fnt: ImageFont.FreeTypeFont,
    fill: tuple[int, int, int],
) -> None:
    width, height = text_size(draw, text, fnt)
    draw.text((x - width / 2, y - height / 2), text, font=fnt, fill=fill)


def x_pos(x: float) -> float:
    return PLOT_L + (x - X_MIN) / (X_MAX - X_MIN) * (PLOT_R - PLOT_L)


def y_pos(y: float) -> float:
    return PLOT_B - (y - Y_MIN) / (Y_MAX - Y_MIN) * (PLOT_B - PLOT_T)


def read_rows() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    with SOURCE.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            model_key = row["model_key"]
            rows.append(
                {
                    "model_key": model_key,
                    "model": DISPLAY_NAMES.get(model_key, row["model_name"]),
                    "group": "Closed" if row["group"].startswith("Closed") else "Open",
                    "auto": float(row["ModelAutoScore"]),
                    "human": float(row["ModelHumanScore"]),
                }
            )
    return rows


def pearson(xs: list[float], ys: list[float]) -> float:
    x_bar = sum(xs) / len(xs)
    y_bar = sum(ys) / len(ys)
    num = sum((x - x_bar) * (y - y_bar) for x, y in zip(xs, ys))
    den_x = math.sqrt(sum((x - x_bar) ** 2 for x in xs))
    den_y = math.sqrt(sum((y - y_bar) ** 2 for y in ys))
    return num / (den_x * den_y)


def regression(xs: list[float], ys: list[float]) -> tuple[float, float]:
    x_bar = sum(xs) / len(xs)
    y_bar = sum(ys) / len(ys)
    slope = sum((x - x_bar) * (y - y_bar) for x, y in zip(xs, ys)) / sum((x - x_bar) ** 2 for x in xs)
    intercept = y_bar - slope * x_bar
    return slope, intercept


def draw_rotated_axis_label(base: Image.Image, text: str) -> None:
    layer = Image.new("RGBA", (640, 70), (255, 255, 255, 0))
    d = ImageDraw.Draw(layer)
    centered_text(d, 320, 35, text, F_AXIS, COLORS["text"])
    rotated = layer.rotate(90, expand=True, resample=Image.Resampling.BICUBIC)
    base.paste(rotated, (70, 410), rotated)


def draw_legend(draw: ImageDraw.ImageDraw) -> None:
    x, y = 1605, 245
    for label, fill, edge in [
        ("Closed API", COLORS["closed"], COLORS["closed_edge"]),
        ("Open / open-access", COLORS["open"], COLORS["open_edge"]),
    ]:
        draw.ellipse((x, y - 15, x + 30, y + 15), fill=fill, outline=edge, width=3)
        draw.text((x + 42, y - 17), label, font=F_LEGEND, fill=COLORS["text"])
        y += 48


def draw_plot(rows: list[dict[str, object]]) -> Image.Image:
    image = Image.new("RGB", (W, H), "white")
    draw = ImageDraw.Draw(image)

    draw.text((PLOT_L, 58), "Automatic--Human Alignment in Model Comparison", font=F_TITLE, fill=COLORS["text"])
    draw.text((PLOT_L, 112), "Each point is one completed LLM backbone.", font=F_NOTE, fill=COLORS["muted"])
    draw_legend(draw)

    draw.rectangle((PLOT_L, PLOT_T, PLOT_R, PLOT_B), outline=COLORS["axis"], width=3)
    for tick in [63.5, 64.0, 64.5, 65.0]:
        x = x_pos(tick)
        draw.line((x, PLOT_T, x, PLOT_B), fill=COLORS["grid"], width=2)
        centered_text(draw, x, PLOT_B + 36, f"{tick:.1f}", F_TICK, COLORS["muted"])
    for tick in [65, 70, 75, 80, 85, 90, 95]:
        y = y_pos(tick)
        draw.line((PLOT_L, y, PLOT_R, y), fill=COLORS["grid"], width=2)
        centered_text(draw, PLOT_L - 48, y, str(tick), F_TICK, COLORS["muted"])

    centered_text(draw, (PLOT_L + PLOT_R) / 2, PLOT_B + 92, "ModelAutoScore", F_AXIS, COLORS["text"])
    draw_rotated_axis_label(image, "ModelHumanScore")

    xs = [float(row["auto"]) for row in rows]
    ys = [float(row["human"]) for row in rows]
    slope, intercept = regression(xs, ys)
    x1, x2 = min(xs), max(xs)
    y1, y2 = slope * x1 + intercept, slope * x2 + intercept
    draw.line((x_pos(x1), y_pos(y1), x_pos(x2), y_pos(y2)), fill=COLORS["line"], width=8)

    for row in sorted(rows, key=lambda r: float(r["human"])):
        key = str(row["model_key"])
        x = x_pos(float(row["auto"]))
        y = y_pos(float(row["human"]))
        fill = COLORS["closed"] if row["group"] == "Closed" else COLORS["open"]
        edge = COLORS["closed_edge"] if row["group"] == "Closed" else COLORS["open_edge"]
        draw.ellipse((x - 15, y - 15, x + 15, y + 15), fill=fill, outline=edge, width=4)
        ox, oy = LABEL_OFFSETS.get(key, (16, -16))
        label = str(row["model"])
        lx, ly = x + ox, y + oy
        width, height = text_size(draw, label, F_LABEL)
        draw.line((x, y, lx, ly + height / 2), fill=(204, 211, 221), width=2)
        draw.rounded_rectangle((lx - 6, ly - 4, lx + width + 6, ly + height + 4), radius=7, fill=(255, 255, 255))
        draw.text((lx, ly), label, font=F_LABEL, fill=COLORS["text"])

    r = pearson(xs, ys)
    box = (1585, 925, 2040, 1095)
    draw.rounded_rectangle(box, radius=18, fill=(248, 250, 252), outline=(224, 230, 236), width=2)
    draw.text((1142, 1068), "Correlation", font=F_NOTE_BOLD, fill=COLORS["text"])
    draw.text((1142, 1110), f"Pearson's r = {r:.4f}", font=F_NOTE_BOLD, fill=COLORS["line"])
    draw.text((1142, 1150), "n = 14 completed LLM backbones", font=F_NOTE, fill=COLORS["muted"])

    draw.text((PLOT_L, 1355), "Source: model-comparison human evaluation summary.", font=F_NOTE, fill=COLORS["muted"])
    return image


def write_data(rows: list[dict[str, object]]) -> None:
    with CSV_OUT.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=["model", "group", "ModelAutoScore", "ModelHumanScore"])
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "model": row["model"],
                    "group": row["group"],
                    "ModelAutoScore": f"{float(row['auto']):.2f}",
                    "ModelHumanScore": f"{float(row['human']):.2f}",
                }
            )


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    rows = read_rows()
    write_data(rows)
    image = draw_plot(rows)
    image.save(PNG_OUT, dpi=(300, 300))
    image.save(PDF_OUT, "PDF", resolution=300.0)
    print(PNG_OUT)
    print(PDF_OUT)
    print(CSV_OUT)


if __name__ == "__main__":
    main()

