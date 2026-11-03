"""Gate tests: admission, quarantine, the H1/H2 hostile fixtures, and the
H3 fail-closed path (spec 2.5, 2.7; spec section 5 hostile fixtures)."""

import unittest

from second_draft import fixtures
from second_draft.auditor import FailingAuditor, FlakyAuditor, TimeoutAuditor
from second_draft.models import State
from second_draft.proposer import DeterministicProposer
from second_draft.store import Store
from second_draft import agent as agent_mod

from tests.helpers import admit_valid_lesson, make_gate, make_store, propose_valid_lesson, seed_training_trajectories


class TestGateAdmission(unittest.TestCase):
    def test_gate_admits_valid_candidate(self):
        tmp, store = make_store()
        with tmp:
            gate = make_gate(store)
            lesson = admit_valid_lesson(store, gate)
            self.assertIs(lesson.state, State.ADMITTED)
            self.assertTrue(lesson.is_retrievable())
            # Validation record carries the Tension B separations disclosure.
            auditor_rec = lesson.validation["auditor"]
            self.assertIn("separations", auditor_rec)
            self.assertEqual(auditor_rec["verdict"], "supports")
            # Admission is scoped (spec 2.3).
            self.assertIn("acc-w1", lesson.scope)

    def test_missing_source_provenance_is_not_admitted(self):
        tmp, store = make_store()
        with tmp:
            gate = make_gate(store)
            lesson = propose_valid_lesson(store)
            lesson.origin = ""
            lesson.origin_source = ""
            decision = gate.evaluate(lesson, fixtures.acceptance_worlds_weekday())
            self.assertEqual(decision["decision"], "quarantined")
            self.assertIs(lesson.state, State.QUARANTINED)
            self.assertFalse(lesson.validation["checks"]["source_cited"])
            self.assertIn("Missing provenance", lesson.validation["failed_check"])

    def test_revalidation_requires_source_provenance(self):
        tmp, store = make_store()
        with tmp:
            gate = make_gate(store)
            lesson = admit_valid_lesson(store, gate)
            lesson.origin = ""
            lesson.origin_source = ""
            result = gate.revalidate(lesson, fixtures.acceptance_worlds_weekday())
            self.assertFalse(result["passed"])
            self.assertFalse(result["checks"]["source_cited"])

    def test_proposer_requires_two_trajectories(self):
        tmp, store = make_store()
        with tmp:
            worlds = fixtures.training_worlds()
            _, _, traj = agent_mod.run_as_trajectory(worlds[0], [], task_id="t")
            store.save_trajectory(traj)
            self.assertEqual(
                DeterministicProposer().propose(store.load_trajectories()), []
            )
            _, _, traj2 = agent_mod.run_as_trajectory(worlds[1], [], task_id="t")
            store.save_trajectory(traj2)
            self.assertEqual(
                len(DeterministicProposer().propose(store.load_trajectories())), 1
            )


class TestHostileFixtures(unittest.TestCase):
    def test_h1_plausible_but_wrong_is_quarantined(self):
        tmp, store = make_store()
        with tmp:
            gate = make_gate(store)
            bad = store.intake(fixtures.bad_lesson_candidate())
            decision = gate.evaluate(bad, fixtures.acceptance_worlds_weekday())
            self.assertEqual(decision["decision"], "quarantined")
            self.assertIs(bad.state, State.QUARANTINED)
            self.assertFalse(bad.is_retrievable())
            # The failed check names the contradiction, not the prose.
            self.assertIn("Contradicted", bad.validation["failed_check"])
            # High proposer confidence did not rescue it (0.9 in the fixture).
            self.assertEqual(bad.confidence, 0.9)

    def test_h2_insufficient_evidence_refused_but_not_recorded_false(self):
        tmp, store = make_store()
        with tmp:
            # The registry deliberately withholds the deciding record
            # (standup_room), so the claim is neither supported nor
            # contradicted -- H2's exact setup.
            gate = make_gate(store, ground_truth={"standup_time": "09:00"})
            cand = store.intake(fixtures.uncorroborated_lesson_candidate())
            decision = gate.evaluate(cand, fixtures.acceptance_worlds_weekday())
            self.assertEqual(decision["decision"], "quarantined")
            self.assertIs(cand.state, State.QUARANTINED)
            self.assertIn("NOT recorded as false", cand.validation["failed_check"])

    def test_h3_failing_auditor_fails_closed(self):
        tmp, store = make_store()
        with tmp:
            gate = make_gate(store, auditor=FailingAuditor())
            lesson = propose_valid_lesson(store)
            decision = gate.evaluate(lesson, fixtures.acceptance_worlds_weekday())
            self.assertEqual(decision["decision"], "fail_closed")
            # Not admitted; held in CHALLENGED with the panel wording.
            self.assertIs(lesson.state, State.CHALLENGED)
            self.assertEqual(
                lesson.validation["check_incomplete"], "check incomplete -- not admitted"
            )
            # Recorded as an evidence-integrity fault -- never fabrication.
            faults = [e for e in store.events()
                      if e["type"] == "evidence_integrity_fault"]
            self.assertEqual(len(faults), 1)
            fabrication = [e for e in store.events()
                             if "fabricat" in e["detail"].lower()
                             and e["type"] != "evidence_integrity_fault"]
            self.assertEqual(fabrication, [])

    def test_h3_timeout_auditor_fails_closed(self):
        tmp, store = make_store()
        with tmp:
            gate = make_gate(store, auditor=TimeoutAuditor())
            lesson = propose_valid_lesson(store)
            decision = gate.evaluate(lesson, fixtures.acceptance_worlds_weekday())
            self.assertEqual(decision["decision"], "fail_closed")
            self.assertIs(lesson.state, State.CHALLENGED)

    def test_bounded_retry_recovers_from_transient_auditor_failure(self):
        tmp, store = make_store()
        with tmp:
            flaky = FlakyAuditor()
            gate = make_gate(store, auditor=flaky)
            lesson = propose_valid_lesson(store)
            decision = gate.evaluate(lesson, fixtures.acceptance_worlds_weekday())
            self.assertEqual(decision["decision"], "admitted")
            self.assertEqual(flaky.calls, 2)  # one failure + one retry
            failures = [e for e in store.events() if e["type"] == "auditor_call_failed"]
            self.assertEqual(len(failures), 1)


if __name__ == "__main__":
    unittest.main()
