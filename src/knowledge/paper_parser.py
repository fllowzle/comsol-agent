# -*- coding: utf-8 -*-
"""论文解析器 - 从 PDF 论文提取仿真参数。"""

from __future__ import annotations

import re
import json
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, field


@dataclass
class PaperInfo:
    title: str = ""
    domain: str = ""
    physics_type: str = ""
    dimension: str = ""
    geometry_params: dict[str, str] = field(default_factory=dict)
    material_params: dict[str, str] = field(default_factory=dict)
    boundary_conditions: list[dict] = field(default_factory=list)
    study_type: str = ""
    solver_hints: dict = field(default_factory=dict)
    key_sentences: list[str] = field(default_factory=list)
    confidence: str = "low"
    missing_info: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "title": self.title, "domain": self.domain, "physics_type": self.physics_type,
            "dimension": self.dimension, "geometry_params": self.geometry_params,
            "material_params": self.material_params, "boundary_conditions": self.boundary_conditions,
            "study_type": self.study_type, "solver_hints": self.solver_hints,
            "confidence": self.confidence, "missing_info": self.missing_info,
        }


def extract_text_from_pdf(pdf_path: Path) -> str:
    try:
        import fitz
    except ImportError:
        raise ImportError("PyMuPDF required: pip install pymupdf")
    doc = fitz.open(str(pdf_path))
    full_text = []
    for page in doc:
        full_text.append(page.get_text())
    doc.close()
    return "\n".join(full_text)


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
}

STUDY_KEYWORDS = {
    "eigenfrequency": ["eigenfrequency", "eigenmode", "band structure"],
    "stationary": ["stationary", "steady state", "static"],
    "time_dependent": ["time dependent", "transient", "time domain"],
    "frequency_domain": ["frequency domain", "frequency sweep"],
}


def scan_paper_domain(text: str) -> dict:
    text_lower = text.lower()
    result = {"domain": "unknown", "physics": "unknown", "study": "unknown", "confidence": "low"}
    domain_scores = {}
    for domain, keywords in DOMAIN_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw.lower() in text_lower)
        if score > 0:
            domain_scores[domain] = score
    if domain_scores:
        best_domain = max(domain_scores, key=domain_scores.get)
        result["domain"] = best_domain
        result["confidence"] = "medium" if domain_scores[best_domain] >= 3 else "low"
    phys_scores = {}
    for phys, keywords in PHYSICS_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw.lower() in text_lower)
        if score > 0:
            phys_scores[phys] = score
    if phys_scores:
        result["physics"] = max(phys_scores, key=phys_scores.get)
    study_scores = {}
    for study, keywords in STUDY_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw.lower() in text_lower)
        if score > 0:
            study_scores[study] = score
    if study_scores:
        result["study"] = max(study_scores, key=study_scores.get)
    return result


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


def extract_numeric_params(text: str) -> dict[str, str]:
    params = {}
    for pattern, param_name, unit_type in NUMERIC_PATTERNS:
        matches = re.findall(pattern, text, re.IGNORECASE)
        if matches:
            value, unit = matches[0] if isinstance(matches[0], tuple) else (matches[0], "")
            params[param_name] = f"{value}{unit}" if unit else value
    return params


BC_KEYWORDS = {
    "periodic": ["periodic", "Bloch", "Brillouin"],
    "pml": ["PML", "perfectly matched layer", "absorbing boundary"],
    "scattering": ["scattering boundary", "SBC"],
    "port": ["port", "waveguide"],
    "pec": ["PEC", "perfect electric conductor"],
    "pmc": ["PMC", "perfect magnetic conductor"],
}


def scan_boundary_conditions(text: str) -> list[dict]:
    text_lower = text.lower()
    found = []
    for bc_type, keywords in BC_KEYWORDS.items():
        matched_kw = [kw for kw in keywords if kw.lower() in text_lower]
        if matched_kw:
            found.append({"type": bc_type, "keywords_found": matched_kw})
    return found


def parse_paper(pdf_path: Path) -> PaperInfo:
    text = extract_text_from_pdf(pdf_path)
    return parse_paper_text(text, title=pdf_path.stem)


def parse_paper_text(text: str, title: str = "") -> PaperInfo:
    info = PaperInfo(title=title)
    scan = scan_paper_domain(text)
    info.domain = scan["domain"]
    info.physics_type = scan["physics"]
    info.study_type = scan["study"]
    info.confidence = scan["confidence"]
    info.geometry_params = extract_numeric_params(text)
    info.boundary_conditions = scan_boundary_conditions(text)
    if any(kw in text for kw in ["2D", "two-dimensional"]):
        info.dimension = "2D"
    elif any(kw in text for kw in ["3D", "three-dimensional"]):
        info.dimension = "3D"
    else:
        info.dimension = "2D"
    if not info.geometry_params:
        info.missing_info.append("geometry params (extract from text or figures)")
    if not info.boundary_conditions:
        info.missing_info.append("boundary condition type (check Methods section)")
    if info.study_type == "unknown":
        info.missing_info.append("solver type (eigenfrequency? frequency domain? stationary?)")
    if info.domain == "unknown":
        info.missing_info.append("domain recognition failed (may need manual specification)")
    return info


def format_for_agent(paper_info: PaperInfo) -> str:
    lines = [
        f"## Paper: {paper_info.title}",
        f"- Domain: {paper_info.domain} (confidence: {paper_info.confidence})",
        f"- Physics: {paper_info.physics_type}",
        f"- Dimension: {paper_info.dimension}",
        f"- Study type: {paper_info.study_type}",
    ]
    if paper_info.geometry_params:
        lines.append("\n### Extracted params")
        for k, v in paper_info.geometry_params.items():
            lines.append(f"  - {k}: {v}")
    if paper_info.boundary_conditions:
        lines.append("\n### Detected boundary conditions")
        for bc in paper_info.boundary_conditions:
            lines.append(f"  - {bc['type']}: keywords {bc['keywords_found']}")
    if paper_info.missing_info:
        lines.append("\n### Missing (needs confirmation)")
        for m in paper_info.missing_info:
            lines.append(f"  - {m}")
    return "\n".join(lines)
