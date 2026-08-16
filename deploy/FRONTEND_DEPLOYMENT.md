# Frontend self-hosting

## Local frontend development

```bash
cd campain-app-main
npm install
npm run dev
```

URL:
- http://localhost:5173

The development frontend calls:
- https://marketing-automation-api.axplitest.com/api

## Local Docker stack

```bash
docker compose -f compose.yaml -f compose.local.yaml up -d --build
```

URLs:
- frontend: http://localhost:8081
- API: http://localhost:8000
- PostgreSQL host access: 127.0.0.1:5433

## Production

The frontend container listens internally on port 80 and is bound on the VPS to:
- 127.0.0.1:8081

The host reverse proxy must route:
- https://marketing-automation.axplitest.com
to:
- http://127.0.0.1:8081

The API remains:
- https://marketing-automation-api.axplitest.com/api

Streamlit is not installed or started by the backend Docker image anymore.
