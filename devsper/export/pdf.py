from __future__ import annotations

from pathlib import Path
import shutil
import subprocess


def _run(cmd: list[str], cwd: Path) -> tuple[bool, str]:
    try:
        p = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True, check=False)
        if p.returncode == 0:
            return True, (p.stdout or "").strip()
        return False, ((p.stderr or p.stdout or "").strip() or f"exit={p.returncode}")
    except Exception as e:
        return False, str(e)


def build_pdf_from_latex(tex_path: Path) -> tuple[str | None, str]:
    """Build PDF from LaTeX/BibTeX if tools are available."""
    if shutil.which("pdflatex") is None:
        return None, "pdflatex not found"
    cwd = tex_path.parent
    base = tex_path.stem
    ok, out = _run(["pdflatex", "-interaction=nonstopmode", tex_path.name], cwd)
    if not ok:
        return None, out
    aux_path = cwd / f"{base}.aux"
    use_bibtex = False
    if (cwd / f"{base}.bib").is_file() and aux_path.is_file() and shutil.which("bibtex") is not None:
        try:
            aux = aux_path.read_text(encoding="utf-8", errors="ignore")
            use_bibtex = "\\citation" in aux
        except Exception:
            use_bibtex = False
    if use_bibtex:
        ok_bib, out_bib = _run(["bibtex", base], cwd)
        if not ok_bib:
            return None, out_bib
        ok2, out2 = _run(["pdflatex", "-interaction=nonstopmode", tex_path.name], cwd)
        if not ok2:
            return None, out2
        ok3, out3 = _run(["pdflatex", "-interaction=nonstopmode", tex_path.name], cwd)
        if not ok3:
            return None, out3
    pdf = cwd / f"{base}.pdf"
    return (str(pdf), "ok") if pdf.is_file() else (None, "latex build finished but PDF missing")


def build_pdf_from_html(html_path: Path) -> tuple[str | None, str]:
    """Build PDF from HTML via available converter (wkhtmltopdf or pandoc)."""
    out_pdf = html_path.with_suffix(".html.pdf")
    if shutil.which("wkhtmltopdf"):
        ok, out = _run(["wkhtmltopdf", html_path.name, out_pdf.name], html_path.parent)
        return (str(out_pdf), "ok") if ok and out_pdf.is_file() else (None, out)
    if shutil.which("pandoc"):
        ok, out = _run(["pandoc", html_path.name, "-o", out_pdf.name], html_path.parent)
        return (str(out_pdf), "ok") if ok and out_pdf.is_file() else (None, out)
    return None, "No HTML->PDF converter found (install wkhtmltopdf or pandoc)"
