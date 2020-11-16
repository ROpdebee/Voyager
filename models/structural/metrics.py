"""Metrics for structural diffs."""
from typing import Mapping, Optional, Sequence

import attr

from models.base import Model
from .diff import Diff, get_diff_category_leafs


@attr.s(auto_attribs=True, frozen=True)
class StructuralDiffMetrics(Model):
    """Model for metrics of structural diffs."""
    v1: str
    v2: str
    metric_summary: Optional[Mapping[str, int]]

    @property
    def id(self) -> str:
        return f'{self.v1}..{self.v2}'

    @classmethod
    def create(
            cls, v1: str, v2: str, diffs: Optional[Sequence[Diff]]
    ) -> 'StructuralDiffMetrics':
        if diffs is None:
            return StructuralDiffMetrics(v1, v2, None)

        metric_summary = {}
        for cat in get_diff_category_leafs():
            metric_summary[cat.__name__] = 0

        # Count the number of each diff category
        for d in diffs:
            metric_summary[d.__class__.__name__] += 1
        return StructuralDiffMetrics(v1, v2, metric_summary)


@attr.s(auto_attribs=True, frozen=True)
class RepoDiffMetrics(Model):
    """Structural diff metrics for multiple versions in a repo."""
    metric_map: Mapping[str, StructuralDiffMetrics]
    role_id: str

    @property
    def id(self) -> str:
        return self.role_id
