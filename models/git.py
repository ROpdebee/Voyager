"""Models for Git."""
from pathlib import Path

import attr

from models.base import Model
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
        return self.path

    @classmethod
    def load(cls, id: str, path: Path) -> 'GitRepo':
        repo_id = XrefID.load(id)
        owner, name = path.parts[-2:]
        return cls(owner=owner, name=name, repo_id=repo_id, path=path)


@attr.s(auto_attribs=True, frozen=True)
class Commit(Model):
    """Model for commits."""
    sha1: str
    summary: str
    authored_date: int  # Second since epoch
    author_name: str
    author_email: str

    @property
    def id(self) -> str:
        return self.sha1
