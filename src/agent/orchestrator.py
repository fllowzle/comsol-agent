# -*- coding: utf-8 -*-
"""
COMSOL Agent - Full-Stack Simulation Automation Platform
COMSOL Agent - 全栈仿真自动化平台

Architecture / 架构
-------------------
    User (NL / PDF paper) / 用户输入 (自然语言 / PDF论文)
      |
      v
  +---------------------------------------------------+
  |  SKILL.md (Codex Skill Layer / Codex 技能层)        |
  +---------------------------------------------------+
  |  AgentOrchestrator (Decision Core / 决策核心)        |
  |  analyze_goal() -> get_execution_plan()             |
  +------------------+--------------------------------+
  | Knowledge / 知识层 | Feedback / 反馈优化层            |
  |  TemplateStore     |  SolverDiagnostics             |
  |  PaperParser       |  ResultValidator               |
  |  ExperienceStore   |                                |
  +------------------+--------------------------------+
  |  MCP Tool Layer / MCP 工具层 (comsol-mcp 40+ tools) |
  +---------------------------------------------------+

Agent Decision Loop / Agent 决策回路 (Core Innovation / 核心创新)
------------------------------------------------------------------
  +----------------------------------------------------------+
  |  1. ANALYZE  Goal + Paper -> Domain + Template Match     |
  |  2. PLAN    Template -> Step-by-step execution plan      |
  |  3. BUILD   MCP tools -> Geometry + Physics + Mesh       |
  |  4. SOLVE   -> Results                                   |
  |  5. DIAGNOSE Failure? -> Root cause + Fix suggestion     |
  |  6. LEARN   User correction -> Store -> Auto-apply next  |
  |       |                                                  |
  |       +------------------ Loop / 循环 ------------------ |
  +----------------------------------------------------------+

Cross-Software Portability / 跨软件可移植性
-------------------------------------------
This architecture is the "skeleton of simulation automation",
decoupled from any specific simulation software:
  本架构是"仿真自动化的骨架"，与具体仿真软件解耦：

  - TemplateStore     : 100% reusable (just swap YAML content / 只换 YAML 内容)
  - PaperParser       : 80%  reusable (swap DOMAIN_KEYWORDS dict / 换关键词词典)
  - ExperienceStore   : 100% reusable (learning loop is software-agnostic / 纠错回路与软件无关)
  - AgentOrchestrator : 95%  reusable (analyze-plan-diagnose-learn loop unchanged)
  - SolverDiagnostics : 30%  reusable (error patterns are software-specific / 每种软件报错不同)

To adapt for new software / 适配新软件的步骤:
  1. Create {software}-mcp server (see docs/mcp_server_template.py)
  2. Create templates/{software}/ with 5-10 YAML templates
  3. Add domain keywords in paper_parser.py
  4. Update ERROR_PATTERNS in solver_diagnostics.py

Author: Codex + User collaboration / Codex + 用户协作
License: MIT
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, field
from enum import Enum

from ..knowledge.template_store import get_template_store, SimulationTemplate
from ..knowledge.paper_parser import PaperInfo, parse_paper, format_for_agent
from ..knowledge.experience_store import get_experience_store
from ..knowledge.knowledge_bridge import get_knowledge_bridge


# ---------------------------------------------------------------------------
# Task State Machine / 任务状态机
# ---------------------------------------------------------------------------

class TaskStatus(Enum):
    """7 states of a simulation task / 仿真任务的 7 种状态."""
    PENDING   = "pending"    # Just created, awaiting analysis
    PLANNING  = "planning"   # Matching template, generating plan
    MODELLING = "modelling"  # Building in COMSOL (geometry + physics + mesh)
    SOLVING   = "solving"    # Solving in progress
    ANALYZING = "analyzing"  # Analyzing results
    FIXING    = "fixing"     # Diagnosing and repairing failure
    COMPLETED = "completed"  # Successfully finished
    FAILED    = "failed"     # Failed after multiple repair attempts


@dataclass
class SimulationTask:
    """Complete state of a simulation task / 一个仿真任务的完整状态.

    Supports / 支持:
    - Resume from interruption / 断点续传 (recover from history)
    - Error traceback / 错误回溯 (errors list tracks all failures and fixes)
    - Audit trail / 结果审计 (every operation is recorded)
    """
    id: str                              # Unique task ID
    description: str                     # User's original description
    domain: str = ""                     # Physics domain (e.g. photonic_crystal)
    matched_template: Optional[str] = None
    paper_info: Optional[PaperInfo] = None
    adapted_params: dict = field(default_factory=dict)
    status: TaskStatus = TaskStatus.PENDING
    history: list[dict] = field(default_factory=list)
    errors: list[dict] = field(default_factory=list)
    result_summary: Optional[str] = None


# ==========================================================================
# AgentOrchestrator — Main Controller / 主控制器
# ==========================================================================

class AgentOrchestrator:
    """Decision brain of the COMSOL Agent / COMSOL Agent 的决策中枢.

    Design Principles / 设计原则
    ---------------------------
    1. Never calls COMSOL API directly — all simulation ops via MCP + Codex/LLM
    2. This module provides "structured decision framework" — analysis, plans, diagnoses
    3. All state is traceable — every step recorded, recoverable after crash
    4. Gets smarter over time — each correction stored as experience, auto-applied next time

    Usage / 使用方式
    ----------------
    # In Codex conversation (guided by SKILL.md)
    agent = get_agent()

    # User says: "simulate this paper"
    analysis = agent.analyze_goal("Simulate Wu-Hu photonic crystal", paper_path="paper.pdf")
    print(analysis["context_for_llm"])   # Full context to inject into LLM

    # Get step-by-step execution plan
    plan = agent.get_execution_plan("Wu-Hu photon crystal")

    # Diagnose failure
    diagnosis = agent.diagnose_error("Singular matrix", domain="photonic_crystal")

    # Learn from user correction
    agent.learn_from_correction(domain="photonic_crystal",
                                trigger="forgot PeriodicCondition",
                                symptom="all eigenfrequencies negative",
                                fix="add PeriodicCondition + k-vector sweep before solving")
    """

    def __init__(self):
        self.templates = get_template_store()     # Template library / 模板库
        self.experiences = get_experience_store()
        self.knowledge = get_knowledge_bridge() # Experience library / 经验库
        self._current_task: Optional[SimulationTask] = None

    # ==================================================================
    # Phase 1: Goal Understanding / 目标理解 (ANALYZE)
    # ==================================================================

    def analyze_goal(self, description: str, paper_path: Optional[str] = None) -> dict:
        """Analyze user goal: domain recognition, template matching, parameter extraction.
        分析用户目标：领域识别、模板匹配、参数提取。

        Workflow / 工作流程
        ------------------
        1. If paper exists -> parse_paper() extracts domain, params, boundary conditions
        2. Match template library by domain + physics + dimension
        3. Retrieve historical experiences for this domain
        4. Generate full LLM context

        Returns / 返回
        --------------
        {task_id, domain, matched_template, paper_analysis, context_for_llm, next_action}
        """
        task_id = f"task_{len(self.experiences._experiences) + 1}"
        task = SimulationTask(id=task_id, description=description)

        # Paper parsing / 论文解析
        paper_info = None
        if paper_path:
            pdf_path = Path(paper_path)
            if pdf_path.suffix.lower() == ".pdf":
                paper_info = parse_paper(pdf_path)
            else:
                from ..knowledge.paper_parser import parse_paper_text
                paper_info = parse_paper_text(paper_path)
            task.paper_info = paper_info
            task.domain = paper_info.domain
            task.status = TaskStatus.PLANNING

        # Template matching / 模板匹配
        query = {}
        if paper_info:
            query["domain"] = paper_info.domain
            query["physics"] = paper_info.physics_type
            query["dimension"] = paper_info.dimension
        matched = self.templates.match(query) if query else None
        task.matched_template = matched.name if matched else None

        # Build LLM context / 构建 LLM 上下文
        context = self._build_context(task, paper_info, matched)

        return {
            "task_id": task.id,
            "domain": task.domain,
            "matched_template": task.matched_template,
            "paper_analysis": paper_info.to_dict() if paper_info else None,
            "context_for_llm": context,
            "next_action": self._suggest_next_action(task, matched),
        }

    def _build_context(self, task, paper_info, matched):
        """Build full context for LLM injection / 构建注入 LLM 的完整上下文.

        Four layers of information / 四层信息:
        1. User goal / 用户目标
        2. Paper-extracted params and BCs / 论文提取的参数和边界条件
        3. Matched template (with pitfalls and adaptable params) / 匹配的模板（含常见坑和可调参数）
        4. Historical correction experiences for this domain / 该领域的历史纠错经验
        """
        parts = [f"## Task: {task.description}\n"]
        if paper_info:
            parts.append(format_for_agent(paper_info)); parts.append("")
        if matched:
            parts.append(self.templates.get_prompt_context(matched.name)); parts.append("")
        domain = task.domain or (paper_info.domain if paper_info else "unknown")
        if domain != "unknown":
            parts.append(self.experiences.get_prompt_context(domain)); parts.append("")
        return "\n".join(parts)

    def _suggest_next_action(self, task, matched):
        """Suggest next action based on current state / 根据当前状态建议下一步."""
        if task.paper_info and task.paper_info.missing_info:
            return f"Missing info: {', '.join(task.paper_info.missing_info)}. Ask user."
        if not matched:
            return "No template matched. Options: (1) specify domain (2) create template (3) ask user."
        return f"Matched template '{matched.name}'. Confirm params then start modelling."

    # ==================================================================
    # Phase 2: Execution Planning / 生成执行计划 (PLAN)
    # ==================================================================

    def get_execution_plan(self, template_name: str, adapted_params: dict = None) -> dict:
        """Generate step-by-step simulation execution plan from template.
        基于模板生成分步仿真执行计划。

        Typical steps / 典型步骤
        -----------------------
        1. comsol_start          - Start COMSOL session
        2. model_create          - Create empty model
        3. model_create_component- Create component container
        4. geometry_create       - Create geometry sequence
        5. geometry_add_feature  - Add geometry primitives
        6. physics_add           - Add physics interface
        7. physics_boundary_*    - Set boundary conditions (MOST CRITICAL! / 最关键!)
        8. mesh_create + build   - Generate mesh
        9. study_solve           - Solve
        10-12. results_*         - Postprocessing (band structure, field plots...)
        13. validate             - Auto-validate results
        """
        tmpl = self.templates.get(template_name)
        if tmpl is None:
            return {"error": f"Template not found: {template_name}"}

        steps = []
        steps.append({"step": 1, "action": "comsol_start", "description": "Start COMSOL session / 启动 COMSOL 会话"})
        steps.append({"step": 2, "action": "model_create + model_create_component", "description": "Create model and component / 创建模型和组件"})

        geo = tmpl.raw.get("geometry", {})
        steps.append({"step": 3, "action": "geometry_create + geometry_add_feature",
                      "feature_type": geo.get("scatterer", {}).get("type", "Block"),
                      "description": "Create geometry / 创建几何"})

        phys = tmpl.raw.get("physics", {})
        steps.append({"step": 4, "action": "physics_add", "interface": phys.get("interface", ""),
                      "description": f"Add {phys.get('interface', '')} physics / 添加物理场"})

        bcs = tmpl.raw.get("boundary_conditions", {})
        for bc_name, bc_config in bcs.items():
            steps.append({"step": len(steps) + 1, "action": "physics_boundary_selection",
                          "type": bc_config.get("type", ""),
                          "description": f"Setup {bc_name} boundary / 设置 {bc_name} 边界条件"})

        mesh = tmpl.raw.get("mesh", {})
        steps.append({"step": len(steps) + 1, "action": "mesh_create + mesh_build",
                      "description": "Generate mesh / 生成网格"})

        study = tmpl.raw.get("study", {})
        steps.append({"step": len(steps) + 1, "action": "study_solve",
                      "description": f"Solve ({study.get('type', '')}) / 求解"})

        post = tmpl.raw.get("postprocessing", {})
        for pp_name, pp_config in post.items():
            steps.append({"step": len(steps) + 1, "action": "results_export_image",
                          "description": f"Export: {pp_name} / 导出结果"})

        validation = tmpl.raw.get("validation", {})
        if validation.get("checks"):
            steps.append({"step": len(steps) + 1, "action": "validate_results",
                          "description": "Auto-validate / 自动验证"})

        return {
            "template": template_name,
            "total_steps": len(steps),
            "steps": steps,
            "common_pitfalls": tmpl.raw.get("meta", {}).get("common_pitfalls", []),
        }

    # ==================================================================
    # Phase 3: Error Diagnosis / 错误诊断 (DIAGNOSE)
    # ==================================================================

    def diagnose_error(self, error_message: str, domain: str) -> dict:
        """Diagnose COMSOL solve errors with root cause and fix suggestions.
        诊断 COMSOL 求解错误，给出根因和修复建议。

        Multi-layer diagnosis strategy / 多层诊断策略
        ---------------------------------------------
        1. Keyword match -> known error pattern library / 关键词匹配已知错误模式
        2. Experience search -> similar historical fixes / 经验库检索历史修复
        3. Generic advice -> fallback / 通用建议兜底

        Known error patterns / 已知错误模式
        ----------------------------------
        - "singular matrix" -> insufficient boundary conditions
        - "periodic"        -> conformal mesh mismatch on periodic boundaries
        - "did not converge"-> solver non-convergence (mesh/tolerance/initial)
        - "out of memory"   -> memory overflow
        - "failed to find"  -> COMSOL Java API object not found
        - "NullPointer"     -> mph API call order error
        """
        patterns = [
            ("singular matrix", {"cause": "Singular matrix - insufficient/conflicting boundary conditions / 矩阵奇异 - 边界条件不足或冲突", "fixes": ["Check physics constraints", "For Eigenfrequency: set search_around", "Check material params not zero/negative"]}),
            ("periodic", {"cause": "Periodic boundary mismatch / 周期性边界不匹配", "fixes": ["Ensure conformal mesh on source/dest boundaries", "Verify k-vector settings", "Use Copy mesh with source first"]}),
            ("did not converge", {"cause": "Solver non-convergence / 求解器不收敛", "fixes": ["Refine mesh / 细化网格", "Adjust solver tolerance", "Check initial values"]}),
            ("out of memory", {"cause": "Memory overflow / 内存不足", "fixes": ["Reduce mesh density", "Reduce eigenfrequency count"]}),
            ("failed to find", {"cause": "API object not found / API 对象未找到", "fixes": ["Check names (case-sensitive!)", "Ensure component exists before geometry"]}),
            ("NullPointerException|NoneType", {"cause": "Null reference - mph API order error / 空引用 - MPH 调用顺序错误", "fixes": ["Check parent objects created first", "Use model.java (property) not model.java() (function)"]}),
        ]
        error_lower = error_message.lower()
        matched = None
        for keyword, diagnosis in patterns:
            if any(kw in error_lower for kw in keyword.split("|")):
                matched = diagnosis; break

        symptom_keywords = [kw for kw in error_lower.split() if len(kw) > 3]
        relevant = self.experiences.find_relevant(domain, symptom_keywords[:5])

        return {
            "error": error_message,
            "diagnosis": matched or {"cause": "Unrecognized", "fixes": ["Check COMSOL logs", "Try simplest version", "Verify in COMSOL GUI"]},
            "relevant_experiences": [{"trigger": e.trigger, "fix": e.fix} for e in relevant],
        }

    # ==================================================================
    # Phase 4: Learning Loop / 学习回路 (LEARN)
    # ==================================================================

    def learn_from_correction(self, domain, trigger, symptom, fix, template_name=None):
        """Learn from user correction — key mechanism for Agent getting smarter.
        从用户纠错中学习 — Agent 越用越聪明的关键机制。

        Effects / 效果
        --------------
        Immediate / 立即: 本次纠错被存储
        Short-term / 短期: 后续同类任务自动检索并注入 LLM 提示
        Long-term / 长期: verified_count 高的经验获得更高权重

        Example / 示例
        --------------
        agent.learn_from_correction(
            domain="photonic_crystal",
            trigger="Tried to solve without PeriodicCondition",
            symptom="All eigenfrequencies returned negative / 本征频率全为负",
            fix="Must add PeriodicCondition + k-vector BEFORE solving / 求解前必须先设置周期性边界+k矢量",
            template_name="Wu-Hu photon crystal",
        )
        """
        exp = self.experiences.record_correction(domain=domain, trigger=trigger, symptom=symptom, root_cause="user feedback", fix=fix, template_name=template_name)
        return f"Recorded experience {exp.id}. Future {domain} tasks will auto-apply. / 已记录经验 {exp.id}，后续 {domain} 任务自动应用。"

    def query_knowledge(self, question: str, domain: str = "") -> dict:
        u"""Query the unified knowledge base across all sources."""
        return self.knowledge.query(question, domain=domain)

    def get_knowledge_context(self, domain: str = "", topic: str = "") -> str:
        u"""Get full knowledge context for a simulation task."""
        return self.knowledge.get_full_context(domain=domain, topic=topic)

    def knowledge_status(self) -> dict:
        u"""Get knowledge base status."""
        return self.knowledge.status_report()

    def print_status(self):
        """Print Agent status summary / 打印 Agent 状态摘要."""
        return "\n".join([
            "=" * 50,
            "COMSOL Agent Status",
            f"  Templates : {len(self.templates.list_all())} in {len(self.templates.list_domains())} domains",
            f"  Experiences: {self.experiences.count} entries",
            "=" * 50,
        ])


# Global singleton / 全局单例
_agent: Optional[AgentOrchestrator] = None

def get_agent() -> AgentOrchestrator:
    """Get Agent singleton / 获取 Agent 单例."""
    global _agent
    if _agent is None:
        _agent = AgentOrchestrator()
    return _agent
