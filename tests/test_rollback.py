"""Rollback / suspension tests (spec 2.3 restore paths; section 6).

- Suspension writes a Reversal record.
- There is no direct un-suspend: restore requires re-validation that
  PASSED; a failed/absent re-validation leaves the version suspended.
- Illegal transitions are rejected by the store in code.
- Supersede-don't-delete: superseded records remain fully retrievable
  as records (Point 5, continuity).
"""

import unittest

from second_draft import fixtures
from second_draft.models import State
from second_draft.store import IllegalTransition

from tests.helpers import admit_valid_lesson, make_gate, make_store, propose_valid_lesson


class TestRollback(unittest.TestCase):
    def test_suspension_writes_reversal_record(self):
        tmp, store = make_store()
        with tmp:
            gate = make_gate(store)
            lesson = admit_valid_lesson(store, gate)
            self.assertIsNone(lesson.reversal)
            store.suspend(lesson, trigger="confirmed_regression",
                          reason="Probe failure.", rollback_target_version=None)
            self.assertIsNotNone(lesson.reversal)
            self.assertEqual(lesson.reversal.trigger, "confirmed_regression")
            self.assertEqual(lesson.reversal.suspended_version, lesson.version)

    def test_restore_requires_passing_revalidation(self):
        tmp, store = make_store()
        with tmp:
            gate = make_gate(store)
            lesson = admit_valid_lesson(store, gate)
            store.suspend(lesson, trigger="human_control", reason="Drill.")
            # Failed re-validation: no restore, still suspended.
            with self.assertRaises(IllegalTransition):
                store.restore_after_revalidation(lesson, {"passed": False})
            self.assertIs(lesson.state, State.SUSPENDED)
            # Passing re-validation under current conditions: restored.
            result = gate.revalidate(lesson, fixtures.acceptance_worlds_weekday())
            self.assertTrue(result["passed"])
            store.restore_after_revalidation(lesson, result)
            self.assertIs(lesson.state, State.ADMITTED)
            self.assertTrue(lesson.is_retrievable())
            self.assertEqual(
                lesson.reversal.revalidation_result["passed"], True
            )

    def test_illegal_transitions_rejected(self):
        tmp, store = make_store()
        with tmp:
            gate = make_gate(store)
            # CANDIDATE -> SUSPENDED is not in the spec 2.3 table.
            lesson = propose_valid_lesson(store)
            with self.assertRaises(IllegalTransition):
                store.transition(lesson, State.SUSPENDED, "Not a listed path.")
            # QUARANTINED -> ADMITTED is not a listed path either.
            bad = store.intake(fixtures.bad_lesson_candidate())
            gate.evaluate(bad, fixtures.acceptance_worlds_weekday())
            self.assertIs(bad.state, State.QUARANTINED)
            with self.assertRaises(IllegalTransition):
                store.transition(bad, State.ADMITTED, "No direct path.")

    def test_superseded_record_survives_and_rollback_restores_it(self):
        """Continuity (Point 5) + H5 rollback: v2 supersedes v1; v2 is
        suspended for regression; v1's record is intact and rollback
        restores its use only after re-validation passes."""
        tmp, store = make_store()
        with tmp:
            gate = make_gate(store)
            v1 = admit_valid_lesson(store, gate)
            # A corrected new version enters as a CANDIDATE and is admitted,
            # superseding v1 (weekend-context revision, as in the demo).
            from second_draft import agent as agent_mod
            from second_draft.proposer import DeterministicProposer
            for w in fixtures.weekend_worlds():
                _, _, traj = agent_mod.run_as_trajectory(w, [v1], task_id="wk")
                store.save_trajectory(traj)
            v2_cand = [
                c for c in DeterministicProposer().propose(store.load_trajectories())
                if c.directive.get("source") == "most_recent"
            ][0]
            v2 = store.intake(v2_cand)
            weekend_gate = make_gate(
                store, ground_truth=fixtures.weekend_worlds()[0]["ground_truth"])
            weekend_gate.evaluate(v2, fixtures.acceptance_worlds_weekend())
            self.assertIs(v2.state, State.ADMITTED)
            self.assertEqual(v1.superseded_by, v2.version)
            self.assertFalse(v1.is_retrievable())  # record kept, use removed
            # Regression -> suspend v2 -> rollback to v1 after re-validation.
            store.suspend(v2, trigger="confirmed_regression",
                          reason="Weekday probes failed.",
                          rollback_target_version=v1.version)
            revalidation = gate.revalidate(v1, fixtures.acceptance_worlds_weekday())
            self.assertTrue(revalidation["passed"])
            restored = store.rollback_to("schedule-cross-check", v1.version, revalidation)
            self.assertIs(restored.state, State.ADMITTED)
            self.assertTrue(restored.is_retrievable())
            # Lineage complete: both versions still on record.
            self.assertEqual(len(store.family_versions("schedule-cross-check")), 2)


if __name__ == "__main__":
    unittest.main()
