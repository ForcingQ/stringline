# Fixture for check 3's can't-tell line: a renderer that crashes with an absolute path in its
# message. Check 3 must cut the path to its last component before printing.
import os

raise RuntimeError(f'fixture crash in {os.path.abspath(__file__)}')
