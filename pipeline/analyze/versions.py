"""Version analysis stage."""
from typing import Any, Collection, ContextManager

from collections import Counter

import util

from config import MainConfig
from models.version import RepoVersions, AnalyzedRepoVersions
from pipeline.extract.versions import ExtractVersions
from pipeline.base import ResultMap, Stage


class AnalyzeVersions(
        Stage[AnalyzedRepoVersions, MainConfig], requires=ExtractVersions
):
    """Analyse extracted versions."""

    def __init__(self, config: MainConfig) -> None:
        super().__init__(config)
        self.out = config.output_directory / 'reports' / 'versions'

    def run(
            self, extract_versions: ResultMap[RepoVersions]
    ) -> ResultMap[AnalyzedRepoVersions]:
        return ResultMap(
                AnalyzedRepoVersions(repo_versions)
                for repo_versions in extract_versions.values())

    def report_results(self, results: ResultMap[AnalyzedRepoVersions]) -> None:
        vals = results.values()
        num_versions = sum(len(v.versions) for v in vals)
        self.report_num_versions(vals)
        self.report_version_kind(vals)
        self.report_unstable_versions(vals)
        self.report_prereleases(vals)
        self.report_times(vals)

        print('--- Analyse Versions ---')
        print(f'Analysed {num_versions} versions, results in {self.out}')

    def plot(
            self, name: str, nrows: int, ncols: int = 1
    ) -> ContextManager[Any]:
        return util.plot(self.out / f'{name}.pdf', nrows, ncols)

    def report_num_versions(
            self, results: Collection[AnalyzedRepoVersions]
    ) -> None:
        with self.plot('num_versions', 2, 2) as (f, ax):
            ax[0, 0].set_title('Any version')
            ax[0, 0].boxplot([len(rv.versions) for rv in results])
            ax[0, 0].set_ylabel('Number of versions')

            ax[0, 1].set_title('Major versions')
            ax[0, 1].boxplot([len(rv.majors) for rv in results])
            ax[0, 1].set_ylabel('Number of versions')

            ax[1, 0].set_title('Minor versions')
            ax[1, 0].boxplot([len(rv.minors) for rv in results])
            ax[1, 0].set_ylabel('Number of versions')

            ax[1, 1].set_title('Patch versions')
            ax[1, 1].boxplot([len(rv.patches) for rv in results])
            ax[1, 1].set_ylabel('Number of versions')

    def report_version_kind(
            self, results: Collection[AnalyzedRepoVersions]
    ) -> None:
        with self.plot('version_kinds', 2, 2) as (f, ax):
            ax[0, 0].set_title('Looks like semantic versions')
            ax[0, 0].boxplot([rv.fraction_like_semantic for rv in results])
            ax[0, 0].set_ylabel('% of versions')

            ax[0, 1].set_title('Has build metadata')
            ax[0, 1].boxplot([rv.fraction_has_build_meta for rv in results])
            ax[0, 1].set_ylabel('% of versions')

            ax[1, 0].set_title('Prereleases')
            ax[1, 0].boxplot([rv.fraction_prereleases for rv in results])
            ax[1, 0].set_ylabel('% of versions')

            ax[1, 1].set_title('Unstable (0.x.y)')
            ax[1, 1].boxplot([rv.fraction_unstable for rv in results])
            ax[1, 1].set_ylabel('% of versions')

    def report_unstable_versions(
            self, results: Collection[AnalyzedRepoVersions]
    ) -> None:
        with self.plot('unstable_versions', 3) as (f, ax):
            labels = ['First release', 'Current release']
            stables = [
                sum(1 for rv in results if not rv.started_as_unstable),
                sum(1 for rv in results if rv.is_now_stable)]
            unstables = [
                sum(1 for rv in results if rv.started_as_unstable),
                sum(1 for rv in results if not rv.is_now_stable)]
            ax[0].set_title('Unstable -> Stable')
            ax[0].barh(labels, stables, label='Stable')
            ax[0].barh(
                    labels, unstables, left=stables,
                    label='Unstable (0.x.y)')
            ax[0].invert_yaxis()
            ax[0].set_xlabel('Number of repos')
            ax[0].legend()

            ax[1].set_title('Time to stable (days)')
            ax[1].boxplot(
                    [rv.time_until_stable.in_days() for rv in results
                     if rv.is_now_stable and rv.started_as_unstable],
                    vert=False)
            ax[1].set_xlabel('Number of days')

            first_versions = Counter(
                    [
                        rv.first_version.normalized for rv in results
                        if rv.first_version is not None]).items()
            first_versions_sort = sorted(first_versions, key=lambda t: -t[1])
            fv_counts = [v[1] for v in first_versions_sort]
            fv_versions = [v[0] for v in first_versions_sort]
            ax[2].set_title('First version')
            done = 0
            for c, v in zip(fv_counts, fv_versions):
                ax[2].barh(['Versions'], [c], label=v, left=done)
                done += c
            ax[2].set_xlabel('Number of repos')
            ax[2].legend(ncol=5)

    def report_prereleases(
            self, results: Collection[AnalyzedRepoVersions]
    ) -> None:
        with self.plot('prerelease_versions', 3) as (f, ax):
            labels = ['Major bump', 'Minor bump', 'Patch bump']
            versions_to_prerlses = [
                (rv, rv.versions_to_prereleases) for rv in results]
            num_major_pres = [
                    len(m[bump])
                    for rv, m in versions_to_prerlses
                    for bump in rv.majors]
            num_minor_pres = [
                    len(m[bump])
                    for rv, m in versions_to_prerlses
                    for bump in rv.minors]
            num_patch_pres = [
                    len(m[bump])
                    for rv, m in versions_to_prerlses
                    for bump in rv.patches]
            ax[0].set_title('Number of prereleases for version bump')
            ax[0].boxplot(
                    [num_major_pres, num_minor_pres, num_patch_pres],
                    labels=labels)
            ax[0].set_ylabel('Number of prereleases')

            time_from_pre = [(rv, rv.time_from_prerelease) for rv in results]
            time_major_pres = [
                    m[bump].in_days()
                    for rv, m in time_from_pre
                    for bump in rv.majors
                    if bump in m]
            time_minor_pres = [
                    m[bump].in_days()
                    for rv, m in time_from_pre
                    for bump in rv.minors
                    if bump in m]
            time_patch_pres = [
                    m[bump].in_days()
                    for rv, m in time_from_pre
                    for bump in rv.patches
                    if bump in m]
            ax[1].set_title('Time until release')
            ax[1].boxplot(
                    [time_major_pres, time_minor_pres, time_patch_pres],
                    labels=labels, vert=False)
            ax[1].invert_yaxis()
            ax[1].set_xlabel('Number of days')

            pre_names = Counter(
                    [v.prerelease
                     for rv in results for v in rv.prereleases]).items()
            pre_names_sort = sorted(pre_names, key=lambda t: -t[1])
            name_counts = [v[1] for v in pre_names_sort]
            name_names = [v[0] for v in pre_names_sort]
            ax[2].set_title('Prerelease name')
            done = 0
            for c, v in zip(name_counts, name_names):
                ax[2].barh(['Versions'], [c], label=v, left=done)
                done += c
            ax[2].set_xlabel('Number of versions')
            ax[2].legend(ncol=5)

    def report_times(self, results: Collection[AnalyzedRepoVersions]) -> None:
        with self.plot('release_times', 4) as (_, ax):
            times = [(rv, rv.time_between_versions) for rv in results]
            ax[0].set_title('Time to any version bump')
            ax[0].boxplot(
                    [t.in_days() for _, tm in times for t in tm.values()],
                    vert=False)
            ax[0].set_xlabel('Number of days')

            major_to_major = [
                    t.in_days()
                    for rv in results
                    for t in rv.time_between_version_bumps(
                        rv.major_to_major_bumps).values()]
            minor_to_major = [
                    t.in_days()
                    for rv in results
                    for t in rv.time_between_version_bumps(
                        rv.minor_to_major_bumps).values()]
            patch_to_major = [
                    t.in_days()
                    for rv in results
                    for t in rv.time_between_version_bumps(
                        rv.patch_to_major_bumps).values()]
            labels = ['major', 'minor', 'patch']
            ax[1].set_title('Time to major bump')
            ax[1].boxplot(
                    [major_to_major, minor_to_major, patch_to_major],
                    labels=labels, vert=False)
            ax[1].set_xlabel('Number of days')
            ax[1].set_ylabel('From last ...')

            minor_to_minor = [
                    t.in_days()
                    for rv in results
                    for t in rv.time_between_version_bumps(
                        rv.minor_to_minor_bumps).values()]
            patch_to_minor = [
                    t.in_days()
                    for rv in results
                    for t in rv.time_between_version_bumps(
                        rv.patch_to_minor_bumps).values()]
            labels = ['minor', 'patch']
            ax[2].set_title('Time to minor bump')
            ax[2].boxplot(
                    [minor_to_minor, patch_to_minor],
                    labels=labels, vert=False)
            ax[2].set_xlabel('Number of days')
            ax[2].set_ylabel('From last ...')

            patch_to_patch = [
                    t.in_days()
                    for rv in results
                    for t in rv.time_between_version_bumps(
                        rv.patch_to_patch_bumps).values()]
            labels = ['patch']
            ax[3].set_title('Time to patch bump')
            ax[3].boxplot(patch_to_patch, labels=labels, vert=False)
            ax[3].set_xlabel('Number of days')
            ax[3].set_ylabel('From last ...')

    @property
    def cache_file_name(self) -> str:
        return 'version_analysis.json'
