"""Preview the archived Word-exported PDF without modifying the report.

This helper rasterizes the existing PDF; it does not regenerate it from Word.
Install requirements-preview.txt and run this script from any working directory.
"""
import argparse
import json
from pathlib import Path

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dpi", type=int, default=150)
    parser.add_argument("--output", type=Path,
                        default=ROOT / ".cache" / "v2_report_preview")
    args = parser.parse_args()
    if not 36 <= args.dpi <= 300:
        parser.error("--dpi must be between 36 and 300")
    output = args.output.resolve()
    if output == ROOT or output.is_relative_to(BASE):
        parser.error("Choose a preview directory outside the archived report folder")
    try:
        import pypdfium2 as pdfium
        from PIL import Image, ImageDraw
    except ImportError:
        parser.error("Install docs/jointsla_v2_report/requirements-preview.txt first")

    source = BASE / "qa" / "JointSLA_v2_Experimental_Report.pdf"
    output.mkdir(parents=True, exist_ok=True)
    pages = []
    with pdfium.PdfDocument(source) as document:
        for i in range(len(document)):
            page = document[i]
            bitmap = page.render(scale=args.dpi / 72)
            picture = bitmap.to_pil()
            path = output / f"page-{i + 1}.png"
            picture.save(path)
            picture.close()
            bitmap.close()
            page.close()
            pages.append(path)

    for start in range(0, len(pages), 9):
        with Image.new("RGB", (1800, 2550), "#dddddd") as canvas:
            draw = ImageDraw.Draw(canvas)
            for i, path in enumerate(pages[start:start + 9]):
                with Image.open(path) as original:
                    picture = original.convert("RGB")
                    picture.thumbnail((585, 810))
                    x, y = (i % 3) * 600, (i // 3) * 850
                    canvas.paste(picture, (x + (600 - picture.width) // 2, y + 30))
                    draw.text((x + 10, y + 8), path.stem, fill="black")
                    picture.close()
            canvas.save(output / f"contact_{start // 9 + 1}.png")

    receipt = {"pages": len(pages), "engine": "pypdfium2", "dpi": args.dpi,
               "source": source.relative_to(ROOT).as_posix(),
               "scope": "Preview of archived PDF; report and QA evidence unchanged"}
    (output / "render_receipt.json").write_text(
        json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(f"Rendered {len(pages)} pages to {output}")


if __name__ == "__main__":
    main()
