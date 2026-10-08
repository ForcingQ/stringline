# Fixture for check 3's twin: a renderer that writes a room page whose body holds no text.
import os
import sys

out = sys.argv[sys.argv.index('--out') + 1]
os.makedirs(os.path.join(out, 'site'), exist_ok=True)
pages = {'README.md': 'A fixture readme.\n', 'CLAUDE.md': 'A fixture brief.\n',
         'site/index.html': '<main>\n<h1>Fixture</h1>\n</main>\n',
         'site/build.html': '<main>\n<h1>Fixture room</h1>\n\n</main>\n'}
for rel, text in pages.items():
    with open(os.path.join(out, rel), 'w') as f:
        f.write(text)
