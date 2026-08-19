# Changelog

## 2026-08-18 — Phase 1 strip

Removed Supabase sync, FastAPI remote API, React UI, sync queue, obsolete scripts and implementation-guide docs. Excised sync coupling from JobDB, Worker, and CLI. Consolidated on `dr_exp.training.dummy_trainer.train` for tests and smoke runs. Pruned runtime dependencies; dev tooling lives in dependency groups only.
