#!/usr/bin/env python3
"""finance-desk command line. Run `python3 fin.py --help`."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))

from finskills.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
