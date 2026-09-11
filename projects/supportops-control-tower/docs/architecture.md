# Architecture and control boundaries

## Identity and lineage

The run identity is SHA-256 over canonical JSON containing the date, aggregate source-file hashes, canonical configuration hash, operational Python source hash, previous run ID and previous result-file hash. The directory name uses the first 16 hexadecimal identity characters; the full digest is retained and checked to reject a prefix collision. Source ordering and JSON key ordering are stable.

The first date has no predecessor. Later dates pin the exact prior result used in day-over-day warnings. Every downstream action revalidates that the prior result still matches its stored hash and that the previous date is current with respect to source data, config and code. `all` executes the required dates chronologically. A standalone later-date stage fails if a prerequisite is stale or unavailable.

## Intake gate

CSV bytes are read once into memory, validated and then copied from those same bytes. Checks cover all required fields, one to ten rows per file, unique ticket IDs across the whole date, matching date/queue, a submission timestamp within the run date, finite nonnegative numeric fields, and controlled vocabularies for channel, customer tier, region, reported priority and symptom code. Each fixture is copied without changing its bytes. Configuration is serialized as a canonical-value snapshot. The manifest is hashed into SQLite before a stage can reuse it.

The three queues preserve their filed names and inputs. Routing correction, priority scoring and SLA evaluation happen downstream in Triage, not during Intake — Intake only validates that the *filed* data is well-formed; it does not yet know where a ticket should actually route.

## Execution state and recovery

SQLite stores historical run IDs, active date pointers, stage checkpoints, trusted artifact hashes, events and failed command attempts. The normal transitions are INTAKEN → TRIAGE_COMPLETED → COMPLETED. A started stage is RUNNING; an execution exception marks that exact stage and run FAILED and records an error event. Resume verifies all committed prerequisites and reruns only an uncommitted or failed stage. Completed checkpoints are reused without new outputs or log events.

Output files are written to a temporary sibling, flushed and atomically replaced. Only after output files exist are their hashes committed as a stage checkpoint. If execution stops before that checkpoint, the uncommitted files can be overwritten during resume. A CLI-level OS advisory file lock prevents simultaneous commands from racing in one workspace and is released by the OS on process exit. Python callers should use `with engine.lock()` around command sequences.

Filesystem writes and SQLite are not one distributed transaction. An abrupt interruption between event persistence and log-file replacement can leave a detectable mismatch; verification then stops for inspection. An unregistered partial intake directory is also preserved and rejected. This intentionally favors evidence preservation over automatic deletion or guessed recovery. Archive copies and registry backups belong together; restoring only one can invalidate evidence.

## Evidence checks and trust

Before Triage, Brief, whatif or export, verification rehashes input/config snapshots, completed-stage artifacts and logs. Log bytes are compared to canonical events stored in SQLite. A report therefore cannot silently narrate altered metrics. Old immutable snapshots remain verifiable, but only current active runs can be exported into a new dashboard bundle.

The registry is a trusted local reference. There are no external signatures, object-store retention policies, multi-user permissions, remote backups, secret stores, enterprise monitoring or production ticketing-system integration in this package. Physical file permissions do not make archives write-proof; unauthorized modifications are detected relative to the registry.

## Routing, priority and briefing

Routing is a fixed `symptom_code → (implied_queue, assigned_team)` lookup table; a ticket whose filed queue disagrees with its implied queue is corrected and logged as `MISROUTED_TICKET`, with both values retained. Effective priority starts from a reported-priority baseline, is floored by a small set of high-severity symptom codes, and is bumped by fixed threshold rules over sentiment, reopen count and customer tier — every rule that fires is recorded on the ticket, not just the final value, so the dashboard can show *why*. None of this logic ever reads the ticket's free-text `important_note` field; a dedicated control test (`test_injected_instruction_text_ignored`) proves routing, priority, SLA and assistant output are byte-identical whether or not that field contains embedded instruction-like text.

The decision planner is a fixed registered tool sequence with explicit prerequisites and reasons. An ops handoff is generated from verified metrics and warnings using a deterministic template. Every numerical fact cites its result JSON field. `validate-handoff` accepts only exactly matching structured facts, warnings and pending approval status; even accepted externally authored prose is labeled UNVERIFIED_DRAFT. This provides a clear integration boundary without claiming unimplemented AI behavior.
