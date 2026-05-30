#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""COMSOL Agent end-to-end test - validates full pipeline without COMSOL."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.agent.orchestrator import get_agent
from src.knowledge.template_store import get_template_store
from src.knowledge.paper_parser import scan_paper_domain, scan_numeric_params_default, scan_boundary_conditions_default
from src.knowledge.experience_store import get_experience_store
from src.feedback.solver_diagnostics import SolverDiagnostics, ResultValidator


def test_paper_parsing():
    print("=" * 50)
    print("TEST 1: Paper Parsing")
    text = "We study a 2D photonic crystal with hexagonal lattice of dielectric rods (epsilon=11.7). Lattice constant a=500nm, radius r=0.2a. Eigenfrequency study with periodic boundary conditions."
    scan = scan_paper_domain(text)
    assert scan["domain"] == "photonic_crystal"
    assert scan["study"] == "eigenfrequency"
    print(f"  PASS: domain={scan['domain']}, study={scan['study']}")
    params = scan_numeric_params_default(text)
    assert "permittivity" in params
    print(f"  PASS: params={params}")
    bcs = scan_boundary_conditions_default(text)
    assert any(bc["type"] == "periodic" for bc in bcs)
    print(f"  PASS: BCs={[bc['type'] for bc in bcs]}")
    return True


def test_template_matching():
    print("\n" + "=" * 50)
    print("TEST 2: Template Matching")
    store = get_template_store()
    templates = store.list_all()
    assert len(templates) >= 1
    print(f"  PASS: {len(templates)} template(s)")
    matched = store.match({"domain": "photonic_crystal", "physics": "electromagnetic"})
    assert matched is not None
    assert "Wu-Hu" in matched.name
    print(f"  PASS: matched={matched.name}, params={len(matched.extract_parameters())}")
    return True


def test_agent_analyze():
    print("\n" + "=" * 50)
    print("TEST 3: Agent Goal Analysis")
    agent = get_agent()
    result = agent.analyze_goal(description="Simulate Wu-Hu photonic crystal", paper_path="2D photonic crystal with hexagonal lattice. Eigenfrequency study.")
    assert result["matched_template"] is not None
    assert result["domain"] == "photonic_crystal"
    print(f"  PASS: matched={result['matched_template']}")
    return True


def test_execution_plan():
    print("\n" + "=" * 50)
    print("TEST 4: Execution Plan")
    agent = get_agent()
    plan = agent.get_execution_plan("Wu-Hu 光子晶体")
    assert "error" not in plan
    assert plan["total_steps"] >= 5
    print(f"  PASS: {plan['total_steps']} steps")
    for s in plan["steps"]:
        print(f"    {s['step']}: {s['action']} - {s['description']}")
    return True


def test_error_diagnosis():
    print("\n" + "=" * 50)
    print("TEST 5: Error Diagnosis")
    agent = get_agent()
    result = agent.diagnose_error("Singular matrix detected", domain="photonic_crystal")
    assert "fixes" in result["diagnosis"]
    print(f"  PASS: cause={result['diagnosis']['cause']}")
    sd = SolverDiagnostics()
    report = sd.diagnose({"success": False, "error": "did not converge"})
    assert report.quality_score == 0.0
    print(f"  PASS: quality_score={report.quality_score}")
    return True


def test_experience_learning():
    print("\n" + "=" * 50)
    print("TEST 6: Experience Learning")
    agent = get_agent()
    msg = agent.learn_from_correction(domain="photonic_crystal", trigger="solve without PeriodicCondition", symptom="negative eigenvalues", fix="Add PeriodicCondition with k-vector sweep before solving", template_name="Wu-Hu 光子晶体")
    assert "Recorded" in msg
    store = get_experience_store()
    assert store.count >= 1
    print(f"  PASS: {store.count} experience(s)")
    ctx = store.get_prompt_context("photonic_crystal")
    assert "PeriodicCondition" in ctx
    print(f"  PASS: context contains fix")
    return True


def test_result_validation():
    print("\n" + "=" * 50)
    print("TEST 7: Result Validation")
    validator = ResultValidator()
    result = validator.compare_with_paper(simulated={"bandgap": 0.15}, paper_expected={"bandgap": {"value": 0.14, "tolerance": 0.10}})
    assert result["all_match"]
    print(f"  PASS: {result['summary']}")
    return True


def test_agent_status():
    print("\n" + "=" * 50)
    print("TEST 8: Agent Status")
    print(get_agent().print_status())
    print("  PASS")
    return True


def main():
    print("=" * 50)
    print("COMSOL Agent E2E Test Suite")
    print("=" * 50)
    tests = [("Paper Parsing", test_paper_parsing), ("Template Matching", test_template_matching), ("Agent Analysis", test_agent_analyze), ("Execution Plan", test_execution_plan), ("Error Diagnosis", test_error_diagnosis), ("Experience Learning", test_experience_learning), ("Result Validation", test_result_validation), ("Agent Status", test_agent_status)]
    passed = 0
    failed = 0
    for name, fn in tests:
        try:
            fn()
            passed += 1
        except Exception as e:
            print(f"\n  FAIL [{name}]: {e}")
            import traceback; traceback.print_exc()
            failed += 1
    print("\n" + "=" * 50)
    print(f"RESULTS: {passed}/{len(tests)} passed")
    print("=" * 50)
    if failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()





