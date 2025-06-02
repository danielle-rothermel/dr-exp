# Config Upload Specification (`docs/config_upload.md`)

## Purpose

The config upload system is responsible for:

* Generating fully resolved Hydra configurations for experiments
* Uploading sweep-level metadata and config instances to Supabase
* De-duplicating configs via hashing
* Structuring sweeps into logical clusters for traceability
* Optionally recording code/environment metadata for reproducibility

This enables scalable sweep orchestration with full version control.

---

## Inputs

* Base config (`.yaml`) file for Hydra
* Sweep definition (e.g., CLI args or override list)
* Cluster metadata (name, description)
* Optional: git commit hash, env fingerprint, interface version

---

## Output Supabase Records

1. **sweep\_config\_clusters**

   * High-level grouping of the sweep
   * Includes name, optional description, creation timestamp

2. **sweep\_configs**

   * One per resolved config instance
   * Includes full resolved `config_json`, hash, and metadata

3. **jobs**

   * Created as empty shell jobs pointing to each `sweep_config`
   * Initially `status = queued`

---

## Command Line Interface (Proposed)

```bash
python -m dr_exp.manager_cli upload-configs \
  --base-config-path configs/base.yaml \
  --sweep "optim.lr=0.001,0.01 model.name=resnet" \
  --cluster-name "lr_vs_model" \
  --description "Sweep over learning rates and model variants" \
  --interface-version v1 \
  --code-version $(git rev-parse HEAD)
```

---

## Config Hashing

Each config is hashed (e.g., via SHA256 of the canonicalized JSON) to detect duplicates and avoid re-uploading identical sweeps.

---

## Code and Interface Metadata

Captured metadata fields include:

* `interface_version`: contract version of training system
* `code_version`: Git hash of training repo
* `env_fingerprint`: hash or description of `requirements.txt`, `uv.lock`, etc.

These are stored with each `sweep_config` and optionally inherited by jobs.

---

## Upload Behavior

* If `sweep_config` hash already exists, jobs will not be re-created unless explicitly forced
* Existing clusters may be reused or a new one created
* Upload script will log the number of new configs and jobs created

---

## Optional Extensions

* Add `nickname` field to each config or job for human-friendly tagging
* Add CLI dry-run flag to preview sweep configs without upload
* Export generated configs to disk (`--save-local`) for inspection or backup
* Auto-split large sweeps into N upload batches

---

## Open Design Questions

1. Should clusters be auto-named based on sweep parameters if `--cluster-name` is omitted?
2. Should jobs created from duplicate configs always reuse existing job IDs or generate new ones?
3. Should config hashes be stored globally or scoped per-cluster?
4. Should upload failures (e.g., Supabase API error) fail fast or retry with backoff?
5. Should we support templated sweep expansions (e.g., matrix-style definitions) beyond CLI parsing?

