from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re


@dataclass
class Branding:
    product_name: str
    logo_path: str
    primary_color: str
    accent_color: str
    background_color: str
    font_sans: str
    font_mono: str


def _extract_color(tailwind_text: str, token: str, fallback: str) -> str:
    m = re.search(rf"{re.escape(token)}\s*:\s*['\"](#[0-9A-Fa-f]{{6}})['\"]", tailwind_text)
    return m.group(1) if m else fallback


def load_branding() -> Branding:
    """Load homepage branding tokens with safe fallbacks."""
    runtime_root = Path(__file__).resolve().parents[2]
    repo_root = runtime_root.parent
    homepage_dir = repo_root / "homepage"
    logo = homepage_dir / "public" / "branding" / "logo.svg"
    tailwind = homepage_dir / "tailwind.config.js"

    primary = "#E0AAFF"
    accent = "#B9F2FF"
    background = "#0C0C12"
    font_sans = "Inter"
    font_mono = "Geist Mono"
    if tailwind.is_file():
        try:
            text = tailwind.read_text(encoding="utf-8")
            primary = _extract_color(text, "orchid", primary)
            accent = _extract_color(text, "cyan", accent)
            background = _extract_color(text, "background", background)
            m_sans = re.search(r"sans\s*:\s*\[\s*['\"]([^'\"]+)['\"]", text)
            if m_sans:
                font_sans = m_sans.group(1)
            m_mono = re.search(r"mono\s*:\s*\[\s*['\"]([^'\"]+)['\"]", text)
            if m_mono:
                font_mono = m_mono.group(1)
        except Exception:
            pass

    return Branding(
        product_name="devsper docproc",
        logo_path=str(logo) if logo.is_file() else "",
        primary_color=primary,
        accent_color=accent,
        background_color=background,
        font_sans=font_sans,
        font_mono=font_mono,
    )
