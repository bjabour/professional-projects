# SupportOps Control Tower

[Interactive dashboard](index.html) · [Seven-slide case study](presentation/index.html) · [Download source](source.zip) · [Website integration notes](docs/PORTFOLIO_INTEGRATION.md)

A portable, reproducible daily ticket-triage and routing workflow. Three small synthetic ticket batches become verified routing decisions, explicit SLA/capacity warnings, an ops handoff, and a portfolio dashboard data bundle. The engineering upgrade adds content-based run identities, predecessor lineage, persisted checkpoints, a SQLite registry, integrity checks, safe resume, execution logs and independently runnable control tests.

**Scope:** 1–3 September 2026, roughly 17 tickets per date across 3 queues: Billing, Technical and Account & Access. Every duration is in minutes. Routing rules, priority scoring, SLA targets and staffing capacity are fixed demonstration proxies.

## Requirements and installation

Python 3.10 or newer. Everything uses Python's standard library; no pip packages, account, API key or network connection are required. Tested on Python 3.14 for Windows. The CLI uses OS file locking and SQLite included with Python.

The prebuilt dashboard and case study need only a modern browser with JavaScript. Rebuilding the portfolio pages or running browser-logic tests additionally requires Node.js 18 or newer; no npm installation is required. There is no requirements-install command because the engine has no third-party Python dependencies.

Extract the source package and open a terminal in this directory. Confirm Python is available:

```powershell
python --version
```

## Run the demonstration

```powershell
python scripts/supportops.py all --all-dates
python scripts/supportops.py verify --all-dates
python scripts/supportops.py status
```

`all` runs Intake → Triage → Brief in chronological order. The first execution creates three run directories and `results/dashboard-data.json`. Repeating the same command reuses verified completed checkpoints and preserves the exact artifact bytes, run IDs and logs. There is no destructive `--replace` option. Changes to valid data, configuration or operational code create new run identities while preserving the earlier runs.

A single-date command also establishes its earlier-date dependencies:

```powershell
python scripts/supportops.py all --run-date 2026-09-03
```

## Run stages separately

For a fresh workspace, process one date at a time:

```powershell
python scripts/supportops.py intake --run-date 2026-09-01
python scripts/supportops.py triage --run-date 2026-09-01
python scripts/supportops.py brief --run-date 2026-09-01
```

Continue with September 2 and then September 3. Intake for a later date requires the previous date's completed Triage checkpoint so its identity can include the exact comparison result. `intake --all-dates` is supported only when those predecessor Triage checkpoints already exist and remain current; a fresh batch request is rejected before creating partial runs. Use `all --all-dates` for initial batch execution.

| Command | Purpose |
| --- | --- |
| `intake` | Validate CSV schemas and rows; copy the validated bytes; snapshot config; persist hashes, lineage and a validation manifest. |
| `triage` | Verify intake evidence; classify and route each ticket; evaluate SLA and capacity; evaluate transparent warning rules. |
| `brief` | Verify triage results; create a deterministic ops handoff, what-if grid and tool-plan trace; refresh the combined JSON export. |
| `all` | Execute dependencies and all stages, reusing valid completed checkpoints. |
| `plan` | Explain the three registered tools, their prerequisites, outputs and selection reasons. |
| `status` | List all historical run IDs, active versions, stages' overall status, integrity and recent failed attempts. |
| `verify` | Rehash snapshots, committed artifacts and logs, check predecessor lineage and compare to current data/config/code. |
| `whatif` | Apply a linear staffing-capacity and ticket-volume sensitivity to verified baseline results. |
| `validate-handoff` | Check externally authored structured facts, warnings and approval status against verified results; leave free text explicitly unverified. |

Use `--workspace PATH` to place data/config/runs in another directory. It must contain `data/YYYY-MM-DD/*.csv` and `config/support_parameters.json`. Code is still loaded from this package. Run commands from any working directory by giving the full path to `scripts/supportops.py`.

## Explore a what-if scenario

```powershell
python scripts/supportops.py whatif --run-date 2026-09-03 --capacity-change-pct 15 --sla-threshold-pct 100 --volume-increase-pct 0
```

Capacity change accepts −30 to +30 percent, SLA threshold 80–120 percent of the configured requirement, and volume increase 0–100 percent. The calculation is a linear adjustment to staffed minutes and required handling minutes; it does not re-route tickets or recompute priority or SLA status. Capacity coverage uses the adjusted staffed minutes divided by adjusted required handling minutes. The capacity gap is the positive shortfall against the effective requirement. The browser portfolio experience exposes the same bounds.

## Run the actual control checks

```powershell
python scripts/check_controls.py
```

This creates isolated temporary workspaces and exercises the real engine and CLI. `results/control-checks.json` records pass/fail results, durations, source hashes and test descriptions. Checks include archived baseline regression, idempotency, failure/resume, missing data, global duplicate IDs, non-finite rejection, data/config/code drift, stale predecessors, input/result/log tampering, stage order, concurrent command rejection, handoff fact enforcement, what-if behavior, portable exports, routing-rule regression, misrouted-ticket reclassification, SLA-boundary accuracy, capacity-shortfall detection, and injected-instruction-text resistance.

## Outputs and structure

```text
supportops-control-tower/
  README.md
  config/support_parameters.json
  data/2026-09-{01,02,03}/       original synthetic fixtures
  supportops/                  standard-library engine and rules
  scripts/supportops.py         command interface
  scripts/check_controls.py    executable test evidence
  tests/expected/              archived regression references
  docs/                       design and portfolio integration notes
  registry.sqlite3             run metadata, active pointers, events, failures
  runs/SUP-YYYYMMDD-HASH/      immutable inputs/config and committed outputs
  results/dashboard-data.json combined portable dashboard data
  results/control-checks.json  real test evidence
  web/                        editable dashboard and story templates
  presentation/               seven-slide case study and reusable styles
  index.html                  self-contained interactive dashboard
  source.zip                  curated source, fixtures, tests and evidence
  project.json                website card metadata and taxonomy
```

Each run includes input CSV snapshots, `config.json`, `manifest.json`, `validation.json`, `result.json`, `brief.json`, `ops-handoff.md`, `whatif-grid.json`, `tool-plan.json`, structured `logs/events.jsonl` and readable `logs/run.log`. Logs go to stderr while command results are JSON on stdout. Exit code 0 means success, 1 a data/control/execution failure and 2 invalid command arguments. A capacity status of CRITICAL is a successful detection outcome, not an execution failure.

## Rebuild the portfolio experience

Run these commands from this project directory:

```powershell
python scripts/supportops.py all --all-dates
python scripts/supportops.py verify --all-dates
python scripts/check_controls.py
node --test tests/browser.test.cjs
python scripts/build_portfolio.py
node scripts/presentation/validate_report.mjs --input presentation/index.html
python scripts/validate_portfolio.py
```

The build refuses failed or stale control evidence and exports whose engine version differs from the tested source. It embeds the three recorded runs and all control results in the dashboard; it derives case-study figures from those same results. The HTML build does not execute the pipeline.

Inside this website's `projects/` structure, the builder updates `supportops-control-tower.html` and `supportops-control-tower-case-study.html` at the website root, alongside this project's `index.html`, `presentation/index.html`, and `source.zip`. When the source is extracted elsewhere, website-root exports are safely written inside the project's `portfolio-export/` directory instead. No files outside the extracted project are changed.

The source download excludes local registry, run folders, caches and environment files. These are recreated by the CLI. Final portable JSON evidence is included. Historical run timestamps and durations naturally differ on fresh executions; routing, priority, SLA and capacity outputs remain reproducible with identical source, configuration and inputs.

### What the browser does

- Compare all three dates; inspect warnings and individual tickets.
- Explore staffing-capacity and ticket-volume shocks without changing recorded results.
- Inspect source hashes, metric lineage and the actual control-check report.
- Replay saved execution logs; this is playback, not a live Python job.
- Generate fixed-template explanations from selected run facts and export the handoff brief.

The dashboard is static and portable. To see new Python runs in it, rebuild the HTML. It does not launch commands, call an LLM, persist approvals, or connect to a live ticketing system.

## Interpretation

The demonstration models a mid-size company's support operation; no real company, vendor or ticketing platform is named. Effective priority, SLA targets, handle-time estimates, and staffing capacity are fixed proxy lookups, not a calibrated workforce-management model. `sentiment_score` is a fixed illustrative proxy, not the output of a real NLP model. The final date intentionally produces a capacity coverage of **96.3%**, below the 100% demonstration requirement, driven by an outage-report cluster in the Technical queue combined with a configured overnight staffing gap; it carries 8 warnings, including one corrected misrouted ticket and two priority escalations.

The orchestration and briefing are **rules based**. No live language model is called. A ticket's free-text `important_note` field is explicitly never read as an instruction by any rule, calculation or the bounded assistant — only structured columns drive routing, priority, SLA and capacity outcomes; this is verified by a dedicated control test. An external model could draft structured facts through the validation boundary, but accepted numeric fields do not validate arbitrary prose. All handoffs stay `PENDING_HUMAN_REVIEW`.

The local SQLite registry is the integrity reference, not a cryptographically signed external ledger. An administrator who can alter both artifacts and the registry is outside the demonstrated trust boundary. See [architecture](docs/architecture.md) for checkpoint and recovery details and [portfolio integration](docs/PORTFOLIO_INTEGRATION.md) for the JSON contract.
