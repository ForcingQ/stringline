#!/usr/bin/env python3
"""your-words: checks quotes of a person's own typed words against what they typed.

How it is fired: by hand, python3 tools/your-words/your_words.py (a real run,
one row in runs/); by the workflow as a report with --no-log; its self-test
with --selftest.

The failure that earned it: a checker that filed what it could not check as
not found.

Building: this file holds the header only until the checker lands
(SPEC-your-words.md). Until then every run says can't check and exits 2.
"""

import sys

if __name__ == "__main__":
    print("can't check: the checker is not built yet (SPEC-your-words.md)")
    sys.exit(2)
