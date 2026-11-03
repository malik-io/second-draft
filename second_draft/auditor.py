"""Auditor adapters.

The auditor renders an evidence ASSESSMENT; the deterministic gate code --
not the auditor -- makes the admission decision (spec 1, Tension B). The
auditor never sees the proposer's chain of reasoning, confidence, or the
admission thresholds (rubric blindness); it receives the claim, the
evidence bundle, and the ground-truth records.

Implementations:
- LocalFixtureAuditor: STUB auditor for the offline slice. Renders verdicts
  deterministically from the fixture evidence bundle. Clearly labeled: it
  is a stand-in for the cross-model audit, not a model.
- MetaModelAuditor: Meta Model API auditor, wired Oct 27 (Oct 26 gate).
- FailingAuditor / TimeoutAuditor / FlakyAuditor: test doubles that
  exercise the gate's fail-closed path (hostile fixture H3).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Optional

from .models import EvidenceRecord, Lesson


@dataclass
class AuditorAssessment:
    verdict: str  # "supports" | "contradicts" | "insufficient"
    rationale: str
    auditor_id: str
    separations: dict[str, Any]  # Tension B disclosure (spec 1)


class Auditor(ABC):
    name: str = "abstract-auditor"

    @abstractmethod
    def assess(
        self,
        claim_text: str,
        asserted_facts: dict[str, Any],
        evidence: list[EvidenceRecord],
        ground_truth: dict[str, Any],
    ) -> AuditorAssessment:
        raise NotImplementedError


class LocalFixtureAuditor(Auditor):
    """STUB auditor (offline slice). Deterministic verdicts rendered from
    the fixture evidence bundle -- a stand-in for the cross-model audit,
    labeled as such everywhere its verdicts are recorded."""

    name = "local-fixture-auditor (STUB)"

    def assess(self, claim_text, asserted_facts, evidence, ground_truth):
        # Contradiction: an asserted fact disagrees with ground truth.
        for key, value in asserted_facts.items():
            if key in ground_truth and ground_truth[key] != value:
                return AuditorAssessment(
                    verdict="contradicts",
                    rationale=(
                        f"Asserted fact {key}={value!r} contradicts the "
                        f"ground-truth record {key}={ground_truth[key]!r}."
                    ),
                    auditor_id=self.name,
                    separations={
                        "model_identity": "proposer=deterministic-local; "
                                          "auditor=local-fixture-stub (no model)",
                        "context_isolation": True,
                        "rubric_blindness": True,
                    },
                )
        # Contradiction carried in the evidence bundle itself.
        for rec in evidence:
            if not rec.supports:
                return AuditorAssessment(
                    verdict="contradicts",
                    rationale=f"Evidence record from {rec.source} contradicts: {rec.detail}",
                    auditor_id=self.name,
                    separations={
                        "model_identity": "proposer=deterministic-local; "
                                          "auditor=local-fixture-stub (no model)",
                        "context_isolation": True,
                        "rubric_blindness": True,
                    },
                )
        # Support requires at least one independent supporting record.
        independent = [r for r in evidence if r.supports]
        if independent:
            return AuditorAssessment(
                verdict="supports",
                rationale=(
                    f"{len(independent)} supporting evidence record(s) in the "
                    f"bundle; no contradiction found against ground truth."
                ),
                auditor_id=self.name,
                separations={
                    "model_identity": "proposer=deterministic-local; "
                                      "auditor=local-fixture-stub (no model)",
                    "context_isolation": True,
                    "rubric_blindness": True,
                },
            )
        return AuditorAssessment(
            verdict="insufficient",
            rationale="No independent supporting evidence in the bundle.",
            auditor_id=self.name,
            separations={
                "model_identity": "proposer=deterministic-local; "
                                  "auditor=local-fixture-stub (no model)",
                "context_isolation": True,
                "rubric_blindness": True,
            },
        )


def meta_separations(proposer_model: str, auditor_model: str) -> dict[str, Any]:
    """Tension B disclosure (spec 1), stated honestly.

    Achieved: different model versions, context isolation, rubric
    blindness, and a deterministic gate (not the auditor) deciding.
    NOT achieved: model-family separation -- proposer and auditor are
    both Muse Spark models on the Meta Model API, so the word
    "independent" in submission text must be scoped to these
    separations, never to cross-family independence.
    """
    return {
        "model_identity": (
            f"proposer={proposer_model} (Meta Model API); "
            f"auditor={auditor_model} (Meta Model API)"
        ),
        "model_family_separation": False,
        "model_family_note": (
            "Both sides are Muse Spark models; separation is by model "
            "version, context, and rubric blindness, not by family."
        ),
        "context_isolation": True,
        "rubric_blindness": True,
        "decision_maker": "deterministic gate code, not the auditor",
    }


class MetaModelAuditor(Auditor):
    """Meta Model API auditor adapter, wired Oct 27 (Oct 26 gate).

    The auditor receives ONLY the claim, the evidence bundle, and the
    ground-truth records. It never sees the proposer's reasoning,
    confidence, the admission thresholds, the held-out outcomes, or
    which result anyone wants (rubric blindness + context isolation).
    It returns an evidence assessment; the deterministic gate code
    makes the admission decision. An unparseable reply or a missing
    key raises MetaApiError, and the gate fails closed -- never a
    fabricated verdict.
    """

    name = "meta-model-api-auditor"

    def __init__(
        self,
        model: str = "muse-spark-1.1",
        proposer_model: str = "muse-spark-1.3",
        client=None,
    ):
        self.model = model
        self.proposer_model = proposer_model
        self._client = client

    def _client_or_default(self):
        if self._client is not None:
            return self._client
        from .meta_client import MetaApiClient

        return MetaApiClient(model=self.model)

    def assess(self, claim_text, asserted_facts, evidence, ground_truth):
        from .meta_client import MetaApiError

        evidence_lines = "\n".join(
            f"- [{rec.source}] supports={rec.supports}: {rec.detail}"
            for rec in evidence
        )
        messages = [
            {
                "role": "system",
                "content": (
                    "You are an evidence assessor. Judge ONLY whether the "
                    "evidence bundle supports, contradicts, or is "
                    "insufficient for the claim, against the ground-truth "
                    "records. Return exactly:\n"
                    "VERDICT: supports | contradicts | insufficient\n"
                    "RATIONALE: <one sentence>\n"
                    "Do not add other text."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Claim: {claim_text}\n"
                    f"Asserted facts: {asserted_facts}\n"
                    f"Evidence:\n{evidence_lines}\n"
                    f"Ground truth: {ground_truth}"
                ),
            },
        ]
        text = self._client_or_default().complete(messages)
        verdict = None
        rationale = ""
        for line in text.splitlines():
            line = line.strip()
            if line.startswith("VERDICT:"):
                verdict = line[len("VERDICT:"):].strip()
            elif line.startswith("RATIONALE:"):
                rationale = line[len("RATIONALE:"):].strip()
        if verdict not in ("supports", "contradicts", "insufficient") or not rationale:
            raise MetaApiError(
                "Meta Model API auditor returned an unparseable assessment; "
                "no verdict was recorded."
            )
        return AuditorAssessment(
            verdict=verdict,
            rationale=rationale,
            auditor_id=self.name,
            separations=meta_separations(self.proposer_model, self.model),
        )


class AuditorUnavailable(Exception):
    """Simulates an unreachable auditor service."""


class FailingAuditor(Auditor):
    """Test double: every call raises (auditor down). Hostile fixture H3."""

    name = "failing-auditor (test double)"

    def assess(self, claim_text, asserted_facts, evidence, ground_truth):
        raise AuditorUnavailable("auditor service unreachable (simulated)")


class TimeoutAuditor(Auditor):
    """Test double: every call times out. Hostile fixture H3, variant 2."""

    name = "timeout-auditor (test double)"

    def assess(self, claim_text, asserted_facts, evidence, ground_truth):
        raise TimeoutError("auditor call timed out (simulated)")


class FlakyAuditor(Auditor):
    """Test double: fails the first call, delegates afterwards. Exercises
    the gate's one bounded retry (spec 2.7)."""

    name = "flaky-auditor (test double)"

    def __init__(self, delegate: Optional[Auditor] = None):
        self._delegate = delegate or LocalFixtureAuditor()
        self.calls = 0

    def assess(self, claim_text, asserted_facts, evidence, ground_truth):
        self.calls += 1
        if self.calls == 1:
            raise AuditorUnavailable("transient auditor failure (simulated)")
        return self._delegate.assess(claim_text, asserted_facts, evidence, ground_truth)
