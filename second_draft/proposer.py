"""Lesson proposer adapters.

A proposer distills candidate lessons from executed trajectories. Two
implementations:

- DeterministicProposer: the local, offline implementation used by this
  vertical slice. Rule-based over structured trajectory fields (verifier
  error tags recurring across >= 2 trajectories). No model, no API key.
- MetaModelProposer: Meta Model API proposer, wired Oct 27 (Oct 26 gate).
  Without a META_API_KEY it raises MetaApiError and the gate fails
  closed; it never fakes a lesson.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from .models import EvidenceRecord, Lesson, Trajectory


class Proposer(ABC):
    """Interface every proposer adapter implements."""

    name: str = "abstract-proposer"

    @abstractmethod
    def propose(self, trajectories: list[Trajectory]) -> list[Lesson]:
        """Return candidate lessons distilled from the trajectories."""
        raise NotImplementedError


def _confidence_from_support(n: int) -> float:
    """Proposer heuristic only -- a count of supporting runs, NOT evidence
    of truth. The gate never admits on confidence alone (spec 2.1)."""
    return round(n / (n + 1), 2)


class DeterministicProposer(Proposer):
    """Extracts a candidate lesson when the same verifier failure pattern
    recurs across at least two independent trajectories.

    Rules implemented for the slice:
    - tag 'schedule_claim_unchecked' in >= 2 trajectories ->
      lesson family 'schedule-cross-check', directive: prefer the calendar
      source for schedule claims.
    - tag 'schedule_claim_stale_calendar' in >= 2 trajectories ->
      lesson family 'schedule-cross-check' (a new version of the same
      lineage), directive: prefer the most recently timestamped note.
    """

    name = "deterministic-local-proposer"

    def propose(self, trajectories: list[Trajectory]) -> list[Lesson]:
        lessons: list[Lesson] = []
        unchecked = [
            t for t in trajectories
            if "schedule_claim_unchecked" in t.verifier_result.get("error_tags", [])
        ]
        if len(unchecked) >= 2:
            lessons.append(self._cross_check_lesson(unchecked))
        stale_cal = [
            t for t in trajectories
            if "schedule_claim_stale_calendar" in t.verifier_result.get("error_tags", [])
        ]
        if len(stale_cal) >= 2:
            lessons.append(self._most_recent_lesson(stale_cal))
        return lessons

    def _cross_check_lesson(self, support: list[Trajectory]) -> Lesson:
        ids = ", ".join(t.trajectory_id for t in support)
        evidence = [
            EvidenceRecord(
                source="verifier",
                kind="verifier-result",
                detail=(
                    f"Trajectory {t.trajectory_id}: verifier flagged "
                    f"'schedule_claim_unchecked' -- the briefing stated a "
                    f"schedule time taken from an uncorroborated note."
                ),
                supports=True,
            )
            for t in support
        ]
        return Lesson(
            family="schedule-cross-check",
            claim_text=(
                "Cross-check any schedule claim against the calendar source "
                "before stating it."
            ),
            origin=f"Trajectories {ids} (executed morning-briefing runs)",
            origin_source="agent-trajectory",
            origin_record_source="agent-run",
            transformation=(
                f"Deterministic distillation: the verifier tag "
                f"'schedule_claim_unchecked' recurred in {len(support)} "
                f"independent trajectories; the common cause (schedule time "
                f"taken from the first note read, unchecked against the "
                f"calendar source) was extracted as a reusable rule."
            ),
            confidence=_confidence_from_support(len(support)),
            directive={"kind": "schedule_source_precedence", "source": "calendar"},
            evidence=evidence,
        )

    def _most_recent_lesson(self, support: list[Trajectory]) -> Lesson:
        ids = ", ".join(t.trajectory_id for t in support)
        evidence = [
            EvidenceRecord(
                source="verifier",
                kind="verifier-result",
                detail=(
                    f"Trajectory {t.trajectory_id}: verifier flagged "
                    f"'schedule_claim_stale_calendar' -- the calendar note "
                    f"was stale and the most recent note held the correct time."
                ),
                supports=True,
            )
            for t in support
        ]
        return Lesson(
            family="schedule-cross-check",
            claim_text=(
                "For schedule claims, prefer the most recently timestamped "
                "note over the calendar source."
            ),
            origin=f"Trajectories {ids} (executed weekend-briefing runs)",
            origin_source="agent-trajectory",
            origin_record_source="agent-run",
            transformation=(
                f"Deterministic distillation: the verifier tag "
                f"'schedule_claim_stale_calendar' recurred in {len(support)} "
                f"independent trajectories; extracted as a revision of the "
                f"schedule-cross-check lineage."
            ),
            confidence=_confidence_from_support(len(support)),
            directive={"kind": "schedule_source_precedence", "source": "most_recent"},
            evidence=evidence,
        )


class MetaModelProposer(Proposer):
    """Meta Model API proposer adapter, wired Oct 27 (Oct 26 gate).

    The model genuinely proposes: it sees the executed trajectories
    (task, outcome, verifier error tags) and returns candidate lessons
    in a constrained format. Code, not the model, validates structure:
    a lesson is emitted only if the same verifier error tag recurs in
    >= 2 trajectories and the directive maps to a behavior the briefing
    agent actually implements (calendar / most_recent schedule
    precedence). Confidence is a support-count heuristic computed in
    code, never the model's self-reported confidence -- the gate never
    admits on confidence alone (spec 2.1).

    Without a META_API_KEY, propose() raises MetaApiError and the
    gate fails closed; it never returns a fabricated lesson.
    """

    name = "meta-model-api-proposer"

    def __init__(self, model: str = "muse-spark-1.3", client=None):
        self.model = model
        self._client = client

    def _client_or_default(self):
        if self._client is not None:
            return self._client
        from .meta_client import MetaApiClient

        return MetaApiClient(model=self.model)

    def propose(self, trajectories: list[Trajectory]) -> list[Lesson]:
        # Recurrence counts are computed in code first: they are the
        # structural validation, not a substitute for the model's proposal.
        tag_support: dict[str, list[Trajectory]] = {}
        for t in trajectories:
            for tag in t.verifier_result.get("error_tags", []):
                tag_support.setdefault(tag, []).append(t)
        if not any(len(v) >= 2 for v in tag_support.values()):
            return []

        summary = "\n".join(
            f"- {t.trajectory_id} task={t.task_id} outcome={t.outcome} "
            f"error_tags={t.verifier_result.get('error_tags', [])}"
            for t in trajectories
        )
        messages = [
            {
                "role": "system",
                "content": (
                    "You distill reusable lessons from executed agent runs. "
                    "Return one lesson per recurring failure pattern, each on "
                    "its own line, in exactly this format:\n"
                    "LESSON: <one-sentence reusable rule> | "
                    "DIRECTIVE: calendar | most_recent | none\n"
                    "DIRECTIVE means: calendar = prefer the calendar source "
                    "for schedule claims; most_recent = prefer the most "
                    "recently timestamped note; none = no machine behavior "
                    "follows from this lesson. Do not add other text."
                ),
            },
            {
                "role": "user",
                "content": f"Executed trajectories:\n{summary}\n\nLessons:",
            },
        ]
        text = self._client_or_default().complete(messages)
        lessons: list[Lesson] = []
        for line in text.splitlines():
            line = line.strip()
            if not line.startswith("LESSON:"):
                continue
            try:
                claim_part, directive_part = line[len("LESSON:"):].split("| DIRECTIVE:")
            except ValueError:
                continue
            claim_text = claim_part.strip()
            directive_source = directive_part.strip()
            if directive_source not in ("calendar", "most_recent"):
                continue
            # The directive must correspond to a recurring tag the code
            # actually observed; otherwise the model's line is dropped.
            wanted_tag = (
                "schedule_claim_unchecked" if directive_source == "calendar"
                else "schedule_claim_stale_calendar"
            )
            support = tag_support.get(wanted_tag, [])
            if len(support) < 2:
                continue
            ids = ", ".join(t.trajectory_id for t in support)
            evidence = [
                EvidenceRecord(
                    source="verifier",
                    kind="verifier-result",
                    detail=(
                        f"Trajectory {t.trajectory_id}: verifier flagged "
                        f"'{wanted_tag}'."
                    ),
                    supports=True,
                )
                for t in support
            ]
            lessons.append(
                Lesson(
                    family="schedule-cross-check",
                    claim_text=claim_text,
                    origin=(
                        f"Trajectories {ids} (executed morning-briefing runs, "
                        f"distilled by Meta Model API model {self.model})"
                    ),
                    origin_source="agent-trajectory",
                    origin_record_source="agent-run",
                    transformation=(
                        f"Meta Model API distillation ({self.model}): the "
                        f"verifier tag '{wanted_tag}' recurred in "
                        f"{len(support)} independent trajectories; the "
                        f"model proposed the reusable rule, code validated "
                        f"recurrence and directive mapping."
                    ),
                    confidence=_confidence_from_support(len(support)),
                    directive={
                        "kind": "schedule_source_precedence",
                        "source": directive_source,
                    },
                    evidence=evidence,
                )
            )
        return lessons
