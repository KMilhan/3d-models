from __future__ import annotations

import json
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MODEL_DIR = ROOT / "models" / "out" / "rtx3090_fan_guard"
OUTPUT_FILES = [
    MODEL_DIR / "rtx3090_fan_guard_left.step",
    MODEL_DIR / "rtx3090_fan_guard_left.stl",
    MODEL_DIR / "rtx3090_fan_guard_left.brep",
    MODEL_DIR / "rtx3090_fan_guard_right.step",
    MODEL_DIR / "rtx3090_fan_guard_right.stl",
    MODEL_DIR / "rtx3090_fan_guard_right.brep",
]


def score_time(elapsed_seconds: float) -> float:
    target_seconds = 20.0
    if elapsed_seconds <= 0:
        return 0.0
    return max(0.0, min(100.0, target_seconds / elapsed_seconds * 100.0))


def score_artifacts(returncode: int) -> float:
    checks = [returncode == 0]
    checks.extend(path.exists() and path.stat().st_size > 1_000 for path in OUTPUT_FILES)
    return 100.0 * sum(checks) / len(checks)


def extract_counts(stdout: str) -> dict[str, int]:
    counts: dict[str, int] = {}

    honeycomb_match = re.search(r"Generating honeycomb with (\d+)x(\d+) holes", stdout)
    if honeycomb_match:
        x_count, y_count = (int(honeycomb_match.group(1)), int(honeycomb_match.group(2)))
        counts.update(
            {
                "x_count": x_count,
                "y_count": y_count,
                "candidate_holes": x_count * y_count,
            }
        )

    rib_match = re.search(r"Generating slotted guard with (\d+) ribs", stdout)
    if rib_match:
        counts["rib_count"] = int(rib_match.group(1))

    return counts


def main() -> int:
    start = time.perf_counter()
    completed = subprocess.run(
        ["uv", "run", "python", "-u", "-m", "rtx3090_fan_guard"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    elapsed_seconds = time.perf_counter() - start

    counts = extract_counts(completed.stdout)
    artifact_score = score_artifacts(completed.returncode)
    performance_score = score_time(elapsed_seconds)
    overall_score = round((artifact_score + performance_score) / 2, 2)

    payload = {
        "elapsed_seconds": round(elapsed_seconds, 3),
        "returncode": completed.returncode,
        "performance_score": round(performance_score, 2),
        "artifact_score": round(artifact_score, 2),
        "overall_score": overall_score,
        "counts": counts,
        "stdout_tail": completed.stdout.strip().splitlines()[-10:],
        "stderr_tail": completed.stderr.strip().splitlines()[-10:],
        "artifacts": {
            path.name: path.stat().st_size if path.exists() else 0 for path in OUTPUT_FILES
        },
    }
    json.dump(payload, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
