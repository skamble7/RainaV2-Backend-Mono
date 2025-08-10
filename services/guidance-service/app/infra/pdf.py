from pathlib import Path
from typing import Optional
import markdown
from weasyprint import HTML   # pip: weasyprint
# Alternatively: reportlab/md-to-pdf of your choice.

def markdown_to_pdf(md: str, out_path: Path) -> Path:
    html = markdown.markdown(md, extensions=["fenced_code", "tables", "toc"])
    HTML(string=f"<article>{html}</article>").write_pdf(str(out_path))
    return out_path
