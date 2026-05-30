# -*- coding: utf-8 -*-
u"""Knowledge Bridge — connects comsol-agent to comsol-mcp knowledge base.
知识桥 — 将 comsol-agent 与 comsol-mcp 知识库打通。

Unified knowledge retrieval with multi-source aggregation and priority:
统一知识检索，多源聚合 + 优先级排序：

  Priority / 优先级:
  1. ExperienceStore (correction memory / 纠错记忆)     ← 最可靠
  2. TemplateStore  (pitfalls in templates / 模板常见坑)
  3. Embedded Guides (Markdown: API, physics, workflow)
  4. PDF Vector Search (ChromaDB / semantic search)
  5. Physics Topic Guides (physics_get_guide)

Sources / 知识来源:
  - comsol-mcp MCP tools: docs_get, pdf_search, physics_get_guide, troubleshoot
  - comsol-mcp embedded Markdown files: mph_api.md, physics_guide.md, workflow.md
  - comsol-mcp ChromaDB: 413MB vector index of 51 COMSOL module PDFs
  - comsol-agent local: TemplateStore, ExperienceStore
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

# Paths to comsol-mcp knowledge
COMSOL_MCP_DIR = Path(r"D:\Program Files\Claude\comsol-mcp")
PROMPTS_DIR = COMSOL_MCP_DIR / "src" / "knowledge" / "prompts"
PDF_DIR = COMSOL_MCP_DIR / "pdf"
KNOWLEDGE_DB_DIR = COMSOL_MCP_DIR / "knowledge_base"


class KnowledgeBridge:
    u"""Unified knowledge interface for COMSOL Agent.

    Usage / 使用:
        kb = KnowledgeBridge()
        result = kb.query("How to set up periodic boundary conditions for photonic crystal?")
        # Returns aggregated results from all sources in priority order.

        context = kb.get_full_context(domain="photonic_crystal", topic="eigenfrequency")
        # Returns complete LLM-ready context for the given domain and topic.
    """

    def __init__(self):
        self._guides_cache: dict[str, str] = {}
        self._physics_cache: Optional[dict] = None
        self._loaded = False

    # ==================================================================
    # Source 1+2: Local templates & experiences
    # ==================================================================

    def _get_experiences(self, domain: str, keywords: list[str] = None) -> list[dict]:
        u"""Get relevant correction experiences."""
        from .experience_store import get_experience_store
        store = get_experience_store()
        if keywords:
            return [
                {"trigger": e.trigger, "symptom": e.symptom, "fix": e.fix,
                 "verified": e.verified_count}
                for e in store.find_relevant(domain, keywords)
            ]
        else:
            return [
                {"trigger": e.trigger, "symptom": e.symptom, "fix": e.fix,
                 "verified": e.verified_count}
                for e in store.find_by_domain(domain)
            ]

    def _get_template_pitfalls(self, domain: str) -> list[str]:
        u"""Get common pitfalls from matching templates."""
        from .template_store import get_template_store
        store = get_template_store()
        templates = store.find_by_domain(domain)
        pitfalls = []
        for t in templates:
            pits = t.to_dict().get("common_pitfalls", [])
            pitfalls.extend(pits)
        return pitfalls

    # ==================================================================
    # Source 3: Embedded Markdown guides
    # ==================================================================

    def _load_guides(self):
        u"""Load all embedded Markdown guides into cache."""
        if self._loaded:
            return
        for md_file in PROMPTS_DIR.glob("*.md"):
            try:
                content = md_file.read_text(encoding="utf-8")
                self._guides_cache[md_file.stem] = content
            except Exception:
                pass
        self._loaded = True

    def get_embedded_doc(self, topic: str) -> Optional[str]:
        u"""Get embedded Markdown documentation by topic name."""
        self._load_guides()
        return self._guides_cache.get(topic)

    def list_embedded_docs(self) -> list[str]:
        u"""List available embedded documentation topics."""
        self._load_guides()
        return list(self._guides_cache.keys())

    def search_guides(self, keywords: list[str]) -> list[dict]:
        u"""Search embedded guides for matching keywords."""
        self._load_guides()
        results = []
        for name, content in self._guides_cache.items():
            content_lower = content.lower()
            score = sum(1 for kw in keywords if kw.lower() in content_lower)
            if score > 0:
                # Extract relevant sections (paragraphs containing keywords)
                paragraphs = content.split("\n\n")
                relevant_paras = []
                for p in paragraphs:
                    if any(kw.lower() in p.lower() for kw in keywords):
                        relevant_paras.append(p.strip()[:300])
                results.append({
                    "source": "embedded_guide",
                    "name": name,
                    "score": score,
                    "snippets": relevant_paras[:3],
                })
        results.sort(key=lambda x: x["score"], reverse=True)
        return results

    # ==================================================================
    # Source 4+5: Physics guides & PDF search (via direct file access)
    # ==================================================================

    def _load_physics_topics(self) -> dict:
        u"""Load physics topic guides from embedded.py."""
        if self._physics_cache is not None:
            return self._physics_cache

        # Import the embedded module to get TOPIC_GUIDES
        import sys
        sys.path.insert(0, str(COMSOL_MCP_DIR))
        try:
            from src.knowledge.embedded import TOPIC_GUIDES, KNOWLEDGE_FILES
            self._physics_cache = {
                "topics": TOPIC_GUIDES,
                "files": KNOWLEDGE_FILES,
            }
        except Exception as e:
            self._physics_cache = {"topics": {}, "files": {}}
        return self._physics_cache

    def get_physics_topic(self, physics_type: str) -> Optional[dict]:
        u"""Get physics topic guide for specific physics type."""
        data = self._load_physics_topics()
        for topic_name, topic_data in data["topics"].items():
            if physics_type.lower() in topic_name.lower():
                return {"topic": topic_name, "data": topic_data}
        return None

    def list_physics_topics(self) -> list[str]:
        u"""List all available physics topic guides."""
        data = self._load_physics_topics()
        return list(data["topics"].keys())

    # ==================================================================
    # Source 5: PDF module listing
    # ==================================================================

    def list_pdf_modules(self) -> list[str]:
        u"""List available COMSOL PDF modules."""
        if not PDF_DIR.exists():
            return []
        return sorted([d.name for d in PDF_DIR.iterdir() if d.is_dir()])

    def find_relevant_module(self, domain: str, physics: str = "") -> list[str]:
        u"""Find relevant PDF modules for a given domain/physics."""
        modules = self.list_pdf_modules()
        relevant = []

        # Domain-based matching
        domain_map = {
            "photonic_crystal": ["Wave_Optics", "RF_Module", "ACDC_Module", "COMSOL_Multiphysics"],
            "polariton": ["Semiconductor_Module", "Wave_Optics", "ACDC_Module"],
            "plasmonic": ["Wave_Optics", "RF_Module", "ACDC_Module"],
            "metasurface": ["Wave_Optics", "RF_Module"],
            "thermal": ["Heat_Transfer_Module"],
            "structural": ["Structural_Mechanics_Module", "Nonlinear_Structural_Materials_Module"],
            "fluid": ["CFD_Module", "Microfluidics_Module"],
            "electromagnetic": ["ACDC_Module", "RF_Module", "Wave_Optics_Module"],
        }

        candidates = domain_map.get(domain, [])
        for mod in modules:
            if any(c.lower() in mod.lower() for c in candidates):
                relevant.append(mod)

        return relevant if relevant else modules[:5]  # fallback: top 5

    # ==================================================================
    # Unified query / 统一查询接口
    # ==================================================================

    def query(self, question: str, domain: str = "", top_k: int = 5) -> dict:
        u"""Unified knowledge query across all sources.

        Args:
            question: Natural language question / 自然语言问题
            domain: Physics domain for filtering / 物理领域
            top_k: Max results per source / 每源最大结果数

        Returns:
            {
                "question": str,
                "domain": str,
                "results": {
                    "experiences": [...],      # correction memory
                    "template_pitfalls": [...],  # common pitfalls
                    "embedded_guides": [...],    # markdown docs
                    "physics_topics": [...],     # physics topic guides
                    "pdf_modules": [...],        # relevant PDF modules
                },
                "summary": str,                  # short summary for LLM
            }
        """
        import re
        keywords = [w.lower() for w in re.findall(r'\w+', question) if len(w) > 2]

        results = {
            "experiences": [],
            "template_pitfalls": [],
            "embedded_guides": [],
            "physics_topics": [],
            "pdf_modules": [],
        }

        # Priority 1: Experiences
        if domain:
            exps = self._get_experiences(domain, keywords[:5])
            results["experiences"] = [
                {"trigger": e["trigger"], "fix": e["fix"], "verified": e["verified"]}
                for e in exps[:top_k]
            ]

        # Priority 2: Template pitfalls
        if domain:
            pitfalls = self._get_template_pitfalls(domain)
            # Filter by keyword relevance
            relevant_pitfalls = []
            for p in pitfalls:
                if any(kw in p.lower() for kw in keywords):
                    relevant_pitfalls.append(p)
            results["template_pitfalls"] = relevant_pitfalls[:top_k]

        # Priority 3: Embedded guides
        guide_matches = self.search_guides(keywords)
        results["embedded_guides"] = guide_matches[:top_k]

        # Priority 4: Physics topics
        for kw in keywords:
            topic = self.get_physics_topic(kw)
            if topic and topic not in results["physics_topics"]:
                results["physics_topics"].append(topic)

        # Priority 5: Relevant PDF modules
        results["pdf_modules"] = self.find_relevant_module(domain, "")[:top_k]

        # Generate summary
        summary = self._generate_summary(results, question)
        results["summary"] = summary

        return {"question": question, "domain": domain, "results": results, "summary": summary}

    def _generate_summary(self, results: dict, question: str) -> str:
        u"""Generate a concise summary for LLM context."""
        parts = []

        experiences = results.get("experiences", [])
        if experiences:
            parts.append(u"## Relevant Experiences / 相关纠错经验")
            for e in experiences[:3]:
                parts.append(f"- {e['trigger']} -> Fix: {e['fix']}")

        pitfalls = results.get("template_pitfalls", [])
        if pitfalls:
            parts.append(u"\n## Common Pitfalls / 常见坑")
            for p in pitfalls[:3]:
                parts.append(f"- {p}")

        guides = results.get("embedded_guides", [])
        if guides:
            parts.append(u"\n## Documentation / 文档参考")
            for g in guides[:2]:
                parts.append(f"- {g['name']}: {'; '.join(g.get('snippets', [])[:2])}")

        topics = results.get("physics_topics", [])
        if topics:
            parts.append(u"\n## Physics Guides / 物理场指南")
            for t in topics[:2]:
                tips = t.get("data", {}).get("tips", [])
                if tips:
                    parts.append(f"- {t['topic']}: {tips[0]}")

        modules = results.get("pdf_modules", [])
        if modules:
            parts.append(u"\n## Relevant PDF Modules / 相关模块文档")
            parts.append(f"- {', '.join(modules[:3])}")

        if not parts:
            return u"No relevant knowledge found. Try rephrasing or specify domain. / 未找到相关知识，请尝试换个问法或指定领域。"

        return "\n".join(parts)

    # ==================================================================
    # Full context generator for Agent / Agent 完整上下文
    # ==================================================================

    def get_full_context(self, domain: str = "", topic: str = "") -> str:
        u"""Generate complete LLM context for a simulation task.

        Combines: templates + experiences + guides + physics + PDF modules.
        组合：模板 + 经验 + 指南 + 物理场 + PDF 模块列表。
        """
        parts = []

        from .template_store import get_template_store
        from .experience_store import get_experience_store

        # 1. Templates
        if domain:
            templates = get_template_store().find_by_domain(domain)
            if templates:
                parts.append(u"## Available Templates / 可用模板")
                for t in templates:
                    parts.append(f"- {t.name}: {t.physics_type}, {t.dimension}, study={t.to_dict()['study_type']}")

        # 2. Experiences
        if domain:
            exp_ctx = get_experience_store().get_prompt_context(domain)
            if exp_ctx:
                parts.append(exp_ctx)

        # 3. Embedded docs
        parts.append(u"\n## Embedded Knowledge / 嵌入式知识")
        for doc_name in ["mph_api", "physics_guide", "workflow"]:
            doc = self.get_embedded_doc(doc_name)
            if doc:
                # Only include relevant sections if topic specified
                if topic and topic.lower() in doc.lower():
                    parts.append(f"\n### {doc_name}")
                    parts.append(doc[:2000] + "\n...(truncated)")
                elif not topic:
                    parts.append(f"\n### {doc_name} (available: use docs_get('{doc_name}'))")

        # 4. Physics topics
        parts.append(u"\n## Physics Topics Available / 物理专题指南")
        physics_topics = self.list_physics_topics()
        if physics_topics:
            parts.append(f"- {', '.join(physics_topics)}")
        else:
            parts.append(u"- (physics guides from MCP tools)")

        # 5. PDF modules
        parts.append(u"\n## PDF Documentation Modules / PDF 文档模块")
        if domain:
            relevant = self.find_relevant_module(domain)
            parts.append(f"- Relevant / 相关: {', '.join(relevant[:5])}")
        else:
            all_mods = self.list_pdf_modules()
            parts.append(f"- {len(all_mods)} modules available / 个模块可用 (use pdf_list_modules)")

        return "\n".join(parts)

    # ==================================================================
    # Status report / 状态报告
    # ==================================================================

    def status_report(self) -> dict:
        u"""Report on knowledge base status."""
        self._load_guides()
        return {
            "embedded_docs": len(self._guides_cache),
            "embedded_doc_names": list(self._guides_cache.keys()),
            "pdf_modules": len(self.list_pdf_modules()),
            "pdf_relevant_photonic": self.find_relevant_module("photonic_crystal"),
            "pdf_relevant_polariton": self.find_relevant_module("polariton"),
            "physics_topics": self.list_physics_topics(),
            "chromadb_path": str(KNOWLEDGE_DB_DIR / "chroma.sqlite3"),
            "chromadb_exists": (KNOWLEDGE_DB_DIR / "chroma.sqlite3").exists(),
            "chromadb_size_mb": round((KNOWLEDGE_DB_DIR / "chroma.sqlite3").stat().st_size / 1024 / 1024, 1)
                if (KNOWLEDGE_DB_DIR / "chroma.sqlite3").exists() else 0,
        }


# Global singleton
_bridge: Optional[KnowledgeBridge] = None


def get_knowledge_bridge() -> KnowledgeBridge:
    u"""Get KnowledgeBridge singleton."""
    global _bridge
    if _bridge is None:
        _bridge = KnowledgeBridge()
    return _bridge