# Portfolio integration: RiskOps Control Tower

This package is saved inside the website repository so it can be carried into a later redesign. The existing three modeling projects are preserved. The local landing page adds an **Automation & Engineering** section with a link to the new console.

## Entry points

| Item | Path from website root | Purpose |
| --- | --- | --- |
| Interactive console | riskops-control-tower.html | Primary portfolio experience |
| Engineering case study | riskops-control-tower-case-study.html | Seven-slide project explanation |
| Project package | projects/riskops-control-tower/ | Portable source, data, tests, and evidence |
| Metadata | projects/riskops-control-tower/project.json | Reusable project card and taxonomy |
| Source download | projects/riskops-control-tower/source.zip | Reproducible source bundle |

Both website-root HTML pages embed their CSS, JavaScript, and demonstration data. They work as static GitHub Pages files without a backend or external JavaScript dependency. Navigation links assume this repository structure; the pages can still be viewed independently.

## Card copy

- **Title:** RiskOps Control Tower
- **Category:** Automation & Engineering
- **Subtitle:** Reproducible risk workflows, scenario analysis, and evidence-linked reporting
- **Tags:** Python, SQLite, data contracts, orchestration, audit trails, scenario analysis, bounded assistant

A reproducible daily risk workflow with versioned runs, verified snapshots, resumable stages, and a bounded reporting assistant. Explore three archived dates, trace five material warnings, and stress liquidity in an interactive control tower. All positions and financial proxies are synthetic.

## What this adds to the portfolio

The existing portfolio emphasizes model selection and prediction. This project demonstrates a different set of capabilities:

- **Systems engineering:** persistent run state, stage prerequisites, content identities, and controlled resume.
- **Data engineering:** strict contracts, source snapshots, finite-value checks, and cross-file validation.
- **Operational controls:** failure diagnostics, verified artifacts, chronological lineage, and testable behavior.
- **Decision interfaces:** exception queues, instrument drill-down, live sensitivity controls, and evidence export.
- **AI system design:** a bounded reporting contract with explicit authority and factual references; the supplied implementation runs in deterministic mode.

Keep **Data Science & Prediction**, **Automation & Engineering**, and **Financial Risk** as reusable project tags. Use the first two as current navigation categories. Avoid adding empty sections until they have completed projects.

## Truthful claims

The package supports claims about implemented controls and observed behavior on three small synthetic fixtures. The control-test report and dashboard evidence are generated from the included implementation. Read test counts from results/control-checks.json rather than copying them permanently into the project card.

Do not describe this as employer work, a production banking system, a live LLM agent, a regulated LCR engine, or measured time savings. The inherited numerical model is deliberately a proxy. “VaR proxy” has no explicit confidence calibration; market yield is an input; gross PV does not net bank assets and liabilities.

## Suggested 45-second explanation

“I started with a simple daily risk-reporting script and upgraded the operating controls around it. The workflow now pins the input data, configuration, code, and preceding result into a run identity. It verifies the artifacts consumed by each stage and can resume without silently replacing completed evidence. The dashboard lets someone trace an exception to its source, explore a liquidity shock, and inspect the recorded tool plan. The reporting assistant uses verified facts and fixed templates in this demonstration, with human review kept separate from technical completion.”

## Refresh and future publication

Use the commands in the project README to run the engine, execute control checks, and rebuild the two HTML pages and source bundle. The build embeds the latest exported evidence and the current control-check report.

This change is saved locally. Publishing or pushing the website is a separate action. During a future website redesign, preserve relative entry-point paths or update the card, metadata, and navigation links together.
