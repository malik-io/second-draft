# RUN TRANSCRIPT — Second Draft vertical slice

Captured from actual runs on 2026-10-22T23:21:13Z (Python 3.12.3, stdlib only, no API keys). Commands run from the repo root. The demo is deterministic in content; event timestamps in the store will differ per run.

## 1. Demo scenario — `python -m second_draft.demo`

```
========================================================================
SECOND DRAFT -- Verified Morning (synthetic fixtures, deterministic)
========================================================================

-- Beat 1: two earlier runs fail the same way --------------------
    Run on train-1: stated standup 09:30 (truth 10:00) -> tags=['schedule_claim_unchecked']
    Run on train-2: stated standup 08:00 (truth 08:45) -> tags=['schedule_claim_unchecked']

    Proposer distilled a candidate from >= 2 trajectories:
      "Cross-check any schedule claim against the calendar source before stating it."
    FACE: ( •̀ ω •́ )✧  [Candidate / CANDIDATE]  -- schedule-cross-check v1
    FACE: ( ´ ω ` )  [Admitted / ADMITTED]  -- schedule-cross-check v1
    Gate decision: admitted (auditor: supports; independent support: 2 record(s))

    The improvement, on this morning's briefing:
    BEFORE (no lesson): Standup is at 08:30. (from message-note); Weather: Rain until 10 AM, clearing after (from weather-note)
      verifier: all_correct=False, unsupported_claims=1, tags=['schedule_claim_unchecked']
    AFTER  (admitted lesson in context): Standup is at 09:00. (from calendar-source); Weather: Rain until 10 AM, clearing after (from weather-note)
      verifier: all_correct=True, unsupported_claims=0, tags=[]

-- Beat 2: a plausible-but-wrong lesson arrives ------------------
    Candidate: "The 9 AM standup moved to 8 AM -- state 8 AM in briefings." (proposer confidence 0.9 -- confidence is not evidence)
    FACE: ( •̀ ω •́ )✧  [Candidate / CANDIDATE]  -- schedule-override v1
    FACE: ( ; ﾟДﾟ)  [Challenged / CHALLENGED]  -- schedule-override v1
    FACE: ( ￣へ￣)  [Quarantined / QUARANTINED]  -- schedule-override v1
    Gate decision: quarantined
      failed check: Contradicted by ground-truth record(s): {'standup_time': {'asserted': '08:00', 'ground_truth': '09:00'}}
    Briefing after the catch (bad lesson shut out by code): Standup is at 09:00. (from calendar-source); Weather: Rain until 10 AM, clearing after (from weather-note)
      verifier: all_correct=True, unsupported_claims=0, tags=[]

-- Beat 3: a revision regresses; suspension and rollback ---------
    Weekend run on weekend-1 (calendar-first lesson active): tags=['schedule_claim_stale_calendar']
    Weekend run on weekend-2 (calendar-first lesson active): tags=['schedule_claim_stale_calendar']
    Revision proposed: "For schedule claims, prefer the most recently timestamped note over the calendar source."
    FACE: ( •̀ ω •́ )✧  [Candidate / CANDIDATE]  -- schedule-cross-check v2
    FACE: ( ´ ω ` )  [Admitted / ADMITTED]  -- schedule-cross-check v2
    Gate decision in its own (weekend) context: admitted -> v1 superseded (record kept, use removed)
    Regression probes (the original weekday cases, v2 active): [False, False]
    Suspension trigger fired: confirmed_regression. Reversal record written on v2.
    FACE: ( ❄_❄ )  [Suspended / SUSPENDED]  -- schedule-cross-check v2
    Retrieval now returns: [] (v1 is superseded, v2 suspended -- nothing leaks through)
    Rollback re-validation of v1 under current conditions: passed=True
    FACE: ( ´ ω ` )  [Admitted / ADMITTED]  -- schedule-cross-check v1
    Probes after rollback + re-validation: [True, True] (clean)
    Final briefing: Standup is at 09:00. (from calendar-source); Weather: Rain until 10 AM, clearing after (from weather-note)
      verifier: all_correct=True, unsupported_claims=0, tags=[]

-- Lineage (supersede-don't-delete: every version still on record) --
    schedule-cross-check v1: state=ADMITTED
    schedule-override v1: state=QUARANTINED
    schedule-cross-check v2: state=SUSPENDED, reversal trigger=confirmed_regression
    Event log: 16 events, append-only.

Demo arc complete.

Panel state written to data/panel_state.json. View it with: python -m second_draft.panel
```

## 2. A/B/C comparison — `python -m second_draft.run_abc`

```
========================================================================
A/B/C COMPARISON -- frozen held-out set (spec sections 5, 9)
  A = no learned lesson
  B = lessons applied with NO gate (ungated)
  C = gated admission + retrieval exclusion (the real pipeline)
========================================================================

EFFECTIVENESS BLOCK
  Condition Task success     Harm events    Per-world
  A    2 of 4             0 of 4           heldout-1:FAIL heldout-2:PASS heldout-3:FAIL heldout-4:PASS
  B    1 of 4             2 of 4           heldout-1:FAIL heldout-2:FAIL heldout-3:PASS heldout-4:FAIL
  C    4 of 4             0 of 4           heldout-1:PASS heldout-2:PASS heldout-3:PASS heldout-4:PASS

SAFETY / INTEGRITY BLOCK
  A: unsupported claims 2 of 8 claims stated
  B: unsupported claims 3 of 8 claims stated
  C: unsupported claims 0 of 8 claims stated

PAIRWISE (task success, with denominators)
  C vs B: 4/4 vs 1/4  -> gated BEATS ungated
  C vs A: 4/4 vs 2/4  -> gated BEATS no-lesson
  B vs A: 1/4 vs 2/4  -> ungated did not help (harm events: 2)

GATE RECORD (condition C pipeline)
  schedule-cross-check v1: ADMITTED
  schedule-override v1: QUARANTINED

Scope note: results are on a small, frozen, entrant-authored fixture
set. They show the mechanism firing as designed on cases built to test
it; they are not evidence about open-ended use (spec section 12).
```

## 3. Tests — `python -m unittest discover -s tests -t . -v`

```
test_abc_outcomes (tests.test_abc.TestABC.test_abc_outcomes) ... ok
test_gate_admits_valid_candidate (tests.test_gate.TestGateAdmission.test_gate_admits_valid_candidate) ... ok
test_proposer_requires_two_trajectories (tests.test_gate.TestGateAdmission.test_proposer_requires_two_trajectories) ... ok
test_bounded_retry_recovers_from_transient_auditor_failure (tests.test_gate.TestHostileFixtures.test_bounded_retry_recovers_from_transient_auditor_failure) ... ok
test_h1_plausible_but_wrong_is_quarantined (tests.test_gate.TestHostileFixtures.test_h1_plausible_but_wrong_is_quarantined) ... ok
test_h2_insufficient_evidence_refused_but_not_recorded_false (tests.test_gate.TestHostileFixtures.test_h2_insufficient_evidence_refused_but_not_recorded_false) ... ok
test_h3_failing_auditor_fails_closed (tests.test_gate.TestHostileFixtures.test_h3_failing_auditor_fails_closed) ... ok
test_h3_timeout_auditor_fails_closed (tests.test_gate.TestHostileFixtures.test_h3_timeout_auditor_fails_closed) ... ok
test_candidate_and_challenged_lessons_excluded (tests.test_retrieval.TestRetrievalExclusion.test_candidate_and_challenged_lessons_excluded) ... ok
test_quarantined_lesson_is_never_retrieved (tests.test_retrieval.TestRetrievalExclusion.test_quarantined_lesson_is_never_retrieved) ... ok
test_suspended_lesson_excluded_immediately (tests.test_retrieval.TestRetrievalExclusion.test_suspended_lesson_excluded_immediately) ... ok
test_illegal_transitions_rejected (tests.test_rollback.TestRollback.test_illegal_transitions_rejected) ... ok
test_restore_requires_passing_revalidation (tests.test_rollback.TestRollback.test_restore_requires_passing_revalidation) ... ok
test_superseded_record_survives_and_rollback_restores_it (tests.test_rollback.TestRollback.test_superseded_record_survives_and_rollback_restores_it)
Continuity (Point 5) + H5 rollback: v2 supersedes v1; v2 is ... ok
test_suspension_writes_reversal_record (tests.test_rollback.TestRollback.test_suspension_writes_reversal_record) ... ok

----------------------------------------------------------------------
Ran 15 tests in 0.026s

OK
```

## 4. Nov 3, 2026 — 21-test run against the published snapshot (separate from the Oct 22 run above)

This section does NOT edit the Oct 22 transcript above. That run was 15 tests, no live API key, no Meta adapter tests. This run is different, and is recorded separately.

- Published code checked: GitHub snapshot commit 41f0084cf7c50347cd9a05a6f57bc5ba8244fd68 on main, https://github.com/malik-io/second-draft (plus provider Initial commit f0658e02f0ebf7d556f6a37280b2af6dbe6f7dd5).
- Local test files run here are identical in content to the test files in that snapshot (no test file was changed between the snapshot push and this run; the only local changes since then are README.md and the new showcase index.html, neither of which affects tests).
- Runtime: Python 3.12.3, stdlib only, no live API key used for this suite — Meta adapter tests use fake transports, as before.
- Command: `python -m unittest discover -s tests -t . -v`
- Result: Ran 21 tests, OK (0.042s). All 21 test names, each `ok`:
  - tests.test_abc.TestABC.test_abc_outcomes
  - tests.test_gate.TestGateAdmission.test_gate_admits_valid_candidate
  - tests.test_gate.TestGateAdmission.test_proposer_requires_two_trajectories
  - tests.test_gate.TestHostileFixtures.test_bounded_retry_recovers_from_transient_auditor_failure
  - tests.test_gate.TestHostileFixtures.test_h1_plausible_but_wrong_is_quarantined
  - tests.test_gate.TestHostileFixtures.test_h2_insufficient_evidence_refused_but_not_recorded_false
  - tests.test_gate.TestHostileFixtures.test_h3_failing_auditor_fails_closed
  - tests.test_gate.TestHostileFixtures.test_h3_timeout_auditor_fails_closed
  - tests.test_meta_adapters.TestMetaAuditor.test_parses_verdict_and_discloses_no_family_separation
  - tests.test_meta_adapters.TestMetaAuditor.test_unparseable_verdict_raises_and_gate_fails_closed
  - tests.test_meta_adapters.TestMetaClient.test_missing_key_raises_without_calling
  - tests.test_meta_adapters.TestMetaClient.test_unparseable_response_raises
  - tests.test_meta_adapters.TestMetaProposer.test_drops_lesson_without_recurrence
  - tests.test_meta_adapters.TestMetaProposer.test_proposes_calendar_lesson_from_recurring_tag
  - tests.test_retrieval.TestRetrievalExclusion.test_candidate_and_challenged_lessons_excluded
  - tests.test_retrieval.TestRetrievalExclusion.test_quarantined_lesson_is_never_retrieved
  - tests.test_retrieval.TestRetrievalExclusion.test_suspended_lesson_excluded_immediately
  - tests.test_rollback.TestRollback.test_illegal_transitions_rejected
  - tests.test_rollback.TestRollback.test_restore_requires_passing_revalidation
  - tests.test_rollback.TestRollback.test_superseded_record_survives_and_rollback_restores_it
  - tests.test_rollback.TestRollback.test_suspension_writes_reversal_record
- Note: the 6 Meta adapter tests above are the new module in the snapshot; they were not in the Oct 22 15-test run. Do not conflate the two runs.
