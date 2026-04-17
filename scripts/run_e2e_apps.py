#!/usr/bin/env python3
"""
Devsper E2E Demo — Two Production Applications
===============================================

App 1: Literature Survey  — photonic metasurfaces in AI (real arxiv papers → LaTeX → PDF)
App 2: Coding Report      — Mie scattering simulation   (real physics code → LaTeX → PDF)

Both use the cross-provider model router (auto picks best available across
OpenAI / Anthropic / GitHub / z.ai / Ollama with scored fallback chains).
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import textwrap
import time
import xml.etree.ElementTree as ET
from pathlib import Path

import httpx
from dotenv import load_dotenv

load_dotenv()
os.environ.setdefault("OLLAMA_HOST", "http://192.168.1.2:11434")

from devsper.providers.router.factory import reset_router
reset_router()

from devsper.utils.models import generate
from devsper.providers.model_router import available_providers, select_model_chain

OUTPUT = Path(__file__).parent.parent / "output"
OUTPUT.mkdir(exist_ok=True)


# ── Helpers ───────────────────────────────────────────────────────────────────

def banner(title: str) -> None:
    print("\n" + "═" * 70)
    print(f"  {title}")
    print("═" * 70)


def compile_pdf(tex_path: Path) -> Path | None:
    """Run pdflatex twice. Returns PDF path if it exists after compilation."""
    pdf = tex_path.with_suffix(".pdf")
    cmd = [
        "pdflatex", "-interaction=nonstopmode",
        "-output-directory", str(tex_path.parent),
        str(tex_path),
    ]
    for _ in range(2):
        subprocess.run(cmd, capture_output=True, text=True, cwd=str(tex_path.parent))
    if pdf.exists() and pdf.stat().st_size > 1000:
        return pdf
    # Show tail of log for diagnosis
    log = tex_path.with_suffix(".log")
    if log.exists():
        lines = log.read_text(errors="replace").splitlines()
        for l in [l for l in lines if l.startswith("!")]:
            print(f"   LaTeX error: {l}")
    return None


def call_model(prompt: str, task_type: str = "planning", label: str = "",
               max_tokens: int = 8192) -> str:
    chain = select_model_chain(task_type, n=5)
    label_str = f"[{label}] " if label else ""
    print(f"  {label_str}Chain: {' → '.join(c.split(':',1)[-1] for c in chain[:3])} ...")
    t0 = time.time()
    out = generate("auto", prompt, task_type=task_type, max_tokens=max_tokens)
    print(f"  {label_str}Done in {time.time()-t0:.1f}s  ({len(out):,} chars)")
    return out


def strip_fences(text: str) -> str:
    text = re.sub(r"^```(?:latex|tex|python)?\s*\n?", "", text.strip(), flags=re.IGNORECASE)
    text = re.sub(r"\n?```\s*$", "", text.strip())
    return text


def extract_latex(text: str) -> str:
    text = strip_fences(text)
    idx = text.find("\\documentclass")
    if idx > 0:
        text = text[idx:]
    return text


# ── App 1: Literature Survey ──────────────────────────────────────────────────

def fetch_arxiv(query: str, max_results: int = 8) -> list[dict]:
    url = "https://export.arxiv.org/api/query"
    r = httpx.get(url, params={
        "search_query": query,
        "max_results": max_results,
        "sortBy": "relevance",
    }, timeout=20.0)
    r.raise_for_status()
    ns = {"a": "http://www.w3.org/2005/Atom"}
    root = ET.fromstring(r.text)
    papers = []
    for entry in root.findall("a:entry", ns):
        title = (entry.findtext("a:title", "", ns) or "").strip().replace("\n", " ")
        abstract = (entry.findtext("a:summary", "", ns) or "").strip().replace("\n", " ")[:500]
        pub = (entry.findtext("a:published", "", ns) or "")[:4]
        authors = [a.findtext("a:name", "", ns) for a in entry.findall("a:author", ns)]
        arxiv_id = (entry.findtext("a:id", "", ns) or "").split("/abs/")[-1].split("v")[0]
        if title and arxiv_id:
            papers.append({"title": title, "abstract": abstract,
                           "year": pub, "authors": authors, "arxiv_id": arxiv_id})
    return papers


SURVEY_PROMPT = textwrap.dedent(r"""
You are an expert academic author. Write a COMPLETE LaTeX document: a rigorous
literature survey titled "Photonic Metasurfaces in Artificial Intelligence:
Design, Optimization, and Applications".

Use the following {n} papers retrieved from arXiv as your primary references.
Cite them as \cite{{ref1}}, \cite{{ref2}}, ... in order.

PAPERS FROM ARXIV:
{context}

REQUIREMENTS — follow exactly:
1. Start with \documentclass[11pt,a4paper]{{article}}
2. Packages: geometry, hyperref, booktabs, graphicx, amsmath, cite
   — do NOT use the 'abstract' package
3. \geometry{{margin=2.5cm}}
4. Title: "Photonic Metasurfaces in Artificial Intelligence: Design, Optimization, and Applications"
   Author: "Devsper Research System" \\ Date: \today
5. Sections (write at least 250 words each):
   - Abstract (use \begin{{abstract}}...\end{{abstract}})
   - 1. Introduction
   - 2. Background: Photonic Metasurfaces
   - 3. AI/ML Methods for Metasurface Design
   - 4. Inverse Design and Optimization
   - 5. Key Findings and Trends
   - 6. Open Challenges
   - 7. Conclusion
6. Include a summary table using booktabs:
   Paper | Year | Key Contribution — list all {n} papers
7. End with:
   \begin{{thebibliography}}{{99}}
   \bibitem{{ref1}} Author(s). Title. arXiv:ID, Year.
   ... one \bibitem per paper ...
   \end{{thebibliography}}
   \end{{document}}

Write ~3500 words of academic prose. Output ONLY valid LaTeX, no fences, no prose outside.
""").strip()


def run_app1() -> Path | None:
    banner("APP 1 — Literature Survey: Photonic Metasurfaces in AI")

    print("  [1/4] Fetching papers from arXiv ...")
    queries = [
        'all:"photonic metasurface" AND all:"machine learning"',
        'all:"metasurface" AND all:"inverse design" AND all:"neural network"',
        'all:"photonic metasurface" AND all:"deep learning"',
        'ti:"metasurface" AND abs:"artificial intelligence"',
    ]
    papers: list[dict] = []
    seen: set[str] = set()
    for q in queries:
        try:
            for p in fetch_arxiv(q, max_results=5):
                if p["arxiv_id"] not in seen:
                    papers.append(p)
                    seen.add(p["arxiv_id"])
        except Exception as e:
            print(f"    query failed: {e}")
        if len(papers) >= 14:
            break
    papers = papers[:8]
    print(f"  Found {len(papers)} papers")
    for i, p in enumerate(papers, 1):
        au = (p["authors"][0] if p["authors"] else "?").split()[-1]
        print(f"    [{i:02d}] {p['year']} {au} — {p['title'][:65]}")

    print("\n  [2/4] Generating LaTeX via best model ...")
    context_lines = []
    for i, p in enumerate(papers, 1):
        au = (p["authors"][0] if p["authors"] else "Unknown").split()[-1]
        if len(p["authors"]) > 1:
            au += " et al."
        context_lines.append(
            f"[{i}] {p['title']} — {au} ({p['year']}) arXiv:{p['arxiv_id']}\n"
            f"    {p['abstract'][:250]}"
        )
    context = "\n".join(context_lines)
    prompt = SURVEY_PROMPT.format(n=len(papers), context=context)
    latex = call_model(prompt, task_type="planning", label="survey", max_tokens=8192)
    latex = extract_latex(latex)

    # Safety: ensure document ends properly
    if "\\end{document}" not in latex:
        if "\\end{thebibliography}" in latex:
            latex += "\n\\end{document}"
        else:
            latex += "\n\\end{thebibliography}\n\\end{document}"

    print("\n  [3/4] Writing .tex ...")
    tex = OUTPUT / "photonic_survey.tex"
    tex.write_text(latex, encoding="utf-8")
    print(f"  Saved: {tex}  ({len(latex):,} chars)")

    print("\n  [4/4] Compiling PDF ...")
    pdf = compile_pdf(tex)
    if pdf:
        print(f"  ✓ PDF: {pdf}  ({pdf.stat().st_size // 1024} KB)")
    else:
        print("  ✗ Compilation failed — .tex saved for inspection")
    return pdf


# ── App 2: Coding Report — Mie Scattering ────────────────────────────────────

# Fallback Mie implementation (always works, used if LLM code fails)
MIE_REFERENCE_CODE = textwrap.dedent("""
import numpy as np
from scipy.special import spherical_jn, spherical_yn
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

def mie_qsca_qabs(x, m, n_max=None):
    \"\"\"Compute Mie scattering and absorption efficiencies.
    x: size parameter = 2*pi*r/lambda
    m: complex refractive index of sphere (relative to medium)
    \"\"\"
    if n_max is None:
        n_max = max(int(x + 4 * x**(1/3) + 2), 5)
    ns = np.arange(1, n_max + 1)
    mx = m * x

    psi_x  = x  * spherical_jn(ns, x)
    psi_mx = mx * spherical_jn(ns, mx)
    xi_x   = x  * (spherical_jn(ns, x) + 1j * spherical_yn(ns, x))

    dpsi_x  = spherical_jn(ns, x)  + x  * spherical_jn(ns, x,  derivative=True)
    dpsi_mx = spherical_jn(ns, mx) + mx * spherical_jn(ns, mx, derivative=True)
    dxi_x   = (spherical_jn(ns, x) + 1j*spherical_yn(ns, x)) + x*(
               spherical_jn(ns, x, derivative=True) + 1j*spherical_yn(ns, x, derivative=True))

    an = (m*psi_mx*dpsi_x  - psi_x *dpsi_mx) / (m*psi_mx*dxi_x  - xi_x*dpsi_mx)
    bn = (  psi_mx*dpsi_x  - m*psi_x*dpsi_mx) / (  psi_mx*dxi_x  - m*xi_x*dpsi_mx)

    factor = 2.0 / x**2
    Qext = factor * np.sum((2*ns + 1) * np.real(an + bn))
    Qsca = factor * np.sum((2*ns + 1) * (np.abs(an)**2 + np.abs(bn)**2))
    Qabs = Qext - Qsca
    return float(Qsca), float(Qabs)

# Compute over size parameter range
m = 1.5 + 0.01j   # SiO2-like nanoparticle in air
x_vals = np.linspace(0.1, 10, 300)
Qsca_vals, Qabs_vals = [], []
for x in x_vals:
    qs, qa = mie_qsca_qabs(x, m)
    Qsca_vals.append(qs)
    Qabs_vals.append(qa)
Qsca_vals = np.array(Qsca_vals)
Qabs_vals = np.array(Qabs_vals)

# Plot
fig, ax = plt.subplots(figsize=(8, 5))
ax.plot(x_vals, Qsca_vals, 'b-', linewidth=2, label=r'$Q_{sca}$')
ax.plot(x_vals, Qabs_vals, 'r--', linewidth=2, label=r'$Q_{abs}$')
ax.set_xlabel('Size parameter $x = 2\\pi r / \\lambda$', fontsize=13)
ax.set_ylabel('Efficiency', fontsize=13)
ax.set_title('Mie Scattering: Dielectric Nanoparticle (m = 1.5 + 0.01i)', fontsize=13)
ax.legend(fontsize=12)
ax.grid(True, alpha=0.3)
plt.tight_layout()
plt.savefig('mie_scattering.png', dpi=150)
plt.close()
print(f"Peak Qsca = {Qsca_vals.max():.4f} at x = {x_vals[Qsca_vals.argmax()]:.3f}")
print(f"Peak Qabs = {Qabs_vals.max():.4f} at x = {x_vals[Qabs_vals.argmax()]:.3f}")
print(f"Qsca at x=1: {float(mie_qsca_qabs(1.0, m)[0]):.4f}")
print(f"Qsca at x=5: {float(mie_qsca_qabs(5.0, m)[0]):.4f}")
print("Plot saved: mie_scattering.png")
""").strip()

CODING_LATEX_PROMPT = textwrap.dedent(r"""
Write a COMPLETE LaTeX technical report for the following Mie scattering Python simulation.

PYTHON CODE:
{code}

SIMULATION RESULTS:
{results}

REQUIREMENTS — follow exactly:
1. \documentclass[11pt,a4paper]{{article}}
2. Packages: geometry, hyperref, listings, xcolor, amsmath, graphicx
   — do NOT use the 'abstract' package
3. \geometry{{margin=2.5cm}}
4. Configure listings for Python:
   \lstset{{language=Python, basicstyle=\ttfamily\small,
     backgroundcolor=\color{{gray!10}}, frame=single,
     breaklines=true, numbers=left, numberstyle=\tiny}}
5. Title: "Mie Scattering Simulation: Photonic Nanoparticle Analysis"
   Author: "Devsper Coding System" \\ Date: \today
6. Sections:
   - Abstract (use \begin{{abstract}}...\end{{abstract}}, ~150 words)
   - 1. Introduction (Mie theory + relevance to photonic metasurfaces, ~300 words)
   - 2. Theory (equations for a_n, b_n, Q_sca, Q_abs using amsmath align env, ~400 words)
   - 3. Implementation (include FULL code using \begin{{lstlisting}}...\end{{lstlisting}})
   - 4. Results and Discussion (discuss numerical results and resonance peaks, ~400 words)
   - 5. Conclusion (~150 words)
7. After the Theory section, include:
   \begin{{figure}}[h]\centering
   \includegraphics[width=0.82\textwidth]{{mie_scattering}}
   \caption{{Mie scattering ($Q_{{sca}}$) and absorption ($Q_{{abs}}$) efficiencies
   versus size parameter $x = 2\pi r/\lambda$ for a dielectric nanoparticle
   with $m = 1.5 + 0.01i$.}}
   \label{{fig:mie}}
   \end{{figure}}
8. End with \end{{document}} (no bibliography needed)

Output ONLY valid LaTeX, no markdown fences, no prose outside the document.
""").strip()


def run_app2() -> Path | None:
    banner("APP 2 — Coding Report: Mie Scattering Simulation")

    # Step 1: try LLM-generated code, fall back to reference implementation
    print("  [1/5] Generating Python simulation code ...")
    llm_code = call_model(
        "Write a complete, runnable Python Mie scattering simulation using scipy.special "
        "spherical Bessel functions (spherical_jn, spherical_yn). Compute Q_sca and Q_abs "
        "for a dielectric nanoparticle (m=1.5+0.01j) over x=[0.1,10]. Save plot as "
        "'mie_scattering.png'. Print peak Q_sca, resonance x, Q_sca at x=1 and x=5. "
        "Output ONLY the Python code, no fences.",
        task_type="code", label="codegen", max_tokens=4096,
    )
    llm_code = strip_fences(llm_code)

    print("\n  [2/5] Running simulation ...")
    result_text = ""
    for code_attempt, code_label in [(llm_code, "LLM"), (MIE_REFERENCE_CODE, "reference")]:
        sim_py = OUTPUT / "mie_sim.py"
        sim_py.write_text(code_attempt, encoding="utf-8")
        proc = subprocess.run(
            [sys.executable, str(sim_py)],
            capture_output=True, text=True, timeout=60,
            cwd=str(OUTPUT),
        )
        out = (proc.stdout + proc.stderr).strip()
        if proc.returncode == 0 and (OUTPUT / "mie_scattering.png").exists():
            result_text = out
            print(f"  ({code_label} code succeeded)")
            print(f"  Output: {out[:300]}")
            # Use whichever code worked for the report
            final_code = code_attempt
            break
        else:
            print(f"  ({code_label} code failed: {out[:150]})")
            final_code = MIE_REFERENCE_CODE
    else:
        result_text = "Simulation did not produce output."
        final_code = MIE_REFERENCE_CODE

    print("\n  [3/5] Generating LaTeX report ...")
    prompt = CODING_LATEX_PROMPT.format(code=final_code, results=result_text or "See code.")
    latex = call_model(prompt, task_type="planning", label="latex", max_tokens=8192)
    latex = extract_latex(latex)
    if "\\end{document}" not in latex:
        latex += "\n\\end{document}"

    print("\n  [4/5] Writing .tex ...")
    tex = OUTPUT / "mie_scattering_report.tex"
    tex.write_text(latex, encoding="utf-8")
    print(f"  Saved: {tex}  ({len(latex):,} chars)")

    print("\n  [5/5] Compiling PDF ...")
    pdf = compile_pdf(tex)
    if pdf:
        print(f"  ✓ PDF: {pdf}  ({pdf.stat().st_size // 1024} KB)")
    else:
        print("  ✗ Compilation failed — .tex and .py saved for inspection")
    return pdf


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print(f"\nProviders: {sorted(available_providers())}")
    print(f"Output:    {OUTPUT}/")

    t0 = time.time()
    pdf1 = run_app1()
    pdf2 = run_app2()

    banner("RESULTS")
    total = time.time() - t0
    print(f"  Total runtime: {total:.0f}s\n")
    status1 = f"✓  {pdf1}  ({pdf1.stat().st_size//1024} KB)" if pdf1 else "✗  failed — see photonic_survey.tex"
    status2 = f"✓  {pdf2}  ({pdf2.stat().st_size//1024} KB)" if pdf2 else "✗  failed — see mie_scattering_report.tex"
    print(f"  Research PDF:  {status1}")
    print(f"  Coding PDF:    {status2}")
    print()
    if pdf1 or pdf2:
        files = " ".join(str(p) for p in [pdf1, pdf2] if p)
        print(f"  open {files}")
