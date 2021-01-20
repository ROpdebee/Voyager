"""Ansible Galaxy API service."""
from typing import Iterator, Mapping, Optional, Type, TypeVar

import enum
import itertools
import urllib.parse

import requests

from models.galaxy import GalaxyAPIPage
from util import ValueMap


class _APIURLs(ValueMap):
    role_search = 'https://galaxy.ansible.com/api/v1/search/roles/'


class OrderField(enum.Enum):
    """Field on which can be ordered."""


@enum.unique
class RoleOrder(OrderField):
    """Field by which to order the roles."""

    DOWNLOAD_RANK = 'download_rank'
    CREATED = 'created'


@enum.unique
class OrderDirection(enum.Enum):
    """Direction in which to order."""

    ASCENDING = 1
    DESCENDING = 2


def _create_order_param(field: OrderField, direction: OrderDirection) -> str:
    direction_modifier = '-' if direction is OrderDirection.DESCENDING else ''
    return f'{direction_modifier}{field.value}'


def _remove_unused_params(
        params: Mapping[str, Optional[str]]
) -> Mapping[str, str]:
    return {k: v for k, v in params.items() if v is not None}


def _convert_bool(b: Optional[bool]) -> Optional[str]:
    """Convert bool to a string that Galaxy understands."""
    if b is None:
        return None

    return 'true' if b else 'false'


class GalaxyAPI:
    """Galaxy API service."""

    _session: requests.Session

    def __init__(self, session: Optional[requests.Session] = None) -> None:
        """Initialize the API service with an optional session."""
        # TODO(ROpdebee): We might need to include a Galaxy API key in the
        #                 future, probably through an environment variable.
        #                 We should probably accept it as an argument here.
        if session is None:  # pragma: no cover (session required for tests)
            session = requests.Session()
        self._session = session

    def _paginate(
            self, api_url: str, **params: Optional[str]
    ) -> Iterator[GalaxyAPIPage]:
        """Paginate through the results of an Ansible Galaxy API query.

        Returns an iterable where new pages are lazily loaded. Requires the
        API URL to return a 'results' field.
        """
        next_link: Optional[str]
        next_link = api_url + '?' + urllib.parse.urlencode(
                _remove_unused_params(params))
        page_num = 0

        while next_link is not None:  # pragma: no branch
            page_num += 1
            result = self._session.get(next_link)
            json = result.json()
            # TODO(ROpdebee): We know the number of results here, but since
            #                 pages are loaded lazily, we return a generator.
            #                 Should we maybe notify of the count as soon as we
            #                 know it?
            if (next_path := json.get('next_link', None)) is not None:
                next_link = 'https://galaxy.ansible.com' + next_path
            else:
                # End of results
                next_link = None

            yield GalaxyAPIPage(page_num, result.text)

    def search_roles(
            self,
            order_by: RoleOrder = RoleOrder.DOWNLOAD_RANK,
            order: OrderDirection = OrderDirection.DESCENDING,
            deprecated: Optional[bool] = False,
            page_size: int = 500
    ) -> Iterator[GalaxyAPIPage]:
        """Search roles using the Galaxy API.

        :param order_by: Field on which to order the results, download rank
                         by default.
        :param order: Return results in ascending or descending order.
        :param deprecated: Whether to include deprecated roles or not.
        """
        return self._paginate(
                _APIURLs.role_search,
                deprecated=_convert_bool(deprecated),
                order_by=_create_order_param(order_by, order),
                page_size=str(page_size))
