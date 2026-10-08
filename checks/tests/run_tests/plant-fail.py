"""A fixture test for the runner's self-test. It answers --selftest; it fails."""
import sys
print("fixture case: one check, not as expected")
print("selftest: FAIL")
sys.exit(1)
