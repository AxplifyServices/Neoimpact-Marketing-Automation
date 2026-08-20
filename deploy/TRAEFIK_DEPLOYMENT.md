# Marketing Automation - Traefik deployment

Production domains:

- Frontend: https://marketing-automation.axplitest.com
- API: https://marketing-automation-api.axplitest.com/api

Production uses the existing external Docker network:

- traefik-public

Traefik labels use:

- entrypoint: websecure
- certificate resolver: letsencrypt

This matches the infrastructure used by the Hire project on the same VPS.

PostgreSQL is attached only to the private `marketing-db` network and exposes no host port in production.

Local:

```bash
docker compose up -d --build
```

- Frontend: http://localhost:8081
- API: http://localhost:8000
- PostgreSQL: 127.0.0.1:5433

Production:

GitHub Actions deploys in this order to keep the application available and to guarantee schema compatibility:

```text
build images
→ ensure PostgreSQL is ready
→ apply pending SQL migrations
→ recreate backend
→ wait for backend health
→ recreate frontend
→ cleanup orphans
```

Migrations are applied by `deploy/apply_migrations.sh`. Applied files are recorded in `schema_migrations`; never edit an already-applied migration, create a new numbered SQL migration instead.

DNS prerequisite:
`marketing-automation.axplitest.com` must resolve to the VPS public IP.
