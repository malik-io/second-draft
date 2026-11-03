"""The Verified Morning briefing agent.

Deterministic for the slice: the agent assembles a briefing (standup time
+ weather) from a world's source notes. Its baseline behavior states the
schedule from the first schedule-bearing note in reading order -- the
failure mode the valid lesson corrects. Learned lessons change behavior
ONLY through their machine-readable directives, and only lessons the
caller supplies (in the real system: store.retrieve(), admitted-only).
"""

from __future__ import annotations

from typing import Any

from .models import Lesson, Trajectory, TrajectoryStep

AUTHORITATIVE_SCHEDULE_SOURCE = "calendar-source"


def _schedule_notes(world: dict[str, Any]) -> list[dict[str, Any]]:
    return [n for n in world["notes"] if "standup_time" in n["facts"]]


def assemble_briefing(world: dict[str, Any], active_lessons: list[Lesson]) -> dict[str, Any]:
    """Assemble a briefing. Returns claims with values AND provenance --
    provenance is what the verifier and the gate reason about."""
    notes = world["notes"]
    sched_notes = _schedule_notes(world)
    # Baseline: first schedule-bearing note in reading order.
    first = sched_notes[0]
    time_value = first["facts"]["standup_time"]
    time_provenance = first["source_id"]

    for lesson in active_lessons:
        d = lesson.directive
        kind = d.get("kind")
        if kind == "schedule_source_precedence" and d.get("source") == "calendar":
            cal = next(
                (n for n in sched_notes if n["source_id"] == AUTHORITATIVE_SCHEDULE_SOURCE),
                None,
            )
            if cal is not None:
                time_value = cal["facts"]["standup_time"]
                time_provenance = cal["source_id"]
        elif kind == "schedule_source_precedence" and d.get("source") == "most_recent":
            latest = max(sched_notes, key=lambda n: n["timestamp"])
            time_value = latest["facts"]["standup_time"]
            time_provenance = latest["source_id"]
        elif kind == "schedule_override":
            time_value = d["time"]
            time_provenance = f"lesson:{lesson.family} v{lesson.version}"

    weather_note = next(n for n in notes if n["kind"] == "weather")
    claims = [
        {
            "key": "standup_time",
            "text": f"Standup is at {time_value}.",
            "value": time_value,
            "provenance": time_provenance,
        },
        {
            "key": "weather",
            "text": f"Weather: {weather_note['facts']['weather']}",
            "value": weather_note["facts"]["weather"],
            "provenance": weather_note["source_id"],
        },
    ]
    return {"world_id": world["world_id"], "claims": claims}


def verify_briefing(world: dict[str, Any], briefing: dict[str, Any]) -> dict[str, Any]:
    """Verify a briefing against the world's ground truth.

    A claim is SUPPORTED if its value matches ground truth AND its
    provenance is corroborated: stated from the authoritative calendar
    source, or independently matching the calendar record. A claim that is
    numerically right but drawn from an uncorroborated lesson/note is
    counted as an unsupported claim (spec section 3: unverified does not
    get silently upgraded to verified).
    """
    truth = world["ground_truth"]
    cal_note = next(
        (n for n in world["notes"] if n["source_id"] == AUTHORITATIVE_SCHEDULE_SOURCE),
        None,
    )
    verdicts = []
    error_tags: list[str] = []
    for claim in briefing["claims"]:
        expected = truth[claim["key"]]
        value_ok = claim["value"] == expected
        if claim["key"] == "standup_time":
            if claim["provenance"] == AUTHORITATIVE_SCHEDULE_SOURCE:
                corroborated = True  # stated from the authoritative record
            elif cal_note is not None:
                # Corroborated iff an independent record (the calendar)
                # agrees with the stated value.
                corroborated = cal_note["facts"]["standup_time"] == claim["value"]
            else:
                corroborated = False
            if not value_ok and not corroborated and cal_note is not None:
                error_tags.append("schedule_claim_unchecked")
            if not value_ok and claim["provenance"] == AUTHORITATIVE_SCHEDULE_SOURCE:
                error_tags.append("schedule_claim_stale_calendar")
        else:
            corroborated = True
        supported = value_ok and corroborated
        verdicts.append(
            {
                "key": claim["key"],
                "stated": claim["value"],
                "expected": expected,
                "value_ok": value_ok,
                "provenance": claim["provenance"],
                "supported": supported,
            }
        )
    return {
        "claims": verdicts,
        "all_correct": all(v["value_ok"] for v in verdicts),
        "unsupported_claims": sum(1 for v in verdicts if not v["supported"]),
        "error_tags": sorted(set(error_tags)),
    }


def run_as_trajectory(
    world: dict[str, Any], active_lessons: list[Lesson], task_id: str
) -> tuple[dict[str, Any], dict[str, Any], Trajectory]:
    """Execute one briefing run and capture it as a Trajectory (attempted
    vs verified outcome kept distinct, spec section 4)."""
    briefing = assemble_briefing(world, active_lessons)
    verdict = verify_briefing(world, briefing)
    steps = [
        TrajectoryStep(
            action="read_notes",
            detail=f"Read {len(world['notes'])} source notes in order.",
            evidence_state="executed",
        ),
        TrajectoryStep(
            action="assemble_briefing",
            detail="; ".join(c["text"] for c in briefing["claims"]),
            evidence_state="executed",
        ),
        TrajectoryStep(
            action="verify_briefing",
            detail=f"Verifier: all_correct={verdict['all_correct']}, "
                   f"tags={verdict['error_tags']}",
            evidence_state="executed",
        ),
    ]
    outcome = (
        "Briefing correct on all claims."
        if verdict["all_correct"]
        else f"Briefing contained error(s): {verdict['error_tags']}"
    )
    traj = Trajectory(
        task_id=task_id,
        inputs={"world_id": world["world_id"],
                "active_lessons": [f"{l.family} v{l.version}" for l in active_lessons]},
        steps=steps,
        outcome=outcome,
        verifier_result=verdict,
    )
    return briefing, verdict, traj
