# -*- coding: utf-8 -*-
"""
=============================================================================
Core Paper Parser Base — 80% Software-Agnostic / 80%软件无关
=============================================================================

COPY THIS FILE to any new agent project. Only add new domain keywords.
复制本文件到任何新 Agent 项目，只需添加新的领域关键词。

Provides PDF text extraction and a generic PaperInfo data class.
The domain/physics/study keyword dictionaries are pluggable —
extend them for your specific software.
提供 PDF 文本提取和通用 PaperInfo 数据类。
领域/物理场/研究类型的关键词词典可插拔扩展。

Usage for new software / 新软件用法:
    from core.paper_parser_base import PaperInfo, scan_text, scan_numeric_params
    # Add your software-specific keywords
    DOMAIN_KEYWORDS["my_domain"] = ["my keyword 1", "my keyword 2"]
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, field


@dataclass
class PaperInfo:
    """Extracted simulation info from a paper / 从论文提取的仿真信息.

    All fields are optional — the parser fills what it can find.
    所有字段可选 — 解析器尽可能填充能找到的信息。
    """
    title: str = ""
    domain: str = ""                        # e.g., photonic_crystal, thermal
    physics_type: str = ""                  # e.g., electromagnetic, heat_transfer
    dimension: str = ""                     # 2D / 3D
    geometry_params: dict[str, str] = field(default_factory=dict)   # {param: value_with_unit}
    material_params: dict[str, str] = field(default_factory=dict)
    boundary_conditions: list[dict] = field(default_factory=list)   # [{type, keywords_found}]
    study_type: str = ""                    # eigenfrequency / stationary / ...
    confidence: str = "low"                 # low / medium / high
    missing_info: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "title": self.title, "domain": self.domain,
            "physics_type": self.physics_type, "dimension": self.dimension,
            "geometry_params": self.geometry_params, "material_params": self.material_params,
            "boundary_conditions": self.boundary_conditions, "study_type": self.study_type,
            "confidence": self.confidence, "missing_info": self.missing_info,
        }


# ---------------------------------------------------------------------------
# PDF Text Extraction / PDF 文本提取
# ---------------------------------------------------------------------------

def extract_text_from_pdf(pdf_path: Path) -> str:
    """Extract plain text from PDF using PyMuPDF / 用 PyMuPDF 提取 PDF 纯文本."""
    try:
        import fitz
    except ImportError:
        raise ImportError("PyMuPDF required: pip install pymupdf")
    doc = fitz.open(str(pdf_path))
    full_text = [page.get_text() for page in doc]
    doc.close()
    return "\n".join(full_text)


# ---------------------------------------------------------------------------
# Generic Keyword Scanner / 通用关键词扫描器
# ---------------------------------------------------------------------------

def scan_text(text: str, keyword_dict: dict[str, list[str]]) -> dict:
    """Scan text against keyword dictionaries, return best match per category.
    用关键词词典扫描文本，返回每个类别的最佳匹配。

    Parameters / 参数:
        text: The text to scan / 待扫描文本
        keyword_dict: {category: [keyword1, keyword2, ...]}
                      e.g., {"thermal": ["temperature", "heat"], "structural": ["stress"]}

    Returns / 返回:
        {best_category: str, confidence: str, scores: {category: score}}
    """
    text_lower = text.lower()
    scores = {}
    for category, keywords in keyword_dict.items():
        score = sum(1 for kw in keywords if kw.lower() in text_lower)
        if score > 0:
            scores[category] = score

    if not scores:
        return {"best": "unknown", "confidence": "low", "scores": {}}

    best = max(scores, key=scores.get)
    confidence = "high" if scores[best] >= 5 else ("medium" if scores[best] >= 3 else "low")
    return {"best": best, "confidence": confidence, "scores": scores}


# ---------------------------------------------------------------------------
# Numeric Parameter Extraction / 数值参数提取
# ---------------------------------------------------------------------------

def scan_numeric_params(text: str, patterns: list[tuple]) -> dict[str, str]:
    """Extract numeric parameters using regex patterns.
    用正则表达式模式提取数值参数。

    Parameters / 参数:
        text: The text to scan
        patterns: list of (regex, param_name, unit_type)
                  # e.g., [(r"temperature\\\\s*=\\\\s*(\d+)", "temperature", "K"), ...]

    Returns / 返回:
        {param_name: "value_unit"}   e.g., {"temperature": "300K"}
    """
    params = {}
    for pattern, param_name, unit_type in patterns:
        matches = re.findall(pattern, text, re.IGNORECASE)
        if matches:
            value, unit = matches[0] if isinstance(matches[0], tuple) else (matches[0], "")
            params[param_name] = f"{value}{unit}" if unit else value
    return params


# ---------------------------------------------------------------------------
# Boundary Condition Scanner / 边界条件扫描器
# ---------------------------------------------------------------------------

def scan_boundary_conditions(text: str, bc_keywords: dict[str, list[str]]) -> list[dict]:
    """Scan text for boundary condition keywords.
    扫描文本中的边界条件关键词。

    Parameters / 参数:
        text: The text to scan
        bc_keywords: {bc_type: [keyword1, keyword2, ...]}
                     e.g., {"periodic": ["periodic", "Bloch"]}

    Returns / 返回:
        [{"type": bc_type, "keywords_found": [matched keywords]}, ...]
    """
    text_lower = text.lower()
    found = []
    for bc_type, keywords in bc_keywords.items():
        matched = [kw for kw in keywords if kw.lower() in text_lower]
        if matched:
            found.append({"type": bc_type, "keywords_found": matched})
    return found


