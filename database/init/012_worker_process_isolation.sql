-- 012_worker_process_isolation.sql
-- Sépare l'API des workers tout en conservant PostgreSQL comme plan de contrôle.
-- Additif et idempotent : aucune donnée métier existante n'est supprimée.

CREATE TABLE IF NOT EXISTS worker_runtime (
    worker_type   TEXT NOT NULL,
    instance_id   TEXT NOT NULL,
    pid           INTEGER,
    status        TEXT NOT NULL DEFAULT 'starting',
    started_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    heartbeat_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    stopped_at    TIMESTAMPTZ,
    details_json  JSONB NOT NULL DEFAULT '{}'::jsonb,
    last_error    TEXT,
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (worker_type, instance_id),
    CONSTRAINT worker_runtime_status_chk
        CHECK (status IN ('starting','running','stopping','stopped','error'))
);

CREATE INDEX IF NOT EXISTS idx_worker_runtime_heartbeat
    ON worker_runtime (worker_type, heartbeat_at DESC);

CREATE TABLE IF NOT EXISTS batch_run_requests (
    id              BIGSERIAL PRIMARY KEY,
    trigger          TEXT NOT NULL DEFAULT 'manual_api',
    status           TEXT NOT NULL DEFAULT 'pending',
    parameters_json  JSONB NOT NULL DEFAULT '{}'::jsonb,
    result_json      JSONB,
    error            TEXT,
    attempts         INTEGER NOT NULL DEFAULT 0,
    available_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    requested_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    started_at       TIMESTAMPTZ,
    heartbeat_at     TIMESTAMPTZ,
    finished_at      TIMESTAMPTZ,
    locked_by        TEXT,
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT batch_run_requests_status_chk
        CHECK (status IN ('pending','processing','completed','failed','cancelled'))
);

-- Une seule demande manuelle active suffit : le batch métier possède déjà son
-- advisory lock PostgreSQL, et empiler des clics n'apporte aucune valeur.
CREATE UNIQUE INDEX IF NOT EXISTS ux_batch_run_requests_single_active
    ON batch_run_requests ((1))
    WHERE status IN ('pending','processing');

CREATE INDEX IF NOT EXISTS idx_batch_run_requests_claim
    ON batch_run_requests (available_at, requested_at, id)
    WHERE status = 'pending';

CREATE INDEX IF NOT EXISTS idx_batch_run_requests_latest
    ON batch_run_requests (requested_at DESC, id DESC);
