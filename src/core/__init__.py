# -*- coding: utf-8 -*-
"""
Core Modules — 100% Software-Agnostic / 100%软件无关
====================================================

These modules can be copied AS-IS to any new agent project.
No software-specific dependencies. No COMSOL references.
这些模块可以直接复制到任何新 Agent 项目，无需修改，无软件依赖。

Modules / 模块:
    experience_store.py   - Persistent correction memory / 持久化纠错记忆
    template_store.py     - YAML template manager with fuzzy matching / YAML模板匹配引擎
    paper_parser_base.py  - Generic PDF text extraction + keyword scanning / 通用PDF文本提取

How to reuse for new software (e.g., ANSYS Agent):
=================================================

    # 1. Copy the core/ directory to your new project
    cp -r comsol_agent/src/core ansys_agent/src/core

    # 2. Use directly — no changes needed
    from core.experience_store import ExperienceStore
    store = ExperienceStore(Path("./ansys_experiences.json"))

    from core.template_store import TemplateStore
    templates = TemplateStore(Path("./ansys_templates"))

    from core.paper_parser_base import PaperInfo, scan_text, scan_numeric_params
    info = PaperInfo(title="My Paper")

    # 3. Add your software-specific keywords
    DOMAIN_KEYWORDS = {"thermal": ["temperature", "heat", "conduction"], ...}
    PHYSICS_KEYWORDS = {"fluid": ["CFD", "turbulence", "Navier-Stokes"], ...}
    result = scan_text(paper_text, DOMAIN_KEYWORDS)

    # 4. The rest of the Agent architecture (orchestrator, SKILL.md)
    #    is also 95% reusable — just swap software-specific sections.
"""

from .experience_store import ExperienceStore, Experience, get_experience_store
from .template_store import TemplateStore, SimulationTemplate, get_template_store
from .paper_parser_base import PaperInfo, extract_text_from_pdf, scan_text, scan_numeric_params, scan_boundary_conditions
