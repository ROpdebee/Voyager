"""Version analysis stage."""
from typing import (
        Any, Callable, Collection, ContextManager, Dict, Iterable, List,
        Sequence, Tuple)

from collections import Counter
from enum import Enum
from pathlib import PurePosixPath

import git
import matplotlib.pyplot as plt

from tqdm import tqdm

from config import MainConfig
from models.galaxy import GalaxyRole
from models.git import GitRepoPath
from models.version import AnalyzedRepoVersions, RepoVersionDiffs, VersionDiff
from pipeline.analyze.versions import AnalyzeVersions
from pipeline.base import ResultMap, Stage
from pipeline.clone import Clone
from pipeline.discover import Discover
from util import plot, write_csv


class AnalyzeCommits(
        Stage[RepoVersionDiffs, MainConfig],
        requires=(AnalyzeVersions, Clone, Discover)
):
    """Analyse diffs between extracted versions."""

    def __init__(self, config: MainConfig) -> None:
        super().__init__(config)
        self.out = config.output_directory / 'reports' / 'version_diffs'

    def run(
            self, analyze_versions: ResultMap[AnalyzedRepoVersions],
            clone: ResultMap[GitRepoPath],
            discover: ResultMap[GalaxyRole]
    ) -> ResultMap[RepoVersionDiffs]:
        results = []
        repos_to_versions: Iterable[AnalyzedRepoVersions] = (
                analyze_versions.values())
        if self.config.progress:
            repos_to_versions = tqdm(
                    repos_to_versions, desc='Extract commits between versions',
                    unit=' repos')

        # TODO(ROpdebee): Would be nice if we could speed this up a bit,
        #                 currently takes 1-2s per repository. Likely due to
        #                 the diffing, haven't profiled yet though. Caching
        #                 should already massively help on consecutive runs
        #                 though.
        for repo_versions in repos_to_versions:
            diff = RepoVersionDiffs.create(
                    repo_versions,
                    git.Repo(
                        self.config.output_directory
                        / clone[repo_versions.id].path))
            results.append(diff)

        self.export_to_csv(results, clone, discover)
        return ResultMap(results)

    def report_results(self, results: ResultMap[RepoVersionDiffs]) -> None:
        vals = results.values()
        num_versions = sum(len(v.bumps) for v in vals)
        self.report_diffs(vals)
        self.report_frequently_changed_files(vals)

        print('--- Analyse Version Diffs ---')
        print(f'Analysed {num_versions} version diffs, results in {self.out}')

    @property
    def cache_file_name(self) -> str:
        return 'versiondiff_analysis.json'

    def plot(
            self, name: str, nrows: int, ncols: int = 1
    ) -> ContextManager[Any]:
        return plot(self.out / f'{name}.pdf', nrows, ncols)

    def report_diffs(self, results: Collection[RepoVersionDiffs]) -> None:
        for outliers, tag in zip((True, False), ('', '_no_outliers')):
            with plot(
                    self.out / f'version_diffs{tag}.pdf', 3,
                    gridspec_kw={
                        'height_ratios': [2, 4, 2],
                        'width_ratios': [3]
                    }, figsize=(15, 6)) as (f, axes):
                report_num_commits(results, axes[0], outliers)
                report_lines_changed(results, axes[1], outliers)
                report_files_changed(results, axes[2], outliers)

    def report_frequently_changed_files(
            self, results: Collection[RepoVersionDiffs]
    ) -> None:
        with plot(
                self.out / 'changed_files.pdf', 5, figsize=(10, 20)
        ) as (f, axes):
            report_touched_files(results, list(axes))

        with plot(
                self.out / 'changed_dirs.pdf', 5, figsize=(10, 20)
        ) as (f, axes):
            report_touched_dirs(results, list(axes))

    def export_to_csv(
            self,
            results: Collection[RepoVersionDiffs],
            repos: ResultMap[GitRepoPath],
            roles: ResultMap[GalaxyRole]
    ) -> None:
        header_files = (
                'role id', 'role name', 'owner', 'repo', 'touched file',
                'insertions', 'deletions', 'v1..v2')
        header_lines = (
                'role id', 'role name', 'owner', 'repo', 'insertions',
                'deletions', 'v1..v2')
        header_commits = (
                'role id', 'role name', 'owner', 'repo', 'commit sha1',
                'author name', 'author email', 'date', 'v1..v2')

        files: List[Tuple[str, str, str, str, str, int, int, str]] = []
        lines: List[Tuple[str, str, str, str, int, int, str]] = []
        commits: List[Tuple[str, str, str, str, str, str, str, int, str]] = []
        for diffs in results:
            role = roles[diffs.id]
            for bump_diff in diffs.bumps:
                diff_id = bump_diff.id
                files.extend((
                        (
                            role.id, role.name, role.github_user,
                            role.github_repo, str(f.file_path),
                            f.insertions, f.deletions, diff_id)
                        for f in bump_diff.touched_files))
                lines.append((
                        role.id, role.name, role.github_user, role.github_repo,
                        bump_diff.insertions, bump_diff.deletions, diff_id))
                commits.extend((
                        (
                            role.id, role.name, role.github_user,
                            role.github_repo, commit.sha1, commit.author_name,
                            commit.author_email, commit.authored_date, diff_id)
                        for commit in bump_diff.commits))

        self.out.mkdir(exist_ok=True, parents=True)
        write_csv(self.out / 'commits.csv', header_commits, commits)
        write_csv(self.out / 'touched_files.csv', header_files, files)
        write_csv(self.out / 'touched_lines.csv', header_lines, lines)


class Label(Enum):
    bumps = 'Any bump'
    major_to_major = 'Major -> Major'
    minor_to_minor = 'Minor -> Minor'
    to_major = '-> Major'
    to_minor = '-> Minor'


def get_diffs_attr(
        results: Collection[RepoVersionDiffs], change_attr: str
) -> Dict[Label, List[int]]:
    # Order of the dict will always be guaranteed to be the order of attribute
    # declarations in Label, since 3.7
    return {
        label: [
            getattr(diff, change_attr)
            for repo in results
            for diff in getattr(repo, label.name)]
        for label in Label}


def report_num_commits(
        results: Collection[RepoVersionDiffs], ax: plt.Axes, outliers: bool
) -> None:
    ax.set_title('#commits between versions')
    ax.set_xlabel('#commits changed')
    ax.set_ylabel('Type of bump')
    commit_per_bump_type = get_diffs_attr(results, 'num_commits')
    ax.boxplot(  # type: ignore[attr-defined]
            commit_per_bump_type.values(),
            labels=[lbl.value for lbl in commit_per_bump_type.keys()],
            vert=False, showfliers=outliers, widths=0.5)
    ax.invert_yaxis()  # type: ignore[attr-defined]


def report_lines_changed(
        results: Collection[RepoVersionDiffs], ax: plt.Axes, outliers: bool
) -> None:
    ax.set_title('#insertions and #deletions between versions')
    ax.set_xlabel('#lines')
    ax.set_ylabel('Type of bump')
    insertions_per_bump_type = get_diffs_attr(results, 'insertions')
    deletions_per_bump_type = get_diffs_attr(results, 'deletions')
    ticks: List[float] = []
    for (i, label) in enumerate(Label):
        ins_dels = [
                insertions_per_bump_type[label],
                deletions_per_bump_type[label]]
        idx = i * 3
        ticks.append(idx + .5)
        bp = ax.boxplot(  # type: ignore[attr-defined]
                ins_dels, positions=[idx, idx + 1],
                vert=False, showfliers=outliers, widths=0.5,
                patch_artist=True)
        for box, color in zip(bp['boxes'], ('green', 'red')):
            box.set_facecolor(color)
    ax.set_yticks(ticks)
    ax.set_yticklabels([label.value for label in Label])

    # Dummy plots for legend
    dummy_insertions, = ax.plot(
            [1, 1], 'g-', label='Insertions')  # type: ignore
    dummy_deletions, = ax.plot(
            [1, 1], 'r-', label='Deletions')  # type: ignore
    ax.legend()
    dummy_insertions.set_visible(False)
    dummy_deletions.set_visible(False)

    ax.invert_yaxis()  # type: ignore[attr-defined]


def report_files_changed(
        results: Collection[RepoVersionDiffs], ax: plt.Axes, outliers: bool
) -> None:
    ax.set_title('#files changed between versions')
    ax.set_xlabel('#files changed')
    ax.set_ylabel('Type of bump')
    files_per_bump_type = get_diffs_attr(results, 'num_files_changed')
    ax.boxplot(  # type: ignore[attr-defined]
            files_per_bump_type.values(),
            labels=[lbl.value for lbl in files_per_bump_type.keys()],
            vert=False, showfliers=outliers, widths=0.5)
    ax.invert_yaxis()  # type: ignore[attr-defined]


def _count_touches(
        diffs: List[VersionDiff], transform: Callable[[PurePosixPath], str],
        num: int
) -> List[Tuple[str, float]]:
    touches_per_diff = (
        {transform(f.file_path) for f in diff.touched_files} for diff in diffs)
    num_diffs = len(diffs)
    counter = Counter((f for touches in touches_per_diff for f in touches))
    top_n = counter.most_common(num)
    t = [(el, count / num_diffs) for (el, count) in top_n]
    for (_, freq) in t:
        assert freq <= 1
    return t


def count_touches_per_bump(
        results: Collection[RepoVersionDiffs],
        transform: Callable[[PurePosixPath], str],
        num: int
) -> Dict[Label, List[Tuple[str, float]]]:
    return {
        label: _count_touches(
                    [diffs for repo in results
                        for diffs in getattr(repo, label.name)],
                    transform, num)
        for label in Label}


def report_touched_files(
        results: Collection[RepoVersionDiffs], axes: Sequence[plt.Axes]
) -> None:
    most_touched_files_per_bump = count_touches_per_bump(results, str, 20)

    for ax, (lbl, files) in zip(axes, most_touched_files_per_bump.items()):
        ax.set_title(f'Frequently touched files in {lbl.value.lower()} bumps')
        ax.set_xlabel('Times touched in version bump (%)')
        ax.set_ylabel('File path')

        ax.barh(  # type: ignore[attr-defined]
                [f[0] for f in files], [f[1] for f in files])
        ax.set_xticks([i / 10 for i in range(0, 11)])
        ax.set_xticklabels([f'{i}%' for i in range(0, 101, 10)])
        ax.invert_yaxis()  # type: ignore[attr-defined]


def report_touched_dirs(
        results: Collection[RepoVersionDiffs], axes: Sequence[plt.Axes]
) -> None:
    most_touched_files_per_bump = count_touches_per_bump(
            results, lambda p: str(p.parent), 20)

    for ax, (lbl, files) in zip(axes, most_touched_files_per_bump.items()):
        ax.set_title(f'Frequently touched dirs in {lbl.value.lower()} bumps')
        ax.set_xlabel('Times touched in version bump (%)')
        ax.set_ylabel('Directory path')

        ax.barh(  # type: ignore[attr-defined]
                [f[0] for f in files], [f[1] for f in files])
        ax.set_xticks([i / 10 for i in range(0, 11)])
        ax.set_xticklabels([f'{i}%' for i in range(0, 101, 10)])
        ax.invert_yaxis()  # type: ignore[attr-defined]
