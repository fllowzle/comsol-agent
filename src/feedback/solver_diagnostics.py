# -*- coding: utf-8 -*-
"""反馈诊断器 — 求解后自动分析结果质量。"""

from __future__ import annotations

import re
from typing import Optional
from dataclasses import dataclass, field


@dataclass
class DiagnosticsReport:
    success: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)
    quality_score: float = 1.0
    details: dict = field(default_factory=dict)


class SolverDiagnostics:
    ERROR_PATTERNS = [
        (r"Failed to (find|locate)", "missing_node", "Object not found - check names (Java API is case-sensitive)"),
        (r"Singular matrix", "singular", "Singular matrix - missing BCs, zero material params, or underconstrained physics"),
        (r"did not converge", "no_convergence", "No convergence - refine mesh, adjust tolerance, check initial values"),
        (r"out of memory", "oom", "Out of memory - reduce mesh density or solve size"),
        (r"periodic.*inconsistent", "periodic_mismatch", "Periodic boundary mismatch - ensure conformal mesh"),
        (r"NullPointerException|NoneType", "null_ref", "Null reference - MPH/COMSOL API call order error"),
        (r"timeout|timed out", "timeout", "Timeout - simplify model or increase timeout"),
        (r"license", "license", "License issue - check COMSOL License"),
    ]

    def diagnose(self, result: dict) -> DiagnosticsReport:
        if result.get("success"):
            return self._diagnose_success(result)
        else:
            return self._diagnose_failure(result)

    def _diagnose_failure(self, result: dict) -> DiagnosticsReport:
        error_msg = result.get("error", str(result))
        report = DiagnosticsReport(success=False, errors=[error_msg])
        for pattern, code, suggestion in self.ERROR_PATTERNS:
            if re.search(pattern, error_msg, re.IGNORECASE):
                report.suggestions.append(suggestion)
                report.details["error_code"] = code
                break
        if not report.suggestions:
            report.suggestions = [
                "Check full COMSOL log",
                "Try simplest version first",
                "Verify in COMSOL GUI manually",
            ]
        report.quality_score = 0.0
        return report

    def _diagnose_success(self, result: dict) -> DiagnosticsReport:
        report = DiagnosticsReport(success=True)
        if "warnings" in result and result["warnings"]:
            report.warnings = result["warnings"]
        return report

    def validate_eigenfrequencies(self, frequencies: list[complex]) -> DiagnosticsReport:
        report = DiagnosticsReport(success=True)
        real_parts = [abs(f.real) for f in frequencies]
        imag_parts = [abs(f.imag) for f in frequencies]
        if any(r <= 0 for r in real_parts):
            report.errors.append("Non-positive eigenfrequency real parts - check search center")
            report.quality_score -= 0.3
        for i, (r, im) in enumerate(zip(real_parts, imag_parts)):
            if r > 0 and im / r > 0.01:
                report.warnings.append(f"Mode {i+1}: imag/real = {im/r:.2e}, possible spurious mode")
                report.quality_score -= 0.1
        report.quality_score = max(0, report.quality_score)
        return report

    def validate_band_structure(self, k_points: list, frequencies: list) -> DiagnosticsReport:
        report = DiagnosticsReport(success=True)
        for band_idx in range(len(frequencies[0]) if frequencies else 0):
            band = [freqs[band_idx] for freqs in frequencies]
            for i in range(1, len(band)):
                jump = abs(band[i] - band[i-1])
                avg = (abs(band[i]) + abs(band[i-1])) / 2
                if avg > 0 and jump / avg > 0.3:
                    report.warnings.append(f"Band {band_idx+1} jump at k-point {i}: {jump/avg*100:.1f}%")
                    report.suggestions.append("Increase k-point density")
                    break
        report.quality_score = max(0, report.quality_score)
        return report


class ResultValidator:
    def compare_with_paper(self, simulated: dict, paper_expected: dict) -> dict:
        comparisons = []
        passed = 0
        failed = 0
        for param, expected in paper_expected.items():
            if param not in simulated:
                comparisons.append({"parameter": param, "status": "missing", "message": f"Not found in results"})
                failed += 1
                continue
            sim_val = simulated[param]
            exp_val = expected if isinstance(expected, (int, float)) else expected.get("value", expected)
            tolerance = expected.get("tolerance", 0.05) if isinstance(expected, dict) else 0.05
            if exp_val == 0:
                match = abs(sim_val) < tolerance
            else:
                match = abs(sim_val - exp_val) / abs(exp_val) < tolerance
            comparisons.append({"parameter": param, "simulated": sim_val, "expected": exp_val, "tolerance": tolerance, "deviation": abs(sim_val - exp_val) / (abs(exp_val) + 1e-9), "match": match})
            if match: passed += 1
            else: failed += 1
        return {"summary": f"{passed}/{passed+failed} params match", "passed": passed, "failed": failed, "details": comparisons, "all_match": failed == 0}
