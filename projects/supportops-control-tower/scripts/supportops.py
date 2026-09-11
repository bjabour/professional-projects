"""Portable entry point. Run from any directory with Python 3.10+."""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

CODE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CODE_ROOT))
from supportops.rules import whatif
from supportops.engine import ControlError, DATES, Engine, PLAN, load


def execute(args, engine):
    dates = DATES if args.all_dates else [args.run_date]
    if args.command == "intake" and args.all_dates:
        for prior_date in DATES[:-1]:
            prior_id = engine.active(prior_date)
            if not prior_id or not any(s["stage"] == "TRIAGE" and s["status"] == "COMPLETED" for s in engine.stages(prior_id)):
                raise ControlError("Batch intake requires existing previous-date TRIAGE checkpoints. On a fresh workspace use all --all-dates, or intake/triage/brief one date at a time")
            engine.verify(prior_id, fresh=True)
    if args.command == "plan":
        return {"mode": "rules_based", "supported_dates": list(DATES), "steps": PLAN, "note": "For a single all command, earlier dates execute first to establish comparison lineage."}
    if args.command == "status":
        return engine.status()
    if args.command == "all":
        engine.all(dates[-1])
        return {"command": "all", "runs": [engine.verify(engine.active(d), fresh=True) for d in DATES[:DATES.index(dates[-1]) + 1]], "dashboard": "results/dashboard-data.json"}
    output = []
    for run_date in dates:
        if args.command == "intake":
            run_id = engine.intake(run_date)
            result = engine.verify(run_id, fresh=True)
        elif args.command in ("triage", "brief"):
            run_id = engine.stage(run_date, "TRIAGE" if args.command == "triage" else "BRIEF")
            result = engine.verify(run_id, fresh=True)
            if args.command == "brief":
                engine.export()
        elif args.command == "verify":
            run_id = engine.active(run_date)
            if not run_id:
                raise ControlError("No prepared run for requested date")
            result = engine.verify(run_id, fresh=True)
        elif args.command == "whatif":
            run_id = engine.active(run_date)
            if not run_id:
                raise ControlError("No prepared run for requested date")
            engine.verify(run_id, fresh=True)
            result = whatif(load(engine.store / run_id / "result.json"), args.capacity_change_pct, args.sla_threshold_pct, args.volume_increase_pct)
            result.update({"run_date": run_date, "run_id": run_id, "approval_status": "PENDING_HUMAN_REVIEW"})
        else:
            result = engine.validate_handoff(run_date, load(args.handoff_file))
        output.append(result)
    return output


def main(argv=None):
    parser = argparse.ArgumentParser(description="SupportOps Control Tower — controlled synthetic daily ticket-triage workflow")
    parser.add_argument("command", choices=("intake", "triage", "brief", "all", "plan", "status", "verify", "whatif", "validate-handoff"))
    target = parser.add_mutually_exclusive_group()
    target.add_argument("--run-date", choices=DATES)
    target.add_argument("--all-dates", action="store_true")
    parser.add_argument("--workspace", type=Path, default=CODE_ROOT, help="Data/config/run workspace; defaults to this package")
    parser.add_argument("--capacity-change-pct", type=float, default=0.)
    parser.add_argument("--sla-threshold-pct", type=float, default=100.)
    parser.add_argument("--volume-increase-pct", type=float, default=0.)
    parser.add_argument("--handoff-file", type=Path)
    args = parser.parse_args(argv)
    if args.command not in {"status", "plan"} and not (args.run_date or args.all_dates):
        parser.error("Choose --run-date or --all-dates")
    if args.command == "validate-handoff" and (not args.handoff_file or not args.run_date):
        parser.error("validate-handoff requires --handoff-file and --run-date")
    engine = None
    try:
        engine = Engine(args.workspace)
        with engine.lock():
            output = execute(args, engine)
        print(json.dumps(output, indent=2, ensure_ascii=False, allow_nan=False))
        return 0
    except (ControlError, ValueError, KeyError, OSError, TypeError, ArithmeticError, sqlite3.Error) as exc:
        if engine:
            engine.failure(args.run_date, args.command, exc)
        print(f"CONTROL_FAILED | command={args.command} | {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
