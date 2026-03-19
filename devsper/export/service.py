from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import json

from devsper.export.branding import load_branding
from devsper.export.collector import bundle_to_json_dict, collect_history_bundle
from devsper.export.pdf import build_pdf_from_html, build_pdf_from_latex
from devsper.export.writers import write_bundle_files


@dataclass
class ExportOptions:
    output_dir: str
    limit: int | None = None
    pdf_pipeline: str = "both"  # latex|html|both
    db_path: str | None = None


def export_all_runs(options: ExportOptions) -> dict:
    out_dir = Path(options.output_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    branding = load_branding()
    bundle = collect_history_bundle(limit=options.limit, db_path=options.db_path)
    written = write_bundle_files(bundle, out_dir, branding)

    history_json = out_dir / "history.json"
    history_json.write_text(json.dumps(bundle_to_json_dict(bundle), indent=2), encoding="utf-8")
    written["history_json"] = str(history_json)

    branding_json = out_dir / "branding.json"
    branding_json.write_text(
        json.dumps(
            {
                "product_name": branding.product_name,
                "logo_path": branding.logo_path,
                "primary_color": branding.primary_color,
                "accent_color": branding.accent_color,
                "background_color": branding.background_color,
                "font_sans": branding.font_sans,
                "font_mono": branding.font_mono,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    written["branding_json"] = str(branding_json)

    pdf_outputs: dict[str, str] = {}
    pdf_errors: dict[str, str] = {}
    if options.pdf_pipeline in ("latex", "both"):
        pdf, msg = build_pdf_from_latex(Path(written["all_runs_tex"]))
        if pdf:
            pdf_outputs["latex_pdf"] = pdf
        else:
            pdf_errors["latex_pdf"] = msg
    if options.pdf_pipeline in ("html", "both"):
        pdf, msg = build_pdf_from_html(Path(written["all_runs_html"]))
        if pdf:
            pdf_outputs["html_pdf"] = pdf
        else:
            pdf_errors["html_pdf"] = msg

    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "run_count": bundle.run_count,
        "output_dir": str(out_dir),
        "files": written,
        "pdf_outputs": pdf_outputs,
        "pdf_errors": pdf_errors,
        "pipelines": {"pdf_pipeline": options.pdf_pipeline},
    }
    manifest_path = out_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest
