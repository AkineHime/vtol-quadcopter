"""Printable colour cards for the dashboard's colour-card reader
(frontend/src/cardReader.js): one coloured disc on white paper per card, read as
the palm's maturity when the phone camera photographs a palm stop.

    pip install reportlab
    python tools/colour_cards.py [out.pdf]     # default: documents/dashboard/colour_cards.pdf

A4, page 1 = how to use, then two cards per page (cut along the dashed line).
Colours sit in the middle of the reader's hue/saturation/brightness bands, so a
printer's drift (pale greens, light browns) still reads correctly."""
from __future__ import annotations

import sys
from pathlib import Path

from reportlab.lib.colors import Color, HexColor
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.pdfgen import canvas

REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "documents" / "dashboard" / "colour_cards.pdf"

# (key, title, what it means, RGB) -- the reader's stage for each colour:
#   tender:      hue 70-170, sat >= .55       ->  RGB (40,160,60):   h 130, s .75, v .63
#   young:       hue 70-170, sat .2-.55       ->  RGB (175,230,150): h 101, s .35, v .90
#   mature:      hue 38-70                    ->  RGB (235,205,40):  h  51, s .83, v .92
#   over-mature: hue 10-45, dark, sat >= .5   ->  RGB (100,60,25):   h  28, s .75, v .39
CARDS = [
    ("tender", "TENDER", "Harvest target (pre-mature)", (40, 160, 60)),
    ("young", "YOUNG", "Not ready yet", (175, 230, 150)),
    ("mature", "MATURE", "Past the tender stage", (235, 205, 40)),
    ("over-mature", "OVER-MATURE", "Too old", (100, 60, 25)),
]
GREY = HexColor("#8a8a8a")         # neutral text: the reader ignores grey and black
INK = HexColor("#222222")
DISC_D = 9.5 * cm                  # ~23% of an A5 half-sheet, ~11% of a whole A4 page in view

W, H = A4


def rgb(c):
    return Color(c[0] / 255, c[1] / 255, c[2] / 255)


def card(c: canvas.Canvas, y0: float, key: str, title: str, meaning: str, col) -> None:
    """One A5-sized card in the half-page starting at y0 (bottom)."""
    cx, cy = W / 2, y0 + 8.6 * cm     # disc 3.85-13.35 cm up the 14.85 cm half, labels below
    c.setFillColor(rgb(col))
    c.setStrokeColor(rgb(col))
    c.circle(cx, cy, DISC_D / 2, stroke=0, fill=1)
    c.setFillColor(GREY)
    c.setFont("Helvetica-Bold", 15)
    c.drawCentredString(cx, y0 + 2.6 * cm, title)
    c.setFont("Helvetica", 10)
    c.drawCentredString(cx, y0 + 1.9 * cm, f"{meaning}  -  reads as \"{key}\"")
    c.setFont("Helvetica", 7)
    c.drawRightString(W - 1.2 * cm, y0 + 0.7 * cm, f"Coconut VTOL colour card  -  RGB {col[0]},{col[1]},{col[2]}")


def instructions(c: canvas.Canvas) -> None:
    x, y = 2 * cm, H - 2.5 * cm
    c.setFillColor(INK)
    c.setFont("Helvetica-Bold", 20)
    c.drawString(x, y, "Colour cards for the phone-camera demo")
    y -= 0.9 * cm
    c.setFont("Helvetica", 10.5)
    c.setFillColor(GREY)
    c.drawString(x, y, "Stand-in for the ripeness model: the dashboard reads the card's colour as the palm's maturity.")
    y -= 1.3 * cm
    c.setFillColor(INK)
    c.setFont("Helvetica-Bold", 12)
    c.drawString(x, y, "The four cards")
    y -= 0.5 * cm
    for key, title, meaning, col in CARDS:
        y -= 0.95 * cm
        c.setFillColor(rgb(col))
        c.circle(x + 0.35 * cm, y + 0.15 * cm, 0.35 * cm, stroke=0, fill=1)
        c.setFillColor(INK)
        c.setFont("Helvetica-Bold", 11)
        c.drawString(x + 1.1 * cm, y + 0.02 * cm, title.title())
        c.setFont("Helvetica", 10.5)
        c.drawString(x + 4.6 * cm, y + 0.02 * cm, meaning)
    steps = [
        ("Print", "Pages 2-3 in colour on plain white paper (any scale works)."
                  " Cut along the dashed lines: four A5 cards."),
        ("Connect", "Phone camera connected on the dashboard's camera card (IP Webcam app or phone browser)."),
        ("Fly", "When the aircraft (real, simulator or fake) reaches a palm stop, the dashboard takes a photo."
                " Hold the card for that palm under the phone camera."),
        ("Frame it", "Card flat and well lit, filling most of the picture, white border visible all round."
                     " Then the reading is about 100%."),
        ("One card", "Only one card in view at a time. Two colours, or a card on a coloured or dark"
                     " background, are rejected as no reading (the photo is still saved)."),
        ("Result", "The palm's maturity updates, the prediction and the next mission re-plan, and a green"
                   " card raises the 'Tender nuts' alert."),
    ]
    y -= 1.4 * cm
    c.setFont("Helvetica-Bold", 12)
    c.drawString(x, y, "How to use")
    for head, body in steps:
        y -= 0.85 * cm
        c.setFont("Helvetica-Bold", 10.5)
        c.drawString(x, y, head)
        c.setFont("Helvetica", 10)
        lines = _wrap(c, body, W - 7 * cm, "Helvetica", 10)
        for i, line in enumerate(lines):
            c.drawString(x + 3 * cm, y - i * 0.45 * cm, line)
        y -= 0.45 * cm * (len(lines) - 1)
    y -= 1.2 * cm
    c.setFont("Helvetica-Bold", 12)
    c.drawString(x, y, "Rules the reader applies")
    rules = [
        "The card colour covers at least 2% of the photo (full confidence from 6%).",
        "White paper fills at least 15% of the photo.",
        "Confidence = share of the main colour among all coloured pixels x size factor; at least 0.6 to count.",
        "Colour only: card shapes are not read, and nothing detects health (pests, frond damage) yet.",
    ]
    c.setFont("Helvetica", 10)
    for r in rules:
        y -= 0.55 * cm
        c.drawString(x + 0.3 * cm, y, "-  " + r)
    c.setFillColor(GREY)
    c.setFont("Helvetica", 8)
    c.drawString(x, 1.5 * cm, "Generated by ground_station/tools/colour_cards.py  -  reader: ground_station/frontend/src/cardReader.js")


def _wrap(c, text, width, font, size):
    words, lines, cur = text.split(), [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if c.stringWidth(t, font, size) <= width:
            cur = t
        else:
            lines.append(cur)
            cur = w
    return lines + [cur]


def build(out: Path) -> Path:
    out.parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(out), pagesize=A4)
    c.setTitle("Coconut VTOL colour cards")
    c.setAuthor("Coconut VTOL ground station")
    instructions(c)
    c.showPage()
    for i in range(0, len(CARDS), 2):
        for half, (key, title, meaning, col) in zip((H / 2, 0), CARDS[i:i + 2]):
            card(c, half, key, title, meaning, col)
        c.setStrokeColor(GREY)
        c.setLineWidth(0.5)
        c.setDash(4, 4)
        c.line(1 * cm, H / 2, W - 1 * cm, H / 2)          # cut line
        c.setDash()
        c.showPage()
    c.save()
    return out


if __name__ == "__main__":
    print(build(Path(sys.argv[1]) if len(sys.argv) > 1 else OUT))
