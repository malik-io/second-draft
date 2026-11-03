"""Shared test helpers: a store + gate wired over a temp directory."""

from __future__ import annotations

import tempfile

from second_draft import agent as agent_mod
from second_draft import fixtures
from second_draft.auditor import LocalFixtureAuditor
from second_draft.gate import Gate
from second_draft.proposer import DeterministicProposer
from second_draft.store import Store


def make_store() -> tuple[tempfile.TemporaryDirectory, Store]:
    tmp = tempfile.TemporaryDirectory()
    return tmp, Store(tmp.name)


def make_gate(store: Store, auditor=None, ground_truth=None) -> Gate:
    return Gate(
        store,
        auditor or LocalFixtureAuditor(),
        ground_truth=ground_truth or fixtures.demo_world()["ground_truth"],
    )


def seed_training_trajectories(store: Store) -> None:
    for w in fixtures.training_worlds():
        _, _, traj = agent_mod.run_as_trajectory(w, [], task_id="morning-briefing")
        store.save_trajectory(traj)


def propose_valid_lesson(store: Store):
    """Distill + intake the valid calendar-cross-check lesson (CANDIDATE)."""
    seed_training_trajectories(store)
    candidates = DeterministicProposer().propose(store.load_trajectories())
    assert len(candidates) == 1
    return store.intake(candidates[0])


def admit_valid_lesson(store: Store, gate: Gate):
    lesson = propose_valid_lesson(store)
    decision = gate.evaluate(lesson, fixtures.acceptance_worlds_weekday())
    assert decision["decision"] == "admitted", decision
    return lesson
