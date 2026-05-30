# -*- coding: utf-8 -*-
"""
=============================================================================
Core Experience Store — 100% Software-Agnostic / 100%软件无关
=============================================================================

COPY THIS FILE to any new agent project. No changes needed.
复制本文件到任何新 Agent 项目，无需修改。

This module manages a persistent store of corrections and learnings.
Works for COMSOL, ANSYS, Lumerical, or any simulation tool.
本模块管理纠错和学习记录的持久化存储。
适用于 COMSOL、ANSYS、Lumerical 或任何仿真工具。

Usage for new software / 新软件用法:
    from core.experience_store import ExperienceStore, Experience
    store = ExperienceStore(Path("./ansys_agent/experiences.json"))
    store.record_correction(domain="thermal", ...)
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, field, asdict
from datetime import datetime


@dataclass
class Experience:
    """A single learning record / 单条经验记录.

    Fields / 字段:
        id          : Unique identifier
        domain      : Domain tag (photonic_crystal, thermal, structural...)
        category    : Type: pitfall / fix / optimization / best_practice
        trigger     : What action caused the issue
        symptom     : What error/phenomenon appeared
        root_cause  : Why it happened
        fix         : The correct approach
        template_name: Associated template (optional)
        timestamp   : When recorded
        verified_count: Times this fix was validated (higher = more reliable)
    """
    id: str
    domain: str
    category: str
    trigger: str
    symptom: str
    root_cause: str
    fix: str
    template_name: Optional[str] = None
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    verified_count: int = 0

    def to_text(self) -> str:
        """Human-readable summary / 人类可读摘要."""
        return f"""
[Experience {self.id}] [{self.domain}] [{self.category}]
Trigger: {self.trigger}
Symptom: {self.symptom}
Root cause: {self.root_cause}
Fix: {self.fix}
Template: {self.template_name or 'N/A'}
Verified: {self.verified_count}
""".strip()


class ExperienceStore:
    """Persistent store of correction experiences / 纠错经验持久化存储.

    Key design / 设计要点:
    - Self-loading: reads from disk on first access
    - Auto-save: writes after every addition
    - Domain-scoped: experiences are tagged by domain for targeted retrieval
    - Verified count: trusted entries get higher priority

    Usage / 用法:
        store = ExperienceStore(Path("./my_experiences.json"))
        store.record_correction(domain="thermal", trigger="...", symptom="...", fix="...")
        relevant = store.find_relevant("thermal", ["diverged", "temperature"])
    """

    def __init__(self, store_path: Optional[Path] = None):
        if store_path is None:
            store_path = Path(__file__).parent.parent.parent / "experiments" / "experiences.json"
        self.store_path = Path(store_path)
        self._experiences: dict[str, Experience] = {}
        self._loaded = False

    def _load(self):
        if self.store_path.exists():
            with open(self.store_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            for exp_data in data:
                exp = Experience(**exp_data)
                self._experiences[exp.id] = exp
        self._loaded = True

    def _save(self):
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.store_path, "w", encoding="utf-8") as f:
            json.dump([asdict(e) for e in self._experiences.values()], f, ensure_ascii=False, indent=2)

    def add(self, exp: Experience) -> Experience:
        """Add an experience and persist / 添加经验并持久化."""
        if not self._loaded: self._load()
        self._experiences[exp.id] = exp
        self._save()
        return exp

    def record_correction(self, domain, trigger, symptom, root_cause, fix, template_name=None):
        """Quick correction record / 快速记录一条纠错."""
        exp_id = f"exp_{int(time.time())}_{domain}"
        exp = Experience(id=exp_id, domain=domain, category="fix", trigger=trigger, symptom=symptom, root_cause=root_cause, fix=fix, template_name=template_name)
        return self.add(exp)

    def get(self, exp_id: str) -> Optional[Experience]:
        if not self._loaded: self._load()
        return self._experiences.get(exp_id)

    def find_by_domain(self, domain: str) -> list[Experience]:
        """Get all experiences for a domain / 获取某领域全部经验."""
        if not self._loaded: self._load()
        return [e for e in self._experiences.values() if e.domain == domain]

    def find_relevant(self, domain: str, symptom_keywords: list[str]) -> list[Experience]:
        """Find experiences matching domain + symptom keywords / 按领域+症状关键词检索."""
        if not self._loaded: self._load()
        results = []
        for exp in self._experiences.values():
            if exp.domain != domain: continue
            symptom_lower = exp.symptom.lower()
            if any(kw.lower() in symptom_lower for kw in symptom_keywords):
                results.append(exp)
        return results

    def get_prompt_context(self, domain: str, max_items: int = 10) -> str:
        """Generate LLM prompt context for a domain / 生成LLM提示上下文."""
        exps = self.find_by_domain(domain)
        if not exps:
            return f"(No experiences for {domain} yet / {domain} 暂无经验)"
        exps.sort(key=lambda e: e.verified_count, reverse=True)
        top = exps[:max_items]
        lines = ["## Historical experiences (by reliability) / 历史经验\n"]
        for exp in top:
            lines.append(f"- **{exp.category}**: {exp.trigger} -> {exp.symptom}")
            lines.append(f"  Fix: {exp.fix}")
        return "\n".join(lines)

    def verify(self, exp_id: str):
        """Validate an experience (increases trust) / 验证经验（增加可信度）."""
        if not self._loaded: self._load()
        if exp_id in self._experiences:
            self._experiences[exp_id].verified_count += 1
            self._save()

    @property
    def count(self) -> int:
        if not self._loaded: self._load()
        return len(self._experiences)


# ============================================================
# For COMSOL Agent: factory function
# 为 COMSOL Agent 提供的工厂函数
# ============================================================
_experience_store: Optional[ExperienceStore] = None

def get_experience_store() -> ExperienceStore:
    global _experience_store
    if _experience_store is None:
        _experience_store = ExperienceStore()
    return _experience_store
