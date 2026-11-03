"""Context assembly / retrieval.

The agent's context is assembled from store.retrieve() and NOTHING else:
only ADMITTED, non-superseded lessons can influence the agent. Exclusion
of quarantined/suspended lessons is a code property of the store, not a
prompt instruction (spec 2.6 step 1 -- the load-bearing piece).
"""

from __future__ import annotations

from .models import Lesson
from .store import Store


def build_context(store: Store) -> list[Lesson]:
    """Return the lessons the agent may use right now."""
    return store.retrieve()


def context_summary(store: Store) -> dict[str, list[str]]:
    """Human-readable split of what is in context vs shut out, for the
    evidence panel."""
    active = [f"{l.family} v{l.version}" for l in store.retrieve()]
    shut_out = [
        f"{l.family} v{l.version} ({l.state.value}"
        + (", superseded)" if l.superseded_by is not None and l.state.value == "ADMITTED" else ")")
        for l in store.all_lessons()
        if not l.is_retrievable()
    ]
    return {"in_context": active, "shut_out": shut_out}
