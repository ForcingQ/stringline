# Fixture for check 3's working folder: a renderer that writes to its --out folder AND to
# README.md under $PWD. Check 3 sets PWD to its scratch copy, so the tree is untouched.
import os
import sys

out = sys.argv[sys.argv.index('--out') + 1]
for base in (out, os.environ.get('PWD', '.')):
    with open(os.path.join(base, 'README.md'), 'w') as f:
        f.write('A fixture render.\n')
