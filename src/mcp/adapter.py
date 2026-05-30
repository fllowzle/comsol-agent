# -*- coding: utf-8 -*-
"""MCP 适配器 - 为 Agent 平台提供结构化的 MCP 工具调用接口。

在 Codex 中，MCP 工具直接由 LLM 通过协议调用。
本模块用于本地测试和脚本化调用。
"""

from __future__ import annotations

import subprocess
import json
import sys
from pathlib import Path
from typing import Optional


COMSOL_MCP_DIR = Path(r"D:\Program Files\Claude\comsol-mcp")


class McpToolCaller:
    """模拟 MCP 工具调用 - 用于本地测试。

    实际在 Codex 中，这些调用由 MCP 协议自动处理。
    这里用 Python 子进程调用 comsol-mcp 的内部函数。
    """

    def __init__(self):
        self._server_path = COMSOL_MCP_DIR / "src"
        sys.path.insert(0, str(COMSOL_MCP_DIR))
        from src.tools.session import session_manager
        self._session = session_manager

    @property
    def is_connected(self) -> bool:
        return self._session.is_connected

    # ---- Session ----

    def comsol_start(self, cores: int = 4) -> dict:
        return self._session.start(cores=cores)

    def comsol_status(self) -> dict:
        return self._session.get_status()

    def comsol_disconnect(self) -> dict:
        return self._session.disconnect()

    # ---- Simulation workflow (high-level) ----

    def simulate_from_template(
        self,
        template_name: str,
        params: Optional[dict] = None,
    ) -> dict:
        """从模板执行完整仿真流程。"""
        from comsol_agent.src.knowledge.template_store import get_template_store

        store = get_template_store()
        tmpl = store.get(template_name)
        if tmpl is None:
            return {"success": False, "error": f"Template not found: {template_name}"}

        results = {"steps": []}

        # Step 1: Session
        r = self.comsol_start()
        results["steps"].append({"step": "session", **r})
        if not r.get("success"):
            return results

        # Step 2: Create model
        try:
            from src.tools.model import session_manager
            client = session_manager.client
            model = client.create()
            model_name = session_manager.add_model(model)
            results["steps"].append({"step": "create_model", "success": True, "name": model_name})

            # Step 3: Component
            jm = model.java
            comp = jm.component().create("comp1", True)
            results["steps"].append({"step": "component", "success": True})

            # Step 4: Geometry
            geo = tmpl.raw.get("geometry", {})
            geom = comp.geom().create("geom1", 2 if tmpl.dimension == "2D" else 3)
            results["steps"].append({"step": "geometry_create", "success": True})

            # Add geometry feature
            scatterer = geo.get("scatterer", {})
            feature_type = scatterer.get("type", "Block")
            if feature_type == "Block":
                a_val = params.get("a", "1e-6") if params else "1e-6"
                block = geom.feature().create("blk1", "Block")
                block.set("size", [a_val, a_val, a_val])
            elif feature_type == "Cylinder":
                r_val = params.get("R", "2e-7") if params else "2e-7"
                cyl = geom.feature().create("cyl1", "Cylinder")
                cyl.set("r", r_val)
            results["steps"].append({"step": "geometry_feature", "success": True, "type": feature_type})

            # Step 5: Physics
            phys = tmpl.raw.get("physics", {})
            interface = phys.get("interface", "")
            if interface:
                physics_node = comp.physics().create("ewfd", interface, "geom1")
                results["steps"].append({"step": "physics", "success": True, "interface": interface})

            # Step 6: Mesh
            mesh_node = comp.mesh().create("mesh1")
            mesh_node.run()
            results["steps"].append({"step": "mesh", "success": True})

            # Step 7: Study
            study_type = tmpl.raw.get("study", {}).get("type", "")
            study_node = jm.study().create("std1")
            if study_type == "Eigenfrequency":
                step = study_node.create("eig1", "Eigenfrequency")
                step.set("neigs", "8")
            results["steps"].append({"step": "study_create", "success": True, "type": study_type})

            # Step 8: Solve
            try:
                model.solve()
                results["steps"].append({"step": "solve", "success": True})
            except Exception as e:
                results["steps"].append({"step": "solve", "success": False, "error": str(e)})

            results["success"] = True
            results["model_name"] = model_name
            return results

        except Exception as e:
            results["steps"].append({"step": "error", "error": str(e)})
            results["success"] = False
            return results


def get_mcp_caller() -> McpToolCaller:
    """获取 MCP 工具调用器（单例）。"""
    return McpToolCaller()
