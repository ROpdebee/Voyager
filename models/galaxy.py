"""Data models for the Ansible Galaxy API."""
from __future__ import annotations

from typing import Any, Dict, Sequence

import abc
import json
from pathlib import Path


from models.base import Model


class GalaxyAPIPage(Model):
    """Container for a page returned by the Galaxy API."""

    def __init__(
            self, page_type: str, page_num: int, page_content: str
    ) -> None:
        self.page_type = page_type
        self.page_num = page_num
        self.page_content: Dict[str, Any] = json.loads(page_content)

    @property
    def id(self) -> str:
        return f'{self.page_type}/{self.page_num}'

    @property
    def response(self) -> Dict[str, object]:
        return self.page_content

    def dump(self, directory: Path) -> Path:
        fpath = directory / f'{self.page_type}_{self.page_num}.json'
        fpath.write_text(json.dumps(
                self.page_content, sort_keys=True, indent=2))
        return fpath

    @classmethod
    def load(cls, page_id: str, path: Path) -> GalaxyAPIPage:
        page_type, page_num_str = page_id.split('/')
        return cls(page_type, int(page_num_str), path.read_text())


class GalaxyImportEventAPIResponse(Model):
    """Container for pages of import events returned by Galaxy API."""

    def __init__(
            self, role_id: int, pages: Sequence[Dict[str, object]]
    ) -> None:
        self.role_id = role_id
        self.pages = pages

    @property
    def id(self) -> str:
        return str(self.role_id)

    def dump(self, directory: Path) -> Path:
        fpath = directory / f'{self.role_id}.json'
        fpath.write_text(json.dumps(self.pages, sort_keys=True, indent=2))
        return fpath

    @classmethod
    def load(cls, role_id: str, path: Path) -> GalaxyImportEventAPIResponse:
        return cls(int(role_id), json.loads(path.read_text()))
