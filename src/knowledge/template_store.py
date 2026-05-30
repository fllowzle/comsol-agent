# -*- coding: utf-8 -*-
"""
=============================================================================
仿真模板存储系统 (Template Store)
=============================================================================

这是 COMSOL Agent 知识层的核心组件——"仿真配方书"。

核心概念
--------
每个模板是一个结构化 YAML 文件，描述了一类物理模型的完整仿真设置：
  - 几何参数（晶格常数、散射体尺寸…）
  - 物理场配置（电磁波/热传导/结构力学…）
  - 边界条件（周期性/完美匹配层/散射边界…）
  - 求解器设置（本征频率/稳态/瞬态…）
  - 后处理（能带图/场分布/参数扫描…）
  - 常见坑（该模型最容易出错的点）
  - 验证标准（自动判断结果是否合理）

模板匹配算法
-----------
采用计分制匹配（非精确匹配，可模糊搜索）：
  domain 匹配     → +3 分  （最重要：光子晶体、极化激元…）
  physics 匹配    → +2 分  （电磁波、半导体、热传导…）
  dimension 匹配  → +1 分  （2D 还是 3D）
  得分最高者胜出。

使用方法
--------
# 加载所有模板
store = get_template_store()

# 列出所有领域
store.list_domains()  # -> ["photonic_crystal", "polariton", ...]

# 查找光子晶体相关模板
store.find_by_domain("photonic_crystal")

# 模糊匹配（给定领域+物理场自动找到最合适的模板）
store.match({"domain": "photonic_crystal", "physics": "electromagnetic"})

# 获取模板的 LLM 提示文本（可直接注入到 Codex 对话中）
store.get_prompt_context("Wu-Hu 光子晶体")

# 提取所有可调参数
template.extract_parameters()
# -> {"a": {"default": "1[um]", "description": "晶格常数"},
#     "R": {"default": "0.2*a", "description": "柱子半径"}, ...}

模板文件格式 (YAML)
-------------------
参见 templates/photonic_crystal/wu_hu.yaml 的完整示例，关键结构：

  meta:
    name: "模型名称"
    domain: photonic_crystal       # 领域标签（用于检索）
    common_pitfalls: [...]         # 常见坑列表（自动注入 LLM 提示）
  geometry:                        # 几何参数（symbol=可调参数名）
    unit_cell: {type: rhombus, lattice_constant: {symbol: a, default: "1[um]"}}
  physics:                         # 物理场配置
    interface: ElectromagneticWavesFrequencyDomain
  boundary_conditions:             # 边界条件（最关键的部分！）
    periodic: {type: PeriodicCondition, source_boundaries: [1,4], ...}
  study:                           # 求解器设置
    type: Eigenfrequency
  validation:                      # 自动验证
    checks: [{condition: "all(freq > 0)", severity: critical}, ...]

扩展新软件
---------
要支持新仿真软件（如 ANSYS、Lumerical），只需：
  1. 新建 templates/{software}/ 目录
  2. 为每种典型模型写一个 YAML 模板
  3. 不修改任何代码 — TemplateStore 自动扫描所有 YAML 文件
"""

from __future__ import annotations

import os
import yaml
import json
from pathlib import Path
from typing import Optional, Any
from dataclasses import dataclass, field


@dataclass
class SimulationTemplate:
    """单个仿真模板的数据结构。

    从 YAML 文件加载，提供结构化访问和参数提取。
    """
    name: str                          # 模板名（如 "Wu-Hu 光子晶体"）
    domain: str                        # 领域标签（photonic_crystal / polariton / ...）
    physics_type: str                  # 物理场类型（electromagnetic / semiconductor / ...）
    dimension: str                     # 维度（2D / 3D）
    raw: dict[str, Any] = field(default_factory=dict)  # 原始 YAML 数据

    @classmethod
    def from_yaml(cls, path: Path) -> "SimulationTemplate":
        """从 YAML 文件加载模板。"""
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
        """转为可序列化的摘要字典。"""
        return {
            "name": self.name,
            "domain": self.domain,
            "physics_type": self.physics_type,
            "dimension": self.dimension,
            "geometry": self._extract_geometry_summary(),
            "boundary_conditions": self._extract_bc_summary(),
            "study_type": self._extract_study_type(),
            "common_pitfalls": self.raw.get("meta", {}).get("common_pitfalls", []),
        }

    def _extract_geometry_summary(self) -> dict:
        geo = self.raw.get("geometry", {})
        return {
            "unit_cell_type": geo.get("unit_cell", {}).get("type", "unknown"),
            "scatterer_type": geo.get("scatterer", {}).get("type", "unknown"),
        }

    def _extract_bc_summary(self) -> list[str]:
        return list(self.raw.get("boundary_conditions", {}).keys())

    def _extract_study_type(self) -> str:
        return self.raw.get("study", {}).get("type", "unknown")

    def extract_parameters(self) -> dict[str, dict]:
        """
        递归提取模板中所有可调参数。

        遍历 geometry、physics、mesh、study 四个部分，
        找到所有带有 symbol 和 default 字段的节点。

        返回格式
        --------
        {
            "a":    {"default": "1[um]",  "description": "晶格常数"},
            "R":    {"default": "0.2*a",  "description": "柱子半径"},
            "f0":   {"default": "200[THz]","description": "搜索中心频率"},
            ...
        }
        """
        params = {}
        for section in ["geometry", "physics", "mesh", "study"]:
            section_data = self.raw.get(section, {})
            params.update(self._walk_params(section_data))
        return params

    def _walk_params(self, data: dict, prefix: str = "") -> dict:
        """递归遍历字典，提取所有 symbol+default 节点。"""
        result = {}
        for key, value in data.items():
            if isinstance(value, dict):
                if "symbol" in value and "default" in value:
                    result[value["symbol"]] = {
                        "default": value["default"],
                        "description": value.get("description", ""),
                        "path": f"{prefix}.{key}".strip("."),
                    }
                else:
                    result.update(self._walk_params(value, f"{prefix}.{key}".strip(".")))
        return result


# ---------------------------------------------------------------------------
# TemplateStore — 模板库管理器
# ---------------------------------------------------------------------------

class TemplateStore:
    """管理所有仿真模板的加载、检索、匹配和保存。

    使用方式
    --------
    # 全局单例（推荐）
    store = get_template_store()

    # 或指定自定义模板目录
    store = TemplateStore(Path("./my_templates"))

    自动发现
    --------
    构造函数会递归扫描 templates_dir 下所有 .yaml 文件并加载。
    新增模板只需放入对应领域子目录，无需修改任何代码。
    """

    def __init__(self, templates_dir: Optional[Path] = None):
        if templates_dir is None:
            # 默认模板目录：项目根目录下的 templates/
            templates_dir = Path(__file__).parent.parent.parent / "templates"
        self.templates_dir = Path(templates_dir)
        self._templates: dict[str, SimulationTemplate] = {}   # name -> template
        self._by_domain: dict[str, list[str]] = {}             # domain -> [name, ...]
        self._loaded = False

    def load_all(self) -> int:
        """递归加载 templates_dir 下所有 .yaml 文件。返回加载数量。"""
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

    def list_all(self) -> list[dict]:
        """列出所有模板的摘要信息。"""
        if not self._loaded: self.load_all()
        return [t.to_dict() for t in self._templates.values()]

    def list_domains(self) -> list[str]:
        """列出所有已覆盖的物理领域。"""
        if not self._loaded: self.load_all()
        return list(self._by_domain.keys())

    def get(self, name: str) -> Optional[SimulationTemplate]:
        """按名称精确获取模板。"""
        if not self._loaded: self.load_all()
        return self._templates.get(name)

    def find_by_domain(self, domain: str) -> list[SimulationTemplate]:
        """获取某个领域下的所有模板。"""
        if not self._loaded: self.load_all()
        names = self._by_domain.get(domain, [])
        return [self._templates[n] for n in names if n in self._templates]

    def match(self, query: dict) -> Optional[SimulationTemplate]:
        """
        根据查询条件匹配最佳模板（计分制模糊匹配）。

        query 示例
        ----------
        {"domain": "photonic_crystal", "physics": "electromagnetic", "dimension": "2D"}

        计分规则
        --------
        domain 完全匹配     → +3 分
        domain 部分匹配     → +3 分（使用 in 操作符，支持子系统匹配）
        physics 部分匹配    → +2 分
        dimension 完全匹配  → +1 分

        返回得分最高的模板，无匹配时返回 None。
        """
        if not self._loaded: self.load_all()

        candidates = list(self._templates.values())
        domain = query.get("domain", "")
        physics = query.get("physics", "").lower()
        dimension = query.get("dimension", "")

        scores = []
        for tmpl in candidates:
            score = 0
            if domain and domain in tmpl.domain:
                score += 3
            if physics and physics in tmpl.physics_type.lower():
                score += 2
            if dimension and dimension == tmpl.dimension:
                score += 1
            if score > 0:
                scores.append((score, tmpl))

        scores.sort(key=lambda x: x[0], reverse=True)
        return scores[0][1] if scores else None

    def get_prompt_context(self, name: str) -> str:
        """
        将模板转换为 LLM 可用的提示文本。

        生成的文本包含：
        - 模板基本信息（领域、物理场、维度、求解类型）
        - 所有可调参数及其默认值和描述
        - 该模型的常见坑列表

        这段文本可以直接注入到 Codex 对话上下文中，
        引导 LLM 正确使用该模板。
        """
        tmpl = self.get(name)
        if tmpl is None:
            return f"[error] template not found: {name}"

        pitfalls = "\n".join(f"  - {p}" for p in tmpl.to_dict().get("common_pitfalls", []))
        params = tmpl.extract_parameters()
        param_lines = "\n".join(
            f"  - {sym}: {info['default']}  # {info['description']}"
            for sym, info in params.items()
        )

        return f"""
## Template: {tmpl.name}
- Domain: {tmpl.domain}
- Physics: {tmpl.physics_type}
- Dimension: {tmpl.dimension}
- Study type: {tmpl.to_dict()['study_type']}
- Geometry: unit_cell={tmpl.to_dict()['geometry']['unit_cell_type']}, scatterer={tmpl.to_dict()['geometry']['scatterer_type']}

### Parameters
{param_lines}

### Common Pitfalls
{pitfalls}
""".strip()

    def save(self, template: SimulationTemplate, filename: Optional[str] = None) -> Path:
        """
        保存（新建或更新）模板到文件。

        自动按领域分目录存储：
        templates/{domain}/{name}.yaml

        如果 filename 不指定，自动从模板名生成。
        """
        domain_dir = self.templates_dir / template.domain
        domain_dir.mkdir(parents=True, exist_ok=True)
        fname = filename or f"{template.name.replace(' ', '_').lower()}.yaml"
        path = domain_dir / fname
        with open(path, "w", encoding="utf-8") as f:
            yaml.dump(template.raw, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
        self._templates[template.name] = template
        self._by_domain.setdefault(template.domain, []).append(template.name)
        return path


# ---------------------------------------------------------------------------
# 全局单例
# ---------------------------------------------------------------------------

_template_store: Optional[TemplateStore] = None


def get_template_store() -> TemplateStore:
    """获取模板库全局单例。首次调用时自动加载所有模板。"""
    global _template_store
    if _template_store is None:
        _template_store = TemplateStore()
        _template_store.load_all()
    return _template_store
