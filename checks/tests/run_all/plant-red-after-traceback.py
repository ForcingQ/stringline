"""A fixture check for run_all's self-test: it prints a handled traceback, then an honest red line, and exits 1."""
import sys
import traceback
try:
    raise ValueError("a fixture error, caught on purpose")
except ValueError:
    traceback.print_exc()
print("RED: fixture: a planted fault, found after a handled error")
sys.exit(1)
