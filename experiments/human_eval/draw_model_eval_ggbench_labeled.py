from __future__ import annotations

import csv
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "scripts" / "human_eval" / "results" / "model_human_eval" / "summary.csv"
OUT_DIR = ROOT / "outputs" / "figures" / "art"

PNG_OUT = OUT_DIR / "model_auto_human_ggbench_labeled.png"
PDF_OUT = OUT_DIR / "model_auto_human_ggbench_labeled.pdf"
TYPO_PDF_OUT = OUT_DIR / "model_auto_huamn.pdf"
DESKTOP_TYPO_PDF_OUT = OUT_DIR / "model_auto_huamn.pdf"
PAPER_TYPO_PDF_OUT = ROOT / "outputs" / "figures" / "pdf" / "model_auto_huamn.pdf"
SVG_OUT = OUT_DIR / "model_auto_human_ggbench_labeled.svg"
CSV_OUT = OUT_DIR / "model_auto_human_ggbench_labeled_data.csv"

FONT = r"C:\Windows\Fonts\times.ttf"
BOLD = r"C:\Windows\Fonts\timesbd.ttf"

SCALE = 2
DPI = 300 * SCALE


def s(value: float) -> int:
    return round(value * SCALE)


LEFT_SAFE_PAD = s(90)
W, H = s(1840) + LEFT_SAFE_PAD, s(1160)
PLOT_L, PLOT_T = s(230) + LEFT_SAFE_PAD, s(92)
PLOT_R, PLOT_B = s(1485) + LEFT_SAFE_PAD, s(985)

X_MIN, X_MAX = 63.5, 65.1
Y_MIN, Y_MAX = 65.0, 100.0

AXIS = (76, 70, 68)
TEXT = (68, 60, 58)
RED = (255, 91, 70)
BLUE = (77, 116, 218)

DISPLAY_NAMES = {
    "gpt5_4": "GPT-5.4",
    "qwen3_5_plus": "Qwen3.5-Plus",
    "gemini_3_1_pro_preview": "Gemini 3.1 Pro",
    "claude_sonnet_4_6": "Claude Sonnet 4.6",
    "qwen3_6_plus": "Qwen3.6-Plus",
    "qwen3_6_max_preview": "Qwen3.6-Max",
    "grok_4_3": "Grok 4.3",
    "paperflow_default": "PaperFlow",
    "mimo2_5pro": "MiMo-V2.5-Pro",
    "deepseek_v4_pro": "DeepSeek-V4-Pro",
    "deepseek_v4_flash": "DeepSeek-V4-Flash",
    "kimi_k2_6": "Kimi K2.6",
    "glm_5_1": "GLM-5.1",
    "minimax_m2_7": "MiniMax-M2.7",
}

MODEL_COLORS = {
    "grok_4_3": (94, 94, 94),
    "kimi_k2_6": (140, 55, 245),
    "deepseek_v4_flash": (250, 133, 134),
    "claude_sonnet_4_6": (145, 188, 145),
    "minimax_m2_7": (246, 194, 45),
    "qwen3_6_plus": (128, 99, 210),
    "paperflow_default": (73, 174, 130),
    "deepseek_v4_pro": (137, 172, 222),
    "glm_5_1": (170, 127, 196),
    "qwen3_6_max_preview": (112, 83, 190),
    "qwen3_5_plus": (155, 205, 134),
    "mimo2_5pro": (224, 128, 221),
    "gemini_3_1_pro_preview": (120, 198, 220),
    "gpt5_4": (255, 142, 103),
}

# Manual offsets keep the dense lower-left cluster readable while preserving
# the GGBench-style direct labels.
BASE_LABEL_OFFSETS = {
    "grok_4_3": (-170, -36),
    "kimi_k2_6": (-118, -52),
    "deepseek_v4_flash": (30, 8),
    "claude_sonnet_4_6": (30, -58),
    "minimax_m2_7": (-178, 8),
    "qwen3_6_plus": (26, 30),
    "paperflow_default": (36, 58),
    "deepseek_v4_pro": (-168, -34),
    "glm_5_1": (-172, 72),
    "qwen3_6_max_preview": (70, 48),
    "qwen3_5_plus": (-94, 104),
    "mimo2_5pro": (-174, -42),
    "gemini_3_1_pro_preview": (82, 54),
    "gpt5_4": (-22, 64),
}
LABEL_OFFSETS = {key: (s(dx), s(dy)) for key, (dx, dy) in BASE_LABEL_OFFSETS.items()}


def load_font(path: str, size: int) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype(path, size)
    except OSError:
        return ImageFont.truetype(r"C:\Windows\Fonts\arial.ttf", size)


F_AXIS = load_font(BOLD, s(64))
F_TICK = load_font(BOLD, s(53))
F_MODEL = load_font(BOLD, s(44))
F_PEARSON = load_font(BOLD, s(56))


def read_rows() -> list[dict[str, object]]:
    rows = []
    with SOURCE.open("r", encoding="utf-8-sig", newline="") as fh:
        for row in csv.DictReader(fh):
            rows.append(
                {
                    "key": row["model_key"],
                    "name": DISPLAY_NAMES[row["model_key"]],
                    "auto": float(row["ModelAutoScore"]),
                    "human": float(row["ModelHumanScore"]),
                }
            )
    return rows


def x_pos(value: float) -> float:
    return PLOT_L + (value - X_MIN) / (X_MAX - X_MIN) * (PLOT_R - PLOT_L)


def y_pos(value: float) -> float:
    return PLOT_B - (value - Y_MIN) / (Y_MAX - Y_MIN) * (PLOT_B - PLOT_T)


def pearson(xs: list[float], ys: list[float]) -> float:
    x_bar = sum(xs) / len(xs)
    y_bar = sum(ys) / len(ys)
    numerator = sum((x - x_bar) * (y - y_bar) for x, y in zip(xs, ys))
    den_x = math.sqrt(sum((x - x_bar) ** 2 for x in xs))
    den_y = math.sqrt(sum((y - y_bar) ** 2 for y in ys))
    return numerator / (den_x * den_y)


def regression(xs: list[float], ys: list[float]) -> tuple[float, float]:
    x_bar = sum(xs) / len(xs)
    y_bar = sum(ys) / len(ys)
    slope = sum((x - x_bar) * (y - y_bar) for x, y in zip(xs, ys)) / sum((x - x_bar) ** 2 for x in xs)
    intercept = y_bar - slope * x_bar
    return slope, intercept


def draw_axes(draw: ImageDraw.ImageDraw) -> None:
    draw.line((PLOT_L, PLOT_T, PLOT_L, PLOT_B), fill=AXIS, width=s(3))
    draw.line((PLOT_L, PLOT_B, PLOT_R, PLOT_B), fill=AXIS, width=s(3))

    for tick in [65, 70, 75, 80, 85, 90, 95, 100]:
        y = y_pos(float(tick))
        draw.line((PLOT_L - s(10), y, PLOT_L, y), fill=AXIS, width=s(3))
        label = str(tick)
        box = draw.textbbox((0, 0), label, font=F_TICK)
        draw.text((PLOT_L - s(18) - (box[2] - box[0]), y - s(18)), label, font=F_TICK, fill=TEXT)

    for tick in [63.5, 64.0, 64.5, 65.0]:
        x = x_pos(tick)
        draw.line((x, PLOT_B, x, PLOT_B + s(13)), fill=AXIS, width=s(3))
        label = f"{tick:.1f}"
        box = draw.textbbox((0, 0), label, font=F_TICK)
        draw.text((x - (box[2] - box[0]) / 2, PLOT_B + s(24)), label, font=F_TICK, fill=TEXT)

    draw.text((PLOT_L - s(48), PLOT_T - s(74)), "Human", font=F_AXIS, fill=TEXT)
    draw.text((PLOT_R + s(45), PLOT_B - s(7)), "ModelAuto", font=F_AXIS, fill=TEXT)


def draw_chart(rows: list[dict[str, object]]) -> Image.Image:
    image = Image.new("RGB", (W, H), "white")
    draw = ImageDraw.Draw(image)
    draw_axes(draw)

    xs = [float(row["auto"]) for row in rows]
    ys = [float(row["human"]) for row in rows]
    slope, intercept = regression(xs, ys)
    r = pearson(xs, ys)

    x1, x2 = min(xs), max(xs)
    y1, y2 = slope * x1 + intercept, slope * x2 + intercept
    draw.line((x_pos(x1), y_pos(y1), x_pos(x2), y_pos(y2)), fill=RED, width=s(6))
    for x, y in [(x1, y1), (x2, y2)]:
        cx, cy = x_pos(x), y_pos(y)
        draw.ellipse((cx - s(10), cy - s(10), cx + s(10), cy + s(10)), fill="white", outline=BLUE, width=s(5))

    for row in rows:
        key = str(row["key"])
        color = MODEL_COLORS[key]
        x = x_pos(float(row["auto"]))
        y = y_pos(float(row["human"]))
        draw.ellipse((x - s(11), y - s(11), x + s(11), y + s(11)), fill=color, outline=color)

    for row in rows:
        key = str(row["key"])
        color = MODEL_COLORS[key]
        x = x_pos(float(row["auto"]))
        y = y_pos(float(row["human"]))
        dx, dy = LABEL_OFFSETS[key]
        draw.text((x + dx, y + dy), str(row["name"]), font=F_MODEL, fill=color)

    pearson_text = f"Pearson's r = {r:.4f}"
    draw.text((PLOT_R - s(430), PLOT_T + s(38)), pearson_text, font=F_PEARSON, fill=RED)

    return image


def write_svg(rows: list[dict[str, object]]) -> None:
    xs = [float(row["auto"]) for row in rows]
    ys = [float(row["human"]) for row in rows]
    slope, intercept = regression(xs, ys)
    r = pearson(xs, ys)
    x1, x2 = min(xs), max(xs)
    y1, y2 = slope * x1 + intercept, slope * x2 + intercept

    def rgb(color: tuple[int, int, int]) -> str:
        return f"rgb({color[0]},{color[1]},{color[2]})"

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">',
        '<rect width="100%" height="100%" fill="white"/>',
        f'<line x1="{PLOT_L}" y1="{PLOT_T}" x2="{PLOT_L}" y2="{PLOT_B}" stroke="{rgb(AXIS)}" stroke-width="3"/>',
        f'<line x1="{PLOT_L}" y1="{PLOT_B}" x2="{PLOT_R}" y2="{PLOT_B}" stroke="{rgb(AXIS)}" stroke-width="3"/>',
    ]
    for tick in [65, 70, 75, 80, 85, 90, 95, 100]:
        y = y_pos(float(tick))
        parts.append(f'<line x1="{PLOT_L-10}" y1="{y}" x2="{PLOT_L}" y2="{y}" stroke="{rgb(AXIS)}" stroke-width="3"/>')
        parts.append(f'<text x="{PLOT_L-18}" y="{y+12}" font-family="Times New Roman" font-size="36" font-weight="700" text-anchor="end" fill="{rgb(TEXT)}">{tick}</text>')
    for tick in [63.5, 64.0, 64.5, 65.0]:
        x = x_pos(tick)
        parts.append(f'<line x1="{x}" y1="{PLOT_B}" x2="{x}" y2="{PLOT_B+13}" stroke="{rgb(AXIS)}" stroke-width="3"/>')
        parts.append(f'<text x="{x}" y="{PLOT_B+60}" font-family="Times New Roman" font-size="36" font-weight="700" text-anchor="middle" fill="{rgb(TEXT)}">{tick:.1f}</text>')
    parts.append(f'<text x="{PLOT_L-48}" y="{PLOT_T-52}" font-family="Times New Roman" font-size="42" font-weight="700" fill="{rgb(TEXT)}">Human</text>')
    parts.append(f'<text x="{PLOT_R+45}" y="{PLOT_B+20}" font-family="Times New Roman" font-size="42" font-weight="700" fill="{rgb(TEXT)}">ModelAuto</text>')
    parts.append(f'<line x1="{x_pos(x1)}" y1="{y_pos(y1)}" x2="{x_pos(x2)}" y2="{y_pos(y2)}" stroke="{rgb(RED)}" stroke-width="6"/>')
    for x, y in [(x1, y1), (x2, y2)]:
        parts.append(f'<circle cx="{x_pos(x)}" cy="{y_pos(y)}" r="10" fill="white" stroke="{rgb(BLUE)}" stroke-width="5"/>')
    for row in rows:
        key = str(row["key"])
        color = MODEL_COLORS[key]
        parts.append(f'<circle cx="{x_pos(float(row["auto"]))}" cy="{y_pos(float(row["human"]))}" r="11" fill="{rgb(color)}"/>')
    for row in rows:
        key = str(row["key"])
        color = MODEL_COLORS[key]
        dx, dy = LABEL_OFFSETS[key]
        parts.append(
            f'<text x="{x_pos(float(row["auto"]))+dx}" y="{y_pos(float(row["human"]))+dy+28}" '
            f'font-family="Times New Roman" font-size="31" font-weight="700" fill="{rgb(color)}">{row["name"]}</text>'
        )
    parts.append(f'<text x="{PLOT_R-430}" y="{PLOT_T+73}" font-family="Times New Roman" font-size="44" font-weight="700" fill="{rgb(RED)}">Pearson&apos;s r = {r:.4f}</text>')
    parts.append("</svg>")
    SVG_OUT.write_text("\n".join(parts), encoding="utf-8")


def write_csv(rows: list[dict[str, object]]) -> None:
    with CSV_OUT.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=["model", "ModelAutoScore", "ModelHumanScore"])
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "model": row["name"],
                    "ModelAutoScore": f'{float(row["auto"]):.2f}',
                    "ModelHumanScore": f'{float(row["human"]):.2f}',
                }
            )


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    PAPER_TYPO_PDF_OUT.parent.mkdir(parents=True, exist_ok=True)
    rows = read_rows()
    image = draw_chart(rows)
    image.save(PNG_OUT, dpi=(DPI, DPI))
    for pdf_out in [PDF_OUT, TYPO_PDF_OUT, DESKTOP_TYPO_PDF_OUT, PAPER_TYPO_PDF_OUT]:
        image.save(pdf_out, "PDF", resolution=float(DPI))
    write_svg(rows)
    write_csv(rows)
    print(PNG_OUT)
    print(PDF_OUT)
    print(TYPO_PDF_OUT)
    print(DESKTOP_TYPO_PDF_OUT)
    print(PAPER_TYPO_PDF_OUT)
    print(SVG_OUT)


if __name__ == "__main__":
    main()

