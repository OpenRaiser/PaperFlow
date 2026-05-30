from __future__ import annotations

from pathlib import Path

import fitz


ROOT = Path(__file__).resolve().parents[2]


ART_DIR = ROOT / "outputs" / "figures" / "art"
FIG_DIR = ROOT / "outputs" / "figures" / "pdf"

PDF_OUT = ART_DIR / "paperflow_error_case_single.pdf"
PNG_OUT = ART_DIR / "paperflow_error_case_single.png"
PAPER_PDF_OUT = FIG_DIR / "paperflow_error_case_single.pdf"
DESKTOP_PDF_OUT = ART_DIR / "paperflow_error_case_single.pdf"

W, H = 420, 248


def rgb(color: tuple[int, int, int]) -> tuple[float, float, float]:
    return tuple(channel / 255 for channel in color)


NAVY = rgb((37, 66, 112))
TITLE_RED = rgb((170, 20, 20))
TEXT = rgb((38, 38, 42))
MUTED = rgb((92, 92, 98))
BLUE_BG = rgb((236, 244, 255))
BLUE = rgb((82, 121, 182))
GREEN_BG = rgb((237, 249, 235))
GREEN = rgb((54, 130, 61))
ORANGE_BG = rgb((255, 244, 231))
ORANGE = rgb((206, 87, 28))
RED_BG = rgb((255, 238, 235))
RED = rgb((190, 45, 38))
GRAY = rgb((116, 116, 116))
WHITE = rgb((255, 255, 255))


def rect(page: fitz.Page, box: tuple[float, float, float, float], fill, stroke=None, width: float = 0.7) -> None:
    page.draw_rect(fitz.Rect(*box), color=stroke, fill=fill, width=width)


def text(
    page: fitz.Page,
    box: tuple[float, float, float, float],
    value: str,
    size: float,
    color=TEXT,
    font: str = "Times-Bold",
    align: int = fitz.TEXT_ALIGN_CENTER,
) -> None:
    x0, y0, x1, y1 = box
    lines = value.count("\n") + 1
    min_height = size * 1.35 * lines + 4
    y1 = max(y1, y0 + min_height)
    page.insert_textbox(fitz.Rect(x0, y0, x1, y1), value, fontsize=size, fontname=font, color=color, align=align)


def chip(page: fitz.Page, x: float, y: float, w: float, h: float, label: str, fill, stroke, color=TEXT) -> None:
    rect(page, (x, y, x + w, y + h), fill=fill, stroke=stroke, width=0.55)
    text(page, (x + 2, y + 2, x + w - 2, y + h + 4), label, 10.8, color=color)


def arrow(page: fitz.Page, x1: float, y: float, x2: float) -> None:
    page.draw_line(fitz.Point(x1, y), fitz.Point(x2, y), color=GRAY, width=1.8)
    page.draw_polyline(
        [
            fitz.Point(x2 - 5, y - 4),
            fitz.Point(x2, y),
            fitz.Point(x2 - 5, y + 4),
        ],
        color=GRAY,
        width=1.8,
    )


def draw_status(page: fitz.Page, x: float, y: float, label: str, value: str, color) -> None:
    text(page, (x, y, x + 72, y + 13), label, 10.2, color=MUTED, align=fitz.TEXT_ALIGN_LEFT)
    text(page, (x + 74, y, x + 108, y + 13), value, 11.0, color=color, align=fitz.TEXT_ALIGN_LEFT)


def draw_panel_1(page: fitz.Page, x: float, y: float, w: float, h: float) -> None:
    rect(page, (x, y, x + w, y + h), BLUE_BG, NAVY)
    text(page, (x + 8, y + 7, x + w - 8, y + 24), "User Evidence", 14.2, color=NAVY)
    text(page, (x + 12, y + 30, x + w - 12, y + 45), "Stable core", 11.2, color=BLUE)
    chip(page, x + 14, y + 49, w - 28, 19, "LLM eval / paper rec", WHITE, BLUE, color=NAVY)
    text(page, (x + 12, y + 73, x + w - 12, y + 88), "Recent signal", 11.2, color=GREEN)
    chip(page, x + 14, y + 92, w - 28, 19, "cross-domain method", WHITE, GREEN, color=GREEN)


def draw_panel_2(page: fitz.Page, x: float, y: float, w: float, h: float) -> None:
    rect(page, (x, y, x + w, y + h), GREEN_BG, GREEN)
    text(page, (x + 8, y + 7, x + w - 8, y + 24), "PaperFlow", 14.2, color=GREEN)
    text(page, (x + 12, y + 31, x + w - 12, y + 47), "Ranks exploratory\npaper high", 11.7, color=TEXT)
    draw_status(page, x + 13, y + 67, "Behavior", "HIGH", GREEN)
    draw_status(page, x + 13, y + 85, "Method", "HIGH", GREEN)
    text(page, (x + 16, y + 105, x + w - 16, y + 122), "selected by user", 10.5, color=GREEN)


def draw_panel_3(page: fitz.Page, x: float, y: float, w: float, h: float) -> None:
    rect(page, (x, y, x + w, y + h), RED_BG, RED)
    text(page, (x + 8, y + 7, x + w - 8, y + 24), "Pseudo-Oracle", 14.2, color=RED)
    text(page, (x + 12, y + 32, x + w - 12, y + 47), "Judges by stable\ntopical overlap", 11.4, color=TEXT)
    draw_status(page, x + 13, y + 70, "Overlap", "LOW", RED)
    text(page, (x + 13, y + 90, x + w - 13, y + 107), "Label: weak_relevant", 11.3, color=RED)
    text(page, (x + 13, y + 111, x + w - 13, y + 126), "label-based view", 9.7, color=MUTED)


def draw_figure(path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page(width=W, height=H)
    rect(page, (0, 0, W, H), WHITE, None)
    rect(page, (8, 8, W - 8, H - 8), WHITE, NAVY, width=0.9)

    text(page, (18, 15, W - 18, 35), "Oracle--Behavior Disagreement", 19.0, color=TITLE_RED, align=fitz.TEXT_ALIGN_LEFT)
    text(
        page,
        (18, 37, W - 18, 54),
        "A useful exploratory paper can conflict with a static topical label.",
        11.2,
        color=MUTED,
        font="Times-Roman",
        align=fitz.TEXT_ALIGN_LEFT,
    )

    card_y, card_h, card_w = 66, 124, 112
    x1, x2, x3 = 18, 154, 290
    draw_panel_1(page, x1, card_y, card_w, card_h)
    arrow(page, x1 + card_w + 9, card_y + 62, x2 - 9)
    draw_panel_2(page, x2, card_y, card_w, card_h)
    arrow(page, x2 + card_w + 9, card_y + 62, x3 - 9)
    draw_panel_3(page, x3, card_y, card_w, card_h)

    rect(page, (18, 202, W - 18, 232), ORANGE_BG, ORANGE, width=0.75)
    text(page, (28, 207, 125, 224), "Error Analysis", 13.8, color=ORANGE, align=fitz.TEXT_ALIGN_LEFT)
    text(
        page,
        (128, 207, W - 28, 223),
        "Exploratory usefulness can be under-credited by static topical labels.",
        10.9,
        color=TEXT,
        font="Times-Roman",
        align=fitz.TEXT_ALIGN_LEFT,
    )
    text(
        page,
        (28, 221, W - 28, 236),
        "Boundary: behavior usefulness != topical relevance",
        11.0,
        color=TITLE_RED,
        align=fitz.TEXT_ALIGN_CENTER,
    )

    doc.save(path, garbage=4, deflate=True)
    doc.close()


def render_png(pdf_path: Path, png_path: Path) -> None:
    doc = fitz.open(pdf_path)
    pix = doc[0].get_pixmap(matrix=fitz.Matrix(4.0, 4.0), alpha=False)
    pix.save(png_path)
    doc.close()


def main() -> None:
    ART_DIR.mkdir(parents=True, exist_ok=True)
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    for out in [PDF_OUT, PAPER_PDF_OUT, DESKTOP_PDF_OUT]:
        draw_figure(out)
    render_png(PDF_OUT, PNG_OUT)
    print(PDF_OUT)
    print(PAPER_PDF_OUT)
    print(DESKTOP_PDF_OUT)
    print(PNG_OUT)


if __name__ == "__main__":
    main()

