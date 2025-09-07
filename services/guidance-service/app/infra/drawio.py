import os
import re
import uuid
import subprocess
import logging
from pathlib import Path
from typing import Optional
from datetime import datetime

logger = logging.getLogger(__name__)

# Prefer override via env DRAWIO_BIN; otherwise use 'drawio' in PATH
DRAWIO_BIN = os.getenv("DRAWIO_BIN", "drawio")

# Flags that make Electron/Draw.io reliable inside containers/CI
SAFE_FLAGS = [
    "--no-sandbox",
    "--disable-gpu",
    "--disable-dev-shm-usage",
    "--user-data-dir=/tmp/drawio-profile",
]

def ensure_valid_drawio_xml(xml_text: str, diagram_name: str = "Page-1") -> str:
    """
    Wrap raw/fragment content into a minimal valid Draw.io file so both
    the Draw.io CLI and app.diagrams.net can open it.
    """
    text = (xml_text or "").strip()
    if text.startswith("<mxfile"):
        return text

    # If it already contains a graph model, just wrap it in mxfile/diagram
    if "<mxGraphModel" in text:
        diagram_body = text
    else:
        # Last-ditch: turn the text into a single label so the file still opens
        safe_label = text[:200].replace('"', "&quot;")
        diagram_body = f"""
<mxGraphModel>
  <root>
    <mxCell id="0"/><mxCell id="1" parent="0"/>
    <mxCell id="2" value="{safe_label}" style="rounded=1;whiteSpace=wrap;html=1;" vertex="1" parent="1">
      <mxGeometry x="20" y="20" width="300" height="120" as="geometry"/>
    </mxCell>
  </root>
</mxGraphModel>
""".strip()

    now = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    did = uuid.uuid4().hex[:8]
    wrapped = f"""<mxfile host="app.diagrams.net" modified="{now}" agent="raina-guidance" version="24.7.16" type="device">
  <diagram id="{did}" name="{diagram_name}">
{diagram_body}
  </diagram>
</mxfile>"""
    return re.sub(r">\s+<", "><", wrapped)


def _run_drawio(src_drawio: Path, out_path: Path, fmt: str, scale: int = 2) -> bool:
    """Internal: call the Draw.io CLI with safe flags."""
    cmd = [
        DRAWIO_BIN, "--export",
        "--format", fmt,
        "--scale", str(scale),
        "--output", str(out_path),
        str(src_drawio),
        *SAFE_FLAGS,
    ]
    try:
        subprocess.run(
            cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=120
        )
        ok = out_path.exists() and out_path.stat().st_size > 0
        if not ok:
            logger.warning("drawio produced no output", extra={"cmd": " ".join(cmd), "out": str(out_path)})
        return ok
    except Exception as e:
        logger.warning("drawio export failed: %s", e, extra={"cmd": " ".join(cmd)})
        return False


def render_drawio_xml_to_png(xml_text: str, out_png: Path, *, drawio_bin: Optional[str] = None) -> bool:
    out_png.parent.mkdir(parents=True, exist_ok=True)
    src_drawio = out_png.with_suffix(".drawio")
    src_drawio.write_text(xml_text or "", encoding="utf-8")

    bin_path = drawio_bin or os.getenv("DRAWIO_BIN") or "drawio"
    base_cmd = [
        bin_path, "--export", "--format", "png", "--scale", "2",
        "--output", str(out_png), str(src_drawio),
        "--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage",
        "--user-data-dir=/tmp/drawio-profile"
    ]
    cmd = ["xvfb-run", "-a", "-s", "-screen 0 1280x720x24 -nolisten tcp -noreset"] + base_cmd

    try:
        subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        ok = out_png.exists() and out_png.stat().st_size > 0
        if ok:
            logger.info("Rendered drawio diagram", extra={"png": str(out_png)})
        else:
            logger.warning("drawio did not produce an image", extra={"png": str(out_png)})
        return ok
    except Exception as e:
        logger.warning("drawio export failed: %s", e)
        return False


def render_drawio_xml_to_svg(
    xml_text: str,
    out_svg: Path,
    *,
    diagram_name: str = "Page-1",
    scale: int = 1,
) -> bool:
    """
    Optional: export to SVG (great for crisp PDFs).
    """
    out_svg.parent.mkdir(parents=True, exist_ok=True)

    valid_xml = ensure_valid_drawio_xml(xml_text, diagram_name=diagram_name)
    src_drawio = out_svg.with_suffix(".drawio")
    src_drawio.write_text(valid_xml, encoding="utf-8")

    ok = _run_drawio(src_drawio, out_svg, fmt="svg", scale=scale)
    if ok:
        logger.info("Rendered drawio SVG", extra={"svg": str(out_svg)})
    return ok
