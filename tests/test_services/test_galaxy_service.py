"""Tests for services.galaxy."""
from typing import TypeVar

import pytest
import requests
import _pytest

from services.galaxy import GalaxyAPI, OrderDirection, RoleOrder


# Names of 15 most popular roles at the time the cassettes were made
ROLE_NAMES = [
        'users', 'docker', 'java', 'nginx', 'php', 'apache', 'composer',
        'pip', 'nfs', 'memcached', 'ssl-certs', 'sensu', 'bootstrap', 'ntp',
        'repo-epel']


@pytest.fixture()
def api(
        request: _pytest.fixtures.SubRequest,
        betamax_parametrized_session: requests.Session
) -> GalaxyAPI:  # pragma: no cover
    """Fixture to create the API with or without a recorded session.

    If the param is absent or True, the recorder is created.
    If the param is False, all requests are carried out.
    """
    if (not hasattr(request, 'param')) or request.param:
        return GalaxyAPI(betamax_parametrized_session)

    return GalaxyAPI()


_F = TypeVar('_F')


def maybe_integration(f: _F) -> _F:
    """Decorator to parametrize a test case for integration testing."""
    # Setting these params causes two test cases to be made for the decorated
    # tests: One which uses a recorded response (the unit test with Betamax),
    # and one which doesn't use Betamax and is marked as an integration test.
    params = [True, pytest.param(False, marks=pytest.mark.integration)]
    return pytest.mark.parametrize('api', params, indirect=['api'])(f)


@maybe_integration
def test_role_search_limit(api: GalaxyAPI) -> None:
    results = api.search_roles(limit=5)

    assert len(list(results)) <= 5


@maybe_integration
def test_role_order_desc(api: GalaxyAPI) -> None:
    results = list(api.search_roles(
            limit=5, order_by=RoleOrder.DOWNLOAD_RANK,
            order=OrderDirection.DESCENDING))
    first = results[0]
    last = results[-1]

    assert first.download_count >= last.download_count


@maybe_integration
def test_role_order_asc(api: GalaxyAPI) -> None:
    results = api.search_roles(
            limit=5, order_by=RoleOrder.CREATED,
            order=OrderDirection.ASCENDING)
    first = next(results)
    second = next(results)

    assert first.created <= second.created


def test_role_search_page(api: GalaxyAPI) -> None:
    roles = api.search_roles(10)
    names = [role.name for role in roles]

    assert names == ROLE_NAMES[:10]


def test_role_search_multi_page(api: GalaxyAPI) -> None:
    roles = api.search_roles(15)
    names = [role.name for role in roles]

    assert names == ROLE_NAMES


@pytest.mark.integration
def test_role_search_page_integration() -> None:
    api = GalaxyAPI()
    roles = api.search_roles(10)
    names = [role.name for role in roles]

    assert len(names) == 10


@pytest.mark.integration
def test_role_search_multi_page_integration() -> None:
    api = GalaxyAPI()
    roles = api.search_roles(15)
    names = [role.name for role in roles]

    assert len(names) == 15
