from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.router import get_router


def _create_ocr_smoke_image() -> Path:
    path = Path("data/ocr_smoke.png")
    path.parent.mkdir(exist_ok=True)
    image = Image.new("RGB", (480, 140), "white")
    draw = ImageDraw.Draw(image)
    draw.text((24, 50), "OCR TEST 123", fill="black")
    image.save(path)
    return path


def main() -> None:
    router = get_router()

    llm_text = router.llm().text("Reply with exactly: ok", max_tokens=128).strip()
    print(f"llm_ok={bool(llm_text)}")
    print(f"llm_text={llm_text[:80]}")

    image_path = _create_ocr_smoke_image()
    ocr_text = router.ocr().extract_text(file_path=str(image_path)).strip()
    print(f"ocr_ok={bool(ocr_text)}")
    print(f"ocr_text={ocr_text[:120]}")


if __name__ == "__main__":
    main()
