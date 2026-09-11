# Architecture and control boundaries

## Identity and lineage

The run identity is SHA-256 over canonical JSON containing the date, aggregate source-file hashes, canonical configuration hash, operational Python source hash, previous run ID and previous result-file hash. The directory name uses the first 16 hexadecimal identity characters; the full digest is retained and checked to reject a prefix collision. Source ordering and JSON key ordering are stable.

The first date has no predecessor. Later dates pin the exact prior result used in day-over-day warnings. Every downstream action revalidates that the prior result still matches its stored hash and that the previous date is current with respect to source data, config and code. `all` executes the required dates chronologically. A standalone later-date stage fails if a prerequisite is stale or unavailable.

## Prepare gate

CSV bytes are read once into memory, validated and then copied from those same bytes. Checks cover all required fields, one to ten rows per file, unique IDs across the whole date, matching date/portfolio, parseable ordered dates, finite nonnegative numeric fields, supported currencies and frequencies, and the configured liquidity requirement. Each fixture is copied without changing its bytes. Configuration is serialized as a canonical-value snapshot. The manifest is hashed into SQLite before a stage can reuse it.

The three portfolios preserve their original names and inputs. Indexation, principal frequency and instrument type remain explicit modeling attributes but are not implemented as full cash-flow mechanics in the v1 proxy math. Coupon frequency affects the proxy discount factor. A production model would need proper contractual and behavioral cash flows, asset/liability signs and governed assumptions.

## Execution state and recovery

SQLite stores historical run IDs, active date pointers, stage checkpoints, trusted artifact hashes, events and failed command attempts. The normal transitions are PREPARED → ETL_COMPLETED → COMPLETED. A started stage is RUNNING; an execution exception marks that exact stage and run FAILED and records an error event. Resume verifies all committed prerequisites and reruns only an uncommitted or failed stage. Completed checkpoints are reused without new outputs or log events.

Output files are written to a temporary sibling, flushed and atomically replaced. Only after output files exist are their hashes committed as a stage checkpoint. If execution stops before that checkpoint, the uncommitted files can be overwritten during resume. A CLI-level OS advisory file lock prevents simultaneous commands from racing in one workspace and is released by the OS on process exit. Python callers should use `with engine.lock()` around command sequences.

Filesystem writes and SQLite are not one distributed transaction. An abrupt interruption between event persistence and log-file replacement can leave a detectable mismatch; verification then stops for inspection. An unregistered partial preparation directory is also preserved and rejected. This intentionally favors evidence preservation over automatic deletion or guessed recovery. Archive copies and registry backups belong together; restoring only one can invalidate evidence.

## Evidence checks and trust

Before ETL, report, scenario or export, verification rehashes input/config snapshots, completed-stage artifacts and logs. Log bytes are compared to canonical events stored in SQLite. A report therefore cannot silently narrate altered metrics. Old immutable snapshots remain verifiable, but only current active runs can be exported into a new dashboard bundle.

The registry is a trusted local reference. There are no external signatures, object-store retention policies, multi-user permissions, remote backups, secret stores, enterprise monitoring or production scheduler in this package. Physical file permissions do not make archives write-proof; unauthorized modifications are detected relative to the registry.

## Arithmetic and briefing

The stdlib implementation reproduces the original NumPy/pandas scale-and-round behavior where the baseline rounded per-instrument arrays. Regression tests compare every original summary metric and portfolio metric to the archived v1 references to six decimals.

The decision planner is a fixed registered tool sequence with explicit prerequisites and reasons. A leadership brief is generated from verified metrics and warnings using a deterministic template. Every numerical fact cites its result JSON field. `validate-brief` accepts only exactly matching structured facts, warnings and pending approval status; even accepted externally authored prose is labeled UNVERIFIED_DRAFT. This provides a clear integration boundary without claiming unimplemented AI behavior.
