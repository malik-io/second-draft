"""Demo entry point:  python -m second_draft.demo [--data data] [--meta]

Runs the full Verified Morning arc end-to-end and writes the panel state
to data/panel_state.json (serve it with: python -m second_draft.panel).

Default mode is the deterministic offline slice (DeterministicProposer +
LocalFixtureAuditor), so the transcript is reproducible. --meta runs the
same arc through the Meta Model API proposer/auditor (requires
META_API_KEY); without a key it exits with a clear error, it never
silently falls back to the stub.
"""

from __future__ import annotations

import argparse
import sys

from .meta_client import MetaApiError
from .panel import DEFAULT_STATE_PATH
from .scenario import run_demo


def main() -> None:
    ap = argparse.ArgumentParser(description="Second Draft -- Verified Morning demo")
    ap.add_argument("--data", default="data",
                    help="store directory (rebuilt from scratch each run)")
    ap.add_argument("--panel-state", default=DEFAULT_STATE_PATH)
    ap.add_argument("--meta", action="store_true",
                    help="use the Meta Model API proposer/auditor (needs META_API_KEY)")
    args = ap.parse_args()
    kwargs = {}
    if args.meta:
        from .auditor import MetaModelAuditor
        from .proposer import MetaModelProposer

        kwargs["proposer"] = MetaModelProposer()
        kwargs["auditor"] = MetaModelAuditor()
    try:
        run_demo(args.data, panel_path=args.panel_state, **kwargs)
    except MetaApiError as exc:
        print(f"Meta mode unavailable: {exc}", file=sys.stderr)
        sys.exit(2)
    print(f"\nPanel state written to {args.panel_state}. "
          f"View it with: python -m second_draft.panel")


if __name__ == "__main__":
    main()
