# -*- coding: utf-8 -*-
"""Assemble the patent-drawing gallery artifact HTML, embedding the 7 PNGs
as base64 data URIs. Run, then the Artifact tool publishes the output file
(kept separate so the huge base64 blobs never pass through the chat)."""
import base64
from pathlib import Path

HERE = Path(__file__).resolve().parent
FIGS = ["FIG1_isometric", "FIG2_top", "FIG3_bottom", "FIG4_front",
        "FIG5_rear", "FIG6_left", "FIG7_right"]

CAPTIONS = {
    "FIG1_isometric": ("FIG. 1", "Perspective view",
        "Lead figure. Shows how the wing, tail booms, twin fin/tail "
        "assembly and quad-X lift rotors relate to one another."),
    "FIG2_top": ("FIG. 2", "Top view",
        "Wing planform is to real dimension (1.3 m span, tapered chord, "
        "unswept leading edge)."),
    "FIG3_bottom": ("FIG. 3", "Bottom view",
        "Distinguishing content vs. the top view: underside camera and "
        "ranging-sensor placement."),
    "FIG4_front": ("FIG. 4", "Front view",
        "Forward propulsion unit centred on the fuselage; wing and tail "
        "seen edge-on."),
    "FIG5_rear": ("FIG. 5", "Rear view",
        "Twin vertical fins and the H-tail horizontal stabiliser, seen "
        "from behind."),
    "FIG6_left": ("FIG. 6", "Left side view",
        "Fuselage pod profile, boom run, and tail assembly in profile."),
    "FIG7_right": ("FIG. 7", "Right side view", "Mirror of FIG. 6."),
}

REAL_FLAG = {
    "FIG1_isometric": "mixed", "FIG2_top": "mixed", "FIG3_bottom": "mixed",
    "FIG4_front": "mixed", "FIG5_rear": "mixed", "FIG6_left": "schematic",
    "FIG7_right": "schematic",
}

def b64(name):
    data = (HERE / f"{name}.png").read_bytes()
    return base64.b64encode(data).decode("ascii")


cards = []
for f in FIGS:
    fig_no, title, note = CAPTIONS[f]
    cards.append(f'''
        <figure class="sheet">
          <div class="sheet-reg tl"></div><div class="sheet-reg tr"></div>
          <div class="sheet-reg bl"></div><div class="sheet-reg br"></div>
          <img src="data:image/png;base64,{b64(f)}" alt="{title}" loading="lazy">
          <figcaption>
            <span class="fig-no">{fig_no}</span>
            <span class="fig-title">{title}</span>
            <span class="fig-note">{note}</span>
          </figcaption>
        </figure>''')

CARDS_HTML = "\n".join(cards)

TEMPLATE_PATH = HERE / "_artifact_template.html"
OUT_PATH = HERE / "patent_drawing_sheet.html"

template = TEMPLATE_PATH.read_text(encoding="utf-8")
OUT_PATH.write_text(template.replace("__CARDS__", CARDS_HTML),
                    encoding="utf-8")
print("wrote", OUT_PATH, OUT_PATH.stat().st_size, "bytes")
