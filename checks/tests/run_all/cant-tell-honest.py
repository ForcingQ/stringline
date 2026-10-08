"""A fixture check for run_all's self-test: it cannot look, says so, and exits 2."""
import sys
print("CAN'T TELL: the fixture could not look")
sys.exit(2)
