"""Versioned lesson store (protected build order, step 1).

On-disk layout under the store root:
  lessons.json   -- every lesson version ever written (never deleted)
  events.jsonl   -- append-only event log (one JSON object per line)
  trajectories/  -- one JSON file per captured trajectory

The store enforces the spec 2.3 transition table in code. Supersede-don't-
delete: records stay retrievable forever; supersession removes *use*, not
the record (spec section 7, Point 5).
"""

from __future__ import annotations

import json
import os
from typing import Any, Optional

from .models import (
    ALLOWED_TRANSITIONS,
    Lesson,
    ReversalRecord,
    State,
    Trajectory,
    utc_now_iso,
)


class IllegalTransition(Exception):
    """Raised when code attempts a state transition the spec forbids."""


class Store:
    def __init__(self, root: str):
        self.root = root
        self.lessons_path = os.path.join(root, "lessons.json")
        self.events_path = os.path.join(root, "events.jsonl")
        self.traj_dir = os.path.join(root, "trajectories")
        os.makedirs(self.traj_dir, exist_ok=True)
        self._lessons: dict[str, Lesson] = {}  # lesson_id -> Lesson
        self._event_seq = 0
        self._load()

    # -- persistence -----------------------------------------------------

    def _load(self) -> None:
        if os.path.exists(self.lessons_path):
            with open(self.lessons_path, encoding="utf-8") as f:
                for d in json.load(f):
                    lesson = Lesson.from_dict(d)
                    self._lessons[lesson.lesson_id] = lesson
        if os.path.exists(self.events_path):
            with open(self.events_path, encoding="utf-8") as f:
                self._event_seq = sum(1 for _ in f)

    def _save_lessons(self) -> None:
        data = [lesson.to_dict() for lesson in self._lessons.values()]
        tmp = self.lessons_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        os.replace(tmp, self.lessons_path)

    def append_event(
        self, event_type: str, detail: str, lesson_id: Optional[str] = None, **extra: Any
    ) -> dict[str, Any]:
        """Append one event to the append-only log. Events are never edited."""
        self._event_seq += 1
        event = {
            "seq": self._event_seq,
            "timestamp": utc_now_iso(),
            "type": event_type,
            "lesson_id": lesson_id,
            "detail": detail,
        }
        event.update(extra)
        with open(self.events_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")
        return event

    def events(self) -> list[dict[str, Any]]:
        if not os.path.exists(self.events_path):
            return []
        with open(self.events_path, encoding="utf-8") as f:
            return [json.loads(line) for line in f if line.strip()]

    # -- trajectories ------------------------------------------------------

    def save_trajectory(self, traj: Trajectory) -> str:
        path = os.path.join(self.traj_dir, f"{traj.trajectory_id}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(traj.to_dict(), f, indent=2, ensure_ascii=False)
        self.append_event(
            "trajectory_captured",
            f"Trajectory {traj.trajectory_id} for task {traj.task_id}: {traj.outcome}",
        )
        return path

    def load_trajectories(self) -> list[Trajectory]:
        out = []
        for name in sorted(os.listdir(self.traj_dir)):
            if name.endswith(".json"):
                with open(os.path.join(self.traj_dir, name), encoding="utf-8") as f:
                    out.append(Trajectory.from_dict(json.load(f)))
        return out

    # -- lessons -----------------------------------------------------------

    def intake(self, lesson: Lesson) -> Lesson:
        """Enter a distilled lesson into the machine as CANDIDATE.

        Guard (spec 2.3): a lesson is distilled from executed work and its
        provenance record is written. An unwritten lesson cannot enter.
        Assigns the next Version within the lesson's family.
        """
        if not lesson.origin or not lesson.transformation:
            raise ValueError("Provenance incomplete: Origin and Transformation are required.")
        existing_versions = [
            l.version for l in self._lessons.values() if l.family == lesson.family
        ]
        lesson.version = (max(existing_versions) + 1) if existing_versions else 1
        lesson.state = State.CANDIDATE
        self._lessons[lesson.lesson_id] = lesson
        self._save_lessons()
        self.append_event(
            "lesson_candidate",
            f"Lesson {lesson.family} v{lesson.version} entered as CANDIDATE: "
            f"{lesson.claim_text}",
            lesson_id=lesson.lesson_id,
            family=lesson.family,
            version=lesson.version,
        )
        return lesson

    def get(self, lesson_id: str) -> Lesson:
        return self._lessons[lesson_id]

    def all_lessons(self) -> list[Lesson]:
        return list(self._lessons.values())

    def family_versions(self, family: str) -> list[Lesson]:
        return sorted(
            (l for l in self._lessons.values() if l.family == family),
            key=lambda l: l.version,
        )

    def transition(self, lesson: Lesson, to_state: State, reason: str) -> Lesson:
        """Move a lesson through the state machine, enforcing spec 2.3 guards."""
        key = (lesson.state, to_state)
        if key not in ALLOWED_TRANSITIONS:
            raise IllegalTransition(
                f"Transition {lesson.state.value} -> {to_state.value} is not in the "
                f"spec 2.3 table. Allowed from {lesson.state.value}: "
                f"{[t.value for (f, t) in ALLOWED_TRANSITIONS if f is lesson.state]}"
            )
        from_state = lesson.state
        lesson.state = to_state
        # Admitting a newer version supersedes older admitted versions of the
        # same family: they keep their record but lose use (spec section 7).
        if to_state is State.ADMITTED:
            for other in self.family_versions(lesson.family):
                if (
                    other.lesson_id != lesson.lesson_id
                    and other.state is State.ADMITTED
                    and other.superseded_by is None
                ):
                    other.superseded_by = lesson.version
                    self.append_event(
                        "lesson_superseded",
                        f"{other.family} v{other.version} superseded by "
                        f"v{lesson.version} (record retained, use removed).",
                        lesson_id=other.lesson_id,
                        family=other.family,
                        version=other.version,
                    )
        self._save_lessons()
        self.append_event(
            "state_transition",
            f"{lesson.family} v{lesson.version}: {from_state.value} -> "
            f"{to_state.value}. Reason: {reason}",
            lesson_id=lesson.lesson_id,
            family=lesson.family,
            version=lesson.version,
            from_state=from_state.value,
            to_state=to_state.value,
            reason=reason,
        )
        return lesson

    def suspend(
        self, lesson: Lesson, trigger: str, reason: str,
        rollback_target_version: Optional[int] = None,
    ) -> Lesson:
        """Fire a suspension trigger (spec 2.5). Writes the Reversal record."""
        lesson.reversal = ReversalRecord(
            trigger=trigger,
            reason=reason,
            suspended_version=lesson.version,
            rollback_target_version=rollback_target_version,
        )
        self.transition(lesson, State.SUSPENDED, f"Suspension trigger: {trigger}. {reason}")
        self.append_event(
            "lesson_suspended",
            f"{lesson.family} v{lesson.version} SUSPENDED. Trigger: {trigger}. {reason}",
            lesson_id=lesson.lesson_id,
            family=lesson.family,
            version=lesson.version,
            trigger=trigger,
        )
        self._save_lessons()
        return lesson

    def restore_after_revalidation(
        self, lesson: Lesson, revalidation_result: dict[str, Any]
    ) -> Lesson:
        """The ONLY suspended -> admitted path (spec 2.3): re-validation.

        The gate must have re-run the full check set plus fresh behavioral
        probes under current conditions and passed them; the result is
        attached to the record. There is no direct un-suspend.
        """
        if lesson.state is not State.SUSPENDED:
            raise IllegalTransition(
                f"restore_after_revalidation requires SUSPENDED, got {lesson.state.value}"
            )
        if not revalidation_result.get("passed"):
            raise IllegalTransition(
                "Re-validation did not pass; the version stays suspended."
            )
        if lesson.reversal is not None:
            lesson.reversal.revalidation_result = revalidation_result
        return self.transition(
            lesson, State.ADMITTED,
            "Restored via re-validation under current conditions (spec 2.3).",
        )

    def rollback_to(self, family: str, target_version: int, revalidation_result: dict[str, Any]) -> Lesson:
        """Roll back to a prior superseded version, only after re-validation.

        The target version was superseded (record kept, use removed). It
        becomes usable again only when re-validation passes under current
        conditions (spec sections 2.3, 6(3c)).
        """
        versions = {l.version: l for l in self.family_versions(family)}
        if target_version not in versions:
            raise KeyError(f"No version {target_version} in family {family}")
        target = versions[target_version]
        if not revalidation_result.get("passed"):
            raise IllegalTransition(
                "Rollback refused: target version did not re-pass re-validation."
            )
        target.validation = dict(target.validation)
        target.validation["rollback_revalidation"] = revalidation_result
        target.superseded_by = None
        self._save_lessons()
        self.append_event(
            "rollback_restored",
            f"{family} v{target_version} restored by rollback after "
            f"re-validation passed under current conditions.",
            lesson_id=target.lesson_id,
            family=family,
            version=target_version,
        )
        return target

    # -- retrieval (the load-bearing code property, spec sections 2.6, 6) --

    def retrieve(self) -> list[Lesson]:
        """Return lessons the agent may use. Exclusion is enforced HERE, in
        code -- quarantined, suspended, challenged, candidate, and superseded
        lessons cannot be retrieved, whatever any prompt says."""
        return [l for l in self._lessons.values() if l.is_retrievable()]
