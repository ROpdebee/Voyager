"""Test configurations."""
from typing import Any, Dict, Generator, List, TextIO

from pathlib import Path

import betamax
import pytest
import requests
import _pytest


@pytest.fixture()
def resource(
        request: _pytest.fixtures.SubRequest, datadir: Path
) -> Generator[TextIO, None, None]:
    """Return a file handle to a resource."""
    resource_name = request.param
    resource_path = datadir / resource_name
    with open(resource_path, 'r') as f:
        yield f


def _create_cassette_name(request: _pytest.fixtures.SubRequest) -> str:
    cassette_name = ''

    if request.module is not None:
        cassette_name += request.module.__name__ + '.'

    if request.cls is not None:
        cassette_name += request.cls.__name__ + '.'

    cassette_name += request.function.__name__

    return cassette_name


@pytest.fixture()
def betamax_mock_sessions(
        request: _pytest.fixtures.SubRequest,
        monkeypatch: _pytest.monkeypatch.MonkeyPatch
) -> None:
    """Fixture to patch requests.Session to record with Betamax."""
    # Patch the Session constructor on requests to return a Betamax session
    OldSession = requests.Session

    def create_recorded_session() -> requests.Session:
        session = OldSession()
        recorder = betamax.Betamax(session)
        recorder.use_cassette(_create_cassette_name(request))
        recorder.start()
        request.addfinalizer(recorder.stop)
        return session

    monkeypatch.setattr(requests, 'Session', create_recorded_session)


def pytest_addoption(parser: _pytest.config.argparsing.Parser) -> None:
    """Add options to pytest parser."""
    parser.addoption(
            '--integration', action='store_true', help='run integration tests')
    parser.addoption(
            '--smoke', action='store_true', help='run smoke tests')


def pytest_collection_modifyitems(
        config: _pytest.config.Config,
        items: List[_pytest.nodes.Item]
) -> None:
    """Modify the collected test items to skip smoke tests."""
    skips: Dict[str, Any] = {}

    if not config.getoption('--smoke'):
        # Do not include the smoke tests
        skip = pytest.mark.skip(
                reason='Smoke test. Run with --smoke or -m smoke to run')
        skips['smoke'] = skip

    if not config.getoption('--integration'):
        # Do not include the integration tests
        skip = pytest.mark.skip(
                reason='Integration test. '
                       'Run with --integration or -m integration to run')
        skips['integration'] = skip

    for tag, skip in skips.items():
        for item in items:
            if tag in item.keywords:
                item.add_marker(skip)


def pytest_configure(config: _pytest.config.Config) -> None:
    """Adapt configuration of tests."""
    with betamax.Betamax.configure() as betamax_config:
        betamax_config.cassette_library_dir = Path(
                'tests', 'resources', 'cassettes')
