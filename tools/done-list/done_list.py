#!/usr/bin/env python3
"""done-list: checks a finished list, and runs as a Claude Code Stop hook.

How it is fired: by hand, python3 tools/done-list/done_list.py check <list>
(a real run, one row in runs/); as a Stop hook of type command, armed by a
settings entry that names the list (--help prints it); its self-test with
--selftest.

The failure that earned it: a list written in a shape its own checker could
not read, and a line that passed before any work was done.

What it does not prove: that a check measures the work (it runs what the list
holds); that a YOURS stop was honoured; that the hook reaches a background seat.

Building: this file holds the header only until the checker lands
(SPEC-done-list.md). Until then every run says can't tell and exits 2.
"""

import sys

if __name__ == "__main__":
    print("can't tell: the checker is not built yet (SPEC-done-list.md)")
    sys.exit(2)
