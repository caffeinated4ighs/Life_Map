"""
health.py — Supabase keep-alive health check.

Calls the Supabase Edge Function health-check endpoint produced by the DB Agent.
Returns True if healthy, False otherwise. Never raises — failures are logged.
"""

import logging
import time
from typing import TYPE_CHECKING

import requests

from orchestrator.logger import log_health_check

if TYPE_CHECKING:
    from orchestrator.config import Config

logger = logging.getLogger("orchestrator")


def health_check(config: "Config") -> bool:
    """
    Ping the Supabase health endpoint.
    Returns True (healthy) or False (unreachable / unhealthy).
    """
    url = config.health_check_url
    headers = {
        "apikey": config.supabase_service_key,
        "Authorization": f"Bearer {config.supabase_service_key}",
    }

    start = time.monotonic()
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        latency_ms = (time.monotonic() - start) * 1000

        if resp.status_code == 200:
            log_health_check(logger, healthy=True, detail=f"status=200 latency_ms={latency_ms:.0f}")
            return True
        else:
            log_health_check(
                logger,
                healthy=False,
                detail=f"status={resp.status_code} body={resp.text[:200]}",
            )
            return False

    except requests.exceptions.ConnectionError as e:
        log_health_check(logger, healthy=False, detail=f"connection_error={e}")
        return False
    except requests.exceptions.Timeout:
        log_health_check(logger, healthy=False, detail="timeout after 10s")
        return False
    except Exception as e:
        log_health_check(logger, healthy=False, detail=f"unexpected_error={e}")
        return False
