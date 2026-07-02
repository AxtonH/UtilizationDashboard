"""Creatives dashboard blueprint, split across focused modules.

Importing the route submodules registers their routes/hooks on the shared
blueprint; endpoint names are unchanged (`creatives.<function>`).
"""
from .blueprint import creatives_bp

from . import deps  # noqa: E402,F401  (before/teardown request hooks)
from . import pages, utilization_api, sales_api, email_api, admin_api  # noqa: E402,F401

__all__ = ["creatives_bp"]
