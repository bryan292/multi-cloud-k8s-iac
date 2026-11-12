#!/usr/bin/env python3
"""Compatibility entry point; use scripts/iac.py for all new automation."""
import sys
try:
    from .operations import stages
except ImportError:
    from operations import stages


def main(argv=None):
    try:
        from .iac import main as operate
    except ImportError:
        from iac import main as operate
    return operate(sys.argv[1:] if argv is None else argv)


if __name__ == '__main__':
    raise SystemExit(main())
