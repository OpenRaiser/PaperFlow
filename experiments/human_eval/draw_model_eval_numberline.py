from __future__ import annotations

import csv
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "scripts" / "human_eval" / "results" / "model_human_eval" / "summary.csv"
OUT_DIR = ROOT / "outputs" / "figures" / "art"
PNG_OUT = OUT_DIR / "model_auto_human_numberline.png"
PDF_OUT = OUT_DIR / "model_auto_human_numberline.pdf"
CSV_OUT = OUT_DIR / "model_auto_human_numberline_data.csv"

FONT = r"C:\Windows\Fonts\arial.ttf"
BOLD = r"C:\Windows\Fonts\arialbd.ttf"

W, H = 2400, 1500
MARGIN_L = 450
MARGIN_R = 250
AXIS_L = 720
AXIS_R = 2140
TOP = 330
ROW_H = 72
AUTO_Y_OFFSET = -11
HUMAN_Y_OFFSET = 11

X_MIN, X_MAX = 60.0, 100.0

COLORS = {
    "text": (44, 52, 64),
    "muted": (104, 112, 124),
    "grid": (224, 230, 236),
    "axis": (152, 160, 172),
    "auto": (126, 185, 222),
    "auto_dark": (59, 120, 164),
    "human": (244, 175, 180),
    "human_dark": (176, 82, 92),
    "closed": (248, 211, 160),
    "open": (220, 235, 192),
    "line": (196, 203, 213),
}

DISPLAY_NAMES = {
    "gpt5_4": "GPT-5.4",
    "qwen3_5_plus": "Qwen3.5-Plus",
    "gemini_3_1_pro_preview": "Gemini 3.1 Pro Preview",
    "claude_sonnet_4_6": "Claude Sonnet 4.6",
    "qwen3_6_plus": "Qwen3.6-Plus",
    "qwen3_6_max_preview": "Qwen3.6-Max-Preview",
    "grok_4_3": "Grok 4.3",
    "paperflow_default": "PaperFlow (Gemini 3 Flash Preview)",
    "mimo2_5pro": "MiMo-V2.5-Pro",
    "deepseek_v4_pro": "DeepSeek-V4-Pro",
    "deepseek_v4_flash": "DeepSeek-V4-Flash",
    "kimi_k2_6": "Kimi K2.6",
    "glm_5_1": "GLM-5.1",
    "minimax_m2_7": "MiniMax-M2.7",
}


def font(path: str, size: int) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype(path, size)
    except OSError:
        return ImageFont.load_default()


F_TITLE = font(BOLD, 44)
F_SUBTITLE = font(FONT, 25)
F_LABEL = font(BOLD, 25)
F_SMALL = font(FONT, 22)
F_SMALL_BOLD = font(BOLD, 22)
F_TICK = font(FONT, 24)
F_VALUE = font(BOLD, 22)


def text_size(draw: ImageDraw.ImageDraw, text: str, fnt: ImageFont.FreeTypeFont) -> tuple[int, int]:
    box = draw.textbbox((0, 0), text, font=fnt)
    return box[2] - box[0], box[3] - box[1]


def draw_text_center(
    draw: ImageDraw.ImageDraw,
    xy: tuple[float, float],
    text: str,
    fnt: ImageFont.FreeTypeFont,
    fill: tuple[int, int, int],
) -> None:
    width, height = text_size(draw, text, fnt)
    draw.text((xy[0] - width / 2, xy[1] - height / 2), text, font=fnt, fill=fill)


def x_pos(score: float) -> float:
    return AXIS_L + (score - X_MIN) / (X_MAX - X_MIN) * (AXIS_R - AXIS_L)


def read_rows() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    with SOURCE.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            model_key = row["model_key"]
            group = "Closed" if row["group"].startswith("Closed") else "Open"
            rows.append(
                {
                    "model_key": model_key,
                    "model": DISPLAY_NAMES.get(model_key, row["model_name"]),
                    "group": group,
                    "auto": float(row["ModelAutoScore"]),
                    "human": float(row["ModelHumanScore"]),
                }
            )
    return sorted(rows, key=lambda item: float(item["human"]), reverse=True)


def rounded_rect(
    draw: ImageDraw.ImageDraw,
    box: tuple[float, float, float, float],
    radius: int,
    fill: tuple[int, int, int],
    outline: tuple[int, int, int] | None = None,
    width: int = 1,
) -> None:
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


def draw_legend(draw: ImageDraw.ImageDraw) -> None:
    y = 130
    items = [
        ("ModelAutoScore", COLORS["auto"], COLORS["auto_dark"]),
        ("ModelHumanScore", COLORS["human"], COLORS["human_dark"]),
    ]
    x = 1450
    for label, fill, outline in items:
        draw.ellipse((x, y - 12, x + 24, y + 12), fill=fill, outline=outline, width=3)
        draw.text((x + 36, y - 15), label, font=F_SMALL_BOLD, fill=COLORS["text"])
        x += 310

    rounded_rect(draw, (1450, 172, 1515, 202), 8, COLORS["closed"])
    draw.text((1530, 170), "Closed", font=F_SMALL, fill=COLORS["text"])
    rounded_rect(draw, (1665, 172, 1730, 202), 8, COLORS["open"])
    draw.text((1745, 170), "Open", font=F_SMALL, fill=COLORS["text"])


def draw_axis(draw: ImageDraw.ImageDraw, y0: int, y1: int) -> None:
    for tick in range(60, 101, 10):
        x = x_pos(float(tick))
        draw.line((x, y0, x, y1), fill=COLORS["grid"], width=2)
        draw_text_center(draw, (x, y0 - 28), str(tick), F_TICK, COLORS["muted"])
    draw.line((AXIS_L, y0, AXIS_R, y0), fill=COLORS["axis"], width=2)
    draw.line((AXIS_L, y1, AXIS_R, y1), fill=COLORS["axis"], width=2)
    draw_text_center(draw, ((AXIS_L + AXIS_R) / 2, y0 - 78), "Score (0-100)", F_SUBTITLE, COLORS["muted"])


def draw_group_chip(draw: ImageDraw.ImageDraw, x: int, y: int, group: str) -> None:
    fill = COLORS["closed"] if group == "Closed" else COLORS["open"]
    rounded_rect(draw, (x, y - 16, x + 88, y + 17), 9, fill)
    draw_text_center(draw, (x + 44, y), group, F_SMALL_BOLD, COLORS["text"])


def draw_plot(rows: list[dict[str, object]]) -> Image.Image:
    image = Image.new("RGB", (W, H), "white")
    draw = ImageDraw.Draw(image)

    draw_text_center(draw, (W / 2, 58), "Model Evaluation: Automatic and Human Scores", F_TITLE, COLORS["text"])
    draw_text_center(
        draw,
        (W / 2, 103),
        "Each row places ModelAutoScore and ModelHumanScore on the same score axis.",
        F_SUBTITLE,
        COLORS["muted"],
    )
    draw_legend(draw)

    y_axis_top = TOP - 50
    y_axis_bottom = TOP + (len(rows) - 1) * ROW_H + 54
    draw_axis(draw, y_axis_top, y_axis_bottom)

    for idx, row in enumerate(rows):
        y = TOP + idx * ROW_H
        if idx % 2 == 0:
            rounded_rect(draw, (70, y - 30, W - 80, y + 31), 10, (249, 251, 253))

        model = str(row["model"])
        group = str(row["group"])
        auto = float(row["auto"])
        human = float(row["human"])
        xa = x_pos(auto)
        xh = x_pos(human)

        model_font = F_SMALL_BOLD if len(model) > 31 else F_LABEL
        draw.text((92, y - 17), model, font=model_font, fill=COLORS["text"])
        draw_group_chip(draw, 585, y, group)

        draw.line((AXIS_L, y, AXIS_R, y), fill=(234, 238, 243), width=1)
        draw.line((xa, y + AUTO_Y_OFFSET, xh, y + HUMAN_Y_OFFSET), fill=COLORS["line"], width=4)

        draw.ellipse((xa - 11, y + AUTO_Y_OFFSET - 11, xa + 11, y + AUTO_Y_OFFSET + 11), fill="white", outline=COLORS["auto_dark"], width=4)
        draw.ellipse((xh - 13, y + HUMAN_Y_OFFSET - 13, xh + 13, y + HUMAN_Y_OFFSET + 13), fill=COLORS["human"], outline=COLORS["human_dark"], width=3)

        draw.text((xa - 33, y - 45), f"{auto:.2f}", font=F_VALUE, fill=COLORS["auto_dark"])
        draw.text((xh + 18, y - 4), f"{human:.2f}", font=F_VALUE, fill=COLORS["human_dark"])

    note = "Pearson r = 0.9632, Spearman rho = 0.9648 across 14 completed LLM backbones"
    draw_text_center(draw, (W / 2, H - 72), note, F_SUBTITLE, COLORS["muted"])
    return image


def write_data_snapshot(rows: list[dict[str, object]]) -> None:
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
    write_data_snapshot(rows)
    image = draw_plot(rows)
    image.save(PNG_OUT, dpi=(300, 300))
    image.save(PDF_OUT, "PDF", resolution=300.0)
    print(PNG_OUT)
    print(PDF_OUT)
    print(CSV_OUT)


if __name__ == "__main__":
    main()

