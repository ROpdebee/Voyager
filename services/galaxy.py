"""Ansible Galaxy API service."""
from typing import Iterator, Mapping, Optional, Type, TypeVar

import enum
import itertools
import urllib.parse

import requests

from models.galaxy import GalaxyModel, GalaxyRole
from util import ValueMap

_ResultType = TypeVar('_ResultType', bound=GalaxyModel)


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
            self, api_url: str, result_cls: Type[_ResultType],
            **params: Optional[str]
    ) -> Iterator[_ResultType]:
        """Paginate through the results of an Ansible Galaxy API query.

        Returns an iterable where new pages are lazily loaded. Requires the
        API URL to return a 'results' field.
        """
        next_link: Optional[str]
        next_link = api_url + '?' + urllib.parse.urlencode(
                _remove_unused_params(params))

        while next_link is not None:  # pragma: no branch
            json = self._session.get(next_link).json()
            # TODO(ROpdebee): We know the number of results here, but since
            #                 pages are loaded lazily, we return a generator.
            #                 Should we maybe notify of the count as soon as we
            #                 know it?
            if (next_path := json.get('next_link', None)) is not None:
                next_link = 'https://galaxy.ansible.com' + next_path
            else:
                # End of results
                next_link = None

            if results := json.get('results'):
                yield from (
                        result_cls.from_json_obj(result) for result in results)
            else:  # pragma: no cover (shouldn't happen)
                raise ValueError(
                        'Galaxy API response does not include results')

    def search_roles(
            self,
            limit: Optional[int] = None,
            order_by: RoleOrder = RoleOrder.DOWNLOAD_RANK,
            order: OrderDirection = OrderDirection.DESCENDING,
            deprecated: Optional[bool] = False,
            page_size: int = 500
    ) -> Iterator[GalaxyRole]:
        """Search roles using the Galaxy API.

        :param limit: The number of results to return, or None for no limit.
        :param order_by: Field on which to order the results, download rank
                         by default.
        :param order: Return results in ascending or descending order.
        :param deprecated: Whether to include deprecated roles or not.
        """
        if limit is not None:
            page_size = min(page_size, limit)

        role_stream = self._paginate(
                _APIURLs.role_search,
                GalaxyRole,
                deprecated=_convert_bool(deprecated),
                order_by=_create_order_param(order_by, order),
                page_size=str(page_size))
        if limit is not None:  # pragma: no branch
            role_stream = itertools.islice(role_stream, limit)
        return role_stream
