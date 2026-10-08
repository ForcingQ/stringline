"""A fixture test for the runner's self-test. It answers --selftest; it prints a handled traceback, carries on, and fails honestly."""
import sys
import traceback
try:
    raise ValueError("a fixture error, caught on purpose")
except ValueError:
    traceback.print_exc()
print("fixture: handled the error above and carried on", file=sys.stderr)
print("fixture case: one check, not as expected")
print("selftest: FAIL")
sys.exit(1)
