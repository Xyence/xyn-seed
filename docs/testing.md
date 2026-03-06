# Testing

## Full E2E Harness

Run:

```bash
scripts/run_e2e_validation.sh
```

The harness validates:

1. Core API endpoint contracts
2. net-inventory API endpoint contracts
3. Workspace isolation for palette/device listing
4. Persistence after API and DB container restarts
5. Palette command registration/execution (`show devices`)
6. Artifact refresh/self-update smoke path

## Notes

- The harness expects a running seed stack (`./xynctl quickstart`).
- If no successful app deployment exists, the harness creates/submits an app-intent draft and waits for the job chain to complete.
- Output ends with a PASS/FAIL summary suitable for CI/local gating.
