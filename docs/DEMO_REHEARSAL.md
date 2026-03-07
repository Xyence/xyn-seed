# Demo Rehearsal

## How to Run

From the `xyn` repo root:

```bash
./scripts/run_demo_rehearsal.sh
```

Artifacts are written under:

```bash
.xyn/demo-rehearsal/<timestamp>/
```

That directory contains:
- `rehearsal.log`
- `test-results/`
- `playwright-report/`

## Environment Prerequisites

- Docker is installed and running
- The `xyn` and `xyn-platform` repos exist side-by-side
- `xyn-platform/apps/xyn-ui` contains the current UI code
- `xynctl quickstart --force` can boot the local stack
- The local demo path is reachable at `http://localhost`

Optional overrides:

```bash
XYN_UI_BASE_URL=http://localhost
XYN_DEMO_REHEARSAL_OUT=/custom/output/dir
XYN_DEMO_REHEARSAL_CONTAINER=xyn-playwright-demo
```

## What the Test Covers

The browser-driven rehearsal walks the visible demo path in this exact sequence:

1. open Xyn
2. build network inventory app
3. submit draft
4. track build
5. show execution trace
6. open deployed app
7. run palette command
8. show artifacts

The test uses the real UI and waits on visible states. It saves:
- screenshots for every demo step
- browser console/request-failure logs
- Playwright failure traces and report output

## What It Does Not Cover

- full artifact publish/import/install semantics for sibling Xyn
- non-demo routes outside the golden path
- deep validation of the deployed app beyond the visible open path and palette/device check
- cross-browser coverage; rehearsal currently uses Playwright Chromium

## How to Interpret Failures

- The failing Playwright step name tells you which demo step broke.
- Check `rehearsal.log` first for the runner-level failure.
- Check `test-results/logs/browser.log` for browser console errors and failed requests.
- Check the matching step screenshot under `test-results/.../screenshots/`.
- If the failure is UI-only while backend APIs still work, treat it as a real demo-path failure.
