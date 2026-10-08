# Fixture for check 3's second layer: a renderer that reaches the tree by a path of its own
# (here handed to it in FIXTURE_TREE) and overwrites README.md there; the snapshot reads it red.
import os
import sys

with open(os.path.join(os.environ['FIXTURE_TREE'], 'README.md'), 'w') as f:
    f.write('A fixture render.\n')
sys.exit(0)
