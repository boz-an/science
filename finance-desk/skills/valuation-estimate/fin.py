#!/usr/bin/env python3
"""Shim that runs the shared finance-desk engine at the plugin root.

Resolves symlinks, so it works whether this skill folder was installed as part
of the plugin or symlinked into ~/.claude/skills by install.sh.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
sys.path.insert(0, ROOT)

from finskills.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
