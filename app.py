"""Compatibility import and executable entry point for NightWire."""

from __future__ import annotations

import sys

from nightwire.app import runtime as _runtime


if __name__ == "__main__":
    _runtime.main()
else:
    # Preserve ``import app`` mutation/monkeypatch behavior during the package migration.
    sys.modules[__name__] = _runtime
