"""Tests for pipeline.Clone."""
from typing import Any, Optional, TextIO

import json

from pathlib import Path

import pytest
import _pytest

from git import RemoteProgress, Repo
import git.exc

from config import CloneConfig, MainConfig
from models.galaxy import GalaxyRole
from models.git import GitRepoPath
from pipeline.base import ResultMap
from pipeline.clone import Clone, CloneException


@pytest.fixture()
def config(tmp_path: Path) -> CloneConfig:
    mc = MainConfig()
    mc.output = tmp_path
    mc.dataset = 'test'
    c = CloneConfig(mc)
    return c


@pytest.fixture()
def mock_clone(monkeypatch: _pytest.monkeypatch.MonkeyPatch) -> None:
    """Fixture to mock the git cloning."""
    class DummyRepo:
        def close(self) -> None:
            return

    def mock(
            url: str, to_path: Path, progress: Optional[RemoteProgress],
            *args: Any, **kwargs: Any
    ) -> DummyRepo:
        if url.endswith('ROpdebee/no-repo-here.git'):
            raise git.exc.InvalidGitRepositoryError('Test repo does not exist')
        (to_path / '.git').mkdir()
        if progress is not None:
            progress.update(
                    RemoteProgress.COUNTING | RemoteProgress.BEGIN, 0, None)
            progress.update(
                    RemoteProgress.COUNTING, 5, 10)
            progress.update(
                    RemoteProgress.COUNTING | RemoteProgress.END, 10, 10)
            progress.update(12345, 10, 10)
        return DummyRepo()
    monkeypatch.setattr(Repo, 'clone_from', mock)


@pytest.mark.parametrize('progress', [True, False])
def test_clone_new_dir(
        config: CloneConfig, mock_clone: None, progress: bool
) -> None:
    config.progress = progress
    stage = Clone(config)
    repo_path = stage.repo_path / 'octocat' / 'Hello-World'

    result_path = stage.clone('octocat', 'Hello-World')

    assert not result_path.is_absolute()
    assert config.output_directory / result_path == repo_path
    assert repo_path.is_dir()
    assert '.git' in {p.name for p in repo_path.iterdir()}


@pytest.mark.parametrize('progress', [True, False])
def test_clone_existing_empty_dir(
        config: CloneConfig, mock_clone: None, progress: bool
) -> None:
    config.progress = progress
    stage = Clone(config)
    repo_path = stage.repo_path / 'octocat' / 'Hello-World'
    repo_path.mkdir(parents=True)

    result_path = stage.clone('octocat', 'Hello-World')

    assert not result_path.is_absolute()
    assert config.output_directory / result_path == repo_path
    assert repo_path.is_dir()
    assert '.git' in {p.name for p in repo_path.iterdir()}


def test_clone_existing_nonempty_dir(
        config: CloneConfig, mock_clone: None
) -> None:
    config.resume = False
    stage = Clone(config)
    repo_path = stage.repo_path / 'octocat' / 'Hello-World'
    repo_path.mkdir(parents=True)
    (repo_path / 'dummy.txt').write_text('Test')

    with pytest.raises(CloneException):
        stage.clone('octocat', 'Hello-World')


def test_clone_new_dir_wrong_perms(
        config: CloneConfig, mock_clone: None
) -> None:
    stage = Clone(config)
    config.output_directory.mkdir(parents=True, exist_ok=True)
    config.output_directory.chmod(0o555)

    with pytest.raises(CloneException):
        stage.clone('octocat', 'Hello-World')


def test_clone_missing_repo(config: CloneConfig, mock_clone: None) -> None:
    stage = Clone(config)

    with pytest.raises(CloneException):
        stage.clone('ROpdebee', 'no-repo-here')


@pytest.mark.integration
def test_clone_integration(config: CloneConfig) -> None:
    stage = Clone(config)
    repo_path = stage.repo_path / 'octocat' / 'Hello-World'

    result_path = stage.clone('octocat', 'Hello-World')

    assert not result_path.is_absolute()
    assert config.output_directory / result_path == repo_path
    assert repo_path.is_dir()
    assert '.git' in {p.name for p in repo_path.iterdir()}


@pytest.mark.integration
def test_clone_integration_missing_repo(config: CloneConfig) -> None:
    stage = Clone(config)

    with pytest.raises(CloneException):
        stage.clone('ROpdebee', 'no-repo-here')


def test_stage_run_empty_input(config: CloneConfig, mock_clone: None) -> None:
    stage = Clone(config)
    prev: ResultMap[GalaxyRole] = ResultMap([])

    paths = stage.run(prev)

    assert not paths


@pytest.mark.parametrize('progress', [True, False])
@pytest.mark.parametrize(
        'resource', ['galaxy_roles.json'], indirect=['resource'])
def test_stage_run(
        config: CloneConfig, progress: bool, resource: TextIO, mock_clone: None
) -> None:
    config.progress = progress
    stage = Clone(config)
    data = json.load(resource)
    prev: ResultMap[GalaxyRole] = ResultMap.structure(
            data, ResultMap[GalaxyRole])

    paths = stage.run(prev)

    assert len(paths) == 2
    for id_, path in paths.items():
        assert not path.path.is_absolute()
        assert (config.output_directory / path.path).exists()
        assert path.owner == path.path.parent.name == prev[id_].github_user
        assert path.name == path.path.name == prev[id_].github_repo
        assert path.id == id_


@pytest.mark.parametrize(
        'resource', ['repo_paths.json'], indirect=['resource'])
def test_report(
        config: CloneConfig, resource: TextIO,
        capsys: _pytest.capture.CaptureFixture
) -> None:
    stage = Clone(config)
    data = json.load(resource)
    results: ResultMap[GitRepoPath] = ResultMap.structure(
            data, ResultMap[GitRepoPath])

    stage.report_results(results)

    captured = capsys.readouterr()
    assert 'Cloned 100 ' in captured.out
    assert str(config.output_directory) in captured.out


def test_report_empty(
        config: CloneConfig, capsys: _pytest.capture.CaptureFixture
) -> None:
    stage = Clone(config)
    results: ResultMap[GitRepoPath] = ResultMap([])

    stage.report_results(results)

    captured = capsys.readouterr()
    assert 'Cloned 0 ' in captured.out
    assert str(config.output_directory) in captured.out
