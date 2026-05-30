# -*- coding: utf-8 -*-
"""COMSOL-specific paper parser — core base + COMSOL domain keywords.
COMSOL 专用论文解析器 — core 基础 + COMSOL 领域关键词."""

import re
from pathlib import Path
from ..core.paper_parser_base import (
    PaperInfo, extract_text_from_pdf, scan_text,
    scan_numeric_params, scan_boundary_conditions,
)

# ============================================================
# COMSOL-SPECIFIC KEYWORD DICTIONARIES / COMSOL 专用关键词词典
# ============================================================

DOMAIN_KEYWORDS = {
    "photonic_crystal": ["photonic crystal", "photonic bandgap", "Bloch mode", "hexagonal lattice", "square lattice", "Wu-Hu", "band structure"],
    "polariton": ["polariton", "exciton-polariton", "strong coupling", "Rabi splitting", "microcavity", "quantum well", "TMDC"],
    "plasmonic": ["plasmon", "surface plasmon", "LSPR", "nanoantenna", "metal nanoparticle"],
    "metasurface": ["metasurface", "meta-atom", "phase gradient", "Pancharatnam-Berry"],
}

PHYSICS_KEYWORDS = {
    "electromagnetic_waves": ["electromagnetic", "Maxwell", "permittivity", "dielectric"],
    "semiconductor": ["Schrodinger", "effective mass", "band gap", "exciton"],
    "heat_transfer": ["thermal", "temperature", "heat flux"],
    "solid_mechanics": ["stress", "strain", "elastic", "displacement"],
    "fluid_dynamics": ["laminar", "turbulent", "Navier-Stokes", "Reynolds"],
}

STUDY_KEYWORDS = {
    "eigenfrequency": ["eigenfrequency", "eigenmode", "band structure"],
    "stationary": ["stationary", "steady state", "static"],
    "time_dependent": ["time dependent", "transient", "time domain"],
    "frequency_domain": ["frequency domain", "frequency sweep"],
}

BC_KEYWORDS = {
    "periodic": ["periodic", "Bloch", "Brillouin"],
    "pml": ["PML", "perfectly matched layer", "absorbing boundary"],
    "scattering": ["scattering boundary", "SBC"],
    "port": ["port", "waveguide"],
}

NUMERIC_PATTERNS = [
    (r"(?:lattice\s*constant|pitch|period)\s*(?:a\s*[=＝]\s*)?(\d+\.?\d*)\s*(nm|um|mm)", "lattice_constant", "length"),
    (r"(?:radius|r\s*[=＝])\s*(\d+\.?\d*)\s*(nm|um|mm)", "radius", "length"),
    (r"(?:wavelength)\s*[=＝]\s*(\d+\.?\d*)\s*(nm|um|mm)", "wavelength", "length"),
    (r"(?:permittivity|epsilon)\s*[=＝]\s*(\d+\.?\d*)", "permittivity", "dimensionless"),
    (r"(?:refractive\s*index|n\s*[=＝])\s*(\d+\.?\d*)", "refractive_index", "dimensionless"),
    (r"(?:thickness|t\s*[=＝])\s*(\d+\.?\d*)\s*(nm|um|mm)", "thickness", "length"),
    (r"(?:frequency|f\s*[=＝])\s*(\d+\.?\d*)\s*(THz|GHz|MHz)", "frequency", "frequency"),
    (r"(?:Rabi\s*splitting)\s*[=＝~～]\s*(\d+\.?\d*)\s*(meV|eV)", "rabi_splitting", "energy"),
]


def scan_paper_domain(text: str) -> dict:
    """Scan paper text for COMSOL-relevant domain/physics/study type."""
    domain = scan_text(text, DOMAIN_KEYWORDS)
    physics = scan_text(text, PHYSICS_KEYWORDS)
    study = scan_text(text, STUDY_KEYWORDS)
    return {
        "domain": domain["best"], "physics": physics["best"],
        "study": study["best"], "confidence": domain["confidence"],
    }


def parse_paper(pdf_path: Path) -> PaperInfo:
    """Full paper parse: PDF -> PaperInfo with COMSOL-specific extraction."""
    text = extract_text_from_pdf(pdf_path)
    return parse_paper_text(text, title=pdf_path.stem)


def parse_paper_text(text: str, title: str = "") -> PaperInfo:
    """Parse paper text with COMSOL-specific keyword extraction."""
    info = PaperInfo(title=title)
    scan = scan_paper_domain(text)
    info.domain = scan["domain"]
    info.physics_type = scan["physics"]
    info.study_type = scan["study"]
    info.confidence = scan["confidence"]
    info.geometry_params = scan_numeric_params(text, NUMERIC_PATTERNS)
    info.boundary_conditions = scan_boundary_conditions(text, BC_KEYWORDS)

    if any(kw in text for kw in ["2D", "two-dimensional"]): info.dimension = "2D"
    elif any(kw in text for kw in ["3D", "three-dimensional"]): info.dimension = "3D"
    else: info.dimension = "2D"

    if not info.geometry_params: info.missing_info.append("geometry params (extract from text or figures)")
    if not info.boundary_conditions: info.missing_info.append("boundary condition type (check Methods section)")
    if info.study_type == "unknown": info.missing_info.append("solver type")
    if info.domain == "unknown": info.missing_info.append("domain recognition failed")
    return info


def format_for_agent(paper_info: PaperInfo) -> str:
    """Format PaperInfo as LLM prompt text."""
    lines = [f"## Paper: {paper_info.title}",
             f"- Domain: {paper_info.domain} (confidence: {paper_info.confidence})",
             f"- Physics: {paper_info.physics_type} | Dimension: {paper_info.dimension}",
             f"- Study type: {paper_info.study_type}"]
    if paper_info.geometry_params:
        lines.append("\n### Extracted params")
        for k, v in paper_info.geometry_params.items(): lines.append(f"  - {k}: {v}")
    if paper_info.boundary_conditions:
        lines.append("\n### Detected BCs")
        for bc in paper_info.boundary_conditions: lines.append(f"  - {bc['type']}")
    if paper_info.missing_info:
        lines.append("\n### Missing (needs confirmation)")
        for m in paper_info.missing_info: lines.append(f"  - {m}")
    return "\n".join(lines)

# Backward-compatible wrappers / 向后兼容包装器
def scan_numeric_params_default(text: str) -> dict[str, str]:
    '''Scan with COMSOL default patterns.'''
    return scan_numeric_params(text, NUMERIC_PATTERNS)

def scan_boundary_conditions_default(text: str) -> list[dict]:
    '''Scan with COMSOL default BC keywords.'''
    return scan_boundary_conditions(text, BC_KEYWORDS)
