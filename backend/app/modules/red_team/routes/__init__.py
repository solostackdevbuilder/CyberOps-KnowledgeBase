"""
Red-team API routes package.

One submodule per concern:

    operations.py            - /api/operations/*
    sessions.py              - /api/sessions/* (CRUD) + sessions_router
    screenshots.py           - /api/sessions/{id}/screenshots/*
    query.py                 - /api/query/*
    insights.py              - /api/insights/* + cache helpers
    faa.py                   - /api/faa/* + FAA routes on sessions
    detection_strategies.py  - /api/detection-strategies/*

`sessions_router` is shared: sessions.py declares it, faa.py and
screenshots.py import and decorate it. The package `__init__` imports
every submodule so all decorators fire before main.py reads the routers.

External users that depend on names from this package:
    app/main.py                            - routers
    app/modules/red_team/team.py           - detection_strategies_router,
                                             _load_cache_from_disk,
                                             _invalidate_cache
    app/plugins/browser_extension/plugin.py - upload_screenshot
"""
# Order matters: sessions.py must be imported before faa.py and
# screenshots.py because they import sessions_router from it and decorate
# it with their own routes at module-import time. insights.py goes first
# because sessions.py imports invalidate_insights_for_operation from it.
from app.modules.red_team.routes.insights import (  # noqa: F401
    insights_router,
    _load_cache_from_disk,
    _invalidate_cache,
)
from app.modules.red_team.routes.sessions import (  # noqa: F401
    sessions_router,
)
from app.modules.red_team.routes.detection_strategies import (  # noqa: F401
    detection_strategies_router,
)
from app.modules.red_team.routes.operations import (  # noqa: F401
    operations_router,
)
from app.modules.red_team.routes.query import (  # noqa: F401
    query_router,
)
from app.modules.red_team.routes.screenshots import (  # noqa: F401
    upload_screenshot,
)
from app.modules.red_team.routes.faa import (  # noqa: F401
    faa_router,
)
