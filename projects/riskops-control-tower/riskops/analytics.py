"""Version-one demonstration arithmetic, implemented with Python's standard library.

These are gross exposure proxies. Deposit/account signs, covariance, cash-flow
valuation, behavioral modeling and regulatory eligibility are not modeled.
"""
from __future__ import annotations

import csv
import io
import math
from datetime import date


def array_round6(value):
    """Match v1 NumPy/pandas scale-and-round behavior without that dependency."""
    return round(value * 1_000_000.0) / 1_000_000.0


def parse_inputs(blobs, run_date, config):
    records, files, seen = [], [], set()
    for spec in config["portfolios"]:
        filename = spec["file"]
        reader = csv.DictReader(io.StringIO(blobs[filename].decode("utf-8-sig")))
        columns = reader.fieldnames or []
        if len(set(columns)) != len(columns):
            raise ValueError(f"{filename}: duplicate column")
        missing = set(config["required_columns"]) - set(columns)
        if missing:
            raise ValueError(f"{filename}: missing columns {sorted(missing)}")
        rows = list(reader)
        if not 1 <= len(rows) <= config["thresholds"]["maximum_instruments_per_file"]:
            raise ValueError(f"{filename}: expected one to ten instruments")
        for row in rows:
            if None in row or any(row.get(k) is None or not row[k].strip() for k in config["required_columns"]):
                raise ValueError(f"{filename}: missing value or malformed row")
            ident = row["instrument_id"]
            if ident in seen:
                raise ValueError(f"{filename}: duplicate instrument ID {ident}")
            seen.add(ident)
            if row["as_of_date"] != run_date or row["portfolio"] != spec["name"]:
                raise ValueError(f"{filename}: date or portfolio mismatch")
            start, maturity = date.fromisoformat(row["start_date"]), date.fromisoformat(row["maturity_date"])
            if start > date.fromisoformat(run_date) or maturity < start:
                raise ValueError(f"{filename}: invalid chronological dates")
            for key in config["numeric_columns"]:
                row[key] = float(row[key])
                if not math.isfinite(row[key]) or row[key] < 0:
                    raise ValueError(f"{filename}: invalid numeric value in {key}")
            if row["currency"] not in config["currency_fx_to_usd"]:
                raise ValueError(f"{filename}: unsupported currency")
            for key in ("coupon_frequency", "principal_frequency"):
                if row[key] not in config["frequency_per_year"]:
                    raise ValueError(f"{filename}: unsupported {key}")
            if row["liquidity_requirement_pct"] != config["thresholds"]["lcr_requirement_pct"]:
                raise ValueError(f"{filename}: liquidity requirement differs from configuration")
            row["source_file"] = filename
            records.append(row)
        files.append({"file": filename, "rows": len(rows), "portfolio": spec["name"], "checks": ["schema", "required_values", "global_unique_ids", "date_and_portfolio", "chronology", "finite_nonnegative_numbers", "currency", "frequency", "liquidity_policy", "row_limit"]})
    return records, files


def weighted(rows, key):
    denominator = sum(abs(r["pv_usd_m"]) for r in rows)
    return sum(r[key] * abs(r["pv_usd_m"]) for r in rows) / denominator if denominator else 0.0


def calculate(rows, run_date, config, previous=None):
    instruments = []
    for original in rows:
        r = dict(original)
        tenor = max((date.fromisoformat(r["maturity_date"]) - date.fromisoformat(run_date)).days / 365.25, 1 / 365.25)
        fx = config["currency_fx_to_usd"][r["currency"]]
        frequency = config["frequency_per_year"][r["coupon_frequency"]]
        ytm = r["market_yield_pct"] / 100
        df = 1 / (1 + ytm / frequency) ** (tenor * frequency)
        pv = (r["book_value"] + r["principal"] * r["coupon_rate_pct"] / 100 * min(tenor, 5) * .35) * df
        duration = min(max(tenor * (.72 + .18 * df), .08), 12)
        modified = duration / (1 + ytm / frequency)
        shock = config["corona_scenario_shock_pct"][r["portfolio"]]
        outflow, buffer = r["net_cash_outflow_30d"] * fx, r["liquidity_buffer"] * fx
        values = {
            "remaining_years": tenor, "fx_to_usd": fx, "payments_per_year": frequency,
            "ytm_pct": r["market_yield_pct"], "discount_factor": df, "pv": pv,
            "duration": duration, "modified_duration": modified,
            "principal_usd_m": r["principal"] * fx, "book_value_usd_m": r["book_value"] * fx,
            "pv_usd_m": pv * fx, "liquidity_buffer_usd_m": buffer,
            "net_cash_outflow_30d_usd_m": outflow, "liquidity_coverage_pct": 100 * buffer / outflow if outflow else 999.,
            "corona_shock_pct": shock, "corona_scenario_pv_usd_m": pv * fx * (1 + shock / 100),
            "corona_loss_usd_m": pv * fx - pv * fx * (1 + shock / 100),
            "var_1d_contribution_usd_m": abs(pv * fx) * modified * config["rate_volatility_bps_by_date"][run_date] / 10000,
        }
        r.update({key: array_round6(value) for key, value in values.items()})
        r["liquidity_status"] = "MEETS" if values["liquidity_coverage_pct"] >= config["thresholds"]["lcr_requirement_pct"] else "BELOW"
        r["calculation_basis"] = "synthetic_deterministic_proxy"
        instruments.append(r)
    def total(key, group=instruments):
        return sum(r[key] for r in group)
    portfolios = []
    for spec in config["portfolios"]:
        group = [r for r in instruments if r["portfolio"] == spec["name"]]
        agg = {"portfolio": spec["name"], "instrument_count": len(group)}
        for key in ("principal_usd_m", "book_value_usd_m", "pv_usd_m", "liquidity_buffer_usd_m", "net_cash_outflow_30d_usd_m", "corona_scenario_pv_usd_m", "corona_loss_usd_m"):
            agg[key] = array_round6(total(key, group))
        for key in ("duration", "modified_duration", "ytm_pct", "discount_factor"):
            agg[key] = array_round6(weighted(group, key))
        flow = total("net_cash_outflow_30d_usd_m", group)
        agg["lcr_pct"] = array_round6(100 * total("liquidity_buffer_usd_m", group) / flow if flow else 999.)
        agg["var_1d_component_usd_m"] = array_round6(math.sqrt(sum(r["var_1d_contribution_usd_m"] ** 2 for r in group)))
        portfolios.append(agg)
    var = math.sqrt(sum(r["var_1d_contribution_usd_m"] ** 2 for r in instruments))
    lcr = 100 * total("liquidity_buffer_usd_m") / total("net_cash_outflow_30d_usd_m") if total("net_cash_outflow_30d_usd_m") else 999.
    metrics = {
        "instrument_count": len(instruments), "portfolio_count": len(portfolios),
        "total_book_value_usd_m": round(total("book_value_usd_m"), 6),
        "total_pv_usd_m": round(total("pv_usd_m"), 6), "var_1d_usd_m": round(var, 6), "var_5d_usd_m": round(var * math.sqrt(5), 6),
        "lcr_pct": round(lcr, 6), "lcr_requirement_pct": config["thresholds"]["lcr_requirement_pct"],
        "liquidity_buffer_usd_m": round(total("liquidity_buffer_usd_m"), 6),
        "net_cash_outflow_30d_usd_m": round(total("net_cash_outflow_30d_usd_m"), 6),
        "corona_scenario_pv_usd_m": round(total("corona_scenario_pv_usd_m"), 6), "corona_loss_usd_m": round(total("corona_loss_usd_m"), 6),
        "weighted_modified_duration": round(weighted(instruments, "modified_duration"), 9),
    }
    old = previous["metrics"] if previous else {}
    def change(current, prior):
        return 100 * (current - prior) / abs(prior) if prior else None
    trends = {
        "total_pv_change_pct": change(total("pv_usd_m"), old.get("total_pv_usd_m")),
        "var_1d_change_pct": change(var, old.get("var_1d_usd_m")),
        "lcr_change_ppts": lcr - old["lcr_pct"] if old else None,
    }
    warnings, thresholds = [], config["thresholds"]
    def warn(code, severity, title, message, metric, current, prior, threshold):
        warnings.append({"id": code, "severity": severity, "title": title, "message": message, "metric": metric, "current": round(current, 4), "previous": round(prior, 4) if prior is not None else None, "threshold": threshold})
    if lcr < metrics["lcr_requirement_pct"]:
        warn("LCR_REQUIREMENT", "CRITICAL", "Liquidity requirement not met", f"LCR is {lcr:.1f}% against the configured {metrics['lcr_requirement_pct']:.1f}% requirement.", "lcr_pct", lcr, old.get("lcr_pct"), metrics["lcr_requirement_pct"])
    if trends["lcr_change_ppts"] is not None and trends["lcr_change_ppts"] <= -thresholds["lcr_daily_drop_warning_ppts"]:
        warn("LCR_DROP", "HIGH", "Large daily LCR decline", f"LCR declined {abs(trends['lcr_change_ppts']):.1f} percentage points day over day.", "lcr_change_ppts", trends["lcr_change_ppts"], 0., thresholds["lcr_daily_drop_warning_ppts"])
    if trends["var_1d_change_pct"] is not None and abs(trends["var_1d_change_pct"]) >= thresholds["var_1d_change_warning_pct"]:
        warn("VAR_MOVEMENT", "HIGH", "Large one-day VaR proxy movement", f"One-day VaR proxy moved {trends['var_1d_change_pct']:+.1f}% versus the previous archived run.", "var_1d_change_pct", trends["var_1d_change_pct"], 0., thresholds["var_1d_change_warning_pct"])
    prior_portfolios = {r["portfolio"]: r for r in previous["portfolios"]} if previous else {}
    for p in portfolios:
        prior = prior_portfolios.get(p["portfolio"])
        movement = change(p["pv_usd_m"], prior["pv_usd_m"]) if prior else None
        if movement is not None and abs(movement) >= thresholds["portfolio_pv_change_warning_pct"]:
            warn("PV_" + p["portfolio"].upper().replace(" ", "_"), "HIGH", f"Large {p['portfolio']} PV movement", f"{p['portfolio']} PV moved {movement:+.1f}% day over day.", p["portfolio"] + "_pv_change_pct", movement, 0., thresholds["portfolio_pv_change_warning_pct"])
    return {
        "run_date": run_date, "status": "CRITICAL" if any(w["severity"] == "CRITICAL" for w in warnings) else "REVIEW" if warnings else "CLEAR",
        "metrics": metrics, "trends": {k: round(v, 6) if v is not None else None for k, v in trends.items()},
        "thresholds": thresholds, "warnings": warnings, "portfolios": portfolios, "instruments": instruments,
    }


def scenario(result, rate_bps=0., buffer_haircut_pct=0., outflow_increase_pct=0., label="Custom"):
    for value, low, high, name in ((rate_bps, -200, 500, "rate_bps"), (buffer_haircut_pct, 0, 100, "buffer_haircut_pct"), (outflow_increase_pct, 0, 200, "outflow_increase_pct")):
        if not math.isfinite(value) or not low <= value <= high:
            raise ValueError(f"{name} must be finite and between {low} and {high}")
    m = result["metrics"]
    stressed_pv = max(0., m["total_pv_usd_m"] * (1 - m["weighted_modified_duration"] * rate_bps / 10000))
    buffer = m["liquidity_buffer_usd_m"] * (1 - buffer_haircut_pct / 100)
    flow = m["net_cash_outflow_30d_usd_m"] * (1 + outflow_increase_pct / 100)
    lcr = 100 * buffer / flow if flow else 999.
    return {"label": label, "rate_bps": rate_bps, "buffer_haircut_pct": buffer_haircut_pct, "outflow_increase_pct": outflow_increase_pct,
            "pv_change_usd_m": round(stressed_pv - m["total_pv_usd_m"], 6), "stressed_pv_usd_m": round(stressed_pv, 6),
            "liquidity_buffer_usd_m": round(buffer, 6), "net_cash_outflow_30d_usd_m": round(flow, 6),
            "lcr_pct": round(lcr, 6), "liquidity_gap_usd_m": round(max(0., flow * m["lcr_requirement_pct"] / 100 - buffer), 6),
            "status": "BREACH" if lcr < m["lcr_requirement_pct"] else "MEETS", "method": "first_order_duration_sensitivity_and_synthetic_liquidity; baseline VaR is not recalculated"}
