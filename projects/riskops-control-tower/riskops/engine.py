"""Content-addressed runs with fail-closed checkpoints and local SQLite evidence."""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import sys
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from .analytics import calculate, parse_inputs, scenario

DATES = ("2026-08-27", "2026-08-28", "2026-08-29")
STAGES = ("PREPARE", "ETL", "REPORT")
FILES = ("Deposits.csv", "Mortgages.csv", "Current_Account.csv")
PLAN = [
    {"step": 1, "tool": "prepare", "requires": ["daily CSV files", "validated configuration", "previous date result (except first date)"], "produces": ["input snapshots", "config snapshot", "content identity", "validation manifest"], "reason": "Establish exact input evidence and predecessor lineage before execution."},
    {"step": 2, "tool": "run-etl", "requires": ["verified PREPARE checkpoint"], "produces": ["instrument proxies", "portfolio summaries", "warning rules", "result hash"], "reason": "Reproduce the accepted arithmetic and evaluate transparent material-change rules."},
    {"step": 3, "tool": "report", "requires": ["verified ETL checkpoint"], "produces": ["grounded brief", "scenario grid", "portfolio JSON export"], "reason": "Translate verified results into reviewable leadership evidence."},
]
NOTES = [
    "Synthetic demonstration with 17 instruments per date; source amounts and all USD outputs are in millions.",
    "Deposits, mortgages and accounts are summed as gross positive exposure proxies, not net bank economic value of equity.",
    "PV, duration, YTM and VaR preserve the original illustrative proxy arithmetic; they are not production valuations or calibrated risk estimates.",
    "VaR uses root-sum-of-squares duration contributions and square-root-of-time scaling; no confidence level or empirical coverage claim is made.",
    "LCR uses a synthetic buffer and synthetic 30-day net outflow; regulatory eligibility, caps and assumptions are not modeled.",
    "The Corona scenario is a fixed portfolio haircut, not a historical backtest.",
    "Planning, explanations and handoffs use deterministic rules; no live language model is called. Human approval is required.",
    "Hashes detect changes relative to a trusted local registry; this is not a signed, externally anchored or administrator-proof audit ledger.",
]
MAPPING = [
    {"metric": "total_pv_usd_m", "source": "result.json:instruments[].pv_usd_m", "method": "Sum of positive discounted book-value/coupon proxies translated using fixed configured FX."},
    {"metric": "var_1d_usd_m", "source": "result.json:instruments[].var_1d_contribution_usd_m", "method": "Root-sum-of-squares of PV × modified duration × synthetic daily rate volatility."},
    {"metric": "var_5d_usd_m", "source": "result.json:metrics.var_1d_usd_m", "method": "One-day proxy × sqrt(5), computed before summary rounding."},
    {"metric": "lcr_pct", "source": "result.json:metrics.liquidity_buffer_usd_m + net_cash_outflow_30d_usd_m", "method": "100 × synthetic liquidity buffer / synthetic 30-day net outflow."},
    {"metric": "corona_loss_usd_m", "source": "config.json:corona_scenario_shock_pct + result.json:instruments", "method": "Sum of fixed portfolio haircut losses: deposits 3%, mortgages 12%, current accounts 8%."},
    {"metric": "weighted_modified_duration", "source": "result.json:instruments[].modified_duration + pv_usd_m", "method": "Absolute-PV-weighted modified duration; drives first-order rate sensitivity only."},
]
CONTROLS = [
    {"id": "input_validation", "title": "Strict input gate", "description": "Three required CSVs, finite numbers, global unique IDs, chronology, frequencies, FX mapping and policy checks."},
    {"id": "content_identity", "title": "Content identity", "description": "A run identity commits to data, configuration, code and the exact predecessor result."},
    {"id": "integrity", "title": "Verify before use", "description": "Rehash input/config snapshots and committed stage artifacts before every downstream action."},
    {"id": "resume", "title": "Safe staged resume", "description": "Only committed checkpoints are reusable; completed stages are idempotent."},
    {"id": "lineage", "title": "Fresh predecessor", "description": "Reject comparisons whose previous date no longer matches current inputs/config/code."},
    {"id": "human_review", "title": "Grounded handoff", "description": "Rule-generated facts include source references and all warnings; approval remains pending."},
]


class ControlError(RuntimeError):
    pass


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8")


def digest(value):
    return hashlib.sha256(value).hexdigest()


def atomic(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        with temp.open("xb") as handle:
            handle.write(value)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, path)
    finally:
        if temp.exists():
            temp.unlink()


def json_bytes(value):
    return json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False, allow_nan=False).encode("utf-8") + b"\n"


def load(path):
    return json.loads(Path(path).read_bytes())


def brief_for(result):
    m = result["metrics"]
    keys = ["total_pv_usd_m", "var_1d_usd_m", "var_5d_usd_m", "lcr_pct", "lcr_requirement_pct", "corona_loss_usd_m"]
    return {
        "mode": "rules_based", "approval_status": "PENDING_HUMAN_REVIEW",
        "headline": f"{result['run_date']}: {result['status']} — {len(result['warnings'])} material warning(s); synthetic LCR {m['lcr_pct']:.1f}%.",
        "facts": [{"label": k, "value": m[k], "unit": "percent" if k.endswith("pct") else "USD millions", "source": f"result.json:metrics.{k}"} for k in keys],
        "warnings": result["warnings"],
        "notes": ["Review the dated evidence and warning thresholds before any decision.", "This handoff is generated from fixed rules and verified fields; no live AI service is involved."],
        "questions": (["Who owns the liquidity remediation review, and when will the buffer/outflow assumptions be revalidated?"] if result["status"] == "CRITICAL" else []) + ["Are the configured proxy assumptions still appropriate for this demonstration?", "Which warnings require escalation and who records the human decision?"],
    }


class Engine:
    def __init__(self, root, code_root=None):
        self.root = Path(root).resolve()
        self.code_root = Path(code_root).resolve() if code_root else Path(__file__).resolve().parents[1]
        self.store = self.root / "runs"
        self.db_path = self.root / "registry.sqlite3"
        self.root.mkdir(parents=True, exist_ok=True)
        with self.db() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS runs (run_id TEXT PRIMARY KEY, run_date TEXT NOT NULL, identity TEXT NOT NULL, manifest_hash TEXT NOT NULL, state TEXT NOT NULL, created_at TEXT NOT NULL, error TEXT);
                CREATE TABLE IF NOT EXISTS stages (run_id TEXT NOT NULL, stage TEXT NOT NULL, status TEXT NOT NULL, artifacts TEXT NOT NULL, duration REAL NOT NULL, PRIMARY KEY(run_id,stage));
                CREATE TABLE IF NOT EXISTS active (run_date TEXT PRIMARY KEY, run_id TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS events (run_id TEXT NOT NULL, sequence INTEGER NOT NULL, payload TEXT NOT NULL, PRIMARY KEY(run_id,sequence));
                CREATE TABLE IF NOT EXISTS failures (id INTEGER PRIMARY KEY, run_date TEXT, command TEXT, error TEXT, created_at TEXT);
            """)

    @contextmanager
    def db(self):
        db = sqlite3.connect(self.db_path, timeout=15)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    @contextmanager
    def lock(self):
        """OS advisory lock released automatically if the owning process exits."""
        handle = (self.root / "execution.lock").open("a+b")
        try:
            if handle.tell() == 0:
                handle.write(b"0")
                handle.flush()
            handle.seek(0)
            try:
                if os.name == "nt":
                    import msvcrt
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except (OSError, BlockingIOError) as exc:
                raise ControlError("Another command holds this workspace's execution lock; retry after it completes") from exc
            try:
                yield
            finally:
                handle.seek(0)
                if os.name == "nt":
                    import msvcrt
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            handle.close()

    def config(self):
        config = load(self.root / "config" / "risk_parameters.json")
        if not isinstance(config, dict):
            raise ControlError("Configuration must be a JSON object")
        if config.get("supported_run_dates") != list(DATES) or tuple(p["file"] for p in config.get("portfolios", [])) != FILES:
            raise ControlError("Configuration must preserve the three supported dates and portfolio files")
        if config.get("reporting_currency") != "USD" or config.get("currency_unit") != "millions":
            raise ControlError("This demonstration requires USD millions reporting")
        def check_numbers(value):
            import math
            if isinstance(value, dict):
                for child in value.values():
                    check_numbers(child)
            elif isinstance(value, list):
                for child in value:
                    check_numbers(child)
            elif isinstance(value, (float, int)) and (not math.isfinite(value)):
                raise ControlError("Configuration contains a non-finite number")
        check_numbers(config)
        if any(v <= 0 for v in config["currency_fx_to_usd"].values()) or any(v <= 0 for v in config["frequency_per_year"].values()):
            raise ControlError("FX and frequency values must be positive")
        if config["thresholds"]["lcr_requirement_pct"] <= 0 or config["thresholds"]["maximum_instruments_per_file"] != 10:
            raise ControlError("Invalid liquidity requirement or file size policy")
        if any(v < 0 for v in config["thresholds"].values()) or any(v < 0 for v in config["rate_volatility_bps_by_date"].values()):
            raise ControlError("Thresholds and volatility inputs must be nonnegative")
        return config

    def code_hash(self):
        paths = sorted(list((self.code_root / "riskops").glob("*.py")) + [self.code_root / "scripts" / "riskops.py"])
        return digest(canonical({p.relative_to(self.code_root).as_posix(): digest(p.read_bytes()) for p in paths}))

    def active(self, run_date):
        with self.db() as db:
            row = db.execute("SELECT run_id FROM active WHERE run_date=?", (run_date,)).fetchone()
        return row["run_id"] if row else None

    def row(self, run_id):
        with self.db() as db:
            row = db.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()
        if not row:
            raise ControlError("Unknown run identity")
        return dict(row)

    def stages(self, run_id):
        with self.db() as db:
            rows = db.execute("SELECT * FROM stages WHERE run_id=?", (run_id,)).fetchall()
        indexed = {r["stage"]: dict(r) for r in rows}
        return [indexed[s] for s in STAGES if s in indexed]

    def events(self, run_id):
        with self.db() as db:
            return [json.loads(r["payload"]) for r in db.execute("SELECT payload FROM events WHERE run_id=? ORDER BY sequence", (run_id,))]

    def event(self, run_id, stage, event, message, level="INFO", **details):
        prior = self.events(run_id)
        payload = {"sequence": len(prior) + 1, "timestamp_utc": datetime.now(timezone.utc).isoformat(), "level": level, "stage": stage, "event": event, "message": message, "details": details}
        entries = prior + [payload]
        with self.db() as db:
            db.execute("INSERT INTO events VALUES(?,?,?)", (run_id, payload["sequence"], canonical(payload).decode()))
        self.write_logs(run_id, entries)
        print(f"{payload['timestamp_utc']} | {level:<7} | {run_id} | {stage:<7} | {event:<20} | {message}", file=sys.stderr)

    @staticmethod
    def log_bytes(entries):
        structured = b"".join(canonical(e) + b"\n" for e in entries)
        readable = "".join(f"{e['timestamp_utc']} | {e['level']:<7} | {e['stage']:<7} | {e['event']:<20} | {e['message']} | {json.dumps(e['details'], sort_keys=True)}\n" for e in entries).encode()
        return structured, readable

    def write_logs(self, run_id, entries):
        structured, readable = self.log_bytes(entries)
        atomic(self.store / run_id / "logs" / "events.jsonl", structured)
        atomic(self.store / run_id / "logs" / "run.log", readable)

    def predecessor(self, run_date):
        index = DATES.index(run_date)
        if index == 0:
            return None, None, None
        prior_date = DATES[index - 1]
        prior_id = self.active(prior_date)
        if not prior_id:
            raise ControlError(f"Previous date {prior_date} has no run; execute all --run-date {run_date} to build dependencies")
        self.verify(prior_id)
        expected, _, _, _ = self.identity(prior_date)
        if self.row(prior_id)["identity"] != digest(canonical(expected)):
            raise ControlError(f"Stale predecessor {prior_date}; rerun all for the selected date")
        if not any(s["stage"] == "ETL" and s["status"] == "COMPLETED" for s in self.stages(prior_id)):
            raise ControlError(f"Previous date {prior_date} must finish ETL before preparing {run_date}")
        result_path = self.store / prior_id / "result.json"
        return prior_id, digest(result_path.read_bytes()), load(result_path)

    def identity(self, run_date):
        if run_date not in DATES:
            raise ControlError(f"Unsupported run date {run_date}; supported dates: {', '.join(DATES)}")
        config = self.config()
        blobs = {name: (self.root / "data" / run_date / name).read_bytes() for name in FILES}
        rows, files = parse_inputs(blobs, run_date, config)
        for f in files:
            f["sha256"] = digest(blobs[f["file"]])
        prior_id, prior_hash, previous = self.predecessor(run_date)
        identity = {"run_date": run_date, "data_sha256": digest(canonical({name: digest(blobs[name]) for name in FILES})), "config_sha256": digest(canonical(config)), "code_sha256": self.code_hash(), "previous_run_id": prior_id, "previous_result_sha256": prior_hash}
        return identity, blobs, {"config": config, "rows": rows, "files": files}, previous

    def verify(self, run_id, fresh=False):
        row = self.row(run_id)
        directory = self.store / run_id
        path = directory / "manifest.json"
        if not path.is_file() or digest(path.read_bytes()) != row["manifest_hash"]:
            raise ControlError("Manifest integrity violation")
        manifest = load(path)
        if digest(canonical(manifest["identity"])) != row["identity"]:
            raise ControlError("Run identity integrity violation")
        for relative, expected in manifest["snapshot_hashes"].items():
            item = directory / relative
            if not item.is_file() or digest(item.read_bytes()) != expected:
                raise ControlError(f"Snapshot integrity violation: {relative}")
        for stage in self.stages(run_id):
            if stage["status"] == "COMPLETED":
                for relative, expected in json.loads(stage["artifacts"]).items():
                    item = directory / relative
                    if not item.is_file() or digest(item.read_bytes()) != expected:
                        raise ControlError(f"Artifact integrity violation: {relative}")
        entries = self.events(run_id)
        for path_name, expected in zip(("events.jsonl", "run.log"), self.log_bytes(entries)):
            path = directory / "logs" / path_name
            if not path.is_file() or path.read_bytes() != expected:
                raise ControlError(f"Log integrity violation: {path_name}")
        prior = manifest["identity"]["previous_run_id"]
        if prior:
            self.verify(prior)
            if digest((self.store / prior / "result.json").read_bytes()) != manifest["identity"]["previous_result_sha256"]:
                raise ControlError("Predecessor result integrity violation")
        if fresh:
            expected, _, _, _ = self.identity(row["run_date"])
            if digest(canonical(expected)) != row["identity"]:
                raise ControlError("Current data/config/code or previous result differs from prepared run; prepare a new identity")
        return {"run_id": run_id, "run_date": row["run_date"], "integrity": "VERIFIED", "freshness": "CURRENT" if fresh else "SNAPSHOT_ONLY", "state": row["state"], "artifact_count": sum(len(json.loads(s["artifacts"])) for s in self.stages(run_id))}

    def commit_stage(self, run_id, stage, outputs, duration):
        directory = self.store / run_id
        hashes = {}
        for relative, payload in outputs.items():
            encoded = payload.encode() if isinstance(payload, str) else json_bytes(payload)
            atomic(directory / relative, encoded)
            hashes[relative] = digest(encoded)
        state = {"PREPARE": "PREPARED", "ETL": "ETL_COMPLETED", "REPORT": "COMPLETED"}[stage]
        with self.db() as db:
            db.execute("INSERT OR REPLACE INTO stages VALUES(?,?,?,?,?)", (run_id, stage, "COMPLETED", canonical(hashes).decode(), duration))
            db.execute("UPDATE runs SET state=?,error=NULL WHERE run_id=?", (state, run_id))
        self.event(run_id, stage, "STAGE_COMPLETE", f"{stage.title()} checkpoint committed", duration_seconds=round(duration, 6), artifact_count=len(hashes))

    def prepare(self, run_date):
        started = time.perf_counter()
        identity, blobs, parsed, _ = self.identity(run_date)
        identity_hash = digest(canonical(identity))
        run_id = "RISK-" + run_date.replace("-", "") + "-" + identity_hash[:16]
        with self.db() as db:
            existing = db.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()
        if existing:
            if existing["identity"] != identity_hash:
                raise ControlError("Run ID collision")
            self.verify(run_id, fresh=True)
            with self.db() as db:
                db.execute("INSERT OR REPLACE INTO active VALUES(?,?)", (run_date, run_id))
            if not any(s["stage"] == "PREPARE" and s["status"] == "COMPLETED" for s in self.stages(run_id)):
                self.commit_stage(run_id, "PREPARE", {"validation.json": {"status": "PASS", "file_count": 3, "instrument_count": len(parsed["rows"]), "files": parsed["files"]}}, time.perf_counter() - started)
            return run_id
        directory = self.store / run_id
        if directory.exists():
            raise ControlError("Unregistered partial run directory exists; preserve it for inspection before retrying")
        directory.mkdir(parents=True)
        snapshots = {}
        for name, blob in blobs.items():
            relative = "inputs/" + name
            atomic(directory / relative, blob)
            snapshots[relative] = digest(blob)
        config_blob = json_bytes(parsed["config"])
        atomic(directory / "config.json", config_blob)
        snapshots["config.json"] = digest(config_blob)
        manifest = {"schema_version": "2.0", "run_id": run_id, "identity": identity, "identity_sha256": identity_hash, "snapshot_hashes": snapshots, "source_files": parsed["files"], "plan": PLAN}
        encoded = json_bytes(manifest)
        atomic(directory / "manifest.json", encoded)
        with self.db() as db:
            db.execute("INSERT INTO runs VALUES(?,?,?,?,?,?,NULL)", (run_id, run_date, identity_hash, digest(encoded), "PREPARING", datetime.now(timezone.utc).isoformat()))
            db.execute("INSERT OR REPLACE INTO active VALUES(?,?)", (run_date, run_id))
        self.write_logs(run_id, [])
        self.event(run_id, "PREPARE", "STAGE_START", "Validating three source files and immutable input snapshots")
        for file in parsed["files"]:
            self.event(run_id, "PREPARE", "FILE_VALIDATED", f"{file['file']}: {file['rows']} instruments passed validation", file=file["file"], rows=file["rows"], sha256=file["sha256"])
        self.commit_stage(run_id, "PREPARE", {"validation.json": {"status": "PASS", "file_count": 3, "instrument_count": len(parsed["rows"]), "files": parsed["files"]}}, time.perf_counter() - started)
        return run_id

    def stage(self, run_date, stage):
        run_id = self.active(run_date)
        if not run_id:
            raise ControlError(f"No prepared run for {run_date}; run prepare first")
        self.verify(run_id, fresh=True)
        completed = {s["stage"] for s in self.stages(run_id) if s["status"] == "COMPLETED"}
        if stage in completed:
            return run_id
        required = set(STAGES[:STAGES.index(stage)])
        if not required <= completed:
            raise ControlError(f"Missing completed prerequisite stages: {sorted(required - completed)}")
        started = time.perf_counter()
        directory = self.store / run_id
        with self.db() as db:
            db.execute("INSERT OR REPLACE INTO stages VALUES(?,?,?,?,?)", (run_id, stage, "RUNNING", "{}", 0.))
            db.execute("UPDATE runs SET state='RUNNING',error=NULL WHERE run_id=?", (run_id,))
        self.event(run_id, stage, "STAGE_START", "Verified prerequisites; executing registered tool", tool=stage.lower(), prerequisites=sorted(required))
        try:
            outputs = self.stage_outputs(run_id, run_date, stage)
            self.commit_stage(run_id, stage, outputs, time.perf_counter() - started)
        except Exception as exc:
            with self.db() as db:
                db.execute("UPDATE stages SET status='FAILED' WHERE run_id=? AND stage=?", (run_id, stage))
                db.execute("UPDATE runs SET state='FAILED',error=? WHERE run_id=?", (str(exc), run_id))
            self.event(run_id, stage, "STAGE_FAILED", "Execution stopped; committed prerequisites retained", level="ERROR", error=str(exc))
            raise
        return run_id

    def stage_outputs(self, run_id, run_date, stage):
        directory = self.store / run_id
        if stage == "ETL":
            config = load(directory / "config.json")
            rows, _ = parse_inputs({name: (directory / "inputs" / name).read_bytes() for name in FILES}, run_date, config)
            prior_id = load(directory / "manifest.json")["identity"]["previous_run_id"]
            previous = load(self.store / prior_id / "result.json") if prior_id else None
            result = calculate(rows, run_date, config, previous)
            result["run_id"] = run_id
            self.event(run_id, stage, "RULES_EVALUATED", f"{len(result['warnings'])} material warnings; risk status {result['status']}", lcr_pct=result["metrics"]["lcr_pct"], var_1d_usd_m=result["metrics"]["var_1d_usd_m"], warning_ids=[w["id"] for w in result["warnings"]])
            outputs = {"result.json": result}
        elif stage == "REPORT":
            result = load(directory / "result.json")
            brief = brief_for(result)
            grid = [scenario(result, label="Baseline"), scenario(result, 100, 5, 10, "Moderate stress"), scenario(result, 200, 15, 25, "Severe stress"), scenario(result, -100, 0, 0, "Rate relief")]
            text = "# Leadership handoff\n\n" + brief["headline"] + "\n\nApproval: PENDING_HUMAN_REVIEW. Generated using deterministic rules.\n\n"
            text += "\n".join(f"- {f['label']}: {f['value']} {f['unit']} (source: {f['source']})" for f in brief["facts"])
            text += "\n\nWarnings\n\n" + ("\n".join(f"- {w['severity']}: {w['message']}" for w in brief["warnings"]) or "No material warnings under the configured rules.")
            text += "\n\nHandoff questions\n\n" + "\n".join("- " + q for q in brief["questions"]) + "\n"
            outputs = {"brief.json": brief, "leadership-handoff.md": text, "scenarios.json": grid, "tool-plan.json": PLAN}
        else:
            raise ControlError("Use prepare to create the first checkpoint")
        return outputs

    def all(self, run_date):
        if run_date not in DATES:
            raise ControlError("Unsupported run date")
        for selected in DATES[:DATES.index(run_date) + 1]:
            run_id = self.prepare(selected)
            self.stage(selected, "ETL")
            self.stage(selected, "REPORT")
        self.export()
        return run_id

    def failure(self, run_date, command, error):
        with self.db() as db:
            db.execute("INSERT INTO failures(run_date,command,error,created_at) VALUES(?,?,?,?)", (run_date, command, str(error), datetime.now(timezone.utc).isoformat()))

    def status(self):
        with self.db() as db:
            runs = [dict(r) for r in db.execute("SELECT r.run_id,r.run_date,r.state,r.created_at,r.error FROM runs r ORDER BY r.created_at")]
            failures = [dict(r) for r in db.execute("SELECT * FROM failures ORDER BY id DESC LIMIT 20")]
        for run in runs:
            run["active"] = run["run_id"] == self.active(run["run_date"])
            try:
                run["integrity"] = self.verify(run["run_id"], fresh=run["active"])["integrity"]
            except Exception as exc:
                run["integrity"] = "FAILED"
                run["integrity_error"] = str(exc)
        return {"runs": runs, "failed_attempts": failures}

    def export(self):
        dates = []
        for run_date in DATES:
            run_id = self.active(run_date)
            if not run_id or self.row(run_id)["state"] != "COMPLETED":
                continue
            self.verify(run_id, fresh=True)
            directory = self.store / run_id
            manifest, result = load(directory / "manifest.json"), load(directory / "result.json")
            result.update({"execution_status": "COMPLETED", "reporting_currency": "USD", "currency_unit": "millions",
                "stages": [{"stage": s["stage"], "status": s["status"], "duration_seconds": round(s["duration"], 6), "artifact_count": len(json.loads(s["artifacts"]))} for s in self.stages(run_id)],
                "logs": self.events(run_id), "provenance": {**manifest["identity"], "identity_sha256": manifest["identity_sha256"], "integrity": "VERIFIED", "source_files": manifest["source_files"]},
                "plan": PLAN, "brief": load(directory / "brief.json"), "scenario_grid": load(directory / "scenarios.json"), "source_mapping": MAPPING, "important_notes": NOTES})
            dates.append(result)
        payload = {"schema_version": "2.0", "project": "RiskOps Control Tower", "mode": "synthetic_rules_based", "reporting_currency": "USD", "currency_unit": "millions", "supported_dates": list(DATES), "dates": dates, "controls": CONTROLS, "methodology": {"valuation": MAPPING[0]["method"], "var": MAPPING[1]["method"] + " " + MAPPING[2]["method"], "liquidity": MAPPING[3]["method"], "corona": MAPPING[4]["method"], "scenario": "First-order parallel-rate sensitivity plus liquidity buffer haircut/outflow increase; no scenario VaR estimate.", "agent": "A deterministic tool planner, state machine and evidence-grounded rule template. No live LLM call."}}
        atomic(self.root / "results" / "dashboard-data.json", json_bytes(payload))
        return payload

    def validate_brief(self, run_date, candidate):
        if not isinstance(candidate, dict):
            raise ControlError("Brief must be a JSON object with facts, warnings and approval_status")
        run_id = self.active(run_date)
        if not run_id:
            raise ControlError("No run exists for requested date")
        self.verify(run_id, fresh=True)
        expected = brief_for(load(self.store / run_id / "result.json"))
        for key in ("facts", "warnings", "approval_status"):
            if candidate.get(key) != expected[key]:
                raise ControlError(f"Brief structured field mismatch: {key}")
        return {"structured_facts": "VERIFIED", "prose_status": "UNVERIFIED_DRAFT", "approval_status": "PENDING_HUMAN_REVIEW", "message": "Only exact structured facts and warnings were checked. Free text has not been semantically validated."}
