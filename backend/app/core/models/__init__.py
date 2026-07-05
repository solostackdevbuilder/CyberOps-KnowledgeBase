"""
Core platform models.
All generic models that are shared across teams live here.
"""
from app.core.models.operation import (
    Operation,
    OperationBase,
    OperationCreate,
    OperationUpdate,
)
from app.core.models.session import (
    Screenshot,
    ScreenshotExtraction,
    Session,
    SessionBase,
    SessionCreate,
    SessionUpdate,
)
from app.core.models.faa import (
    FAAItem,
    FAAItemCreate,
    FAAItemUpdate,
)
from app.core.models.insights import (
    GeneralInsights,
    InsightsGenerateRequest,
    NextStep,
)

# CachedInsights is intentionally NOT re-exported here. The base dict-typed
# class in app.core.models.insights is an implementation detail for teams
# that want to subclass with their own typed `insights` field (red_team uses
# InsightsResponse). Teams import the typed version from their own module
# so the public core surface stays unambiguous.

__all__ = [
    # Operations
    "Operation",
    "OperationBase",
    "OperationCreate",
    "OperationUpdate",
    # Sessions
    "Screenshot",
    "ScreenshotExtraction",
    "Session",
    "SessionBase",
    "SessionCreate",
    "SessionUpdate",
    # FAA
    "FAAItem",
    "FAAItemCreate",
    "FAAItemUpdate",
    # Insights
    "GeneralInsights",
    "InsightsGenerateRequest",
    "NextStep",
]
