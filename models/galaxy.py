"""Data models for the Ansible Galaxy API."""
import abc
from collections.abc import MutableMapping

import attr
import pendulum

from models.base import Model


class GalaxyModel(Model, abc.ABC):
    """Base class for Galaxy models."""

    pass


@attr.s(auto_attribs=True)
class GalaxyRole(GalaxyModel):
    """Model for roles in the Galaxy API.

    :ivar id: The ID of the role.
    :vartype id: :class:`int`
    :ivar name: The name of the role.
    :vartype name: :class:`str`
    :ivar description: The description of the role.
    :vartype description: :class:`str`
    :ivar github_user: The owner of the GitHub repository for this role.
    :vartype github_user: :class:`str`
    :ivar github_repo: The name of the GitHub repository for this role.
    :vartype github_repo: :class:`str`
    :ivar created: The creation date of this role.
    :vartype created: :class:`~pendulum.DateTime`
    :ivar modified: The last modified date of this role.
    :vartype modified: :class:`~pendulum.DateTime`
    :ivar download_count: The number of downloads for this role.
    :vartype download_count: :class:`int`
    :ivar stargazers_count: The number of stargazers of the GitHub repo.
    :vartype stargazers_count: :class:`int`
    :ivar forks_count: The number of forks of the GitHub repo.
    :vartype forks_count: :class:`int`
    :ivar open_issues_count: The number of open issues for the GitHub repo.
    :vartype open_issues_count: :class:`int`
    """

    _id: int
    name: str
    description: str
    namespace: str
    github_user: str
    github_repo: str
    created: pendulum.DateTime
    modified: pendulum.DateTime
    download_count: int
    stargazers_count: int
    forks_count: int
    open_issues_count: int

    @classmethod
    def from_json_obj(cls, json_obj: object) -> 'GalaxyRole':
        """Deserialize from a JSON object."""
        # Map 'id' key to '_id' in Galaxy API results
        if isinstance(json_obj, MutableMapping):
            if '_id' not in json_obj:
                json_obj['_id'] = json_obj['id']
            if 'namespace' not in json_obj:
                namespace = json_obj['summary_fields']['namespace']['name']
                json_obj['namespace'] = namespace
        return super().from_json_obj(json_obj)

    @property
    def id(self) -> str:
        """Get the ID."""
        return str(self._id)
