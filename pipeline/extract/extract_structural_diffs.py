"""Discovery part of the pipeline."""
from typing import Any, Dict, List, Iterable, Mapping, Sequence, Set, cast, Tuple, Optional

import itertools
from pathlib import Path

import git
import pendulum
from ansible.errors import AnsibleError
from tqdm import tqdm

from config import MainConfig
from models.role_metadata import GalaxyMetadata
from models.git import GitRepo, GitCommit, GitTag, GitRepoMetadata
from models.serialize import CONVERTER
from models.structural.role import StructuralRoleModel, MultiStructuralRoleModel
from models.structural.diff import StructuralRoleEvolution
from models.version import Version
from pipeline.base import ResultMap, Stage, CacheMiss
from pipeline.extract.extract_structural_models import ExtractStructuralModels


from pprint import pprint

class ExtractStructuralDiffs(
        Stage[StructuralRoleEvolution, MainConfig],
        requires=ExtractStructuralModels
):
    """Extract metadata from the collected roles."""

    dataset_dir_name = 'StructuralRoleEvolution'

    def run(
            self,
            extract_structural_models: ResultMap[MultiStructuralRoleModel]
    ) -> ResultMap[StructuralRoleEvolution]:
        """Run the stage."""
        models_it: Iterable[MultiStructuralRoleModel] = extract_structural_models.values()

        if self.config.progress:
            models_it = tqdm(models_it, desc='Extract structural diffs')

        return ResultMap(map(StructuralRoleEvolution.create, models_it))

    def report_results(self, results: ResultMap[StructuralRoleEvolution]) -> None:
        """Report statistics on gathered roles."""
        num_diff_sets = sum(len(res.diff_sets) for res in results.values())
        num_diffs = sum(len(diffs.diffs) for res in results.values() for diffs in res.diff_sets)
        print('--- Role Structural Diff Extraction ---')
        print(f'Extracted {num_diff_sets} diff sets ({num_diffs} diffs) for {len(results)} roles')
