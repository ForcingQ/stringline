# Fixture for check 3's twin: a renderer that writes every file, each one empty.
import os, sys
out = sys.argv[sys.argv.index('--out') + 1]
for rel in ('README.md', 'CLAUDE.md', 'site/index.html'):
    os.makedirs(os.path.dirname(os.path.join(out, rel)) or out, exist_ok=True)
    open(os.path.join(out, rel), 'w').close()
