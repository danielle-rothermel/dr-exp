# dr_exp package

A thin layer over dr-platform (durable queue and ledger) and dr-exec (isolated
child-process execution). See the repository `README.md` for the user-facing
contract and `CLAUDE.md` for the invariants that constrain edits here.

Subpackages:

- `config/` — the YAML boundary. Closed vocabularies and persisted-format
  literals (`names.py`), the job and sweep models (`job.py`), content-addressed
  identity (`identity.py`), and machine profiles (`machine.py`).
- `execution/` — running one attempt through dr-exec: job construction and
  outcome interpretation (`attempt.py`), shutdown fan-out to in-flight attempts
  (`cancellation.py`), and durable storage behind an input reference
  (`store.py`).
- `platform/` — everything dr-platform-facing: the pipeline and its stage body
  (`pipeline.py`), the DBOS worker runtime (`worker.py`), submission, drain
  loops, inspection, database access, a submission-only registry, and the
  pinned application version (`version.py`).
- `training/` — `dummy_trainer.py`, the reference implementation of the trainer
  contract, used by the tests and the smoke run.
- `cli/` — the `dr_exp` command line.
