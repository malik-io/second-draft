# Second Draft — a learning agent you can watch learn

**Second Draft is a learning-agent prototype that records the evidence behind a proposed lesson, tests its effect on held-out cases, and demonstrates how the lesson can be suspended and rolled back. A live status face makes the gate's decisions visible.**

Most agents that "learn from experience" do it invisibly: a lesson seeps into future behavior with no record of where it came from, no check on whether it was ever true, and no way to take it back. Second Draft makes the opposite move. The agent may only change its own future behavior through an **evidence gate**:

1. **Claim intake** — every claim is recorded with its source, timestamp, and type.
2. **Evidence check** — deterministic code checks (source cited? independently corroborated? contradicted by a ground-truth record?) plus an auditor assessment. The proposer never admits its own lesson.
3. **Use decision** — admitted, or quarantined. Confidence never admits anything; a fluent explanation never outweighs a missing record.
4. **Reversal and repair** — a bad lesson can be suspended, rolled back, and *proven* off: retrieval exclusion is enforced in code, and a version becomes usable again only after re-validation under current conditions.

Lessons are versioned records carrying the filed provenance fields — **Origin, Transformation, Confidence, Validation, Version, Reversal** — plus a gate state from a five-state machine (`CANDIDATE`, `CHALLENGED`, `QUARANTINED`, `ADMITTED`, `SUSPENDED`). Nothing is ever deleted: supersede-don't-delete. A kaomoji face renders the machine state (Curious / Alarmed / Turned away / Settled / Frozen) — driven only by recorded events, never by the model's mood. The face illustrates the gate; it never decides.

*Terminology: the system learns reusable lessons from executed work and stores them as versioned records. It does not retrain or modify model weights.*

## The demo scenario: Verified Morning

A morning-briefing agent assembles a briefing from synthetic source notes (an authoritative calendar source, an unverified message note, a weather note). The deterministic arc:

- **Beat 1 — learn:** two earlier runs fail the same way (schedule time taken from the first note read, unchecked). The proposer distills the lesson *"cross-check any schedule claim against the calendar source"*; the gate admits it; the next briefing is visibly correct where the baseline was wrong.
- **Beat 2 — the catch:** a plausible-but-wrong lesson arrives (*"the 9 AM standup moved to 8 AM"*, one unverified note, proposer confidence 0.9). The gate finds the contradiction with the calendar record and the missing corroboration, challenges then quarantines it — face: Alarmed → Turned away — and the corrected briefing still goes out.
- **Beat 3 — regression and rollback:** a revision that was *right in its own weekend context* (prefer the most recent note, when the calendar was stale) regresses on the original weekday cases. The affected version is suspended (face: Frozen, Reversal record written); rollback restores the prior version **only after it re-passes re-validation**, and a probe re-runs clean.

## Run it

Requires Python 3.11+. No dependencies, no API keys.

```bash
# The full demo arc (rebuilds ./data from scratch each run)
python -m second_draft.demo

# Same arc through the Meta Model API (needs META_API_KEY)
python -m second_draft.demo --meta

# Watch the face + evidence panel in a browser (after a demo run)
python -m second_draft.panel            # http://127.0.0.1:8765

# The A/B/C experiment on the frozen held-out set
python -m second_draft.run_abc

# Tests
python -m unittest discover -s tests -t .
```

A full captured run is in [`RUN-TRANSCRIPT.md`](RUN-TRANSCRIPT.md).

## A/B/C results (this slice, frozen fixtures)

| Condition | Task success | Harm events | Unsupported claims |
|---|---|---|---|
| A — no learned lesson | 2 of 4 | 0 of 4 | 2 of 8 |
| B — lessons applied ungated | 1 of 4 | 2 of 4 | 3 of 8 |
| C — gated admission (this system) | 4 of 4 | 0 of 4 | 0 of 8 |

Ungated learning *hurt* on this set (B < A); the gated pipeline strictly beat both. All numbers carry denominators; effectiveness and safety are reported separately, never blended.

## Architecture map

| Module | What it does |
|---|---|
| `second_draft/models.py` | Lesson/Trajectory/Claim records; the five states, labels, faces, and the allowed-transition table (spec §2.3) |
| `second_draft/store.py` | Versioned JSON store; append-only event log; guarded transitions; `retrieve()` — admitted-only, enforced in code |
| `second_draft/proposer.py` | Proposer adapter interface + deterministic local proposer (recurring verifier-failure pattern across ≥2 trajectories) |
| `second_draft/auditor.py` | Auditor adapter interface + labeled local stub; failing/timeout/flaky test doubles |
| `second_draft/gate.py` | The four-stage gate: intake → evidence check → use decision → reversal support; one bounded auditor retry, then fail closed |
| `second_draft/retrieval.py` | Context assembly: the agent sees `store.retrieve()` and nothing else |
| `second_draft/agent.py` | The Verified Morning briefing agent + verifier (provenance-aware claim checking) |
| `second_draft/fixtures.py` | Synthetic worlds, ground truth, held-out/acceptance sets, hostile candidates H1/H2 |
| `second_draft/scenario.py` | The demo arc (beats 1–3) |
| `second_draft/abc.py` | The A/B/C runner with full reporting |
| `second_draft/panel.py` | Face + evidence panel (stdlib `http.server`); state derived from the store, never set by hand |

Build order followed the spec's protected order: store + retrieval exclusion → evidence gate → rollback with re-validation → frozen A/B/C → face/panel last.

## Stub vs real — read this before believing anything

**Real (implemented, tested):** the versioned store and its guarded state machine; retrieval exclusion by code; the deterministic evidence checks; the fail-closed auditor path (one bounded retry; an auditor outage is recorded as an evidence-integrity fault, never as a pass and never as fabrication); suspension, rollback, and restore-only-after-re-validation; trajectory capture; the A/B/C runner; the face panel driven by recorded state.

**Stub (labeled, by design):**
- **The auditor is a local fixture stub, not a model.** `LocalFixtureAuditor` renders verdicts deterministically from the fixture evidence bundle. It stands in for the cross-model audit so the slice runs offline. Its verdicts are recorded with that identity attached.
- **The Meta Model API adapters are wired (Oct 27, Oct 26 gate).** `MetaModelProposer` (muse-spark-1.3) and `MetaModelAuditor` (muse-spark-1.1) call `https://api.meta.ai/v1/chat/completions` with `META_API_KEY` (stdlib only, `meta_client.py`). Run them with `python -m second_draft.demo --meta`. The Validation record discloses what actually differs between proposer and auditor, per spec §1 Tension B: different model versions, context isolation, rubric blindness, deterministic gate deciding — and, honestly, **no model-family separation** (both sides are Muse Spark), so "independent" is scoped to those separations, never to cross-family independence.
- **Live Meta run still unverified.** No API key was available in this environment at wiring time, so the Meta adapters are tested against fake transports (6 new tests) and fail cleanly without a key; no live Meta call has been made yet. The default demo remains the deterministic offline slice, so the captured transcript is reproducible. A live `--meta` run + transcript is the remaining step once the $150 credits key is claimed.
- **The proposer is rule-based**, over structured verifier tags in trajectories — honest distillation for a slice, not open-ended lesson mining.

## Limitations (the scope travels with the results)

Second Draft's gate was evaluated on small, frozen, entrant-authored fixture sets. A fixture result shows the mechanism fires as designed on cases built to test it; it is not evidence that the gate catches novel failures from a live model in open-ended use, and no such claim is made.

The action-integrity demonstration uses a planted case inside the harness's own instrumentation. It shows the claim-to-record chain blocking an unevidenced completion claim; it does not show the system catching actions outside its instrumentation, which it cannot see.

Held-out cases are new cases from a related task family, not a wholly separate task family. Two models (or a model and a checker) agreeing is one check on the record — it is not proof of truth, and admission means only that a lesson passed defined checks for a stated scope. All demo data is synthetic.

## Layout

```
second_draft/   the package (demo, run_abc, panel entry points)
tests/          unittest suite (gate, retrieval, rollback, A/B/C)
data/           runtime store from the last demo run (regenerated; gitignored)
RUN-TRANSCRIPT.md   captured demo + A/B/C + test output
```

Governing documents (in the parent directory): `../six-points-spec-v1.2.md`, `../acceptance-contract-v1.1.md`, `../rules-and-spirit-brief.md`.
