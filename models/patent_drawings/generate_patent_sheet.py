"""
generate_patent_sheet.py -- builds a 3-view patent-style line drawing
(isometric + top + side) straight from the verified FreeCAD solid model.

    "E:/proggramming/Freecad/bin/freecadcmd.exe" generate_patent_sheet.py

Replaces the earlier make_patent_views.py, which approximated the
airframe from a hand-derived point cloud before the real FreeCAD model
existed. Every line here comes from FreeCAD's own hidden-line-removal
projection of the actual solid (models/freecad/build_assembly.py) --
no separate geometry to keep in sync.

Pipeline: open the assembly -> build 3 TechDraw orthographic/iso
views -> pull each view's raw SVG path data via TechDraw.viewPartAsSvg
(headless, no GUI needed) -> compose them into one labelled sheet.
"""
import FreeCAD as App
import TechDraw

FREECAD_DIR = r"E:\proggramming\semester proj\models\freecad"
OUT_DIR = r"E:\proggramming\semester proj\models\patent_drawings"
SRC = FREECAD_DIR + r"\coconut_quadplane_assembly.FCStd"


def build_views(doc):
    objs = [o for o in doc.Objects if hasattr(o, "Shape") and o.Shape.Volume > 0]
    page = doc.addObject('TechDraw::DrawPage', 'PatentPage')
    template = doc.addObject('TechDraw::DrawSVGTemplate', 'Template')
    template.Template = (r"E:\proggramming\Freecad\data\Mod\TechDraw"
                         r"\Templates\ISO\A3_Landscape_blank.svg")
    page.Template = template

    def make_view(name, direction, xdirection):
        v = doc.addObject('TechDraw::DrawViewPart', name)
        v.Source = objs
        v.Direction = App.Vector(*direction)
        v.XDirection = App.Vector(*xdirection)
        page.addView(v)
        doc.recompute()
        v.ScaleType = "Custom"
        v.Scale = 0.12
        return v

    # aircraft axes: X = fore(-)/aft(+), Y = span, Z = up
    views = {
        "ViewIso": make_view("ViewIso", (1, -1, 1), (1, 1, 0)),
        "ViewTop": make_view("ViewTop", (0, 0, 1), (1, 0, 0)),
        "ViewSide": make_view("ViewSide", (0, -1, 0), (1, 0, 0)),
    }
    doc.recompute()
    return views


def compose_sheet(frags, out_path):
    PANEL_W, PANEL_H, PAD, LABEL_H = 480, 420, 16, 36
    panels = [("ViewIso", "FIG. 1 -- PERSPECTIVE VIEW"),
             ("ViewTop", "FIG. 2 -- TOP VIEW"),
             ("ViewSide", "FIG. 3 -- SIDE VIEW")]
    sheet_w = PANEL_W * 3 + PAD * 4
    sheet_h = PANEL_H + LABEL_H + PAD * 2
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {sheet_w} {sheet_h}" '
            f'width="{sheet_w}" height="{sheet_h}" font-family="Arial, sans-serif">',
            f'<rect x="0" y="0" width="{sheet_w}" height="{sheet_h}" fill="white"/>']
    for i, (key, label) in enumerate(panels):
        frag, (x0, y0, w, h) = frags[key]
        px, py = PAD + i * (PANEL_W + PAD), PAD
        vb_x, vb_y = x0, -(y0 + h)
        parts.append(f'<g transform="translate({px},{py})">')
        parts.append(f'<svg x="0" y="0" width="{PANEL_W}" height="{PANEL_H}" '
                     f'viewBox="{vb_x} {vb_y} {w} {h}" preserveAspectRatio="xMidYMid meet">')
        parts.append('<g transform="scale(1,-1)">')
        parts.append(frag)
        parts.append('</g></svg>')
        parts.append(f'<text x="{PANEL_W/2}" y="{PANEL_H + 24}" text-anchor="middle" '
                     f'font-size="16" fill="black">{label}</text>')
        parts.append('</g>')
    parts.append('</svg>')
    open(out_path, "w", encoding="utf-8").write("".join(parts))


def main():
    doc = App.openDocument(SRC)
    views = build_views(doc)

    # Each view's tight bounding box (x, y, width, height), in the
    # view's own local mm coordinates -- needed to give each panel a
    # correct viewBox, since viewPartAsSvg() returns bare <path> data
    # with no bounding info of its own. Measured directly against the
    # rendered SVG (load the raw fragment in a browser, wrap it in a
    # generous placeholder viewBox, then read element.getBBox()) --
    # NOT via regex on the path text, which is unreliable: elliptical
    # arc commands ("A rx ry x-axis-rotation ...") embed a rotation
    # angle that looks exactly like another coordinate. Fixed for this
    # model at Scale=0.12; re-measure the same way if the airframe's
    # overall dimensions change enough to matter.
    bboxes = {
        "ViewIso":  (-73.278, -48.229, 146.556, 96.458),
        "ViewTop":  (-78.657, -89.968, 157.314, 179.937),
        "ViewSide": (-78.657, -21.773, 157.314, 43.548),
    }
    frags = {name: (TechDraw.viewPartAsSvg(v), bboxes[name])
            for name, v in views.items()}

    out_svg = OUT_DIR + r"\patent_sheet.svg"
    compose_sheet(frags, out_svg)
    print("Wrote", out_svg)


main()
