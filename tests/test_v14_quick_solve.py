"""v1.4 T3 — P1-4 快速求解 quick-solve（InMemory 一次性端到端）。"""

from __future__ import annotations

from tests.conftest import FIVE_KEYS
from vencertia.cli import app
from vencertia.quick_solve import run_quick_solve


def test_quick_solve_default_no_args():
    """默认全参数可用：view=summary、FIVE_KEYS 超集、lightweight 标记。"""
    s = run_quick_solve()
    assert s["view"] == "summary"
    assert set(s) >= FIVE_KEYS
    assert s["lightweight"] is True


def test_quick_solve_five_section_contract():
    """返回 5 段合同：current_judgment 五态、next_step 非空。"""
    s = run_quick_solve()
    assert s["current_judgment"] in {"ACT", "TEST", "HOLD", "WAIT", "STOP"}
    assert s["next_step"]


def test_quick_solve_custom_params_override():
    """自定义 problem/options 可跑通且不抛错（DecisionEngine 需 >=2 选项）。"""
    s = run_quick_solve(
        problem_text="自定义问题",
        options=[{"id": "a", "label": "A"}, {"id": "b", "label": "B"}],
    )
    assert s["view"] == "summary"
    assert s["lightweight"] is True


def test_quick_solve_cli_registered():
    """CLI 顶层命令集含 quick-solve。"""
    names = [c.name for c in app.registered_commands]
    assert "quick-solve" in names
