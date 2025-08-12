# app/diagrams/drawio.py
# Minimal helpers to turn simple node/edge models into draw.io (mxGraph) XML.
# We keep layout dead-simple (grid/rows) so the first cut is usable out of the box.

from xml.sax.saxutils import escape

def _mxfile(diagram_name: str, inner_xml: str) -> str:
    return (
        f'<mxfile host="app.diagrams.net">'
        f'<diagram name="{escape(diagram_name)}">'
        f'<mxGraphModel><root>'
        f'<mxCell id="0"/><mxCell id="1" parent="0"/>'
        f'{inner_xml}'
        f'</root></mxGraphModel></diagram></mxfile>'
    )

def _rect_cell(id_: str, label: str, x: int, y: int, w: int = 160, h: int = 60, parent: str = "1") -> str:
    style = "rounded=1;whiteSpace=wrap;html=1;fillColor=#dae8fc;strokeColor=#6c8ebf;"
    return (
        f'<mxCell id="{id_}" value="{escape(label)}" style="{style}" vertex="1" parent="{parent}">'
        f'<mxGeometry x="{x}" y="{y}" width="{w}" height="{h}" as="geometry"/></mxCell>'
    )

def _edge_cell(id_: str, src: str, tgt: str, label: str = "", parent: str = "1") -> str:
    style = "endArrow=block;html=1;rounded=0;strokeColor=#6c8ebf;"
    return (
        f'<mxCell id="{id_}" value="{escape(label)}" style="{style}" edge="1" parent="{parent}" source="{src}" target="{tgt}">'
        f'<mxGeometry relative="1" as="geometry"/></mxCell>'
    )

def simple_grid(nodes: list[dict], edges: list[dict], title: str, cols: int = 4) -> str:
    """
    nodes: [{id, label}], edges: [{id, source, target, label?}]
    Returns a full draw.io mxfile string.
    """
    x0, y0, dx, dy = 40, 40, 200, 120
    xml_nodes = []
    for idx, n in enumerate(nodes):
        row, col = divmod(idx, cols)
        x, y = x0 + col * dx, y0 + row * dy
        xml_nodes.append(_rect_cell(n["id"], n["label"], x, y))
    xml_edges = [_edge_cell(e["id"], e["source"], e["target"], e.get("label", "")) for e in edges]
    return _mxfile(title, "".join(xml_nodes + xml_edges))
