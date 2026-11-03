"""A/B/C entry point:  python -m second_draft.run_abc"""

from __future__ import annotations

from .abc import format_report, run_abc


def main() -> None:
    print(format_report(run_abc()))


if __name__ == "__main__":
    main()
