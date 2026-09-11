"""Version-one demonstration arithmetic, implemented with Python's standard library.

These are proxy routing, priority and staffing-capacity rules. Real natural-
language classification, workforce management and historical handle-time
modeling are not implemented; ticket free text is never read as an
instruction by any function in this module.
"""
from __future__ import annotations

import csv
import io
import math
import operator
from datetime import date, datetime

OPS = {"lte": operator.le, "gte": operator.ge, "eq": operator.eq}


def parse_inputs(blobs, run_date, config):
    records, files, seen = [], [], set()
    for spec in config["queues"]:
        filename = spec["file"]
        reader = csv.DictReader(io.StringIO(blobs[filename].decode("utf-8-sig")))
        columns = reader.fieldnames or []
        if len(set(columns)) != len(columns):
            raise ValueError(f"{filename}: duplicate column")
        missing = set(config["required_columns"]) - set(columns)
        if missing:
            raise ValueError(f"{filename}: missing columns {sorted(missing)}")
        rows = list(reader)
        if not 1 <= len(rows) <= config["thresholds"]["maximum_tickets_per_file"]:
            raise ValueError(f"{filename}: expected one to ten tickets")
        for row in rows:
            if None in row or any(row.get(k) is None or not row[k].strip() for k in config["required_columns"]):
                raise ValueError(f"{filename}: missing value or malformed row")
            ident = row["ticket_id"]
            if ident in seen:
                raise ValueError(f"{filename}: duplicate ticket ID {ident}")
            seen.add(ident)
            if row["as_of_date"] != run_date or row["queue"] != spec["name"]:
                raise ValueError(f"{filename}: date or queue mismatch")
            submitted = datetime.fromisoformat(row["submitted_at"])
            if submitted.date().isoformat() != run_date:
                raise ValueError(f"{filename}: submission timestamp outside run date")
            for key in config["numeric_columns"]:
                row[key] = float(row[key])
                if not math.isfinite(row[key]) or row[key] < 0:
                    raise ValueError(f"{filename}: invalid numeric value in {key}")
            row["sentiment_score"] = float(row["sentiment_score"])
            if not math.isfinite(row["sentiment_score"]) or not -1.0 <= row["sentiment_score"] <= 1.0:
                raise ValueError(f"{filename}: sentiment_score out of range")
            if row["channel"] not in config["channels"]:
                raise ValueError(f"{filename}: unsupported channel")
            if row["customer_tier"] not in config["customer_tiers"]:
                raise ValueError(f"{filename}: unsupported customer tier")
            if row["region"] not in config["regions"]:
                raise ValueError(f"{filename}: unsupported region")
            if row["reported_priority"] not in config["reported_priority_baseline"]:
                raise ValueError(f"{filename}: unsupported reported priority")
            if row["symptom_code"] not in config["symptom_routing"]:
                raise ValueError(f"{filename}: unsupported symptom code")
            row["source_file"] = filename
            records.append(row)
        files.append({
            "file": filename, "rows": len(rows), "queue": spec["name"],
            "checks": ["schema", "required_values", "global_unique_ids", "date_and_queue", "submission_timestamp",
                       "finite_nonnegative_numbers", "sentiment_range", "channel", "customer_tier", "region",
                       "reported_priority", "symptom_code", "row_limit"],
        })
    return records, files


def _priority_rank(order, code):
    return order.index(code) + 1


def effective_priority(row, config):
    order = config["priority_order"]
    rank = _priority_rank(order, config["reported_priority_baseline"][row["reported_priority"]])
    fired = []
    floor = config["priority_floor_symptoms"].get(row["symptom_code"])
    if floor:
        floor_rank = _priority_rank(order, floor)
        if floor_rank < rank:
            fired.append({"id": "SYMPTOM_FLOOR", "detail": f"{row['symptom_code']} floors priority at {floor}"})
            rank = floor_rank
    for rule in config["priority_bump_rules"]:
        if OPS[rule["op"]](row[rule["field"]], rule["value"]):
            candidate = max(1, rank - rule["bump"])
            if candidate < rank:
                fired.append({"id": rule["id"], "detail": rule["description"]})
                rank = candidate
    return order[rank - 1], fired


def route(row, config):
    routing = config["symptom_routing"][row["symptom_code"]]
    return routing["implied_queue"], routing["assigned_team"], routing["implied_queue"] != row["queue"]


def evaluate_sla(row, effective, config):
    target = config["sla_targets"][effective][row["customer_tier"]]
    fr_status = "MEETS" if row["first_response_minutes"] <= target["first_response_minutes"] else "BREACH"
    res_status = "MEETS" if row["resolution_minutes"] <= target["resolution_minutes"] else "BREACH"
    overall = "BREACH" if "BREACH" in (fr_status, res_status) else "MEETS"
    return target, fr_status, res_status, overall


def calculate(rows, run_date, config, previous=None):
    tickets = []
    for original in rows:
        r = dict(original)
        effective, fired = effective_priority(r, config)
        implied_queue, assigned_team, misrouted = route(r, config)
        target, fr_status, res_status, sla_status = evaluate_sla(r, effective, config)
        reported_code = config["reported_priority_baseline"][r["reported_priority"]]
        r.update({
            "reported_priority_code": reported_code,
            "effective_priority": effective,
            "priority_rules_fired": fired,
            "implied_queue": implied_queue,
            "assigned_team": assigned_team,
            "misrouted": misrouted,
            "sla_first_response_target_minutes": target["first_response_minutes"],
            "sla_resolution_target_minutes": target["resolution_minutes"],
            "estimated_handle_minutes": target["handle_minutes"],
            "sla_first_response_status": fr_status,
            "sla_resolution_status": res_status,
            "sla_status": sla_status,
            "calculation_basis": "synthetic_deterministic_proxy",
        })
        tickets.append(r)

    def total(key, group):
        return sum(t[key] for t in group)

    queues = []
    for spec in config["queues"]:
        group = [t for t in tickets if t["implied_queue"] == spec["name"]]
        required = total("estimated_handle_minutes", group)
        available = config["staffing_capacity_minutes"][run_date][spec["name"]]
        breaches = sum(1 for t in group if t["sla_status"] == "BREACH")
        queues.append({
            "queue": spec["name"], "ticket_count": len(group),
            "required_handling_minutes": round(required, 4),
            "available_agent_minutes": round(float(available), 4),
            "ccr_pct": round(100 * available / required, 6) if required else 999.0,
            "breach_count": breaches,
            "breach_rate_pct": round(100 * breaches / len(group), 4) if group else 0.0,
        })

    total_required = total("required_handling_minutes", queues)
    total_available = total("available_agent_minutes", queues)
    ccr = 100 * total_available / total_required if total_required else 999.0
    breach_count = total("breach_count", queues)
    metrics = {
        "ticket_count": len(tickets), "queue_count": len(queues),
        "required_handling_minutes": round(total_required, 4),
        "available_agent_minutes": round(total_available, 4),
        "ccr_pct": round(ccr, 6), "ccr_requirement_pct": config["thresholds"]["ccr_requirement_pct"],
        "breach_count": breach_count,
        "breach_rate_pct": round(100 * breach_count / len(tickets), 4) if tickets else 0.0,
        "misrouted_count": sum(1 for t in tickets if t["misrouted"]),
        "escalated_count": sum(1 for t in tickets if t["priority_rules_fired"]),
    }

    old = previous["metrics"] if previous else {}

    def change(current, prior):
        return 100 * (current - prior) / abs(prior) if prior else None

    trends = {
        "required_handling_change_pct": change(total_required, old.get("required_handling_minutes")),
        "ccr_change_ppts": (ccr - old["ccr_pct"]) if old else None,
    }

    warnings, thresholds = [], config["thresholds"]

    def warn(code, severity, title, message, metric, current, prior, threshold, **extra):
        warnings.append({
            "id": code, "severity": severity, "title": title, "message": message, "metric": metric,
            "current": round(current, 4) if isinstance(current, (int, float)) else current,
            "previous": round(prior, 4) if isinstance(prior, (int, float)) else prior,
            "threshold": threshold, **extra,
        })

    if ccr < metrics["ccr_requirement_pct"]:
        warn("CAPACITY_REQUIREMENT", "CRITICAL", "Capacity requirement not met",
             f"Capacity coverage is {ccr:.1f}% against the configured {metrics['ccr_requirement_pct']:.1f}% requirement.",
             "ccr_pct", ccr, old.get("ccr_pct"), metrics["ccr_requirement_pct"])

    if trends["ccr_change_ppts"] is not None and trends["ccr_change_ppts"] <= -thresholds["ccr_daily_drop_warning_ppts"]:
        warn("CCR_DROP", "HIGH", "Large daily capacity decline",
             f"Capacity coverage declined {abs(trends['ccr_change_ppts']):.1f} percentage points day over day.",
             "ccr_change_ppts", trends["ccr_change_ppts"], 0.0, thresholds["ccr_daily_drop_warning_ppts"])

    prior_queues = {q["queue"]: q for q in previous["queues"]} if previous else {}
    for q in queues:
        prior = prior_queues.get(q["queue"])
        movement = change(q["required_handling_minutes"], prior["required_handling_minutes"]) if prior else None
        if movement is not None and movement >= thresholds["queue_backlog_change_warning_pct"]:
            warn("BACKLOG_GROWTH", "HIGH", f"Large {q['queue']} backlog growth",
                 f"{q['queue']} required handling time grew {movement:+.1f}% day over day.",
                 q["queue"] + "_required_handling_change_pct", movement, 0.0,
                 thresholds["queue_backlog_change_warning_pct"], queue=q["queue"])
        if q["ticket_count"] and q["breach_rate_pct"] >= thresholds["sla_breach_rate_warning_pct"]:
            warn("SLA_BREACH_CLUSTER", "HIGH", f"{q['queue']} SLA breach cluster",
                 f"{q['breach_count']} of {q['ticket_count']} {q['queue']} tickets breached their SLA target.",
                 q["queue"] + "_breach_rate_pct", q["breach_rate_pct"], None,
                 thresholds["sla_breach_rate_warning_pct"], queue=q["queue"])

    for t in tickets:
        if t["misrouted"]:
            warn("MISROUTED_TICKET", "MEDIUM", "Ticket filed under the wrong queue",
                 f"{t['ticket_id']} was filed under {t['queue']} but routes to {t['implied_queue']} ({t['assigned_team']}).",
                 "queue", t["implied_queue"], t["queue"], None, ticket_id=t["ticket_id"])
        if t["reopened_count"] >= thresholds["recurring_ticket_reopen_threshold"]:
            warn("RECURRING_TICKET", "MEDIUM", "Ticket reopened repeatedly",
                 f"{t['ticket_id']} has been reopened {int(t['reopened_count'])} times.",
                 "reopened_count", t["reopened_count"], None,
                 thresholds["recurring_ticket_reopen_threshold"], ticket_id=t["ticket_id"])
        if t["priority_rules_fired"] and t["effective_priority"] != t["reported_priority_code"]:
            warn("PRIORITY_ESCALATION", "MEDIUM", "Reported priority understated",
                 f"{t['ticket_id']} escalated from {t['reported_priority_code']} to {t['effective_priority']}.",
                 "effective_priority", t["effective_priority"], t["reported_priority_code"], None,
                 ticket_id=t["ticket_id"])

    status = "CRITICAL" if any(w["severity"] == "CRITICAL" for w in warnings) else ("REVIEW" if warnings else "CLEAR")
    return {
        "run_date": run_date, "status": status, "metrics": metrics,
        "trends": {k: (round(v, 6) if isinstance(v, (int, float)) else v) for k, v in trends.items()},
        "thresholds": thresholds, "warnings": warnings, "queues": queues, "tickets": tickets,
    }


def whatif(result, capacity_change_pct=0.0, sla_threshold_pct=100.0, volume_increase_pct=0.0, label="Custom"):
    for value, low, high, name in (
        (capacity_change_pct, -30, 30, "capacity_change_pct"),
        (sla_threshold_pct, 80, 120, "sla_threshold_pct"),
        (volume_increase_pct, 0, 100, "volume_increase_pct"),
    ):
        if not math.isfinite(value) or not low <= value <= high:
            raise ValueError(f"{name} must be finite and between {low} and {high}")
    m = result["metrics"]
    available = m["available_agent_minutes"] * (1 + capacity_change_pct / 100)
    required = m["required_handling_minutes"] * (1 + volume_increase_pct / 100)
    ccr = 100 * available / required if required else 999.0
    requirement = m["ccr_requirement_pct"] * sla_threshold_pct / 100
    gap = max(0.0, required * requirement / 100 - available)
    return {
        "label": label, "capacity_change_pct": capacity_change_pct, "sla_threshold_pct": sla_threshold_pct,
        "volume_increase_pct": volume_increase_pct,
        "available_agent_minutes": round(available, 4), "required_handling_minutes": round(required, 4),
        "ccr_pct": round(ccr, 6), "effective_requirement_pct": round(requirement, 4),
        "capacity_gap_minutes": round(gap, 4),
        "status": "BREACH" if ccr < requirement else "MEETS",
        "method": "linear_capacity_and_volume_sensitivity; baseline routing and priority are not recalculated",
    }
