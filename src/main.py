# -*- coding: utf-8 -*-
\"\"\"COMSOL Agent 平台入口。\"\"\"

from pathlib import Path
from .agent.orchestrator import get_agent
from .knowledge.template_store import get_template_store
from .knowledge.experience_store import get_experience_store


def main():
    \"\"\"CLI 入口 — 打印状态并启动 Agent。\"\"\"
    agent = get_agent()
    print(agent.print_status())
    print("\nCOMSOL Agent 已就绪。通过 Codex MCP 协议交互。")
    print(f"模板目录: {get_template_store().templates_dir}")
    print(f"经验库: {get_experience_store().store_path}")


if __name__ == "__main__":
    main()
