# proc-config

## Purpose
Guide users to produce and validate a `proc` draft for scheme design.

## When to Use
- User is configuring "data preparation" before reconciliation.
- User asks to normalize raw files/datasets into recon-ready tables.

## Required Inputs
- Business goal
- Source description
- Sample files or sample datasets

## Workflow
1. Clarify target output table and required columns.
2. Generate `proc_draft_json`.
3. Run trial with `execution_proc_draft_trial`.
4. Summarize trial result and open issues.
5. Ask user to confirm or refine constraints.

## Guardrails
- Keep drafts in memory session only.
- Do not persist final rules before explicit confirmation.
- Prefer deterministic and auditable transformations.

