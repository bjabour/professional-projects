# Portfolio integration: SupportOps Control Tower

This package is saved inside the website repository alongside RiskOps Control Tower. Both sit in the **Automation & Engineering** section of the homepage. The local landing page links to the new console next to the existing one.

## Entry points

| Item | Path from website root | Purpose |
| --- | --- | --- |
| Interactive console | supportops-control-tower.html | Primary portfolio experience |
| Engineering case study | supportops-control-tower-case-study.html | Seven-slide project explanation |
| Project package | projects/supportops-control-tower/ | Portable source, data, tests, and evidence |
| Metadata | projects/supportops-control-tower/project.json | Reusable project card and taxonomy |
| Source download | projects/supportops-control-tower/source.zip | Reproducible source bundle |

Both website-root HTML pages embed their CSS, JavaScript, and demonstration data. They work as static GitHub Pages files without a backend or external JavaScript dependency. Navigation links assume this repository structure; the pages can still be viewed independently.

## Card copy

- **Title:** SupportOps Control Tower
- **Category:** Automation & Engineering
- **Subtitle:** Reproducible ticket-triage workflows, staffing what-if analysis, and evidence-linked reporting
- **Tags:** Python, SQLite, data contracts, orchestration, audit trails, scenario analysis, bounded assistant, rule-based classification

A reproducible daily ticket-triage workflow with versioned runs, verified snapshots, resumable stages, and a bounded ops assistant. Explore three archived dates, trace a misrouted ticket and its correction, and stress staffing capacity in an interactive control tower. All tickets and staffing figures are synthetic.

## What this adds to the portfolio

RiskOps Control Tower demonstrates this engineering pattern in a financial-risk domain. This project demonstrates the same caliber of work applied to a distinct, clearly "company-facing" operations problem:

- **Systems engineering:** persistent run state, stage prerequisites, content identities, and controlled resume — identical rigor, different domain.
- **Data engineering:** strict contracts, source snapshots, controlled vocabularies, and cross-file validation.
- **Rule-based classification:** deterministic routing correction and explainable priority scoring, with every fired rule recorded for the UI to trace.
- **Operational controls:** failure diagnostics, verified artifacts, chronological lineage, and testable behavior — including a **prompt-injection-resistance control test**, a differentiator beyond the RiskOps precedent, proving a ticket's free-text field can never influence routing, priority, SLA or assistant output.
- **Decision interfaces:** exception queues, ticket drill-down with routing rationale, live staffing/volume sensitivity controls, and evidence export.
- **AI system design:** a bounded reporting contract with explicit authority and factual references; the supplied implementation runs in deterministic mode.

Keep **Automation & Engineering** as the shared navigation category between this project and RiskOps. Avoid adding empty sections until they have completed projects.

## Truthful claims

The package supports claims about implemented controls and observed behavior on synthetic fixtures. The control-test report and dashboard evidence are generated from the included implementation. Read test counts from `results/control-checks.json` rather than copying them permanently into the project card.

Do not describe this as employer work, a production support desk, a live LLM agent, or a real workforce-management system. `sentiment_score` is a fixed illustrative proxy, not the output of a real NLP or ML sentiment model. Handle-time and SLA-target tables are fixed demonstration lookups, not measured historical average handle time. `source_system` values are synthetic tags and never imply a real vendor or platform integration (no claim of Zendesk, Salesforce, Freshdesk, or any named ticketing system). No real company, employer or customer is named anywhere in the dataset or copy. Capacity Coverage Ratio (CCR) figures are demonstration proxies for a staffing model, not a calibrated capacity-planning system.

## Suggested 45-second explanation

"I took the same engineering discipline I built for a financial-risk workflow and applied it to a different, very company-relevant problem: ticket triage and routing. The workflow validates a daily ticket batch, corrects misrouted tickets against a rules table, scores an explainable priority, and evaluates staffing capacity against required handling time. Every run pins its input data, configuration, code, and preceding result into a run identity, and can resume without silently replacing completed evidence. A ticket's free-text notes are explicitly never read as instructions — I wrote a dedicated test that proves an embedded prompt-injection attempt changes nothing about the outcome. The dashboard lets someone trace a routing decision to the rule that fired, explore a staffing shock, and inspect the recorded tool plan. The ops assistant uses verified facts and fixed templates in this demonstration, with human review kept separate from technical completion."

## Refresh and future publication

Use the commands in the project README to run the engine, execute control checks, and rebuild the two HTML pages and source bundle. The build embeds the latest exported evidence and the current control-check report.

This change is saved locally. Publishing or pushing the website is a separate action. During a future website redesign, preserve relative entry-point paths or update the card, metadata, and navigation links together.
