from ..config import settings
from .builderspace import BuilderSpaceProvider
from .heuristic import HeuristicProvider

_HEURISTIC_PROVIDER = HeuristicProvider()
_BUILDERSPACE_PROVIDER = BuilderSpaceProvider()


def get_ai_provider():
    if settings.ai_provider == "builderspace":
        return _BUILDERSPACE_PROVIDER
    return _HEURISTIC_PROVIDER
