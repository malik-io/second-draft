"""Core data models for Second Draft.

The five machine states, their presentation labels, and their faces are
normative (spec v1.2, section 2.3). The machine state is authoritative;
the label and the face are presentation only. If the face ever disagrees
with the machine state, that is a bug -- the record wins.
"""

from __future__ import annotations

import enum
import time
import uuid
from dataclasses import dataclass, field, asdict
from typing import Any, Optional


def utc_now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


class State(enum.Enum):
    CANDIDATE = "CANDIDATE"
    CHALLENGED = "CHALLENGED"
    QUARANTINED = "QUARANTINED"
    ADMITTED = "ADMITTED"
    SUSPENDED = "SUSPENDED"


# Spec 2.3 mapping table: machine state -> (presentation label, kaomoji face).
# "Alarmed" is a visual treatment of CHALLENGED, never a state of its own.
FACES: dict[State, tuple[str, str]] = {
    State.CANDIDATE: ("Candidate", "( •̀ ω •́ )✧"),
    State.CHALLENGED: ("Challenged", "( ; ﾟДﾟ)"),
    State.QUARANTINED: ("Quarantined", "( ￣へ￣)"),
    State.ADMITTED: ("Admitted", "( ´ ω ` )"),
    State.SUSPENDED: ("Suspended", "( ❄_❄ )"),
}


def label_for(state: State) -> str:
    return FACES[state][0]


def face_for(state: State) -> str:
    return FACES[state][1]


# Allowed transitions and their guards (spec 2.3). The store enforces this
# table; a transition not listed here is rejected in code.
ALLOWED_TRANSITIONS: dict[tuple[Optional[State], State], str] = {
    (None, State.CANDIDATE): (
        "A lesson is distilled from executed work and its provenance "
        "record is written."
    ),
    (State.CANDIDATE, State.CHALLENGED): (
        "An evidence check raised a conflict, contradiction, or evidence gap."
    ),
    (State.CANDIDATE, State.ADMITTED): (
        "All defined checks pass AND the lesson passes its acceptance test "
        "on the held-out set. Admission is scoped."
    ),
    (State.CHALLENGED, State.QUARANTINED): (
        "The flagged check resolved as a failure, or cannot be resolved "
        "with available evidence. Fails closed."
    ),
    (State.CHALLENGED, State.ADMITTED): (
        "The conflict was resolved by new evidence or a corrected version, "
        "which re-passed the full check set and the held-out acceptance test."
    ),
    (State.ADMITTED, State.CHALLENGED): (
        "New evidence contradicts the lesson, a held-out regression is "
        "detected, or a human re-opens it."
    ),
    (State.ADMITTED, State.SUSPENDED): (
        "A suspension trigger fired (spec 2.5). Immediate; no check-pass "
        "can override a trigger."
    ),
    (State.QUARANTINED, State.SUSPENDED): (
        "A quarantined lesson is later confirmed as a hard-rule case "
        "(confirmed fabrication or unauthorized action)."
    ),
    (State.SUSPENDED, State.ADMITTED): (
        "Restore ONLY via re-validation: the same version re-passes its "
        "full check set plus fresh behavioral probes under current "
        "conditions. There is no direct un-suspend button."
    ),
}


@dataclass
class EvidenceRecord:
    """One piece of evidence attached to a claim/lesson."""

    source: str  # who/what produced this record (e.g. "calendar-source")
    kind: str  # e.g. "source-note", "verifier-result", "ground-truth", "trajectory"
    detail: str
    supports: bool  # True = supports the claim, False = contradicts it

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "EvidenceRecord":
        return cls(**d)


@dataclass
class ReversalRecord:
    """Written when a lesson is suspended / rolled back. Never deleted."""

    trigger: str  # e.g. "confirmed_regression", "human_control", "fabrication"
    reason: str
    suspended_version: int
    rollback_target_version: Optional[int] = None
    revalidation_result: Optional[dict[str, Any]] = None
    timestamp: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ReversalRecord":
        return cls(**d)


@dataclass
class Lesson:
    """A versioned lesson record with the filed provenance fields.

    Provenance fields (from the application as filed): Origin, Transformation,
    Confidence, Validation, Version, Reversal -- plus the gate state.
    `family` groups versions of the same lesson (v1, v2, ... of one lineage).
    `directive` is the machine-readable behavior the lesson asks the agent
    to adopt; retrieval only ever returns ADMITTED, non-superseded lessons.
    """

    family: str
    claim_text: str
    origin: str  # Origin: where the lesson came from (trajectory ids, source)
    origin_source: str  # source type that originated the claim
    transformation: str  # Transformation: how raw work became this lesson
    confidence: float  # Confidence: proposer heuristic, NOT evidence of truth
    directive: dict[str, Any]  # machine-readable behavior change
    origin_record_source: str = ""  # id of the specific record that originated it
    asserted_facts: dict[str, Any] = field(default_factory=dict)
    evidence: list[EvidenceRecord] = field(default_factory=list)
    validation: dict[str, Any] = field(default_factory=dict)  # Validation record
    version: int = 0  # Version: assigned by the store at intake
    lesson_id: str = field(default_factory=lambda: new_id("lesson"))
    state: State = State.CANDIDATE
    scope: str = ""  # admission scope, set on admission
    superseded_by: Optional[int] = None  # version number that superseded this one
    reversal: Optional[ReversalRecord] = None  # Reversal record, once suspended
    created_at: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["state"] = self.state.value
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Lesson":
        d = dict(d)
        d["state"] = State(d["state"])
        d["evidence"] = [EvidenceRecord.from_dict(e) for e in d.get("evidence", [])]
        rev = d.get("reversal")
        d["reversal"] = ReversalRecord.from_dict(rev) if rev else None
        return cls(**d)

    def is_retrievable(self) -> bool:
        """Code-level retrieval rule: only ADMITTED and not superseded."""
        return self.state is State.ADMITTED and self.superseded_by is None


@dataclass
class Claim:
    """A claim entering gate stage 1 (claim intake). Spec 2.1 / section 3."""

    text: str
    source: str  # model | user | other-agent | tool/document | claimed-action
    claim_type: str  # claim | instruction | observation
    asserted_facts: dict[str, Any] = field(default_factory=dict)
    evidence: list[EvidenceRecord] = field(default_factory=list)
    claim_id: str = field(default_factory=lambda: new_id("claim"))
    timestamp: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class TrajectoryStep:
    action: str
    detail: str
    # Execution-evidence state, kept distinct per spec section 4:
    # attempted | executed | sent | delivered | acknowledged
    evidence_state: str = "attempted"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Trajectory:
    """A structured record of one executed run (spec: trajectory capture)."""

    task_id: str
    inputs: dict[str, Any]
    steps: list[TrajectoryStep]
    outcome: str  # free-text outcome summary
    verifier_result: dict[str, Any]  # per-claim verdicts + error tags
    trajectory_id: str = field(default_factory=lambda: new_id("traj"))
    timestamp: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Trajectory":
        d = dict(d)
        d["steps"] = [TrajectoryStep(**s) for s in d.get("steps", [])]
        return cls(**d)
