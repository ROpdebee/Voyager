"""Tests for models.git package."""

from pathlib import Path

from models.git import GitRepoPath


def test_create() -> None:
    p = GitRepoPath('me', 'my_repo', '123', Path('tmp', 'my_repo'))

    assert p.owner == 'me'
    assert p.name == 'my_repo'
    assert p.role_id == '123'
    assert p.path.parent == Path('tmp')
    assert p.id == '123'


def test_serialize_obj() -> None:
    p = GitRepoPath('me', 'my_repo', '123', Path('tmp', 'my_repo'))

    assert GitRepoPath.from_json_obj(p.to_json_obj()) == p


def test_serialize_str() -> None:
    p = GitRepoPath('me', 'my_repo', '123', Path('tmp', 'my_repo'))

    assert GitRepoPath.from_json_str(p.to_json_str()) == p
