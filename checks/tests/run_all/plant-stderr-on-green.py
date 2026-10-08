"""A fixture check for run_all's self-test: it prints green and exits 0, with a warning on standard error."""
import sys
print("GREEN · read 1 fixture · against nothing real")
print("warning: the fixture check could not finish reading", file=sys.stderr)
