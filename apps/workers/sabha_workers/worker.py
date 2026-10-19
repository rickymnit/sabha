"""Entry module for the Celery CLI: `celery -A sabha_workers.worker worker -Q ...` or `... beat`.

Builds the app from settings (environment and .env) and registers every task (sabha_workers.tasks).
"""

from __future__ import annotations

from sabha_core.logging import configure_logging
from sabha_core.settings import get_settings
from sabha_workers.celery_app import create_app
from sabha_workers.tasks import register

settings = get_settings()
configure_logging(settings.log_level)
app = create_app(settings)
register(app)
