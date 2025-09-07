from pathlib import Path
from app.config import settings

OUTPUT_DIR = Path(settings.OUTPUT_DIR).resolve()
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

def path_for(filename: str) -> Path:
    return OUTPUT_DIR / filename

def images_dir_for_workspace(safe_workspace_name: str) -> Path:
    p = OUTPUT_DIR / "images" / safe_workspace_name
    p.mkdir(parents=True, exist_ok=True)
    return p

def rel_to_output(p: Path) -> Path:
    """Return a path relative to OUTPUT_DIR for embedding in Markdown."""
    try:
        return p.resolve().relative_to(OUTPUT_DIR.resolve())
    except Exception:
        return p  # as-is (absolute)
