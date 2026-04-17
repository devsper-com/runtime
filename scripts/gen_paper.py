#!/usr/bin/env python3
"""
Demo: one natural-language prompt → Devsper builds the agent pipeline,
picks the tools, executes research + simulation + writing, compiles PDF.

Usage:
    OLLAMA_HOST=http://192.168.1.2:11434 uv run python scripts/gen_paper.py
"""
import os, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
os.environ.setdefault("OLLAMA_HOST", "http://192.168.1.2:11434")
os.environ.setdefault("DEVSPER_MID_MODEL", "ollama:gemma4:e4b")
os.environ.setdefault("DEVSPER_FAST_MODEL", "ollama:gemma4:e4b")
os.environ.setdefault("DEVSPER_SLOW_MODEL", "ollama:gemma4:e4b")

# Reset cached router so env vars above are picked up
import devsper.providers.router.factory as _factory
_factory._router_instance = None

from devsper.graph.runtime import GraphRuntime

OUT_DIR = Path(__file__).parent.parent / "output"
OUT_DIR.mkdir(exist_ok=True)

# ─────────────────────────────────────────────────────────────────────────────
# The prompt. This is the ONLY thing the user provides.
# Devsper parses it, builds agents with the right tools, runs everything.
# ─────────────────────────────────────────────────────────────────────────────
PROMPT = f"""# Research Paper: Photonic Metasurfaces

Write a complete peer-reviewed academic paper on Photonic Metasurfaces and compile it to a LaTeX PDF.

- Search arxiv for the top 10 recent papers on photonic metasurfaces and dielectric metalenses. Extract real titles, authors, years, and key findings.
- Search arxiv for papers on Mie resonances, Pancharatnam-Berry phase, and inverse design of metasurfaces. Extract real citations.
- Simulate and compute: use python to run Mie theory (scipy.special.spherical_jn) to compute scattering cross-section spectra for Si nanospheres (r=75nm, 100nm, 125nm) across 400-900nm. Also compute phase response vs pillar diameter (100-300nm) for a TiO2 metasurface at 532nm using coupled dipole model. Save matplotlib figures to {OUT_DIR}/fig1_mie.png and {OUT_DIR}/fig2_phase.png.
- Write LaTeX for Abstract and Introduction sections covering: what metasurfaces are, generalized Snell's law (cite yu2011), historical context, and paper scope. Use real papers from the search results as \\cite{{key}} references.
- Write LaTeX for Theory section: generalized Snell's law equations, Mie resonances in dielectric nanoresonators, Pancharatnam-Berry geometric phase, Jones matrix formalism. Include equations in LaTeX math mode. Reference the simulation results.
- Write LaTeX for Design & Fabrication section: FDTD/FEM simulation methods, inverse design, EBL/nanoimprint fabrication, material platforms (Si, TiO2, GaN). Cite real papers from search.
- Write LaTeX for Applications section: metalenses (cite khorasaninejad2016), holography, beam steering, nonlinear metasurfaces, sensing. One subsection per application.
- Write LaTeX for Recent Advances and Challenges sections: tunable metasurfaces, AI-driven design, scalability challenges, future directions.
- Assemble all LaTeX sections with a proper document header, the simulation figures using \\includegraphics, a bibliography from the real arxiv search results, and compile to PDF using python subprocess pdflatex. Save final PDF to {OUT_DIR}/photonic_metasurfaces.pdf and print the path.
"""

if __name__ == "__main__":
    print("=" * 70)
    print("  Devsper: single prompt → agent pipeline → research paper")
    print(f"  Output: {OUT_DIR}/photonic_metasurfaces.pdf")
    print("=" * 70 + "\n")

    rt = GraphRuntime()
    result = rt.run_from_text(
        PROMPT,
        optimize_for="quality",
        population_size=8,
        max_generations=4,
    )

    print("\n" + "=" * 70)
    print(f"  Completed nodes: {result['completed_nodes']}")
    print("=" * 70)
    for node_id, output in result["results"].items():
        preview = output[:400].replace("\n", " ")
        print(f"\n[{node_id}] ({len(output)} chars)\n  {preview}...")

    pdf = OUT_DIR / "photonic_metasurfaces.pdf"
    if pdf.exists():
        print(f"\n✓ PDF ready: {pdf}")
    else:
        print("\n⚠  PDF not found — check node outputs above")
