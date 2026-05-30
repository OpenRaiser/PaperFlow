from __future__ import annotations

import textwrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[2]


ART_DIR = ROOT / "outputs" / "figures" / "art"
FIG_DIR = ROOT / "outputs" / "figures" / "pdf"

PNG_OUT = ART_DIR / "paperflow_error_analysis.png"
PDF_OUT = ART_DIR / "paperflow_error_analysis.pdf"
SVG_OUT = ART_DIR / "paperflow_error_analysis.svg"
PAPER_PDF_OUT = FIG_DIR / "paperflow_error_analysis.pdf"

FONT = r"C:\Windows\Fonts\times.ttf"
BOLD = r"C:\Windows\Fonts\timesbd.ttf"
ITALIC = r"C:\Windows\Fonts\timesi.ttf"
BOLD_ITALIC = r"C:\Windows\Fonts\timesbi.ttf"

W, H = 2200, 1320
MARGIN_X = 85
MARGIN_TOP = 50
PANEL_GAP_X = 46
PANEL_GAP_Y = 65
PANEL_W = (W - 2 * MARGIN_X - PANEL_GAP_X) // 2
PANEL_H = 565

NAVY = (32, 56, 92)
TITLE_RED = (190, 0, 0)
TEXT = (10, 10, 10)
BG = (255, 254, 247)
PROBLEM_BG = (231, 242, 254)
OUTPUT_BG = (247, 242, 250)
ERROR_BG = (255, 241, 230)
TARGET_BG = (243, 252, 238)
PROBLEM_TAG = (187, 235, 246)
OUTPUT_TAG = (166, 143, 229)
ERROR_TAG = (221, 86, 75)
TARGET_TAG = (188, 223, 174)
GREEN = (34, 124, 55)


PANELS = [
    {
        "title": "Stable-Profile Over-Anchoring",
        "problem": (
            "A user with a long medical-NLP history begins selecting graph-retrieval "
            "papers across several recent days."
        ),
        "response": (
            "PaperFlow ranks a familiar core-topic survey above emerging graph-agent "
            "papers because old interests and author priors remain dominant."
        ),
        "error": (
            "Stable profile evidence can over-concentrate relevance. The system may "
            "retrieve pseudo-oracle relevant papers while under-exposing new interests."
        ),
        "target": (
            "Preserve high-confidence core papers, but reserve Top-20 capacity for "
            "repeated new-topic signals and make the trade-off explicit."
        ),
    },
    {
        "title": "Ambiguous Feedback Overreaction",
        "problem": (
            "The user skips several papers from one method family, then later selects "
            "a related paper with a stronger application match."
        ),
        "response": (
            "The updater treats the skips as a broad negative preference and reduces "
            "the whole method family in subsequent rankings."
        ),
        "error": (
            "Skips are weak and context-dependent. They may reflect display budget, "
            "title mismatch, or timing rather than stable dislike."
        ),
        "target": (
            "Use only local, weak decay for skips. Require repeated skips plus no "
            "positive selections before changing long-term preference weights."
        ),
    },
    {
        "title": "Interest-Drift Boundary Error",
        "problem": (
            "A user alternates between an old topic and multimodal-agent papers during "
            "a short transition window."
        ),
        "response": (
            "The drift module enters a shifting state after a short burst and suppresses "
            "old-topic exposure too aggressively."
        ),
        "error": (
            "The system can confuse transient exploration with sustained migration when "
            "cross-day evidence is still thin."
        ),
        "target": (
            "Stay in observing mode longer, check anchor stability, and maintain old-new "
            "balance until sustained selection evidence accumulates."
        ),
    },
    {
        "title": "Report Evidence Granularity",
        "problem": (
            "A selected paper needs a concise reading report, but the user mainly wants "
            "method details and evidence for key claims."
        ),
        "response": (
            "The report has the expected sections, yet evidence is broad and not tied "
            "to the exact claims, experiments, or paper locations."
        ),
        "error": (
            "Report quality can be structurally complete but weak in fine-grained "
            "evidence coverage. Report feedback should not directly alter interests."
        ),
        "target": (
            "Ground summary points in concrete sections or claims, adjust report density, "
            "and keep report-style feedback separate from ranking interests."
        ),
    },
]


def load_font(path: str, size: int) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype(path, size)
    except OSError:
        return ImageFont.truetype(r"C:\Windows\Fonts\arial.ttf", size)


F_TITLE = load_font(BOLD_ITALIC, 36)
F_TAG = load_font(BOLD, 25)
F_BODY = load_font(ITALIC, 23)
F_BODY_BOLD = load_font(BOLD_ITALIC, 23)
F_NUM = load_font(BOLD, 22)


def text_box(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont) -> tuple[int, int]:
    box = draw.textbbox((0, 0), text, font=font)
    return box[2] - box[0], box[3] - box[1]


def wrap_lines(text: str, chars: int) -> list[str]:
    return textwrap.wrap(text, width=chars, break_long_words=False, break_on_hyphens=False)


def draw_centered(
    draw: ImageDraw.ImageDraw,
    xy: tuple[float, float],
    text: str,
    font: ImageFont.FreeTypeFont,
    fill: tuple[int, int, int],
) -> None:
    tw, th = text_box(draw, text, font)
    draw.text((xy[0] - tw / 2, xy[1] - th / 2), text, font=font, fill=fill)


def draw_wrapped_text(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    text: str,
    font: ImageFont.FreeTypeFont,
    fill: tuple[int, int, int],
    chars: int,
    line_gap: int = 6,
) -> None:
    x, y = xy
    for line in wrap_lines(text, chars):
        draw.text((x, y), line, font=font, fill=fill)
        _, lh = text_box(draw, line, font)
        y += lh + line_gap


def draw_badge(
    draw: ImageDraw.ImageDraw,
    x: int,
    y: int,
    label: str,
    color: tuple[int, int, int],
    text_color: tuple[int, int, int] = TEXT,
) -> None:
    tw, _ = text_box(draw, label, F_TAG)
    w = tw + 42
    h = 43
    draw.rounded_rectangle((x, y, x + w, y + h), radius=7, fill=color)
    draw_centered(draw, (x + w / 2, y + h / 2 + 1), label, F_TAG, text_color)


def draw_card(
    draw: ImageDraw.ImageDraw,
    x: int,
    y: int,
    w: int,
    h: int,
    tag: str,
    tag_color: tuple[int, int, int],
    body: str,
    body_font: ImageFont.FreeTypeFont,
    fill: tuple[int, int, int],
    chars: int,
    tag_text_color: tuple[int, int, int] = TEXT,
) -> None:
    draw.rounded_rectangle((x, y, x + w, y + h), radius=26, fill=fill)
    tag_w = text_box(draw, tag, F_TAG)[0] + 42
    draw_badge(draw, x + (w - tag_w) // 2, y - 33, tag, tag_color, tag_text_color)
    draw_wrapped_text(draw, (x + 22, y + 42), body, body_font, TEXT, chars)


def panel_position(idx: int) -> tuple[int, int]:
    row = idx // 2
    col = idx % 2
    x = MARGIN_X + col * (PANEL_W + PANEL_GAP_X)
    y = MARGIN_TOP + row * (PANEL_H + PANEL_GAP_Y)
    return x, y


def draw_panel(draw: ImageDraw.ImageDraw, idx: int, panel: dict[str, str]) -> None:
    x, y = panel_position(idx)
    title_y = y + 2
    draw_centered(draw, (x + PANEL_W / 2, title_y + 26), panel["title"], F_TITLE, TITLE_RED)

    box_y = y + 72
    draw.rectangle((x, box_y, x + PANEL_W, y + PANEL_H), outline=NAVY, width=4, fill=BG)

    inner_x = x + 24
    inner_y = box_y + 58
    col_gap = 26
    row_gap = 55
    card_w = (PANEL_W - 48 - col_gap) // 2
    card_h = 180
    bottom_h = 190

    draw_card(
        draw,
        inner_x,
        inner_y,
        card_w,
        card_h,
        "Problem",
        PROBLEM_TAG,
        panel["problem"],
        F_BODY_BOLD,
        PROBLEM_BG,
        38,
    )
    draw_card(
        draw,
        inner_x + card_w + col_gap,
        inner_y,
        card_w,
        card_h,
        "Model Response",
        OUTPUT_TAG,
        panel["response"],
        F_BODY_BOLD,
        OUTPUT_BG,
        38,
        (255, 255, 255),
    )
    draw_card(
        draw,
        inner_x,
        inner_y + card_h + row_gap,
        card_w,
        bottom_h,
        "Error Analysis",
        ERROR_TAG,
        panel["error"],
        F_BODY,
        ERROR_BG,
        38,
        (255, 255, 255),
    )
    draw_card(
        draw,
        inner_x + card_w + col_gap,
        inner_y + card_h + row_gap,
        card_w,
        bottom_h,
        "Better Target",
        TARGET_TAG,
        panel["target"],
        F_BODY,
        TARGET_BG,
        38,
    )

    draw.ellipse((x + 22, box_y + 16, x + 56, box_y + 50), fill=(255, 255, 255), outline=NAVY, width=3)
    draw_centered(draw, (x + 39, box_y + 34), str(idx + 1), F_NUM, NAVY)


def draw_png() -> Image.Image:
    image = Image.new("RGB", (W, H), "white")
    draw = ImageDraw.Draw(image)
    for idx, panel in enumerate(PANELS):
        draw_panel(draw, idx, panel)
    return image


def svg_escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def write_svg() -> None:
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">',
        '<rect width="100%" height="100%" fill="white"/>',
        "<!-- The publication PDF/PNG is rendered from the same data by PIL. -->",
    ]
    for idx, panel in enumerate(PANELS):
        x, y = panel_position(idx)
        parts.append(
            f'<rect x="{x}" y="{y + 72}" width="{PANEL_W}" height="{PANEL_H - 72}" '
            f'fill="rgb{BG}" stroke="rgb{NAVY}" stroke-width="4"/>'
        )
        parts.append(
            f'<text x="{x + PANEL_W / 2}" y="{y + 40}" text-anchor="middle" '
            f'font-family="Times New Roman" font-size="36" font-style="italic" '
            f'font-weight="700" fill="rgb{TITLE_RED}">{svg_escape(panel["title"])}</text>'
        )
    parts.append("</svg>")
    SVG_OUT.write_text("\n".join(parts), encoding="utf-8")


def main() -> None:
    ART_DIR.mkdir(parents=True, exist_ok=True)
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    image = draw_png()
    image.save(PNG_OUT)
    image.save(PDF_OUT, "PDF", resolution=300.0)
    image.save(PAPER_PDF_OUT, "PDF", resolution=300.0)
    write_svg()
    print(f"Wrote {PNG_OUT}")
    print(f"Wrote {PDF_OUT}")
    print(f"Wrote {PAPER_PDF_OUT}")


if __name__ == "__main__":
    main()

