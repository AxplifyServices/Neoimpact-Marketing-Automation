from __future__ import annotations

import sys

from app.workers.runtime import current_instance_healthy


def main() -> int:
    worker_type = str(sys.argv[1] if len(sys.argv) > 1 else "").strip().lower()
    if not worker_type:
        print("worker type required", file=sys.stderr)
        return 2
    try:
        if current_instance_healthy(worker_type):
            print(f"{worker_type}: healthy")
            return 0
        print(f"{worker_type}: unhealthy", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"{worker_type}: healthcheck error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
