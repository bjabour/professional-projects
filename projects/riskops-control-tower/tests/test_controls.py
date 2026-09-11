"""Behavioral controls tested in isolated workspaces using the unchanged fixtures."""
from __future__ import annotations

import copy
import csv
import io
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from riskops.analytics import scenario
from riskops.engine import ControlError, DATES, Engine, atomic, canonical, digest, json_bytes, load


class ControlTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="riskops-controls-")
        self.addCleanup(self.temp.cleanup)
        self.workspace = Path(self.temp.name)
        shutil.copytree(ROOT / "data", self.workspace / "data")
        shutil.copytree(ROOT / "config", self.workspace / "config")
        self.engine = Engine(self.workspace)
        self.capture = io.StringIO()
        self.log_patch = patch("sys.stderr", self.capture)
        self.log_patch.start()
        self.addCleanup(self.log_patch.stop)

    def cli(self, *args):
        return subprocess.run([sys.executable, str(ROOT / "scripts" / "riskops.py"), *args, "--workspace", str(self.workspace)], capture_output=True, text=True, timeout=30)

    def change_csv(self, date_value, filename, edit):
        path = self.workspace / "data" / date_value / filename
        reader = csv.DictReader(io.StringIO(path.read_text(encoding="utf-8-sig")))
        fields, rows = reader.fieldnames, list(reader)
        edit(rows)
        output = io.StringIO(newline="")
        writer = csv.DictWriter(output, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
        atomic(path, output.getvalue().encode())

    def test_baseline_regression_all_dates(self):
        """All v1 USD metrics and portfolio metrics match the archived baseline to six decimals."""
        self.engine.all(DATES[-1])
        for d in DATES:
            expected = load(ROOT / "tests" / "expected" / (d + ".json"))
            actual = load(self.engine.store / self.engine.active(d) / "result.json")
            for metric, value in expected["metrics"].items():
                self.assertAlmostEqual(actual["metrics"][metric], value, places=6, msg=f"{d} {metric}")
            self.assertEqual(actual["status"], expected["status"])
            self.assertEqual(len(actual["warnings"]), len(expected["warnings"]))
            for old, new in zip(expected["portfolios"], actual["portfolios"]):
                for key, value in old.items():
                    if isinstance(value, (int, float)):
                        self.assertAlmostEqual(new[key], value, places=6, msg=f"{d} {old['portfolio']} {key}")
                    else:
                        self.assertEqual(new[key], value)

    def test_idempotent_completed_run(self):
        """Repeated all reuses exact run identities, artifact bytes and log events."""
        self.engine.all(DATES[-1])
        ids = [self.engine.active(d) for d in DATES]
        before = {p.relative_to(self.engine.store).as_posix(): digest(p.read_bytes()) for p in self.engine.store.rglob("*") if p.is_file()}
        dashboard = (self.workspace / "results" / "dashboard-data.json").read_bytes()
        self.engine.all(DATES[-1])
        after = {p.relative_to(self.engine.store).as_posix(): digest(p.read_bytes()) for p in self.engine.store.rglob("*") if p.is_file()}
        self.assertEqual(ids, [self.engine.active(d) for d in DATES])
        self.assertEqual(before, after)
        self.assertEqual(dashboard, (self.workspace / "results" / "dashboard-data.json").read_bytes())

    def test_staged_resume_after_failure(self):
        """A failed ETL retains valid prepare evidence and resumes without rebuilding the checkpoint."""
        run_id = self.engine.prepare(DATES[0])
        before = (self.engine.store / run_id / "validation.json").read_bytes()
        with patch("riskops.engine.calculate", side_effect=ValueError("Injected ETL failure")):
            with self.assertRaisesRegex(ValueError, "Injected ETL failure"):
                self.engine.stage(DATES[0], "ETL")
        self.assertEqual(self.engine.row(run_id)["state"], "FAILED")
        self.assertTrue(any(e["event"] == "STAGE_FAILED" for e in self.engine.events(run_id)))
        self.engine.stage(DATES[0], "ETL")
        self.engine.stage(DATES[0], "REPORT")
        self.assertEqual(before, (self.engine.store / run_id / "validation.json").read_bytes())
        self.assertEqual(self.engine.verify(run_id, fresh=True)["state"], "COMPLETED")

    def test_missing_input_is_visible(self):
        """A missing input returns nonzero and appears in status failed_attempts without a prepared run."""
        (self.workspace / "data" / DATES[0] / "Deposits.csv").unlink()
        result = self.cli("prepare", "--run-date", DATES[0])
        self.assertEqual(result.returncode, 1)
        self.assertIn("CONTROL_FAILED", result.stderr)
        status = self.engine.status()
        self.assertEqual(status["runs"], [])
        self.assertEqual(len(status["failed_attempts"]), 1)
        self.assertIn("Deposits.csv", status["failed_attempts"][0]["error"])

    def test_duplicate_id_across_portfolios(self):
        """IDs must be globally unique across all three files, not just unique within each file."""
        self.change_csv(DATES[0], "Mortgages.csv", lambda rows: rows[0].update(instrument_id="DEP-001"))
        with self.assertRaisesRegex(ValueError, "duplicate instrument ID"):
            self.engine.prepare(DATES[0])
        self.assertIsNone(self.engine.active(DATES[0]))

    def test_nonfinite_input_rejected(self):
        """NaN cannot propagate through risk calculations or dashboard JSON."""
        self.change_csv(DATES[0], "Deposits.csv", lambda rows: rows[0].update(principal="NaN"))
        with self.assertRaisesRegex(ValueError, "invalid numeric"):
            self.engine.prepare(DATES[0])

    def test_snapshot_tamper_blocks_etl(self):
        """Changing archived input bytes blocks ETL even when the CSV remains parseable."""
        run_id = self.engine.prepare(DATES[0])
        path = self.engine.store / run_id / "inputs" / "Deposits.csv"
        atomic(path, path.read_bytes().replace(b"220.0000", b"221.0000", 1))
        with self.assertRaisesRegex(ControlError, "Snapshot integrity"):
            self.engine.stage(DATES[0], "ETL")

    def test_config_drift_creates_new_identity(self):
        """Live config drift blocks downstream reuse; preparing again preserves the old snapshot as a new run starts."""
        old_id = self.engine.prepare(DATES[0])
        old_snapshot = (self.engine.store / old_id / "config.json").read_bytes()
        config_path = self.workspace / "config" / "risk_parameters.json"
        config = load(config_path)
        config["currency_fx_to_usd"]["ILS"] += .001
        atomic(config_path, json_bytes(config))
        with self.assertRaisesRegex(ControlError, "differs from prepared"):
            self.engine.stage(DATES[0], "ETL")
        new_id = self.engine.prepare(DATES[0])
        self.assertNotEqual(old_id, new_id)
        self.assertEqual(old_snapshot, (self.engine.store / old_id / "config.json").read_bytes())

    def test_source_drift_creates_new_identity(self):
        """Changing valid source data creates a new ID and preserves completed original results."""
        old_id = self.engine.all(DATES[0])
        old_result = (self.engine.store / old_id / "result.json").read_bytes()
        self.change_csv(DATES[0], "Deposits.csv", lambda rows: rows[0].update(book_value="219.0000"))
        new_id = self.engine.all(DATES[0])
        self.assertNotEqual(old_id, new_id)
        self.assertEqual(old_result, (self.engine.store / old_id / "result.json").read_bytes())

    def test_stale_predecessor_rejected(self):
        """A changed previous-day input cannot silently drive comparisons on an old result."""
        self.engine.all(DATES[0])
        self.change_csv(DATES[0], "Deposits.csv", lambda rows: rows[0].update(book_value="219.0000"))
        with self.assertRaisesRegex(ControlError, "Stale predecessor"):
            self.engine.prepare(DATES[1])
        self.engine.all(DATES[1])
        manifest = load(self.engine.store / self.engine.active(DATES[1]) / "manifest.json")
        self.assertEqual(manifest["identity"]["previous_run_id"], self.engine.active(DATES[0]))

    def test_result_tamper_blocks_report(self):
        """A modified ETL result cannot be narrated or exported."""
        run_id = self.engine.prepare(DATES[0])
        self.engine.stage(DATES[0], "ETL")
        path = self.engine.store / run_id / "result.json"
        result = load(path)
        result["metrics"]["lcr_pct"] = 999
        atomic(path, json_bytes(result))
        with self.assertRaisesRegex(ControlError, "Artifact integrity"):
            self.engine.stage(DATES[0], "REPORT")

    def test_log_tamper_detected(self):
        """JSONL event history is checked against the SQLite record before downstream use."""
        run_id = self.engine.prepare(DATES[0])
        path = self.engine.store / run_id / "logs" / "events.jsonl"
        atomic(path, b"{}\n")
        with self.assertRaisesRegex(ControlError, "Log integrity"):
            self.engine.verify(run_id)

    def test_stage_order_enforced(self):
        """Report cannot skip the ETL prerequisite."""
        self.engine.prepare(DATES[0])
        with self.assertRaisesRegex(ControlError, "prerequisite"):
            self.engine.stage(DATES[0], "REPORT")

    def test_brief_fact_and_warning_enforcement(self):
        """Structured values, all warnings and pending approval must match; arbitrary prose stays unverified."""
        run_id = self.engine.all(DATES[-1])
        candidate = load(self.engine.store / run_id / "brief.json")
        candidate["headline"] = "An externally authored assertion that was not verified."
        self.assertEqual(self.engine.validate_brief(DATES[-1], candidate)["prose_status"], "UNVERIFIED_DRAFT")
        for edit in (lambda b: b["facts"][0].update(value=0), lambda b: b["warnings"].pop(), lambda b: b.update(approval_status="APPROVED")):
            changed = copy.deepcopy(candidate)
            edit(changed)
            with self.assertRaisesRegex(ControlError, "structured field mismatch"):
                self.engine.validate_brief(DATES[-1], changed)

    def test_scenario_bounds_and_zero_shock(self):
        """Zero shock preserves PV/LCR; worsening liquidity raises the gap; invalid inputs are rejected."""
        run_id = self.engine.all(DATES[0])
        result = load(self.engine.store / run_id / "result.json")
        baseline = scenario(result)
        self.assertEqual(baseline["stressed_pv_usd_m"], result["metrics"]["total_pv_usd_m"])
        self.assertAlmostEqual(baseline["lcr_pct"], result["metrics"]["lcr_pct"], places=6)
        stress = scenario(result, 200, 15, 25)
        self.assertLess(stress["stressed_pv_usd_m"], baseline["stressed_pv_usd_m"])
        self.assertGreater(stress["liquidity_gap_usd_m"], 0)
        self.assertNotIn("var_1d_usd_m", stress)
        for kwargs in ({"rate_bps": float("nan")}, {"buffer_haircut_pct": 101}, {"outflow_increase_pct": -1}, {"rate_bps": 501}):
            with self.assertRaises(ValueError):
                scenario(result, **kwargs)

    def test_lock_denial_does_not_fail_owner(self):
        """A concurrent rejected command cannot change the active command's RUNNING state or event history."""
        run_id = self.engine.prepare(DATES[0])
        with self.engine.db() as db:
            db.execute("INSERT INTO stages VALUES(?,?,?,?,?)", (run_id, "ETL", "RUNNING", "{}", 0.))
            db.execute("UPDATE runs SET state='RUNNING' WHERE run_id=?", (run_id,))
        events = self.engine.events(run_id)
        with self.engine.lock():
            result = self.cli("verify", "--run-date", DATES[0])
        self.assertEqual(result.returncode, 1)
        self.assertIn("execution lock", result.stderr)
        self.assertEqual(self.engine.row(run_id)["state"], "RUNNING")
        self.assertEqual(self.engine.events(run_id), events)

    def test_portable_export_and_lineage(self):
        """Export includes real stages, logs, sources, all warnings and correct predecessor identities without local paths."""
        self.engine.all(DATES[-1])
        payload = self.engine.export()
        self.assertEqual(len(payload["dates"]), 3)
        serialized = canonical(payload).decode()
        self.assertNotIn(str(self.workspace), serialized)
        self.assertNotIn("C:\\", serialized)
        for index, result in enumerate(payload["dates"]):
            self.assertEqual(result["metrics"]["instrument_count"], 17)
            self.assertEqual(len(result["stages"]), 3)
            self.assertEqual(len(result["provenance"]["source_files"]), 3)
            self.assertEqual(result["brief"]["warnings"], result["warnings"])
            self.assertTrue(all(s["duration_seconds"] >= 0 for s in result["stages"]))
            prior = payload["dates"][index - 1]["run_id"] if index else None
            self.assertEqual(result["provenance"]["previous_run_id"], prior)

    def test_fresh_batch_prepare_preflight(self):
        """Batch prepare rejects missing predecessor checkpoints before creating any partial runs."""
        result = self.cli("prepare", "--all-dates")
        self.assertEqual(result.returncode, 1)
        self.assertIn("all --all-dates", result.stderr)
        self.assertEqual(self.engine.status()["runs"], [])

    def test_nonobject_brief_is_clean_error(self):
        """Valid JSON with the wrong top-level type returns a clear control error instead of a traceback."""
        path = self.workspace / "candidate.json"
        atomic(path, b"[]")
        result = self.cli("validate-brief", "--run-date", DATES[0], "--brief-file", str(path))
        self.assertEqual(result.returncode, 1)
        self.assertIn("Brief must be a JSON object", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_code_drift_rejects_reuse(self):
        """A change to operational source changes the run identity and blocks an old prepared checkpoint."""
        source = self.workspace / "source"
        shutil.copytree(ROOT / "riskops", source / "riskops")
        (source / "scripts").mkdir()
        shutil.copy2(ROOT / "scripts" / "riskops.py", source / "scripts" / "riskops.py")
        engine = Engine(self.workspace, code_root=source)
        old_id = engine.prepare(DATES[0])
        code = source / "riskops" / "analytics.py"
        atomic(code, code.read_bytes() + b"\n# source identity change\n")
        with self.assertRaisesRegex(ControlError, "differs from prepared"):
            engine.stage(DATES[0], "ETL")
        self.assertNotEqual(engine.prepare(DATES[0]), old_id)

    def test_unsupported_date_exit(self):
        """Unsupported dates are rejected by the command parser with exit code 2."""
        result = self.cli("all", "--run-date", "2026-09-01")
        self.assertEqual(result.returncode, 2)
        self.assertIn("invalid choice", result.stderr)


if __name__ == "__main__":
    unittest.main()
