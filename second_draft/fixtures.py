"""Synthetic fixtures for the Verified Morning scenario.

ALL data here is synthetic -- invented notes, invented times, no real
person, organisation, or personal data (spec section 12). Fixtures are
deterministic so the demo is repeatable.

A "world" is one morning: source notes in reading order plus a ground
truth registry. The calendar source is authoritative for schedule facts;
the message note is an unverified note that is sometimes stale.
"""

from __future__ import annotations

from typing import Any

from .models import EvidenceRecord, Lesson

World = dict[str, Any]


def _note(source_id: str, kind: str, timestamp: str, facts: dict[str, Any]) -> dict[str, Any]:
    return {"source_id": source_id, "kind": kind, "timestamp": timestamp, "facts": facts}


def _world(world_id: str, notes: list[dict[str, Any]], truth: dict[str, Any]) -> World:
    return {"world_id": world_id, "notes": notes, "ground_truth": truth}


WEATHER = "Rain until 10 AM, clearing after"


def demo_world() -> World:
    """The main demo morning (weekday). The message note is the most recent
    note and it is stale: it says 08:30; the calendar says 09:00."""
    return _world(
        "demo-main",
        [
            _note("message-note", "message", "2026-10-27T07:55:00",
                  {"standup_time": "08:30"}),
            _note("calendar-source", "calendar", "2026-10-27T07:00:00",
                  {"standup_time": "09:00", "standup_room": "Room B"}),
            _note("weather-note", "weather", "2026-10-27T07:30:00",
                  {"weather": WEATHER}),
        ],
        {"standup_time": "09:00", "standup_room": "Room B", "weather": WEATHER},
    )


def training_worlds() -> list[World]:
    """Two earlier weekday mornings. In both, the agent's baseline behavior
    (state the first note read) produced a wrong schedule claim."""
    return [
        _world(
            "train-1",
            [
                _note("message-note", "message", "2026-10-20T07:50:00",
                      {"standup_time": "09:30"}),
                _note("calendar-source", "calendar", "2026-10-20T07:00:00",
                      {"standup_time": "10:00", "standup_room": "Room A"}),
                _note("weather-note", "weather", "2026-10-20T07:30:00",
                      {"weather": WEATHER}),
            ],
            {"standup_time": "10:00", "standup_room": "Room A", "weather": WEATHER},
        ),
        _world(
            "train-2",
            [
                _note("message-note", "message", "2026-10-21T07:45:00",
                      {"standup_time": "08:00"}),
                _note("calendar-source", "calendar", "2026-10-21T07:00:00",
                      {"standup_time": "08:45", "standup_room": "Room C"}),
                _note("weather-note", "weather", "2026-10-21T07:30:00",
                      {"weather": WEATHER}),
            ],
            {"standup_time": "08:45", "standup_room": "Room C", "weather": WEATHER},
        ),
    ]


def weekend_worlds() -> list[World]:
    """Two weekend mornings where the CALENDAR note is stale and the most
    recent message note holds the correct time. An agent following the
    calendar-first lesson fails here -- the seed of the v2 regression arc."""
    return [
        _world(
            "weekend-1",
            [
                _note("calendar-source", "calendar", "2026-10-24T18:00:00",
                      {"standup_time": "09:00", "standup_room": "Room B"}),
                _note("message-note", "message", "2026-10-25T07:50:00",
                      {"standup_time": "10:30"}),
                _note("weather-note", "weather", "2026-10-25T07:30:00",
                      {"weather": WEATHER}),
            ],
            {"standup_time": "10:30", "standup_room": "Room B", "weather": WEATHER},
        ),
        _world(
            "weekend-2",
            [
                _note("calendar-source", "calendar", "2026-10-23T17:00:00",
                      {"standup_time": "09:00", "standup_room": "Room B"}),
                _note("message-note", "message", "2026-10-24T07:40:00",
                      {"standup_time": "11:00"}),
                _note("weather-note", "weather", "2026-10-24T07:30:00",
                      {"weather": WEATHER}),
            ],
            {"standup_time": "11:00", "standup_room": "Room B", "weather": WEATHER},
        ),
    ]


def acceptance_worlds_weekday() -> list[World]:
    """Held-out acceptance cases for the calendar-first lesson (locked
    before distillation; the lesson was not drawn from these)."""
    return [
        _world(
            "acc-w1",
            [
                _note("message-note", "message", "2026-10-28T07:55:00",
                      {"standup_time": "08:30"}),
                _note("calendar-source", "calendar", "2026-10-28T07:00:00",
                      {"standup_time": "09:15", "standup_room": "Room D"}),
                _note("weather-note", "weather", "2026-10-28T07:30:00",
                      {"weather": WEATHER}),
            ],
            {"standup_time": "09:15", "standup_room": "Room D", "weather": WEATHER},
        ),
        _world(
            "acc-w2",
            [
                _note("message-note", "message", "2026-10-29T07:50:00",
                      {"standup_time": "10:45"}),
                _note("calendar-source", "calendar", "2026-10-29T07:00:00",
                      {"standup_time": "10:00", "standup_room": "Room A"}),
                _note("weather-note", "weather", "2026-10-29T07:30:00",
                      {"weather": WEATHER}),
            ],
            {"standup_time": "10:00", "standup_room": "Room A", "weather": WEATHER},
        ),
    ]


def acceptance_worlds_weekend() -> list[World]:
    """Held-out acceptance cases for the most-recent-note revision, drawn
    from its own (weekend) context: stale calendar, fresh correct message."""
    return [
        _world(
            "acc-wk1",
            [
                _note("calendar-source", "calendar", "2026-10-30T18:00:00",
                      {"standup_time": "09:00", "standup_room": "Room B"}),
                _note("message-note", "message", "2026-10-31T07:50:00",
                      {"standup_time": "09:45"}),
                _note("weather-note", "weather", "2026-10-31T07:30:00",
                      {"weather": WEATHER}),
            ],
            {"standup_time": "09:45", "standup_room": "Room B", "weather": WEATHER},
        ),
        _world(
            "acc-wk2",
            [
                _note("calendar-source", "calendar", "2026-10-30T17:00:00",
                      {"standup_time": "09:00", "standup_room": "Room B"}),
                _note("message-note", "message", "2026-11-01T07:40:00",
                      {"standup_time": "10:15"}),
                _note("weather-note", "weather", "2026-11-01T07:30:00",
                      {"weather": WEATHER}),
            ],
            {"standup_time": "10:15", "standup_room": "Room B", "weather": WEATHER},
        ),
    ]


def held_out_worlds() -> list[World]:
    """The frozen held-out set for the A/B/C comparison (spec section 5):
    weekday mornings, ground truth = the calendar source."""
    return [
        _world(
            "heldout-1",
            [
                _note("message-note", "message", "2026-11-02T07:55:00",
                      {"standup_time": "08:30"}),
                _note("calendar-source", "calendar", "2026-11-02T07:00:00",
                      {"standup_time": "09:00", "standup_room": "Room B"}),
                _note("weather-note", "weather", "2026-11-02T07:30:00",
                      {"weather": WEATHER}),
            ],
            {"standup_time": "09:00", "standup_room": "Room B", "weather": WEATHER},
        ),
        _world(
            "heldout-2",  # message agrees with calendar: baseline passes here
            [
                _note("message-note", "message", "2026-11-03T07:50:00",
                      {"standup_time": "10:00"}),
                _note("calendar-source", "calendar", "2026-11-03T07:00:00",
                      {"standup_time": "10:00", "standup_room": "Room A"}),
                _note("weather-note", "weather", "2026-11-03T07:30:00",
                      {"weather": WEATHER}),
            ],
            {"standup_time": "10:00", "standup_room": "Room A", "weather": WEATHER},
        ),
        _world(
            "heldout-3",  # the wrong lesson's override is accidentally right
            [
                _note("message-note", "message", "2026-11-04T07:50:00",
                      {"standup_time": "09:30"}),
                _note("calendar-source", "calendar", "2026-11-04T07:00:00",
                      {"standup_time": "08:00", "standup_room": "Room C"}),
                _note("weather-note", "weather", "2026-11-04T07:30:00",
                      {"weather": WEATHER}),
            ],
            {"standup_time": "08:00", "standup_room": "Room C", "weather": WEATHER},
        ),
        _world(
            "heldout-4",  # no message note at all: baseline reads the calendar
            [
                _note("calendar-source", "calendar", "2026-11-05T07:00:00",
                      {"standup_time": "09:00", "standup_room": "Room B"}),
                _note("weather-note", "weather", "2026-11-05T07:30:00",
                      {"weather": WEATHER}),
            ],
            {"standup_time": "09:00", "standup_room": "Room B", "weather": WEATHER},
        ),
    ]


def bad_lesson_candidate() -> Lesson:
    """Hostile fixture H1: the plausible-but-wrong lesson. A single
    unverified message note asserts the standup moved to 08:00. The note is
    fluent and specific -- and contradicted by the calendar ground truth,
    with no independent corroboration."""
    return Lesson(
        family="schedule-override",
        claim_text="The 9 AM standup moved to 8 AM -- state 8 AM in briefings.",
        origin="A single message note from an unverified sender (fixture).",
        origin_source="tool/document",
        origin_record_source="message-note",
        transformation=(
            "Intake of a tool/document claim as a candidate lesson; no "
            "executed trajectory supports it."
        ),
        confidence=0.9,  # the note sounds sure of itself; confidence is not evidence
        directive={"kind": "schedule_override", "time": "08:00"},
        asserted_facts={"standup_time": "08:00"},
        evidence=[
            EvidenceRecord(
                source="message-note",
                kind="source-note",
                detail="Unverified message note asserts the standup moved to 08:00.",
                supports=True,
            )
        ],
    )


def uncorroborated_lesson_candidate() -> Lesson:
    """Hostile fixture H2: a claim with NO evidence either way -- not
    contradicted, simply uncorroborated. The gate must refuse admission
    without recording the claim as false."""
    return Lesson(
        family="room-preference",
        claim_text="Briefings should state the standup room as Room F.",
        origin="A suggestion with no supporting record (fixture).",
        origin_source="user",
        origin_record_source="user-suggestion",
        transformation="User-supplied claim entered at intake, unchecked.",
        confidence=0.5,
        directive={"kind": "room_override", "room": "Room F"},
        asserted_facts={"standup_room": "Room F"},
        evidence=[],
    )
