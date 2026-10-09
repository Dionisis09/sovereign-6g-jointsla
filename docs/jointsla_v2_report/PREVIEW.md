# Preview the archived report

From the repository root:

```powershell
python -m pip install -r docs/jointsla_v2_report/requirements-preview.txt
python docs/jointsla_v2_report/render_word.py
```

The helper creates 30 page images, four contact sheets and a rendering receipt
in `.cache/v2_report_preview/`, which is excluded from Git. It works without a
desktop assistant installation or Microsoft Word. It previews the existing
Word-exported PDF under `qa/`; it does not convert a changed DOCX into a new PDF.
The archived Word document, PDF, figures, manifests and QA evidence remain intact.

Use `--dpi 72` for a smaller preview or `--output <directory>` for a separate
output location. The script refuses output inside the archived report folder.
Historical manifests retain their original source paths as provenance; those
machine-specific paths do not configure this preview helper.
