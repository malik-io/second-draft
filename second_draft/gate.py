"""The four-stage evidence gate (spec 2.1).

  (1) Claim intake      -- every claim/lesson recorded with source + type.
  (2) Evidence check    -- deterministic code checks + auditor assessment.
  (3) Use decision      -- admitted / quarantined (never on confidence,
                           never on the proposer's eloquence).
  (4) Reversal & repair -- suspension, rollback, re-validation (store.py
                           enforces the transitions; this module runs the
                           checks that guard them).

Fail-closed semantics (spec 2.5, 2.7): if the auditor errors or times out,
the gate retries ONCE; if it still fails, the lesson is NOT admitted, the
event is recorded as an evidence-integrity fault -- never as a pass, never
as fabrication. "Fail closed" is a refusal outcome, full stop.
"""

from __future__ import annotations

from typing import Any, Callable, Optional

from . import agent as agent_mod
from .auditor import Auditor, AuditorAssessment
from .models import Lesson, State
from .store import Store

# An acceptance runner judges a candidate lesson on held-out worlds:
# fn(lesson, worlds) -> {"passed": bool, "results": [...]}
AcceptanceRunner = Callable[[Lesson, list[dict[str, Any]]], dict[str, Any]]


def default_acceptance_runner(lesson: Lesson, worlds: list[dict[str, Any]]) -> dict[str, Any]:
    """Run the briefing agent with ONLY this lesson active on each held-out
    world; the lesson passes iff every briefing is fully correct."""
    results = []
    for world in worlds:
        briefing = agent_mod.assemble_briefing(world, [lesson])
        verdict = agent_mod.verify_briefing(world, briefing)
        results.append(
            {"world_id": world["world_id"], "all_correct": verdict["all_correct"]}
        )
    return {"passed": all(r["all_correct"] for r in results), "results": results}


class Gate:
    def __init__(
        self,
        store: Store,
        auditor: Auditor,
        ground_truth: dict[str, Any],
        acceptance_runner: AcceptanceRunner = default_acceptance_runner,
        on_transition: Optional[Callable[[Lesson], None]] = None,
    ):
        self.store = store
        self.auditor = auditor
        self.ground_truth = ground_truth
        self.acceptance_runner = acceptance_runner
        # Optional observer fired after every state transition the gate
        # performs -- the demo uses it so intermediate states (CHALLENGED)
        # reach the face panel, not just the final state.
        self.on_transition = on_transition

    def _transition(self, lesson: Lesson, to_state: State, reason: str) -> None:
        self.store.transition(lesson, to_state, reason)
        if self.on_transition is not None:
            self.on_transition(lesson)

    # -- stage 2 helpers ---------------------------------------------------

    def _deterministic_checks(self, lesson: Lesson) -> dict[str, Any]:
        checks: dict[str, Any] = {}
        checks["source_cited"] = bool(lesson.origin and lesson.origin_source)
        # Contradiction: an asserted fact disagrees with the ground-truth
        # registry (an independent record the claimant does not control).
        contradictions = {
            k: {"asserted": v, "ground_truth": self.ground_truth[k]}
            for k, v in lesson.asserted_facts.items()
            if k in self.ground_truth and self.ground_truth[k] != v
        }
        checks["contradictions"] = contradictions
        checks["contradicted"] = bool(contradictions)
        # Corroboration: >= 1 supporting record from a source OTHER than
        # the record that originated the claim.
        independent = [
            r for r in lesson.evidence
            if r.supports and r.source != lesson.origin_record_source
        ]
        checks["independent_support_count"] = len(independent)
        checks["corroborated"] = len(independent) >= 1
        return checks

    def _auditor_assessment(self, lesson: Lesson) -> Optional[AuditorAssessment]:
        """Call the auditor with ONE bounded retry (spec 2.7). Returns None
        if the auditor could not produce a verdict at all."""
        for attempt in (1, 2):
            try:
                return self.auditor.assess(
                    lesson.claim_text,
                    lesson.asserted_facts,
                    lesson.evidence,
                    self.ground_truth,
                )
            except Exception as exc:  # timeout or service error: an instrument event
                self.store.append_event(
                    "auditor_call_failed",
                    f"Auditor attempt {attempt} failed for {lesson.family} "
                    f"v{lesson.version}: {type(exc).__name__}: {exc}",
                    lesson_id=lesson.lesson_id,
                    attempt=attempt,
                )
        return None

    # -- stages 1-3: evaluate a candidate -----------------------------------

    def evaluate(
        self, lesson: Lesson, acceptance_worlds: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Run intake -> evidence check -> use decision for one candidate.
        The lesson must already be in the store (CANDIDATE). Returns the
        decision record; the lesson's state in the store is authoritative."""
        assert lesson.state is State.CANDIDATE, "evaluate() requires a CANDIDATE lesson"
        checks = self._deterministic_checks(lesson)
        assessment = self._auditor_assessment(lesson)

        # FAIL CLOSED: the instrument failed, not the lesson. The lesson is
        # challenged, NOT admitted, and the event is an evidence-integrity
        # fault -- never a pass, never fabrication (spec 2.5, 2.7; H3).
        if assessment is None:
            lesson.validation = {
                "checks": checks,
                "auditor": None,
                "check_incomplete": "check incomplete -- not admitted",
                "decision": "fail_closed",
            }
            self._transition(
                lesson, State.CHALLENGED,
                "Auditor unavailable after one bounded retry; failing closed.",
            )
            self.store.append_event(
                "evidence_integrity_fault",
                f"Auditor produced no verdict for {lesson.family} "
                f"v{lesson.version}; lesson held in CHALLENGED, not admitted. "
                f"This is an instrument fault, not a finding about the lesson.",
                lesson_id=lesson.lesson_id,
            )
            return {"decision": "fail_closed", "state": lesson.state.value,
                    "checks": checks, "auditor": None}

        validation: dict[str, Any] = {
            "checks": checks,
            "auditor": {
                "auditor_id": assessment.auditor_id,
                "verdict": assessment.verdict,
                "rationale": assessment.rationale,
                "separations": assessment.separations,
            },
        }

        # Contradiction: deterministic registry OR auditor. Evidence wins
        # over plausibility -- a challenged lesson is never admitted on the
        # strength of its explanation (spec 2.3; hostile fixture H1).
        if checks["contradicted"] or assessment.verdict == "contradicts":
            detail = (
                f"Contradicted by ground-truth record(s): {checks['contradictions']}"
                if checks["contradicted"] else assessment.rationale
            )
            validation["decision"] = "quarantined"
            validation["failed_check"] = detail
            lesson.validation = validation
            self._transition(lesson, State.CHALLENGED, f"Evidence check flagged: {detail}")
            self._transition(
                lesson, State.QUARANTINED,
                "Flagged check resolved as failure: claim contradicted by evidence.",
            )
            return {"decision": "quarantined", "state": lesson.state.value,
                    "checks": checks, "auditor": assessment.verdict}

        # Insufficient evidence: refused, but NOT recorded as false
        # (hostile fixture H2: unverified is not the same as wrong).
        if not checks["source_cited"] or not checks["corroborated"] or assessment.verdict == "insufficient":
            validation["decision"] = "quarantined"
            validation["failed_check"] = (
                ("Missing provenance: source citation is required. " if not checks["source_cited"] else "")
                + "Insufficient evidence: no independent corroborating record. "
                "Held unverified -- explicitly NOT recorded as false."
            )
            lesson.validation = validation
            self._transition(
                lesson, State.CHALLENGED,
                "Evidence gap: no independent corroboration.",
            )
            self._transition(
                lesson, State.QUARANTINED,
                "Unresolved with available evidence; fails closed (unverified "
                "is never admitted as verified).",
            )
            return {"decision": "quarantined", "state": lesson.state.value,
                    "checks": checks, "auditor": assessment.verdict}

        # All evidence checks pass -> held-out acceptance test (spec 5).
        acceptance = self.acceptance_runner(lesson, acceptance_worlds)
        validation["acceptance_test"] = acceptance
        if not acceptance["passed"]:
            validation["decision"] = "quarantined"
            validation["failed_check"] = (
                "Failed the held-out acceptance test: "
                f"{acceptance['results']}"
            )
            lesson.validation = validation
            self._transition(
                lesson, State.CHALLENGED,
                "Held-out acceptance test failed.",
            )
            self._transition(
                lesson, State.QUARANTINED,
                "A lesson that does not help on held-out cases is not admitted.",
            )
            return {"decision": "quarantined", "state": lesson.state.value,
                    "checks": checks, "auditor": assessment.verdict,
                    "acceptance": acceptance}

        validation["decision"] = "admitted"
        lesson.validation = validation
        lesson.scope = (
            f"Held-out acceptance worlds: "
            f"{[w['world_id'] for w in acceptance_worlds]}"
        )
        self._transition(
            lesson, State.ADMITTED,
            "All evidence checks passed and the held-out acceptance test passed.",
        )
        return {"decision": "admitted", "state": lesson.state.value,
                "checks": checks, "auditor": assessment.verdict,
                "acceptance": acceptance}

    # -- stage 4 support: re-validation --------------------------------------

    def revalidate(
        self, lesson: Lesson, acceptance_worlds: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Re-run the full check set + acceptance under current conditions.
        Guards both restore paths (suspended -> admitted, rollback target).
        A version that does not re-pass does not become usable."""
        checks = self._deterministic_checks(lesson)
        assessment = self._auditor_assessment(lesson)
        if assessment is None:
            return {"passed": False, "reason": "auditor unavailable during re-validation",
                    "checks": checks}
        acceptance = self.acceptance_runner(lesson, acceptance_worlds)
        passed = (
            not checks["contradicted"]
            and checks["corroborated"]
            and assessment.verdict == "supports"
            and acceptance["passed"]
        )
        return {
            "passed": passed,
            "checks": checks,
            "auditor_verdict": assessment.verdict,
            "acceptance": acceptance,
        }
