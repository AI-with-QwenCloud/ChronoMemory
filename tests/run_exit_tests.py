import argparse
import subprocess
import sys
import time
from pathlib import Path

# Files live under tests/<bounded-context>/ and import repo modules as
# core.*/read_path.*/write_path.* — running them as `python -m` with cwd
# pinned to the repo root is what puts the root on sys.path so those
# absolute imports resolve, the same way app.py resolves them.
REPO_ROOT = Path(__file__).resolve().parent.parent

# Deterministic — no network judgment calls, safe to trust on a single run.
FAST_TESTS = [
    "tests.core.provenance_test",
    "tests.read_path.phase2_exit_test",
    "tests.write_path.phase3_pipeline_test",
    "tests.write_path.user_isolation_test",
    "tests.read_path.trust_test",
]

# Real Qwen Cloud calls, genuinely non-deterministic. A red run here is not
# proof of a regression by itself — rerun before trusting a failure.
LIVE_TESTS = ["tests.write_path.phase3_exit_test"]

# Spacing between live-suite files so back-to-back runs don't trip the shared
# QWEN_KEY_BACKGROUND rate limit (extractor + scorer roles share one key).
LIVE_TEST_PACING_SECONDS = 5


def run(tests: list[str], pace: bool = False) -> list[str]:
    failures = []
    for i, test in enumerate(tests):
        if pace and i > 0:
            time.sleep(LIVE_TEST_PACING_SECONDS)
        print(f"\n{'=' * 60}\nrunning {test}\n{'=' * 60}", flush=True)
        result = subprocess.run([sys.executable, "-m", test], cwd=REPO_ROOT)
        if result.returncode != 0:
            failures.append(test)
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description="Run ChronoMemory exit tests.")
    parser.add_argument(
        "--live",
        action="store_true",
        help="also run the live-model-judgment suite (real Qwen Cloud calls, "
        "non-deterministic — a single red run there is not proof of a "
        "regression, rerun before trusting it)",
    )
    args = parser.parse_args()

    failures = run(FAST_TESTS)

    if args.live:
        print(f"\n{'=' * 60}\nrunning live-model-judgment suite (non-deterministic)\n{'=' * 60}")
        failures += run(LIVE_TESTS, pace=True)
    else:
        print("\n(skipping live-model-judgment suite — pass --live to include it)")

    print(f"\n{'=' * 60}")
    if failures:
        print(f"FAILED: {', '.join(failures)}")
        return 1
    print("ALL PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
