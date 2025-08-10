# RAINA Workspace Service

System of Record for Workspaces. Minimal fields by design; artifacts/ADRs/tasks are separate services keyed by `workspace_id`.

## Run locally

```bash
# From repo root
cd deploy && docker-compose up -d --build
# API at http://localhost:8010, Swagger at /docs