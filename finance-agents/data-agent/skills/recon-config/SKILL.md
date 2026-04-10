# recon-config

## Purpose
Guide users to produce and validate a `recon` draft for scheme design.

## When to Use
- User is configuring reconciliation logic after data preparation.
- User asks to define matching keys, compare columns, tolerance, and output.

## Required Inputs
- Source/target table identity
- Matching keys
- Compare fields and tolerance
- Expected exception categories

## Workflow
1. Clarify source/target table binding.
2. Generate `recon_draft_json`.
3. Run trial with `execution_recon_draft_trial`.
4. Summarize trial result and unresolved constraints.
5. Ask user to confirm or refine constraints.

## Guardrails
- Keep drafts in memory session only.
- Do not persist final rules before explicit confirmation.
- Ensure recon rules stay compatible with proc output table naming.

