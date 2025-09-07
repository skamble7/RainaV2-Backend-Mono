from pathlib import Path
from typing import Optional
import markdown
from weasyprint import HTML
from app.infra.storage import OUTPUT_DIR

def markdown_to_pdf(md: str, out_path: Path, base_dir: Optional[Path] = None) -> Path:
    """
    Convert Markdown -> HTML -> PDF.
    base_dir is critical so WeasyPrint can resolve relative image paths like 'images/...'.
    """
    html = markdown.markdown(md, extensions=["fenced_code", "tables", "toc"])
    base = str((base_dir or OUTPUT_DIR).resolve())
    HTML(string=f"<article>{html}</article>", base_url=base).write_pdf(str(out_path))
    return out_path
