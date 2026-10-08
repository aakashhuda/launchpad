"""Central model registry.

Importing this module ensures every domain ``models.py`` is loaded so that
SQLAlchemy can resolve cross-module ``relationship("...")`` string targets at
mapper-configure time. Import it once at application startup (``src.main``) and
in the Alembic environment.
"""

from __future__ import annotations

import src.auth.models  # noqa: F401
import src.community.models  # noqa: F401
import src.notifications.models  # noqa: F401
import src.products.models  # noqa: F401
import src.staff.models  # noqa: F401
import src.topics.models  # noqa: F401
import src.users.models  # noqa: F401
