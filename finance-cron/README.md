Finance Cron Runner
===================

This directory holds the scheduled reconciliation runner that calls `data-agent`'s internal `recon` API without relying on the chat workflow.

Structure
---------
- `config/cron_config.yaml` – template describing the cron job parameters (rule code, datasets used, run context).
- `run_reconciliation.py` – entrypoint script that loads the config, assembles the planned `recon_inputs`, and invokes the new `data-agent` internal API.

What to implement later
----------------------
- data gathering / dataset loaders (`fetch_dataset`).
- idempotency, retry policy, and persistence of run metadata.
- real credentials or service tokens for the internal API.

Execution
---------
This module assumes Python 3.10+ and `requests`. The script can be invoked directly, e.g.:

```
python run_reconciliation.py --config config/cron_config.yaml
```

Before wiring it into cron, make sure data-agent exposes `/api/internal/recon/run` and document the expected payload in the config template.
