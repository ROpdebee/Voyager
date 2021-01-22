"""Version analysis stage."""
from typing import (
        Collection,
        Dict,
        Iterable,
        List,
        Optional,
        Sequence,
        Tuple,
        Union
)

import json

from collections import defaultdict
from itertools import chain
from functools import lru_cache
from pathlib import Path
from shutil import copytree, rmtree
from tempfile import TemporaryDirectory

import git

from ansible.errors import AnsibleError
from tqdm import tqdm

from config import DiffConfig
from models.git import GitRepo
from models.structural.diff import Diff, get_diff_category_leafs
from models.structural.metrics import RepoDiffMetrics, StructuralDiffMetrics
from models.structural.role import Role
from models.version import RepoVersions, Version
from pipeline.extract.versions import ExtractVersions
from pipeline.base import ResultMap, Stage
from pipeline.collect.clone import Clone
from util import write_csv


class StructuralDiff(
        Stage[RepoDiffMetrics, DiffConfig],
        requires=(ExtractVersions, Clone)
):
    """Analyse diffs between extracted versions."""

    def __init__(self, config: DiffConfig) -> None:
        super().__init__(config)
        self.out = config.output_directory / 'reports' / 'structural_diffs'
        self.dump_dir = self.out / 'dump'
        self.out.mkdir(exist_ok=True, parents=True)
        try:
            rmtree(self.dump_dir)
        except FileNotFoundError:
            pass
        self.dump_dir.mkdir()

    def run(
            self, extract_versions: ResultMap[RepoVersions],
            clone: ResultMap[GitRepo]
    ) -> ResultMap[RepoDiffMetrics]:
        results = []
        repos_to_bumps: Dict[GitRepo, List[Tuple[Version, Version]]]
        repos_to_bumps = defaultdict(list)
        for repo_id, repo_versions in extract_versions.items():
            repos_to_bumps[clone[repo_id]].extend(
                    zip(repo_versions.versions, repo_versions.versions[1:]))

        repo_list: Iterable[Tuple[GitRepo, List[Tuple[Version, Version]]]]
        bump_pbar: Optional[tqdm]
        repo_list = [(r, b) for r, b in repos_to_bumps.items() if b]
        if self.config.progress:
            repo_list = tqdm(
                    repo_list, desc='Extract structural diffs',
                    unit=' repos')
            bump_pbar = tqdm(
                    desc='Extract structural diffs', unit=' version pairs',
                    total=sum(len(rb[1]) for rb in repos_to_bumps.items()))
        else:
            bump_pbar = None

        for repo_path, versions in repo_list:
            results.append(self.diff_repo(repo_path, versions, bump_pbar))
        if bump_pbar is not None:
            bump_pbar.close()

        self.export_to_csv(results)
        return ResultMap(results)

    def diff_repo(
            self, repo_path: GitRepo,
            bumps: Sequence[Tuple[Version, Version]],
            bump_pbar: Optional[tqdm]
    ) -> RepoDiffMetrics:
        # Copy the role repo to a temp dir, since we'll be checking out
        # different tags and would like the dataset to remain in its normal
        # condition.
        repo_cache_file_name = self.cache_file_name.replace(
                '.json', repo_path.path.name + '.json')
        repo_cache_dir = self.config.output_directory / 'struct_diff_cache'
        repo_cache_file = repo_cache_dir / repo_cache_file_name
        repo_cache_dir.mkdir(exist_ok=True)

        try:
            rdm = RepoDiffMetrics.from_json_str(repo_cache_file.read_text())
            if bump_pbar is not None:
                bump_pbar.update(len(rdm.metric_map))
            return rdm
        except (OSError, json.JSONDecodeError):
            pass

        repo_source = self.config.output_directory / repo_path.path
        results: List[StructuralDiffMetrics] = []
        with TemporaryDirectory() as tmpdir:
            role_path = Path(tmpdir) / repo_source.name
            self._copy_repo(repo_source, role_path)
            for v1, v2 in bumps:
                diffs = self.diff_versions(role_path, v1, v2)
                self.dump_diffs(
                        repo_path.path.name, v1.original, v2.original, diffs)
                results.append(StructuralDiffMetrics.create(
                        v1.original, v2.original, diffs))
                if bump_pbar is not None:
                    bump_pbar.update(1)
        rdm = RepoDiffMetrics(
                role_id=repo_path.id,
                metric_map={f'{m.v1}..{m.v2}': m for m in results})
        try:
            repo_cache_file.write_text(rdm.to_json_str())
        except OSError:
            pass
        return rdm

    def diff_versions(
            self, role_path: Path, v1: Version, v2: Version
    ) -> Optional[Sequence[Diff]]:
        try:
            role_v1 = self._load_role(role_path, v1)
            role_v2 = self._load_role(role_path, v2)
        except (AnsibleError, UnicodeEncodeError):
            return None
        except Exception:
            print(f'Failed to load {role_path} {v1} {v2}')
            raise
        return role_v1.diff(role_v2)

    def dump_diffs(
            self, role_name: str, v1: str, v2: str,
            diffs: Optional[Sequence[Diff]]
    ) -> None:
        if not self.config.dump_changes:
            return
        dump_file = self.dump_dir / (role_name + '.txt')
        with dump_file.open('at') as dump_f:
            header = f'{v1} -> {v2}'
            print(header, file=dump_f)
            print('=' * len(header), file=dump_f)
            print(file=dump_f)
            if diffs is None:
                print('FAILED', file=dump_f)
                return

            sorted_diffs = sorted(diffs, key=lambda d: d.object_id)
            for d in sorted_diffs:
                print(d, file=dump_f)
                print(file=dump_f)

    def _copy_repo(self, orig_path: Path, new_path: Path) -> None:
        """Copy the repository to a new path."""
        copytree(orig_path, new_path, symlinks=True)

    # Cache these results a bit, since we don't want to unnecessarily parse
    # a role twice. The size of the cache could probably be decreased further.
    @lru_cache(10)
    def _load_role(self, repo_path: Path, version: Version) -> Role:
        g = git.Git(repo_path)
        g.checkout(version.original, '-f')
        return Role.load(repo_path, self.config.output_directory / 'repos')

    def report_results(self, results: ResultMap[RepoDiffMetrics]) -> None:
        vals = results.values()
        num_versions = sum(len(m.metric_map) for m in vals)

        print('--- Analyse Structural Diffs ---')
        print(f'Analysed {num_versions} version diffs, results in {self.out}')

    @property
    def cache_file_name(self) -> str:
        return 'structural_diff_analysis.json'

    def export_to_csv(
            self,
            results: Collection[RepoDiffMetrics],
    ) -> None:
        header: Tuple[str, ...] = ('role id', 'v1', 'v2')
        change_cats = sorted(c.__name__ for c in get_diff_category_leafs())
        header = tuple(chain(header, change_cats))

        csv_lines: List[Tuple[Union[str, int, None], ...]] = []
        for repo_metrics in results:
            role_id = repo_metrics.id
            for metrics in repo_metrics.metric_map.values():
                v1 = metrics.v1
                v2 = metrics.v2
                summ = metrics.metric_summary
                csv_line: Tuple[Union[str, int, None], ...] = (role_id, v1, v2)
                if summ is None:
                    csv_line = tuple(chain(
                            csv_line, [None] * len(change_cats)))
                else:
                    csv_line = tuple(chain(
                            csv_line, (summ[cat] for cat in change_cats)))
                csv_lines.append(csv_line)

        write_csv(self.out / 'diff_metrics.csv', header, csv_lines)
