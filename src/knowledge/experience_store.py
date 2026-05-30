# -*- coding: utf-8 -*-
"""经验积累系统 — Agent 的纠错回路持久化。"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, field, asdict
from datetime import datetime


@dataclass
class Experience:
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
        if not self._loaded:
            self._load()
        self._experiences[exp.id] = exp
        self._save()
        return exp

    def record_correction(self, domain, trigger, symptom, root_cause, fix, template_name=None):
        exp_id = f"exp_{int(time.time())}_{domain}"
        exp = Experience(id=exp_id, domain=domain, category="fix", trigger=trigger, symptom=symptom, root_cause=root_cause, fix=fix, template_name=template_name)
        return self.add(exp)

    def get(self, exp_id: str) -> Optional[Experience]:
        if not self._loaded:
            self._load()
        return self._experiences.get(exp_id)

    def find_by_domain(self, domain: str) -> list[Experience]:
        if not self._loaded:
            self._load()
        return [e for e in self._experiences.values() if e.domain == domain]

    def find_relevant(self, domain: str, symptom_keywords: list[str]) -> list[Experience]:
        if not self._loaded:
            self._load()
        results = []
        for exp in self._experiences.values():
            if exp.domain != domain:
                continue
            symptom_lower = exp.symptom.lower()
            if any(kw.lower() in symptom_lower for kw in symptom_keywords):
                results.append(exp)
        return results

    def get_prompt_context(self, domain: str) -> str:
        exps = self.find_by_domain(domain)
        if not exps:
            return f"(No experiences for {domain} yet)"
        exps.sort(key=lambda e: e.verified_count, reverse=True)
        top = exps[:10]
        lines = ["## Historical experiences (by reliability)\n"]
        for exp in top:
            lines.append(f"- **{exp.category}**: {exp.trigger} -> {exp.symptom}")
            lines.append(f"  Fix: {exp.fix}")
        return "\n".join(lines)

    def verify(self, exp_id: str):
        if not self._loaded:
            self._load()
        if exp_id in self._experiences:
            self._experiences[exp_id].verified_count += 1
            self._save()

    def list_all(self, domain: Optional[str] = None) -> list[dict]:
        if not self._loaded:
            self._load()
        exps = self._experiences.values()
        if domain:
            exps = [e for e in exps if e.domain == domain]
        return [asdict(e) for e in exps]

    @property
    def count(self) -> int:
        if not self._loaded:
            self._load()
        return len(self._experiences)


_experience_store: Optional[ExperienceStore] = None


def get_experience_store() -> ExperienceStore:
    global _experience_store
    if _experience_store is None:
        _experience_store = ExperienceStore()
    return _experience_store
