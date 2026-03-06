# Endpoint Contracts

Xyn uses lightweight JSON contracts for practical API compatibility checks.

## Files

- `contracts/core-api.json`
- `contracts/net-inventory-api.json`

Each endpoint entry defines:

- `method`
- `path`
- `success_status`
- `request_json` (optional)
- `required_response_fields`
- `workspace_scope` notes

## Validate Manually

```bash
python3 scripts/validate_contracts.py \
  --contract contracts/core-api.json \
  --base-url http://seed.localhost \
  --workspace-id <workspace-id> \
  --workspace-slug default
```

```bash
python3 scripts/validate_contracts.py \
  --contract contracts/net-inventory-api.json \
  --base-url http://localhost:<net-inventory-port> \
  --workspace-id <workspace-id>
```

The validator supports value substitution (`$workspace_id`, `$workspace_slug`, `$rand`) and extracted IDs from previous responses.
