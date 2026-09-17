"""Dump the template structure: every block (paragraph or table) with index,
style, and a text preview, so we can see exactly where each section lives."""
import sys
from docx import Document
from docx.document import Document as _Doc
from docx.table import Table
from docx.text.paragraph import Paragraph
from docx.oxml.ns import qn


def iter_block_items(parent):
    if isinstance(parent, _Doc):
        parent_elm = parent.element.body
    else:
        parent_elm = parent._tc
    for child in parent_elm.iterchildren():
        if child.tag == qn("w:p"):
            yield Paragraph(child, parent)
        elif child.tag == qn("w:tbl"):
            yield Table(child, parent)


doc = Document(sys.argv[1])
for i, block in enumerate(iter_block_items(doc)):
    if isinstance(block, Table):
        rows = len(block.rows)
        cols = len(block.columns)
        first = " | ".join(c.text.strip().replace("\n", " ")[:22] for c in block.rows[0].cells)
        print(f"[{i:03d}] TABLE {rows}x{cols}  hdr: {first}")
    else:
        style = block.style.name if block.style else "?"
        txt = block.text.strip().replace("\n", " ")
        # note images
        imgs = block._p.findall(".//" + qn("w:drawing"))
        img_mark = f"  <{len(imgs)} IMG>" if imgs else ""
        if txt or img_mark:
            print(f"[{i:03d}] {style[:26]:26} | {txt[:95]}{img_mark}")
        else:
            print(f"[{i:03d}] {style[:26]:26} | (empty)")
