"""A/B/C smoke test: the frozen held-out comparison lands as the fixtures
were designed to land, with denominators (spec section 5)."""

import unittest

from second_draft.abc import run_abc


class TestABC(unittest.TestCase):
    def test_abc_outcomes(self):
        result = run_abc()
        a, b, c = result["A"], result["B"], result["C"]
        self.assertEqual((a["total"], b["total"], c["total"]), (4, 4, 4))
        self.assertEqual(a["successes"], 2)
        self.assertEqual(b["successes"], 1)  # ungated learning HURT here
        self.assertEqual(c["successes"], 4)  # gated beats both, strictly
        self.assertEqual(b["harm_events"], 2)
        self.assertEqual(c["harm_events"], 0)
        self.assertEqual(c["unsupported_claims"], 0)
        self.assertGreater(b["unsupported_claims"], 0)
        self.assertEqual(result["gate_record"]["schedule-override v1"], "QUARANTINED")
        self.assertEqual(result["gate_record"]["schedule-cross-check v1"], "ADMITTED")


if __name__ == "__main__":
    unittest.main()
