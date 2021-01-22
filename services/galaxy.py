"""Ansible Galaxy API service."""
from typing import Callable, Dict, Iterator, Mapping, Optional, Sequence, Type, TypeVar

import enum
import itertools
import json
import re
import urllib.parse
from json.decoder import JSONDecodeError
from pathlib import Path
from time import sleep

import requests
import tqdm
from requests.exceptions import Timeout

from models.galaxy import GalaxyAPIPage, GalaxyImportEventAPIResponse


def _log(text: str) -> None:
    # Not thread safe, but doesn't really matter that much
    with Path('galaxy.log').open('at') as flog:
        flog.write(text + '\n')


def _remove_unused_params(
        params: Mapping[str, Optional[str]]
) -> Mapping[str, str]:
    return {k: v for k, v in params.items() if v is not None}


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
            self, api_url: str,
            **params: Optional[str]
    ) -> Iterator[str]:
        """Paginate through the results of an Ansible Galaxy API query.

        Returns an iterable where new pages are lazily loaded. Requires the
        API URL to return a 'results' field.
        """
        next_link: Optional[str]
        next_link = api_url + '?' + urllib.parse.urlencode(
                _remove_unused_params(params))
        page_num = 1
        _log(f'{api_url}: Start')

        while next_link is not None:  # pragma: no branch
            try:
                result = self._session.get(next_link, timeout=30)
            except Timeout:
                # Try again with same link.
                _log(f'{next_link}: Timed out')
                continue
            try:
                json = result.json()
            except JSONDecodeError:
                # Ugly workaround for potential rate limiting. Sleep and retry
                # with the same link
                if result.status_code != 500:
                    _log(f'{next_link}: Rate limit?')
                    sleep(5)
                    continue
                else:
                    _log(f'{next_link}: 500 Server Error')
                    if 'page=' in next_link:
                        next_link = re.sub(
                                r'page=\d+', f'page={page_num + 1}', next_link)
                    else:
                        next_link = next_link + f'&page={page_num + 1}'
                    page_num += 1
                    continue

            if (next_path := json.get('next_link', None)) is not None:
                next_link = 'https://galaxy.ansible.com' + next_path
            else:
                # End of results
                next_link = None

            yield result.text
            page_num += 1

        _log(f'{api_url}: Done')

    def load_pages(
            self, page_name: str, page_url: str,
            page_size: int = 500,
    ) -> Iterator[GalaxyAPIPage]:
        """Load API content pages."""
        page_it = self._paginate(
                page_url, page_size=str(page_size))
        yield from (
                GalaxyAPIPage(page_name, page_num + 1, page)
                for page_num, page in enumerate(page_it))

    def load_role(self, role_id: int) -> Optional[Dict[str, object]]:
        try:
            result = self._session.get(
                    f'https://galaxy.ansible.com/api/v1/roles/{role_id}/')
            if result.status_code == 403:
                # Forbidden
                return None
            return result.json()  # type: ignore[no-any-return]
        except Timeout:
            # Try again with same link.
            _log(f'{role_id}: Timed out')
            return self.load_role(role_id)
        except JSONDecodeError:
            # Try again with same link.
            if result.status_code != 500:
                sleep(5)
                _log(f'{role_id}: Rate limit?')
                return self.load_role(role_id)
            else:
                raise
