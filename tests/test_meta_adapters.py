"""Tests for the Meta Model API adapters (Oct 26 gate wiring).

No live API calls, no key: every Meta call goes through an injected
fake transport returning a canned chat-completion payload. The
missing-key path is tested by constructing a client with no key and
no key in the environment (the test env sets neither).
"""

import os
import unittest

from second_draft import fixtures
from second_draft.auditor import MetaModelAuditor
from second_draft.gate import Gate
from second_draft.meta_client import MetaApiClient, MetaApiError
from second_draft.models import EvidenceRecord
from second_draft.proposer import MetaModelProposer
from second_draft.store import Store

from tests.helpers import make_store, propose_valid_lesson


def _fake_client(model, text):
    def transport(url, payload, headers):
        assert url.endswith("/chat/completions")
        assert payload["model"] == model
        return {"choices": [{"message": {"content": text}}]}

    return MetaApiClient(model=model, api_key="test-key-only", transport=transport)


class TestMetaClient(unittest.TestCase):
    def test_missing_key_raises_without_calling(self):
        env = {k: v for k, v in os.environ.items()
               if k not in ("META_API_KEY", "MODEL_API_KEY")}
        old = dict(os.environ)
        try:
            os.environ.clear()
            os.environ.update(env)
            with self.assertRaises(MetaApiError):
                MetaApiClient(model="muse-spark-1.3")
        finally:
            os.environ.clear()
            os.environ.update(old)

    def test_unparseable_response_raises(self):
        client = MetaApiClient(
            model="muse-spark-1.3", api_key="test-key-only",
            transport=lambda u, p, h: {"choices": []},
        )
        with self.assertRaises(MetaApiError):
            client.complete([{"role": "user", "content": "hi"}])


class TestMetaProposer(unittest.TestCase):
    def test_proposes_calendar_lesson_from_recurring_tag(self):
        tmp, store = make_store()
        try:
            for w in fixtures.training_worlds():
                from second_draft import agent as agent_mod

                _, _, traj = agent_mod.run_as_trajectory(w, [], task_id="morning-briefing")
                store.save_trajectory(traj)
            proposer = MetaModelProposer(client=_fake_client(
                "muse-spark-1.3",
                "LESSON: Cross-check schedule claims against the calendar source. "
                "| DIRECTIVE: calendar",
            ))
            lessons = proposer.propose(store.load_trajectories())
            self.assertEqual(len(lessons), 1)
            self.assertEqual(lessons[0].directive["source"], "calendar")
            self.assertIn("muse-spark-1.3", lessons[0].transformation)
        finally:
            tmp.cleanup()

    def test_drops_lesson_without_recurrence(self):
        tmp, store = make_store()
        try:
            proposer = MetaModelProposer(client=_fake_client(
                "muse-spark-1.3",
                "LESSON: Cross-check schedule claims against the calendar source. "
                "| DIRECTIVE: calendar",
            ))
            # No trajectories at all: nothing recurring, nothing proposed.
            self.assertEqual(proposer.propose(store.load_trajectories()), [])
        finally:
            tmp.cleanup()


class TestMetaAuditor(unittest.TestCase):
    def _evidence(self):
        return [EvidenceRecord(source="verifier", kind="verifier-result",
                               detail="two runs flagged the tag", supports=True)]

    def test_parses_verdict_and_discloses_no_family_separation(self):
        auditor = MetaModelAuditor(client=_fake_client(
            "muse-spark-1.1",
            "VERDICT: supports\nRATIONALE: Two records support the claim.",
        ))
        assessment = auditor.assess(
            "Cross-check schedule claims.", {}, self._evidence(),
            {"standup_time": "09:00"},
        )
        self.assertEqual(assessment.verdict, "supports")
        self.assertFalse(assessment.separations["model_family_separation"])
        self.assertTrue(assessment.separations["context_isolation"])
        self.assertTrue(assessment.separations["rubric_blindness"])

    def test_unparseable_verdict_raises_and_gate_fails_closed(self):
        auditor = MetaModelAuditor(client=_fake_client(
            "muse-spark-1.1", "A free-form essay with no verdict line.",
        ))
        tmp, store = make_store()
        try:
            lesson = propose_valid_lesson(store)
            gate = Gate(store, auditor,
                        ground_truth=fixtures.demo_world()["ground_truth"])
            decision = gate.evaluate(lesson, fixtures.acceptance_worlds_weekday())
            self.assertEqual(decision["decision"], "fail_closed")
            self.assertEqual(lesson.state.value, "CHALLENGED")
        finally:
            tmp.cleanup()


if __name__ == "__main__":
    unittest.main()
