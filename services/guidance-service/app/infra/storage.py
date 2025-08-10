from pathlib import Path
from app.config import settings

OUTPUT_DIR = Path(settings.OUTPUT_DIR)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

def pdf_path_for(artifact_id: str) -> Path:
    safe = artifact_id.replace("/", "_")
    return OUTPUT_DIR / f"{safe}.pdf"
