"""Tests for the discovery stage."""
import pytest
import _pytest

from config import DiscoverConfig
from pipeline.discover import Discover

ROLE_NAMES = [
        'users', 'docker', 'java', 'nginx', 'php', 'apache', 'composer',
        'pip', 'nfs', 'memcached', 'ssl-certs', 'sensu', 'bootstrap', 'ntp',
        'repo-epel']


@pytest.fixture()
def default_config() -> DiscoverConfig:
    cfg = DiscoverConfig()
    cfg.count = 15

    return cfg


@pytest.mark.parametrize('progress', [True, False])
def test_run_w_progress(
        betamax_mock_sessions: None,
        default_config: DiscoverConfig,
        progress: bool
) -> None:
    default_config.progress = progress
    discover = Discover(default_config)
    results = discover.run()

    assert len(results) == default_config.count
    assert [r.name for r in results.values()] == ROLE_NAMES


def test_report(
    betamax_mock_sessions: None,
    default_config: DiscoverConfig,
    capsys: _pytest.capture.CaptureFixture
) -> None:
    discover = Discover(default_config)
    results = discover.run()
    discover.report_results(results)

    captured = capsys.readouterr()
    assert 'Discovered 15 roles' in captured.out
    assert '5 authors' in captured.out
    assert 'Max download count: 5866622' in captured.out
    assert 'Min download count: 1218183' in captured.out
