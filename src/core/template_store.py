# -*- coding: utf-8 -*-
"""
=============================================================================
Core Template Store — 100% Software-Agnostic / 100%软件无关
=============================================================================

COPY THIS FILE to any new agent project. No changes needed.
复制本文件到任何新 Agent 项目，无需修改。

Manages YAML-based simulation templates with fuzzy matching.
适用于任何基于 YAML 模板的仿真自动化的模板管理。

Usage for new software / 新软件用法:
    from core.template_store import TemplateStore, SimulationTemplate
    store = TemplateStore(Path("./ansys_agent/templates"))
    store.match({"domain": "thermal", "physics": "conduction"})

Template YAML format / 模板 YAML 格式:
    meta:
      name: "Model name"
      domain: thermal        # Domain tag for matching
      physics_type: heat_transfer
      dimension: 3D
    ...any software-specific sections...
"""

from __future__ import annotations

import yaml
from pathlib import Path
from typing import Optional, Any
from dataclasses import dataclass, field


@dataclass
class SimulationTemplate:
    """Generic simulation template / 通用仿真模板.

    The raw field holds the full YAML dict. Structured access via properties.
    raw 字段保存完整 YAML 字典，通过属性提供结构化访问。
    """

    name: str                         # Template name / 模板名
    domain: str                       # Domain tag / 领域标签 (thermal, photonic...)
    physics_type: str                 # Physics type / 物理场类型
    dimension: str                    # 2D / 3D
    raw: dict[str, Any] = field(default_factory=dict)  # Full YAML data / 完整 YAML 数据

    @classmethod
    def from_yaml(cls, path: Path) -> "SimulationTemplate":
        """Load template from YAML file / 从 YAML 文件加载模板."""
        with open(path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f)
        meta = raw.get("meta", {})
        return cls(
            name=meta.get("name", path.stem),
            domain=meta.get("domain", "unknown"),
            physics_type=meta.get("physics_type", "unknown"),
            dimension=meta.get("dimension", "2D"),
            raw=raw,
        )

    def to_dict(self) -> dict:
        """Serializable summary / 可序列化的摘要."""
        return {
            "name": self.name,
            "domain": self.domain,
            "physics_type": self.physics_type,
            "dimension": self.dimension,
        }

    def extract_parameters(self) -> dict[str, dict]:
        """Recursively extract all {symbol, default, description} params.
        递归提取所有带 symbol+default 的可调参数。

        Walks the entire YAML tree looking for keys with both 'symbol' and 'default'.
        遍历整个 YAML 树，找到所有同时有 symbol 和 default 的节点。
        """
        def walk(data: dict, prefix: str = "") -> dict:
            result = {}
            for key, value in data.items():
                if isinstance(value, dict):
                    if "symbol" in value and "default" in value:
                        result[value["symbol"]] = {
                            "default": value["default"],
                            "description": value.get("description", ""),
                        }
                    else:
                        result.update(walk(value, f"{prefix}.{key}".strip(".")))
            return result
        return walk(self.raw)


class TemplateStore:
    """Generic YAML template manager / 通用 YAML 模板管理器.

    Key features / 核心功能:
    - Auto-discovery: recursively loads all .yaml files
    - Fuzzy matching: scoring-based match by domain, physics, dimension
    - CRUD: create, read, update, delete templates
    - LLM context: generate prompt-ready text from templates

    Usage / 用法:
        store = TemplateStore(Path("./my_templates"))
        store.load_all()
        matched = store.match({"domain": "thermal"})
    """

    def __init__(self, templates_dir: Optional[Path] = None):
        if templates_dir is None:
            templates_dir = Path(__file__).parent.parent.parent / "templates"
        self.templates_dir = Path(templates_dir)
        self._templates: dict[str, SimulationTemplate] = {}
        self._by_domain: dict[str, list[str]] = {}
        self._loaded = False

    def load_all(self) -> int:
        """Load all YAML files recursively / 递归加载所有 YAML 文件."""
        self._templates.clear()
        self._by_domain.clear()
        count = 0
        for yaml_file in self.templates_dir.rglob("*.yaml"):
            try:
                tmpl = SimulationTemplate.from_yaml(yaml_file)
                self._templates[tmpl.name] = tmpl
                self._by_domain.setdefault(tmpl.domain, []).append(tmpl.name)
                count += 1
            except Exception as e:
                print(f"[TemplateStore] skip {yaml_file}: {e}")
        self._loaded = True
        return count

    # ---- Query / 查询 ----
    def list_all(self) -> list[dict]:
        if not self._loaded: self.load_all()
        return [t.to_dict() for t in self._templates.values()]

    def list_domains(self) -> list[str]:
        if not self._loaded: self.load_all()
        return list(self._by_domain.keys())

    def get(self, name: str) -> Optional[SimulationTemplate]:
        if not self._loaded: self.load_all()
        return self._templates.get(name)

    def find_by_domain(self, domain: str) -> list[SimulationTemplate]:
        if not self._loaded: self.load_all()
        return [self._templates[n] for n in self._by_domain.get(domain, []) if n in self._templates]

    def match(self, query: dict) -> Optional[SimulationTemplate]:
        """Fuzzy match best template by scoring / 计分制模糊匹配.

        Scoring rules / 计分规则:
            domain match     -> +3 (most important / 最重要)
            physics match    -> +2
            dimension match  -> +1
        """
        if not self._loaded: self.load_all()
        candidates = list(self._templates.values())
        domain_q = query.get("domain", "")
        physics_q = query.get("physics", "").lower()
        dimension_q = query.get("dimension", "")

        scores = []
        for tmpl in candidates:
            score = 0
            if domain_q and domain_q in tmpl.domain: score += 3
            if physics_q and physics_q in tmpl.physics_type.lower(): score += 2
            if dimension_q and dimension_q == tmpl.dimension: score += 1
            if score > 0: scores.append((score, tmpl))

        scores.sort(key=lambda x: x[0], reverse=True)
        return scores[0][1] if scores else None

    # ---- CRUD / 增删改查 ----
    def save(self, template: SimulationTemplate, filename: Optional[str] = None) -> Path:
        """Save template to file / 保存模板到文件."""
        domain_dir = self.templates_dir / template.domain
        domain_dir.mkdir(parents=True, exist_ok=True)
        fname = filename or f"{template.name.replace(' ', '_').lower()}.yaml"
        path = domain_dir / fname
        with open(path, "w", encoding="utf-8") as f:
            yaml.dump(template.raw, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
        self._templates[template.name] = template
        self._by_domain.setdefault(template.domain, []).append(template.name)
        return path

    # ---- LLM integration / LLM 集成 ----
    def get_prompt_context(self, name: str) -> str:
        """Generate LLM prompt text from template / 生成 LLM 提示文本."""
        tmpl = self.get(name)
        if tmpl is None: return f"[error] template not found: {name}"

        params = tmpl.extract_parameters()
        param_lines = "\n".join(f"  - {sym}: {info['default']}  # {info['description']}" for sym, info in params.items())

        return f"""
## Template: {tmpl.name}
- Domain: {tmpl.domain} | Physics: {tmpl.physics_type} | Dimension: {tmpl.dimension}

### Parameters
{param_lines}
""".strip()


# ============================================================
# For COMSOL Agent: factory function
# ============================================================
_template_store: Optional[TemplateStore] = None

def get_template_store() -> TemplateStore:
    global _template_store
    if _template_store is None:
        _template_store = TemplateStore()
        _template_store.load_all()
    return _template_store
