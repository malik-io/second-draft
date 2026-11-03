"""Retrieval exclusion tests (spec 2.6 step 1; section 6(3a)).

Exclusion is a code property of the store: quarantined, suspended,
challenged, candidate, and superseded lessons cannot be retrieved.
"""

import unittest

from second_draft import fixtures
from second_draft.models import State
from second_draft.retrieval import build_context

from tests.helpers import admit_valid_lesson, make_gate, make_store


class TestRetrievalExclusion(unittest.TestCase):
    def test_quarantined_lesson_is_never_retrieved(self):
        tmp, store = make_store()
        with tmp:
            gate = make_gate(store)
            bad = store.intake(fixtures.bad_lesson_candidate())
            gate.evaluate(bad, fixtures.acceptance_worlds_weekday())
            self.assertIs(bad.state, State.QUARANTINED)
            self.assertEqual(build_context(store), [])

    def test_suspended_lesson_excluded_immediately(self):
        tmp, store = make_store()
        with tmp:
            gate = make_gate(store)
            lesson = admit_valid_lesson(store, gate)
            self.assertEqual([l.lesson_id for l in build_context(store)],
                             [lesson.lesson_id])
            store.suspend(lesson, trigger="human_control",
                          reason="Test suspension.")
            self.assertIs(lesson.state, State.SUSPENDED)
            self.assertEqual(build_context(store), [])

    def test_candidate_and_challenged_lessons_excluded(self):
        tmp, store = make_store()
        with tmp:
            from tests.helpers import propose_valid_lesson
            lesson = propose_valid_lesson(store)
            self.assertIs(lesson.state, State.CANDIDATE)
            self.assertEqual(build_context(store), [])
            store.transition(lesson, State.CHALLENGED, "Flagged for review.")
            self.assertEqual(build_context(store), [])


if __name__ == "__main__":
    unittest.main()
