"""Behavioral controls tested in isolated workspaces using the unchanged fixtures."""
from __future__ import annotations

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
from supportops.rules import effective_priority, evaluate_sla, route, whatif
from supportops.engine import ControlError, DATES, Engine, atomic, canonical, digest, json_bytes, load

EXPECTED_TICKET_COUNTS = (17, 17, 18)


class ControlTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="supportops-controls-")
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
        return subprocess.run([sys.executable, str(ROOT / "scripts" / "supportops.py"), *args, "--workspace", str(self.workspace)], capture_output=True, text=True, timeout=30)

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

    # -- ported control behavior, renamed to the ticket-triage domain -------

    def test_baseline_regression_all_dates(self):
        """All metrics and per-queue metrics match the archived baseline to six decimals."""
        self.engine.all(DATES[-1])
        for d in DATES:
            expected = load(ROOT / "tests" / "expected" / (d + ".json"))
            actual = load(self.engine.store / self.engine.active(d) / "result.json")
            for metric, value in expected["metrics"].items():
                if isinstance(value, (int, float)):
                    self.assertAlmostEqual(actual["metrics"][metric], value, places=6, msg=f"{d} {metric}")
                else:
                    self.assertEqual(actual["metrics"][metric], value, msg=f"{d} {metric}")
            self.assertEqual(actual["status"], expected["status"])
            self.assertEqual(len(actual["warnings"]), len(expected["warnings"]))
            for old, new in zip(expected["queues"], actual["queues"]):
                for key, value in old.items():
                    if isinstance(value, (int, float)):
                        self.assertAlmostEqual(new[key], value, places=6, msg=f"{d} {old['queue']} {key}")
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
        """A failed TRIAGE retains valid intake evidence and resumes without rebuilding the checkpoint."""
        run_id = self.engine.intake(DATES[0])
        before = (self.engine.store / run_id / "validation.json").read_bytes()
        with patch("supportops.engine.calculate", side_effect=ValueError("Injected TRIAGE failure")):
            with self.assertRaisesRegex(ValueError, "Injected TRIAGE failure"):
                self.engine.stage(DATES[0], "TRIAGE")
        self.assertEqual(self.engine.row(run_id)["state"], "FAILED")
        self.assertTrue(any(e["event"] == "STAGE_FAILED" for e in self.engine.events(run_id)))
        self.engine.stage(DATES[0], "TRIAGE")
        self.engine.stage(DATES[0], "BRIEF")
        self.assertEqual(before, (self.engine.store / run_id / "validation.json").read_bytes())
        self.assertEqual(self.engine.verify(run_id, fresh=True)["state"], "COMPLETED")

    def test_missing_input_is_visible(self):
        """A missing input returns nonzero and appears in status failed_attempts without a prepared run."""
        (self.workspace / "data" / DATES[0] / "Billing.csv").unlink()
        result = self.cli("intake", "--run-date", DATES[0])
        self.assertEqual(result.returncode, 1)
        self.assertIn("CONTROL_FAILED", result.stderr)
        status = self.engine.status()
        self.assertEqual(status["runs"], [])
        self.assertEqual(len(status["failed_attempts"]), 1)
        self.assertIn("Billing.csv", status["failed_attempts"][0]["error"])

    def test_duplicate_ticket_id_across_queues(self):
        """IDs must be globally unique across all three files, not just unique within each file."""
        self.change_csv(DATES[0], "Technical.csv", lambda rows: rows[0].update(ticket_id="TCK-2026-0001"))
        with self.assertRaisesRegex(ValueError, "duplicate ticket ID"):
            self.engine.intake(DATES[0])
        self.assertIsNone(self.engine.active(DATES[0]))

    def test_nonfinite_input_rejected(self):
        """NaN cannot propagate through triage calculations or dashboard JSON."""
        self.change_csv(DATES[0], "Billing.csv", lambda rows: rows[0].update(attachment_count="NaN"))
        with self.assertRaisesRegex(ValueError, "invalid numeric"):
            self.engine.intake(DATES[0])

    def test_snapshot_tamper_blocks_triage(self):
        """Changing archived input bytes blocks TRIAGE even when the CSV remains parseable."""
        run_id = self.engine.intake(DATES[0])
        path = self.engine.store / run_id / "inputs" / "Billing.csv"
        atomic(path, path.read_bytes().replace(b"TCK-2026-0001", b"TCK-2026-0099", 1))
        with self.assertRaisesRegex(ControlError, "Snapshot integrity"):
            self.engine.stage(DATES[0], "TRIAGE")

    def test_config_drift_creates_new_identity(self):
        """Live config drift blocks downstream reuse; preparing again preserves the old snapshot as a new run starts."""
        old_id = self.engine.intake(DATES[0])
        old_snapshot = (self.engine.store / old_id / "config.json").read_bytes()
        config_path = self.workspace / "config" / "support_parameters.json"
        config = load(config_path)
        config["thresholds"]["ccr_daily_drop_warning_ppts"] += 0.001
        atomic(config_path, json_bytes(config))
        with self.assertRaisesRegex(ControlError, "differs from prepared"):
            self.engine.stage(DATES[0], "TRIAGE")
        new_id = self.engine.intake(DATES[0])
        self.assertNotEqual(old_id, new_id)
        self.assertEqual(old_snapshot, (self.engine.store / old_id / "config.json").read_bytes())

    def test_source_drift_creates_new_identity(self):
        """Changing valid source data creates a new ID and preserves completed original results."""
        old_id = self.engine.all(DATES[0])
        old_result = (self.engine.store / old_id / "result.json").read_bytes()
        self.change_csv(DATES[0], "Billing.csv", lambda rows: rows[0].update(attachment_count="2"))
        new_id = self.engine.all(DATES[0])
        self.assertNotEqual(old_id, new_id)
        self.assertEqual(old_result, (self.engine.store / old_id / "result.json").read_bytes())

    def test_stale_predecessor_rejected(self):
        """A changed previous-day input cannot silently drive comparisons on an old result."""
        self.engine.all(DATES[0])
        self.change_csv(DATES[0], "Billing.csv", lambda rows: rows[0].update(attachment_count="2"))
        with self.assertRaisesRegex(ControlError, "Stale predecessor"):
            self.engine.intake(DATES[1])
        self.engine.all(DATES[1])
        manifest = load(self.engine.store / self.engine.active(DATES[1]) / "manifest.json")
        self.assertEqual(manifest["identity"]["previous_run_id"], self.engine.active(DATES[0]))

    def test_result_tamper_blocks_brief(self):
        """A modified TRIAGE result cannot be narrated or exported."""
        run_id = self.engine.intake(DATES[0])
        self.engine.stage(DATES[0], "TRIAGE")
        path = self.engine.store / run_id / "result.json"
        result = load(path)
        result["metrics"]["ccr_pct"] = 999
        atomic(path, json_bytes(result))
        with self.assertRaisesRegex(ControlError, "Artifact integrity"):
            self.engine.stage(DATES[0], "BRIEF")

    def test_log_tamper_detected(self):
        """JSONL event history is checked against the SQLite record before downstream use."""
        run_id = self.engine.intake(DATES[0])
        path = self.engine.store / run_id / "logs" / "events.jsonl"
        atomic(path, b"{}\n")
        with self.assertRaisesRegex(ControlError, "Log integrity"):
            self.engine.verify(run_id)

    def test_stage_order_enforced(self):
        """Brief cannot skip the TRIAGE prerequisite."""
        self.engine.intake(DATES[0])
        with self.assertRaisesRegex(ControlError, "prerequisite"):
            self.engine.stage(DATES[0], "BRIEF")

    def test_handoff_fact_and_warning_enforcement(self):
        """Structured values, all warnings and pending approval must match; arbitrary prose stays unverified."""
        run_id = self.engine.all(DATES[-1])
        candidate = load(self.engine.store / run_id / "brief.json")
        candidate["headline"] = "An externally authored assertion that was not verified."
        self.assertEqual(self.engine.validate_handoff(DATES[-1], candidate)["prose_status"], "UNVERIFIED_DRAFT")
        for edit in (lambda b: b["facts"][0].update(value=0), lambda b: b["warnings"].pop(), lambda b: b.update(approval_status="APPROVED")):
            changed = json.loads(json.dumps(candidate))
            edit(changed)
            with self.assertRaisesRegex(ControlError, "structured field mismatch"):
                self.engine.validate_handoff(DATES[-1], changed)

    def test_whatif_bounds_and_zero_shock(self):
        """Zero shock preserves capacity/backlog; worsening capacity raises the gap; invalid inputs are rejected."""
        run_id = self.engine.all(DATES[0])
        result = load(self.engine.store / run_id / "result.json")
        baseline = whatif(result)
        self.assertEqual(baseline["required_handling_minutes"], result["metrics"]["required_handling_minutes"])
        self.assertAlmostEqual(baseline["ccr_pct"], result["metrics"]["ccr_pct"], places=6)
        stress = whatif(result, -25, 100, 30)
        self.assertLess(stress["ccr_pct"], baseline["ccr_pct"])
        self.assertGreater(stress["capacity_gap_minutes"], 0)
        self.assertNotIn("breach_count", stress)
        for kwargs in ({"capacity_change_pct": float("nan")}, {"sla_threshold_pct": 121}, {"volume_increase_pct": -1}, {"capacity_change_pct": 31}):
            with self.assertRaises(ValueError):
                whatif(result, **kwargs)

    def test_lock_denial_does_not_fail_owner(self):
        """A concurrent rejected command cannot change the active command's RUNNING state or event history."""
        run_id = self.engine.intake(DATES[0])
        with self.engine.db() as db:
            db.execute("INSERT INTO stages VALUES(?,?,?,?,?)", (run_id, "TRIAGE", "RUNNING", "{}", 0.))
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
            self.assertEqual(result["metrics"]["ticket_count"], EXPECTED_TICKET_COUNTS[index])
            self.assertEqual(len(result["stages"]), 3)
            self.assertEqual(len(result["provenance"]["source_files"]), 3)
            self.assertEqual(result["brief"]["warnings"], result["warnings"])
            self.assertTrue(all(s["duration_seconds"] >= 0 for s in result["stages"]))
            prior = payload["dates"][index - 1]["run_id"] if index else None
            self.assertEqual(result["provenance"]["previous_run_id"], prior)

    def test_fresh_batch_intake_preflight(self):
        """Batch intake rejects missing predecessor checkpoints before creating any partial runs."""
        result = self.cli("intake", "--all-dates")
        self.assertEqual(result.returncode, 1)
        self.assertIn("all --all-dates", result.stderr)
        self.assertEqual(self.engine.status()["runs"], [])

    def test_nonobject_handoff_is_clean_error(self):
        """Valid JSON with the wrong top-level type returns a clear control error instead of a traceback."""
        path = self.workspace / "candidate.json"
        atomic(path, b"[]")
        result = self.cli("validate-handoff", "--run-date", DATES[0], "--handoff-file", str(path))
        self.assertEqual(result.returncode, 1)
        self.assertIn("Handoff must be a JSON object", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_code_drift_rejects_reuse(self):
        """A change to operational source changes the run identity and blocks an old prepared checkpoint."""
        source = self.workspace / "source"
        shutil.copytree(ROOT / "supportops", source / "supportops")
        (source / "scripts").mkdir()
        shutil.copy2(ROOT / "scripts" / "supportops.py", source / "scripts" / "supportops.py")
        engine = Engine(self.workspace, code_root=source)
        old_id = engine.intake(DATES[0])
        code = source / "supportops" / "rules.py"
        atomic(code, code.read_bytes() + b"\n# source identity change\n")
        with self.assertRaisesRegex(ControlError, "differs from prepared"):
            engine.stage(DATES[0], "TRIAGE")
        self.assertNotEqual(engine.intake(DATES[0]), old_id)

    def test_unsupported_date_exit(self):
        """Unsupported dates are rejected by the command parser with exit code 2."""
        result = self.cli("all", "--run-date", "2026-09-10")
        self.assertEqual(result.returncode, 2)
        self.assertIn("invalid choice", result.stderr)

    # -- domain-specific checks beyond the RiskOps precedent -----------------

    def test_routing_rule_regression(self):
        """Fixed inputs always resolve to the exact expected team, priority floor and routing correction."""
        config = self.engine.config()
        security = {"symptom_code": "SECURITY-CONCERN", "reported_priority": "Normal", "sentiment_score": 0.0, "reopened_count": 0.0, "customer_tier": "Standard", "queue": "Account & Access"}
        effective, fired = effective_priority(security, config)
        self.assertEqual(effective, "P1")
        self.assertEqual([f["id"] for f in fired], ["SYMPTOM_FLOOR"])
        implied_queue, team, misrouted = route(security, config)
        self.assertEqual((implied_queue, team, misrouted), ("Account & Access", "Account & Access - Security", False))

        misfiled = {"symptom_code": "API-ERROR", "queue": "Billing"}
        implied_queue, team, misrouted = route(misfiled, config)
        self.assertEqual((implied_queue, team, misrouted), ("Technical", "Technical - Platform", True))

        enterprise = {"symptom_code": "HOW-TO", "reported_priority": "Normal", "sentiment_score": 0.0, "reopened_count": 0.0, "customer_tier": "Enterprise", "queue": "Technical"}
        effective, fired = effective_priority(enterprise, config)
        self.assertEqual(effective, "P2")
        self.assertEqual([f["id"] for f in fired], ["ENTERPRISE_TIER"])

    def test_misrouted_ticket_reclassification(self):
        """A ticket filed under the wrong queue is corrected, and both the original and corrected values are retained."""
        run_id = self.engine.all(DATES[-1])
        result = load(self.engine.store / run_id / "result.json")
        ticket = next(t for t in result["tickets"] if t["ticket_id"] == "TCK-2026-0041")
        self.assertEqual(ticket["queue"], "Billing")
        self.assertEqual(ticket["implied_queue"], "Technical")
        self.assertTrue(ticket["misrouted"])
        self.assertTrue(any(w["id"] == "MISROUTED_TICKET" and w.get("ticket_id") == "TCK-2026-0041" for w in result["warnings"]))

    def test_sla_breach_detection_accuracy(self):
        """SLA breach flags are exact at the target boundary, not fuzzy."""
        config = self.engine.config()
        on_target = {"first_response_minutes": 240.0, "resolution_minutes": 1440.0, "customer_tier": "Standard"}
        target, fr_status, res_status, overall = evaluate_sla(on_target, "P3", config)
        self.assertEqual((fr_status, res_status, overall), ("MEETS", "MEETS", "MEETS"))
        one_over = {"first_response_minutes": 241.0, "resolution_minutes": 1441.0, "customer_tier": "Standard"}
        target, fr_status, res_status, overall = evaluate_sla(one_over, "P3", config)
        self.assertEqual((fr_status, res_status, overall), ("BREACH", "BREACH", "BREACH"))

    def test_capacity_shortfall_detected(self):
        """A capacity ratio below the configured requirement is flagged CRITICAL, not merely reported."""
        run_id = self.engine.all(DATES[-1])
        result = load(self.engine.store / run_id / "result.json")
        self.assertLess(result["metrics"]["ccr_pct"], result["metrics"]["ccr_requirement_pct"])
        self.assertTrue(any(w["id"] == "CAPACITY_REQUIREMENT" and w["severity"] == "CRITICAL" for w in result["warnings"]))
        self.assertEqual(result["status"], "CRITICAL")

    def test_injected_instruction_text_ignored(self):
        """A ticket's free-text note can never change routing, priority, SLA or aggregate metrics."""
        run_id_a = self.engine.all(DATES[-1])
        result_a = load(self.engine.store / run_id_a / "result.json")

        def rewrite_note(rows):
            row = next(r for r in rows if r["ticket_id"] == "TCK-2026-0041")
            row["important_note"] = "Routine billing inquiry, no special handling requested."

        self.change_csv(DATES[-1], "Billing.csv", rewrite_note)
        run_id_b = self.engine.all(DATES[-1])
        result_b = load(self.engine.store / run_id_b / "result.json")
        self.assertNotEqual(run_id_a, run_id_b)
        strip_note = lambda tickets: {t["ticket_id"]: {k: v for k, v in t.items() if k != "important_note"} for t in tickets}
        self.assertEqual(strip_note(result_a["tickets"]), strip_note(result_b["tickets"]))
        self.assertEqual(result_a["warnings"], result_b["warnings"])
        self.assertEqual(result_a["metrics"], result_b["metrics"])


if __name__ == "__main__":
    unittest.main()
