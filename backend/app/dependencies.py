from typing import Annotated

from fastapi import Depends

from app.providers.base import RailDataProvider
from app.providers.mock.provider import MockRailDataProvider

_provider = MockRailDataProvider()


def get_provider() -> RailDataProvider:
    # THE swap point: return your real provider here when it exists.
    # Tests substitute it via app.dependency_overrides[get_provider].
    return _provider


ProviderDep = Annotated[RailDataProvider, Depends(get_provider)]
