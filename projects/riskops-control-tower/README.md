# RiskOps Control Tower

[Interactive dashboard](index.html) · [Seven-slide case study](presentation/index.html) · [Download source](source.zip) · [Website integration notes](docs/PORTFOLIO_INTEGRATION.md)

A portable, reproducible upgrade of the original daily risk automation example. Three small synthetic portfolio files become verified results, explicit warnings, a leadership handoff and a portfolio dashboard data bundle. The engineering upgrade adds content-based run identities, predecessor lineage, persisted checkpoints, a SQLite registry, integrity checks, safe resume, execution logs and independently runnable control tests.

**Scope:** 27–29 August 2026, 17 instruments per date: 6 Deposits, 6 Mortgages and 5 Current Account instruments. Every amount is in millions; reporting is in USD, using the original fixed demonstration FX rates. Original CSV fixtures and six-decimal baseline outputs are retained.

## Requirements and installation

Python 3.10 or newer. Everything uses Python's standard library; no pip packages, account, API key or network connection are required. Tested on Python 3.14 for Windows. The CLI uses OS file locking and SQLite included with Python.

The prebuilt dashboard and case study need only a modern browser with JavaScript. Rebuilding the portfolio pages or running browser-logic tests additionally requires Node.js 18 or newer; no npm installation is required. There is no requirements-install command because the engine has no third-party Python dependencies.

Extract the source package and open a terminal in this directory. Confirm Python is available:

```powershell
python --version
```

## Run the demonstration

```powershell
python scripts/riskops.py all --all-dates
python scripts/riskops.py verify --all-dates
python scripts/riskops.py status
```

`all` runs Prepare → ETL → Report in chronological order. The first execution creates three run directories and `results/dashboard-data.json`. Repeating the same command reuses verified completed checkpoints and preserves the exact artifact bytes, run IDs and logs. There is no destructive `--replace` option. Changes to valid data, configuration or operational code create new run identities while preserving the earlier runs.

A single-date command also establishes its earlier-date dependencies:

```powershell
python scripts/riskops.py all --run-date 2026-08-29
```

## Run stages separately

For a fresh workspace, process one date at a time:

```powershell
python scripts/riskops.py prepare --run-date 2026-08-27
python scripts/riskops.py run-etl --run-date 2026-08-27
python scripts/riskops.py report --run-date 2026-08-27
```

Continue with August 28 and then August 29. Prepare for a later date requires the previous date's completed ETL checkpoint so its identity can include the exact comparison result. `prepare --all-dates` is supported only when those predecessor ETL checkpoints already exist and remain current; a fresh batch request is rejected before creating partial runs. Use `all --all-dates` for initial batch execution.

| Command | Purpose |
| --- | --- |
| `prepare` | Validate CSV schemas and rows; copy the validated bytes; snapshot config; persist hashes, lineage and a validation manifest. |
| `run-etl` | Verify prepared evidence; calculate the accepted v1 proxies; evaluate transparent change and liquidity rules. |
| `report` | Verify ETL results; create a deterministic leadership brief, scenario grid and tool-plan trace; refresh the combined JSON export. |
| `all` | Execute dependencies and all stages, reusing valid completed checkpoints. |
| `plan` | Explain the three registered tools, their prerequisites, outputs and selection reasons. |
| `status` | List all historical run IDs, active versions, stages' overall status, integrity and recent failed attempts. |
| `verify` | Rehash snapshots, committed artifacts and logs, check predecessor lineage and compare to current data/config/code. |
| `scenario` | Apply a first-order rate sensitivity and synthetic liquidity changes to verified baseline results. |
| `validate-brief` | Check externally authored structured facts, warnings and approval status against verified results; leave free text explicitly unverified. |

Use `--workspace PATH` to place data/config/runs in another directory. It must contain `data/YYYY-MM-DD/*.csv` and `config/risk_parameters.json`. Code is still loaded from this package. Run commands from any working directory by giving the full path to `scripts/riskops.py`.

## Explore a scenario

```powershell
python scripts/riskops.py scenario --run-date 2026-08-29 --rate-bps 100 --buffer-haircut-pct 5 --outflow-increase-pct 10
```

Rates accept −200 to +500 basis points, buffer haircut 0–100%, and outflow increase 0–200%. The calculation uses baseline PV × (1 − weighted modified duration × rate shock), floored at zero. Liquidity coverage uses the reduced buffer divided by increased outflow. The liquidity gap is the positive buffer shortfall against the configured requirement. This sensitivity does not revalue cash flows or recalculate VaR. The browser portfolio experience may intentionally expose narrower slider ranges.

## Run the actual control checks

```powershell
python scripts/check_controls.py
```

This creates isolated temporary workspaces and exercises the real engine and CLI. `results/control-checks.json` records pass/fail results, durations, source hashes and test descriptions. Checks include archived baseline regression, idempotency, failure/resume, missing data, global duplicate IDs, NaN rejection, data/config/code drift, stale predecessors, input/result/log tampering, stage order, concurrent command rejection, brief fact enforcement, scenario behavior and portable exports.

## Outputs and structure

```text
riskops-control-tower/
  README.md
  config/risk_parameters.json
  data/2026-08-{27,28,29}/       original synthetic fixtures
  riskops/                     standard-library engine and arithmetic
  scripts/riskops.py            command interface
  scripts/check_controls.py    executable test evidence
  tests/expected/              archived v1 regression references
  docs/                       design and portfolio integration notes
  registry.sqlite3             run metadata, active pointers, events, failures
  runs/RISK-YYYYMMDD-HASH/      immutable inputs/config and committed outputs
  results/dashboard-data.json combined portable dashboard data
  results/control-checks.json  real test evidence
  web/                        editable dashboard and story templates
  presentation/               seven-slide case study and reusable styles
  index.html                  self-contained interactive dashboard
  source.zip                  curated source, fixtures, tests and evidence
  project.json                website card metadata and taxonomy
```

Each run includes input CSV snapshots, `config.json`, `manifest.json`, `validation.json`, `result.json`, `brief.json`, `leadership-handoff.md`, `scenarios.json`, `tool-plan.json`, structured `logs/events.jsonl` and readable `logs/run.log`. Logs go to stderr while command results are JSON on stdout. Exit code 0 means success, 1 a data/control/execution failure and 2 invalid command arguments. A risk status of CRITICAL is a successful detection outcome, not an execution failure.

## Rebuild the portfolio experience

Run these commands from this project directory:

```powershell
python scripts/riskops.py all --all-dates
python scripts/riskops.py verify --all-dates
python scripts/check_controls.py
node --test tests/browser.test.cjs
python scripts/build_portfolio.py
node scripts/presentation/validate_report.mjs --input presentation/index.html
python scripts/validate_portfolio.py
```

The build refuses failed or stale control evidence and exports whose engine version differs from the tested source. It embeds the three recorded runs and all control results in the dashboard; it derives case-study figures from those same results. The HTML build does not execute the pipeline.

Inside this website's `projects/` structure, the builder updates `riskops-control-tower.html` and `riskops-control-tower-case-study.html` at the website root, alongside this project's `index.html`, `presentation/index.html`, and `source.zip`. When the source is extracted elsewhere, website-root exports are safely written inside the project's `portfolio-export/` directory instead. No files outside the extracted project are changed.

The source download excludes local registry, run folders, caches and environment files. These are recreated by the CLI. Final portable JSON evidence is included. Historical run timestamps and durations naturally differ on fresh executions; financial outputs and evidence-based identities remain reproducible with identical source, configuration and inputs.

### What the browser does

- Compare all three dates; inspect warnings and individual positions.
- Explore rate and liquidity shocks without changing recorded results.
- Inspect source hashes, metric lineage and the actual control-check report.
- Replay saved execution logs; this is playback, not a live Python job.
- Generate fixed-template explanations from selected run facts and export the handoff brief.

The dashboard is static and portable. To see new Python runs in it, rebuild the HTML. It does not launch commands, call an LLM, persist approvals, or connect to live financial systems.

## Interpretation

The demonstration preserves the original financial proxy formulas. Deposits and accounts are positive gross exposures; their sum is **not net bank economic value of equity**. The VaR proxy has no calibrated confidence level; synthetic LCR is not a regulatory compliance result. The Corona haircut is a fixed stress illustration. The final date intentionally produces an LCR of 91.798196%, below the 100% demonstration requirement, and five warnings.

The orchestration and briefing are **rules based**. No live language model is called. An external model could draft structured facts through the validation boundary, but accepted numeric fields do not validate arbitrary prose. All briefs stay `PENDING_HUMAN_REVIEW`.

The local SQLite registry is the integrity reference, not a cryptographically signed external ledger. An administrator who can alter both artifacts and the registry is outside the demonstrated trust boundary. See [architecture](docs/architecture.md) for checkpoint and recovery details and [portfolio integration](docs/portfolio-integration.md) for the JSON contract.
