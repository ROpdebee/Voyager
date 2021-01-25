"""Models for Git."""
from typing import Optional, Union, Sequence
from pathlib import Path

import attr
import git
import pendulum
import yaml

try:
    from yaml import CLoader as Loader, CDumper as Dumper
except ImportError:
    from yaml import Loader, Dumper  # type: ignore[misc]

from models.base import Model
from models.serialize import CONVERTER
from models.role_metadata import Repository, XrefID


@attr.s(auto_attribs=True, frozen=True)
class GitRepo(Model):
    """Model for a local path containing a Git repository."""
    owner: str
    name: str
    repo_id: XrefID
    path: Path

    @property
    def id(self) -> str:
        return str(self.repo_id)

    def dump(self, directory: Path) -> Path:
        return directory / self.path

    @classmethod
    def load(cls, id: str, path: Path) -> 'GitRepo':
        repo_id = XrefID.load(id)
        owner, name = path.parts[-2:]
        return cls(owner=owner, name=name, repo_id=repo_id, path=path)


@attr.s(auto_attribs=True, frozen=True)
class GitCommit(Model):
    """Model for commits."""
    sha1: str
    message: str
    authored_datetime: pendulum.DateTime
    author_name: str
    author_email: str
    committed_datetime: pendulum.DateTime
    committer_name: str
    committer_email: str

    @property
    def id(self) -> str:
        return self.sha1


    @classmethod
    def from_git_commit(cls, commit: git.objects.commit.Commit) -> 'GitCommit':
        return GitCommit(
            sha1=commit.hexsha, message=commit.message,
            author_name=commit.author.name, author_email=commit.author.email,
            authored_datetime=pendulum.from_timestamp(commit.authored_date),
            committer_name=commit.committer.name,
            committer_email=commit.committer.email,
            committed_datetime=pendulum.from_timestamp(commit.committed_date))


@attr.s(auto_attribs=True, frozen=True)
class GitTag(Model):
    """Model for git tags."""
    name: str
    message: Optional[str]
    commit_sha1: str
    tagged_datetime: Optional[pendulum.DateTime]
    tagger_name: Optional[str]
    tagger_email: Optional[str]

    @property
    def id(self) -> str:
        return self.name

    @classmethod
    def from_git_tag(cls, tag: git.refs.tag.TagReference) -> Optional['GitTag']:
        if not tag.tag:
            return GitTag(
                    name=tag.name, commit_sha1=tag.commit.hexsha, message=None,
                    tagger_name=None, tagger_email=None, tagged_datetime=None)
        actual_tag = tag.tag
        return GitTag(
                name=actual_tag.tag, message=actual_tag.message,
                commit_sha1=actual_tag.object.hexsha, tagger_name=actual_tag.tagger.name,
                tagger_email=actual_tag.tagger.email,
                tagged_datetime=pendulum.from_timestamp(actual_tag.tagged_date))


@attr.s(auto_attribs=True)
class GitRepoMetadata(Model):
    commits: Sequence[GitCommit]
    tags: Sequence[GitTag]
    repo_owner: str
    repo_name: str

    @property
    def id(self) -> str:
        return f'{self.repo_owner}/{self.repo_name}'

    def dump(self, path: Path) -> Path:
        owner_dir = path / self.repo_owner
        owner_dir.mkdir(exist_ok=True, parents=True)
        repo_file = owner_dir / (self.repo_name + '.yaml')
        content = {
            'commits': CONVERTER.unstructure(self.commits),
            'tags': CONVERTER.unstructure(self.tags)
        }
        repo_file.write_text(yaml.dump(content, sort_keys=True))
        return repo_file


    @classmethod
    def load(self, id: str, path: Path) -> 'GitRepoMetadata':
        return _LazyGitRepoMetadataProxy(path.stem, path.parts[-2], path)


class _LazyGitRepoMetadataProxy(GitRepoMetadata):

    def __init__(self, repo_name: str, repo_owner: str, path: Path) -> None:
        self._repo_name = repo_name
        self._repo_owner = repo_owner
        self._file = path
        self._loaded = False

    def _ensure_loaded(self) -> None:
        if not self._loaded:
            content = yaml.load(self._file.read_text(), Loader=Loader)
            self._commits = CONVERTER.structure(content['commits'], Sequence[GitCommit])
            self._tags = CONVERTER.structure(content['tags'], Sequence[GitTag])
            self._loaded = True

    @property
    def repo_name(self) -> str:  # type: ignore[override]
        return self._repo_name

    @property
    def repo_owner(self) -> str:  # type: ignore[override]
        return self._repo_owner

    @property
    def commits(self) -> str:  # type: ignore[override]
        self._ensure_loaded()
        return self._commits  # type: ignore[no-any-return]

    @property
    def tags(self) -> str:  # type: ignore[override]
        self._ensure_loaded()
        return self._tags  # type: ignore[no-any-return]
