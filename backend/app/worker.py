from __future__ import annotations

from .services.background_jobs import run_worker_forever


if __name__ == "__main__":
    run_worker_forever()
