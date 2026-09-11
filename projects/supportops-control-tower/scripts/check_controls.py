"""Execute the real integration tests and export readable machine evidence."""
from __future__ import annotations

import io
import sys
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from supportops.engine import Engine, atomic, digest, json_bytes


class EvidenceResult(unittest.TextTestResult):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.evidence = []

    def startTest(self, test):
        self.started = time.perf_counter()
        super().startTest(test)

    def record(self, test, status, detail=None):
        self.evidence.append({"id": test._testMethodName.removeprefix("test_"), "test": test.id(), "title": test.shortDescription(), "status": status, "duration_seconds": round(time.perf_counter() - self.started, 6), "detail": detail or "Assertions passed against an isolated workspace using the original synthetic fixtures."})

    def addSuccess(self, test):
        super().addSuccess(test)
        self.record(test, "PASS")

    def addFailure(self, test, err):
        super().addFailure(test, err)
        self.record(test, "FAIL", self._exc_info_to_string(err, test))

    def addError(self, test, err):
        super().addError(test, err)
        self.record(test, "ERROR", self._exc_info_to_string(err, test))


def main():
    suite = unittest.defaultTestLoader.discover(str(ROOT / "tests"), pattern="test_controls.py")
    result = unittest.TextTestRunner(verbosity=2, resultclass=EvidenceResult).run(suite)
    payload = {"schema_version": "1.0", "generated_at_utc": datetime.now(timezone.utc).isoformat(), "command": "python scripts/check_controls.py", "status": "PASS" if result.wasSuccessful() else "FAIL", "tests_run": result.testsRun, "passed": sum(x["status"] == "PASS" for x in result.evidence), "failed": len(result.failures) + len(result.errors), "code_sha256": Engine(ROOT).code_hash(), "test_source_sha256": digest((ROOT / "tests" / "test_controls.py").read_bytes()), "checks": result.evidence}
    atomic(ROOT / "results" / "control-checks.json", json_bytes(payload))
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
