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

GitHub Actions uses:

```bash
docker compose -f docker-compose.prod.yml up -d --build --force-recreate --remove-orphans
```

DNS prerequisite:
`marketing-automation.axplitest.com` must resolve to the VPS public IP.
