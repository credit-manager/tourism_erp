"""Models package — import domain files directly (e.g. from app.models.hotel import Hotel)."""
# Only base primitives are auto-loaded; domain files are imported explicitly.
from app.models.base import (Base, engine, SessionLocal, DATABASE_URL,
    WorkflowMixin, Currency, ExchangeRate, _SysCfg)
