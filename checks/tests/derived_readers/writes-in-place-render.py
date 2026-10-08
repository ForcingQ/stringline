# Fixture for check 3's first break: a renderer that writes to its --out folder AND in place.
# The self-test keeps the real renderer beside it as render.py.kept and runs it both ways.
import os
import subprocess
import sys

real = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'render.py.kept')
for args in (sys.argv[1:], []):
    subprocess.run([sys.executable, real] + args, check=True, capture_output=True)
