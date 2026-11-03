"""The Verified Morning demo arc (deterministic, synthetic fixtures only).

Arc:
  (i)   Two earlier runs fail the same way -> a VALID lesson is distilled,
        the gate admits it, and a later briefing visibly improves.
  (ii)  A plausible-but-wrong lesson arrives from one unverified note ->
        the gate catches the contradiction + missing corroboration,
        quarantines it (face: Alarmed -> Turned away), and the corrected
        briefing still goes out.
  (iii) A revision that was right in its own (weekend) context regresses
        on the original cases -> the affected version is suspended (face:
        Frozen), and rollback restores the prior version ONLY after
        re-validation; a probe re-runs clean.

The panel state file is rewritten at every state change, derived from the
store's records -- the face illustrates the gate, it never decides.
"""

from __future__ import annotations

import os
import shutil
from typing import Callable

from . import agent as agent_mod
from . import fixtures
from .auditor import LocalFixtureAuditor
from .gate import Gate
from .models import State, face_for, label_for
from .panel import DEFAULT_STATE_PATH, write_panel_state
from .proposer import DeterministicProposer
from .retrieval import build_context
from .store import Store

Say = Callable[[str], None]


def _face_line(store: Store, lesson, say: Say) -> None:
    say(f"    FACE: {face_for(lesson.state)}  [{label_for(lesson.state)} / {lesson.state.value}]"
        f"  -- {lesson.family} v{lesson.version}")


def _briefing_line(world, lessons, say: Say, caption: str) -> dict:
    briefing = agent_mod.assemble_briefing(world, lessons)
    verdict = agent_mod.verify_briefing(world, briefing)
    claims = "; ".join(
        f"{c['text']} (from {c['provenance']})" for c in briefing["claims"]
    )
    say(f"    {caption}: {claims}")
    say(f"      verifier: all_correct={verdict['all_correct']}, "
        f"unsupported_claims={verdict['unsupported_claims']}, tags={verdict['error_tags']}")
    return verdict


def run_demo(data_dir: str, say: Say = print, panel_path: str = DEFAULT_STATE_PATH,
             proposer=None, auditor=None) -> dict:
    """Run the demo arc. Default proposer/auditor are the deterministic
    offline pair, so the captured transcript is reproducible. Pass
    MetaModelProposer()/MetaModelAuditor() for the live Meta mode
    (requires META_API_KEY; a missing key or bad reply fails closed
    in the gate, it never silently falls back to the stub)."""
    if os.path.exists(data_dir):
        shutil.rmtree(data_dir)
    store = Store(data_dir)
    proposer = proposer or DeterministicProposer()
    auditor = auditor or LocalFixtureAuditor()
    world = fixtures.demo_world()

    def watch(lesson) -> None:
        # Every gate transition reaches the panel + narration immediately,
        # so intermediate states (CHALLENGED / Alarmed) are visible.
        write_panel_state(panel_path, store, lesson)
        _face_line(store, lesson, say)

    gate = Gate(store, auditor, ground_truth=world["ground_truth"],
                on_transition=watch)

    say("=" * 72)
    say("SECOND DRAFT -- Verified Morning (synthetic fixtures, deterministic)")
    say("=" * 72)

    # ---- Beat (i): learn a valid lesson from two failed runs -------------
    say("\n-- Beat 1: two earlier runs fail the same way --------------------")
    for w in fixtures.training_worlds():
        briefing, verdict, traj = agent_mod.run_as_trajectory(w, [], task_id="morning-briefing")
        store.save_trajectory(traj)
        say(f"    Run on {w['world_id']}: stated standup "
            f"{briefing['claims'][0]['value']} (truth {w['ground_truth']['standup_time']}) "
            f"-> tags={verdict['error_tags']}")

    candidates = proposer.propose(store.load_trajectories())
    assert len(candidates) == 1, f"expected exactly 1 candidate, got {len(candidates)}"
    lesson = store.intake(candidates[0])
    write_panel_state(panel_path, store, lesson)
    say(f"\n    Proposer distilled a candidate from >= 2 trajectories:")
    say(f"      \"{lesson.claim_text}\"")
    _face_line(store, lesson, say)

    decision = gate.evaluate(lesson, fixtures.acceptance_worlds_weekday())
    write_panel_state(panel_path, store, lesson, last_decision=decision)
    say(f"    Gate decision: {decision['decision']} "
        f"(auditor: {decision.get('auditor')}; independent support: "
        f"{decision['checks']['independent_support_count']} record(s))")

    say("\n    The improvement, on this morning's briefing:")
    _briefing_line(world, [], say, "BEFORE (no lesson)")
    _briefing_line(world, build_context(store), say, "AFTER  (admitted lesson in context)")

    # ---- Beat (ii): the plausible-but-wrong lesson ------------------------
    say("\n-- Beat 2: a plausible-but-wrong lesson arrives ------------------")
    bad = store.intake(fixtures.bad_lesson_candidate())
    write_panel_state(panel_path, store, bad)
    say(f"    Candidate: \"{bad.claim_text}\" (proposer confidence {bad.confidence} -- "
        f"confidence is not evidence)")
    _face_line(store, bad, say)
    decision = gate.evaluate(bad, fixtures.acceptance_worlds_weekday())
    write_panel_state(panel_path, store, bad, last_decision=decision)
    say(f"    Gate decision: {decision['decision']}")
    say(f"      failed check: {bad.validation.get('failed_check')}")
    _briefing_line(world, build_context(store), say,
                   "Briefing after the catch (bad lesson shut out by code)")

    # ---- Beat (iii): regression, suspension, rollback ---------------------
    say("\n-- Beat 3: a revision regresses; suspension and rollback ---------")
    for w in fixtures.weekend_worlds():
        _, verdict, traj = agent_mod.run_as_trajectory(
            w, build_context(store), task_id="weekend-briefing"
        )
        store.save_trajectory(traj)
        say(f"    Weekend run on {w['world_id']} (calendar-first lesson active): "
            f"tags={verdict['error_tags']}")
    new_candidates = [
        c for c in proposer.propose(store.load_trajectories())
        if c.directive.get("source") == "most_recent"
    ]
    assert len(new_candidates) == 1
    v2 = store.intake(new_candidates[0])
    write_panel_state(panel_path, store, v2)
    say(f"    Revision proposed: \"{v2.claim_text}\"")
    _face_line(store, v2, say)
    weekend_gate = Gate(store, auditor,
                        ground_truth=fixtures.weekend_worlds()[0]["ground_truth"],
                        on_transition=watch)
    decision = weekend_gate.evaluate(v2, fixtures.acceptance_worlds_weekend())
    write_panel_state(panel_path, store, v2, last_decision=decision)
    say(f"    Gate decision in its own (weekend) context: {decision['decision']} "
        f"-> v1 superseded (record kept, use removed)")

    probes = fixtures.acceptance_worlds_weekday()
    probe_before = [
        agent_mod.verify_briefing(w, agent_mod.assemble_briefing(w, build_context(store)))["all_correct"]
        for w in probes
    ]
    say(f"    Regression probes (the original weekday cases, v2 active): {probe_before}")
    assert not all(probe_before), "fixture error: v2 should regress on weekday probes"

    store.append_event(
        "regression_detected",
        "Confirmed regression: admitted v2 fails held-out weekday cases it "
        "previously passed (as v1). Suspending the affected version only.",
        lesson_id=v2.lesson_id,
    )
    v1 = store.family_versions("schedule-cross-check")[0]
    store.suspend(
        v2, trigger="confirmed_regression",
        reason="v2 (most-recent-note precedence) states the stale message "
               "note's time on the weekday cases v1 passed.",
        rollback_target_version=v1.version,
    )
    write_panel_state(panel_path, store, v2)
    say(f"    Suspension trigger fired: confirmed_regression. "
        f"Reversal record written on v2.")
    _face_line(store, v2, say)
    say(f"    Retrieval now returns: "
        f"{[f'{l.family} v{l.version}' for l in build_context(store)]} "
        f"(v1 is superseded, v2 suspended -- nothing leaks through)")

    revalidation = gate.revalidate(v1, probes)
    say(f"    Rollback re-validation of v1 under current conditions: "
        f"passed={revalidation['passed']}")
    assert revalidation["passed"]
    restored = store.rollback_to("schedule-cross-check", v1.version, revalidation)
    write_panel_state(panel_path, store, restored)
    _face_line(store, restored, say)
    probe_after = [
        agent_mod.verify_briefing(w, agent_mod.assemble_briefing(w, build_context(store)))["all_correct"]
        for w in probes
    ]
    say(f"    Probes after rollback + re-validation: {probe_after} (clean)")
    _briefing_line(world, build_context(store), say, "Final briefing")

    say("\n-- Lineage (supersede-don't-delete: every version still on record) --")
    for l in store.all_lessons():
        say(f"    {l.family} v{l.version}: state={l.state.value}"
            + (f", superseded_by=v{l.superseded_by}" if l.superseded_by else "")
            + (f", reversal trigger={l.reversal.trigger}" if l.reversal else ""))
    say(f"    Event log: {len(store.events())} events, append-only.")
    say("\nDemo arc complete.")
    return {"store": store, "data_dir": data_dir}
