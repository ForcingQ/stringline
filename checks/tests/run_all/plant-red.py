"""A fixture check for run_all's self-test: red, and its exit code agrees."""
import sys
print("RED: fixture: a planted fault")
sys.exit(1)
