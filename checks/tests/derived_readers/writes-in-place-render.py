# Fixture for check 3's first break: a renderer that writes to its --out folder AND in place,
# into the folder it was run from. Check 3 runs it from a scratch copy, so the tree is untouched.
import os
import sys

out = sys.argv[sys.argv.index('--out') + 1]
for base in (out, os.path.dirname(os.path.abspath(__file__))):
    with open(os.path.join(base, 'README.md'), 'w') as f:
        f.write('A fixture render.\n')
