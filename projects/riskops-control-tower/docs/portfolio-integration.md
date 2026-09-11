# Portfolio integration

Copy the portable `results/dashboard-data.json` and `results/control-checks.json` into the website's project asset directory. Link a ZIP of this complete source package for technical reviewers. The engine does not publish, modify a website checkout or require a browser server.

`dashboard-data.json` uses schema version `2.0`:

- Top level: `project`, `mode`, `reporting_currency`, `currency_unit`, `supported_dates`, `dates`, `controls`, `methodology`.
- Each date: `run_date`, `run_id`, risk `status`, `execution_status`, `metrics`, `trends`, `warnings`, `portfolios`, `instruments`, `stages`, `logs`, `provenance`, `plan`, `brief`, `scenario_grid`, `source_mapping`, `important_notes`.
- Metrics preserve the original snake_case USD-million keys; `weighted_modified_duration` is added for sensitivity exploration.
- Warnings have stable `id`, `severity`, `title`, `message`, `metric`, `current`, `previous` and `threshold` fields. The brief includes the same complete warning list.
- Stages have `stage`, `status`, `duration_seconds`, `artifact_count`. Logs include actual UTC timestamps, sequence numbers, events and details.
- Provenance includes data/config/code hashes, full identity digest, previous run/result identity and source file row counts/hashes. All file references are portable relative references; no absolute local paths are exported.
- Scenario records include shock parameters, `stressed_pv_usd_m`, `pv_change_usd_m`, `lcr_pct`, `liquidity_gap_usd_m` and status. A positive liquidity gap is a deficit. `var_1d_usd_m` is deliberately absent from scenario outputs because the scenario model does not produce a new VaR estimate.

`control-checks.json` uses schema version `1.0`, with generation time, command, operational source hash, test-source hash, total/passed/failed counts and `checks[]`. Each check has a stable ID, test name, description, real status and duration. The website should describe these as recorded test evidence, not live server tests or simulated runs.

Suggested portfolio story: fragmented daily files → explicit control gates → reproducible results → material-exception review → traceable handoff. The project illustrates data engineering, stateful orchestration, validation, observability, risk-domain communication and interactive scenario design. It does not claim real institutional deployments, financial performance improvements, production regulatory models or a live AI agent.
