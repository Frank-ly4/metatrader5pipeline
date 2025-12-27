# Latent Workspace (Planning & Registry)

This folder is a self-contained staging area for the latent-space integration work. Nothing here modifies your main project unless you copy files over explicitly.

## Contents
- Integration plan: `Integration_Plan_Latent_Space_v4.2.4.md`
- Step-by-step explainer: `Step-by-Step_Explainer_12-Steps.md`
- Notes (migrated): `notes/`
- Templates/schemas:
  - `strategy_card.template.yaml`
  - `registry_graph.schema.json`
  - `registry_graph.example.json`
- Helper code:
  - `latent_registry_tools.py` – generates `strategy_card.yaml` files and a lineage graph from the main project outputs

## How to use (without touching the repo)
1. Review/edit the plan and explainer here.
2. Run `latent_registry_tools.py` pointing to your main project outputs to produce strategy cards and a registry graph locally in this folder.
3. When ready to integrate, copy files into the repo paths suggested in the plan (e.g., `src/latent/*`, `scripts/run_proposals.py`), or keep them external and only copy artifacts.

## Generate cards and registry graph
```bash
# Example (Windows PowerShell input paths)
python .\latent_registry_tools.py ^
  --runs_dir "C:\\Users\\frank\\Desktop\\opt_4\\4.2\\4.2.4\\outputs\\runs" ^
  --out_dir  "C:\\Users\\frank\\Desktop\\Latent"
```
- Produces: `cards/strategy_card_<uid>.yaml` and `registry/graph.json` under the `--out_dir`.
- You can limit to specific `trial_uid`s with `--uids` or let it derive UIDs from runs.

## Copy‑paste workflow
- Keep iterating here; when you’re satisfied:
  - Copy `latent_registry_tools.py` into `scripts/` (rename to `run_registry.py` if desired).
  - Copy templates/schemas into `meta/` inside the repo.
  - Later, add code packages from this workspace (e.g., `src/latent/*`) as you adopt the full integration.

## Safety and provenance
- No in-place edits of your repo. Artifacts produced here include hashes and timestamps for traceability.
