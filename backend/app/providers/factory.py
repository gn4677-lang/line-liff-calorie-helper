from ..config import settings
from .builderspace import BuilderSpaceProvider
from .heuristic import HeuristicProvider


def get_ai_provider():
    if settings.ai_provider == "builderspace":
        return BuilderSpaceProvider()
    return HeuristicProvider()
