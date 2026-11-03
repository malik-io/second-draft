"""The A/B/C comparison (spec sections 5, 9).

  A = no learned lesson
  B = lessons applied with NO gate (ungated adoption)
  C = gated admission (gate + retrieval exclusion, the real pipeline)

Same frozen held-out worlds in all three conditions. Reported per
condition, with denominators: task success, unsupported claims, harm
events (worlds where the condition failed but baseline A succeeded).
Effectiveness and safety are reported in separate blocks and never
blended into one score (spec 9.2).
"""

from __future__ import annotations

import tempfile
from typing import Any

from . import agent as agent_mod
from . import fixtures
from .auditor import LocalFixtureAuditor
from .gate import Gate
from .proposer import DeterministicProposer
from .retrieval import build_context
from .store import Store


def _run_condition(worlds: list[dict[str, Any]], lessons: list) -> dict[str, Any]:
    per_world = []
    for w in worlds:
        briefing = agent_mod.assemble_briefing(w, lessons)
        verdict = agent_mod.verify_briefing(w, briefing)
        per_world.append(
            {
                "world_id": w["world_id"],
                "success": verdict["all_correct"],
                "unsupported_claims": verdict["unsupported_claims"],
                "claims": len(verdict["claims"]),
            }
        )
    return {
        "worlds": per_world,
        "successes": sum(1 for r in per_world if r["success"]),
        "total": len(per_world),
        "unsupported_claims": sum(r["unsupported_claims"] for r in per_world),
        "total_claims": sum(r["claims"] for r in per_world),
    }


def run_abc() -> dict[str, Any]:
    worlds = fixtures.held_out_worlds()
    proposer = DeterministicProposer()

    # Shared raw material: training trajectories -> proposed lessons.
    with tempfile.TemporaryDirectory() as tmp:
        seed_store = Store(tmp)
        for w in fixtures.training_worlds():
            _, _, traj = agent_mod.run_as_trajectory(w, [], task_id="morning-briefing")
            seed_store.save_trajectory(traj)
        proposed = proposer.propose(seed_store.load_trajectories())
    valid_lesson = proposed[0]
    bad_lesson = fixtures.bad_lesson_candidate()
    # Ungated condition B holds lessons at version 1 for display purposes.
    valid_lesson.version = 1
    bad_lesson.version = 1

    # A: no lesson.
    cond_a = _run_condition(worlds, [])

    # B: ungated -- every proposed lesson applied, in proposal order. The
    # wrong lesson was proposed last, so its override wins.
    cond_b = _run_condition(worlds, [valid_lesson, bad_lesson])

    # C: the real pipeline -- intake, gate, retrieval by code.
    with tempfile.TemporaryDirectory() as tmp:
        store = Store(tmp)
        gate = Gate(store, LocalFixtureAuditor(),
                    ground_truth=fixtures.demo_world()["ground_truth"])
        for w in fixtures.training_worlds():
            _, _, traj = agent_mod.run_as_trajectory(w, [], task_id="morning-briefing")
            store.save_trajectory(traj)
        for cand in proposer.propose(store.load_trajectories()):
            admitted = store.intake(cand)
            gate.evaluate(admitted, fixtures.acceptance_worlds_weekday())
        bad = store.intake(fixtures.bad_lesson_candidate())
        gate.evaluate(bad, fixtures.acceptance_worlds_weekday())
        cond_c = _run_condition(worlds, build_context(store))
        gate_record = {
            f"{l.family} v{l.version}": l.state.value for l in store.all_lessons()
        }

    # Harm: worlds where the condition failed but baseline A succeeded.
    a_by_world = {r["world_id"]: r["success"] for r in cond_a["worlds"]}
    for cond in (cond_b, cond_c):
        cond["harm_events"] = sum(
            1 for r in cond["worlds"] if not r["success"] and a_by_world[r["world_id"]]
        )
    cond_a["harm_events"] = 0

    return {"A": cond_a, "B": cond_b, "C": cond_c, "gate_record": gate_record,
            "world_count": len(worlds)}


def format_report(result: dict[str, Any]) -> str:
    lines = []
    lines.append("=" * 72)
    lines.append("A/B/C COMPARISON -- frozen held-out set (spec sections 5, 9)")
    lines.append("  A = no learned lesson")
    lines.append("  B = lessons applied with NO gate (ungated)")
    lines.append("  C = gated admission + retrieval exclusion (the real pipeline)")
    lines.append("=" * 72)
    lines.append("\nEFFECTIVENESS BLOCK")
    lines.append(f"  {'Condition':<4} {'Task success':<16} {'Harm events':<14} Per-world")
    for name in ("A", "B", "C"):
        c = result[name]
        per = " ".join(
            f"{r['world_id']}:{'PASS' if r['success'] else 'FAIL'}" for r in c["worlds"]
        )
        lines.append(
            f"  {name:<4} {c['successes']} of {c['total']:<13} "
            f"{c['harm_events']} of {c['total']:<11} {per}"
        )
    lines.append("\nSAFETY / INTEGRITY BLOCK")
    for name in ("A", "B", "C"):
        c = result[name]
        lines.append(
            f"  {name}: unsupported claims {c['unsupported_claims']} of "
            f"{c['total_claims']} claims stated"
        )
    lines.append("\nPAIRWISE (task success, with denominators)")
    a, b, c = result["A"], result["B"], result["C"]
    lines.append(f"  C vs B: {c['successes']}/{c['total']} vs {b['successes']}/{b['total']}"
                 f"  -> gated {'BEATS' if c['successes'] > b['successes'] else 'does not beat'} ungated")
    lines.append(f"  C vs A: {c['successes']}/{c['total']} vs {a['successes']}/{a['total']}"
                 f"  -> gated {'BEATS' if c['successes'] > a['successes'] else 'does not beat'} no-lesson")
    lines.append(f"  B vs A: {b['successes']}/{b['total']} vs {a['successes']}/{a['total']}"
                 f"  -> ungated {'helped' if b['successes'] > a['successes'] else 'did not help'}"
                 f" (harm events: {b['harm_events']})")
    lines.append("\nGATE RECORD (condition C pipeline)")
    for k, v in result["gate_record"].items():
        lines.append(f"  {k}: {v}")
    lines.append(
        "\nScope note: results are on a small, frozen, entrant-authored fixture\n"
        "set. They show the mechanism firing as designed on cases built to test\n"
        "it; they are not evidence about open-ended use (spec section 12)."
    )
    return "\n".join(lines)
