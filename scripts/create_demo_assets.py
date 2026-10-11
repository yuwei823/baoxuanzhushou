"""Create explicitly synthetic marketing examples for UI and live smoke tests."""

import hashlib
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "src/insurance_audit/static"
FONT = Path("C:/Windows/Fonts/msyh.ttc")
EXAMPLES = [
    [
        "保险知识小课堂",
        "分红保险：如何理解演示利益？",
        "请结合下一张图片的风险说明阅读。",
        "仅作教育演示，不推荐具体产品。",
    ],
    [
        "风险与限制说明",
        "分红属于非保证利益，实际分红可能为零。",
        "不要把演示收益当作承诺收益。",
        "仅作教育演示，不推荐具体产品。",
    ],
]


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    manifest = {}
    for index, lines in enumerate(EXAMPLES, 1):
        image = Image.new("RGB", (1000, 520), "#f0f5ed")
        draw = ImageDraw.Draw(image)
        draw.rounded_rectangle((25, 25, 975, 495), 20, fill="#ffffff")
        for row, line in enumerate(lines):
            draw.text(
                (60, 65 + row * 100),
                line,
                font=ImageFont.truetype(str(FONT), 35 if row == 0 else 28),
                fill="#173d36",
            )
        path = OUTPUT / f"demo-{index}.png"
        image.save(path)
        manifest[hashlib.sha256(path.read_bytes()).hexdigest()] = "\n".join(lines)
    (OUTPUT / "demo-images.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
