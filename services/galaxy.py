"""Ansible Galaxy API service."""
from typing import Iterator, Mapping, Optional, Sequence, Type, TypeVar

import enum
import itertools
import json
import urllib.parse
from json.decoder import JSONDecodeError
from time import sleep

import requests

from models.galaxy import GalaxyImportEventAPIResponse, GalaxySearchAPIPage
from util import ValueMap


class _APIURLs(ValueMap):
    role_search = 'https://galaxy.ansible.com/api/v1/search/roles/'
    import_events = 'https://galaxy.ansible.com/api/v1/roles/{role_id}/imports/'


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
    ) -> Iterator[str]:
        """Paginate through the results of an Ansible Galaxy API query.

        Returns an iterable where new pages are lazily loaded. Requires the
        API URL to return a 'results' field.
        """
        next_link: Optional[str]
        next_link = api_url + '?' + urllib.parse.urlencode(
                _remove_unused_params(params))
        page_num = 1

        while next_link is not None:  # pragma: no branch
            result = self._session.get(next_link)
            try:
                json = result.json()
            except JSONDecodeError:
                # Ugly workaround for potential rate limiting. Sleep and retry
                # with the same link
                print('Rate limit?')
                sleep(5)
                continue
            # TODO(ROpdebee): We know the number of results here, but since
            #                 pages are loaded lazily, we return a generator.
            #                 Should we maybe notify of the count as soon as we
            #                 know it?
            if (next_path := json.get('next_link', None)) is not None:
                next_link = 'https://galaxy.ansible.com' + next_path
            else:
                # End of results
                next_link = None

            yield result.text
            return
            page_num += 1

    def search_roles(
            self,
            order_by: RoleOrder = RoleOrder.DOWNLOAD_RANK,
            order: OrderDirection = OrderDirection.DESCENDING,
            deprecated: Optional[bool] = False,
            page_size: int = 500
    ) -> Iterator[GalaxySearchAPIPage]:
        """Search roles using the Galaxy API.

        :param order_by: Field on which to order the results, download rank
                         by default.
        :param order: Return results in ascending or descending order.
        :param deprecated: Whether to include deprecated roles or not.
        """
        page_it = self._paginate(
                _APIURLs.role_search,
                deprecated=_convert_bool(deprecated),
                order_by=_create_order_param(order_by, order),
                page_size=str(page_size))
        yield from (
                GalaxySearchAPIPage(page_num + 1, page)
                for page_num, page in enumerate(page_it))

    def load_import_events(
            self, role_ids: Sequence[int]
    ) -> Iterator[GalaxyImportEventAPIResponse]:
        yield from (
                self.load_import_events_for_role(role_id)
                for role_id in role_ids)

    def load_import_events_for_role(
            self, role_id: int
    ) -> GalaxyImportEventAPIResponse:
        page_it = self._paginate(
                _APIURLs.import_events.format(role_id=role_id),
                page_size='500')
        return GalaxyImportEventAPIResponse(
                role_id, [json.loads(page) for page in page_it])

