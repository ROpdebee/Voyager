"""Models for Git."""
from pathlib import Path

import attr

from models.base import Model


@attr.s(auto_attribs=True, frozen=True)
class GitRepoPath(Model):
    """Model for a local path containing a Git repository."""
    owner: str
    name: str
    role_id: str
    path: Path

    @property
    def id(self) -> str:
        return self.role_id


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
