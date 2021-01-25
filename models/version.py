"""Model for versions."""
from typing import (
        Callable, Dict, Iterator, List, Optional, Sequence, Set, Tuple, Union,
        overload)

from collections import defaultdict, OrderedDict
from functools import cached_property, lru_cache
from itertools import chain, dropwhile, takewhile
from operator import attrgetter
from pathlib import PurePosixPath

import attr
import git
import pendulum

from models.base import Model
from models.git import GitCommit as Commit


MMP = Tuple[int, int, int]
Bump = Tuple['Version', 'Version']

# SHA1 hash of an empty git tree
GIT_EMPTY_TREE = '4b825dc642cb6eb9a060e54bf8d69288fbee4904'


@attr.s(auto_attribs=True, frozen=True, order=False)
class Version(Model):
    """Model for versions.

    Implemented according to https://semver.org/.
    """

    major: int
    minor: int
    patch: int
    extra: Optional[str]
    prerelease: Optional[str]
    build_meta: Optional[str]

    original: str
    date: pendulum.DateTime
    commit_sha: str

    @property
    def is_prerelease(self) -> bool:
        """Is this version a prerelease?"""
        return self.prerelease is not None

    @property
    def has_build_meta(self) -> bool:
        """Does this version have build metadata?"""
        return self.build_meta is not None

    @property
    def is_initial_dev(self) -> bool:
        """Is this version a part of initial development?

        Is major version equal to 0?
        """
        return self.major == 0

    @property
    def is_major_version(self) -> bool:
        """Is this version a major bump?"""
        return self.minor <= 0 and self.patch <= 0 and not self.is_prerelease

    @property
    def is_minor_version(self) -> bool:
        """Is this version a minor version?"""
        return self.minor > 0 and self.patch <= 0 and not self.is_prerelease

    @property
    def is_patch_version(self) -> bool:
        """Is this version a patch bump?"""
        return self.patch > 0 and not self.is_prerelease

    @property
    def id(self) -> str:
        """Get the ID of the version, i.e. the version itself."""
        return self.original

    @property
    def is_semantic_version(self) -> bool:
        """Check whether the version follows the semantic versioning scheme.

        The version needs to have a major, minor, and patch number.
        """
        return -1 not in self.mmp and self.extra is not None

    @property
    def was_parsed_correctly(self) -> bool:
        """Check whether there were issues parsing the version."""
        return self.major != -1

    @property
    def has_extra(self) -> bool:
        """Check whether there is an extra version number."""
        return self.extra is not None

    @property
    def mmp(self) -> MMP:
        return (self.major, self.minor, self.patch)

    def __gt__(self, other: 'Version') -> bool:
        # First check the major, minor, patch numbers
        if self.mmp != other.mmp:
            return self.mmp > other.mmp

        # Prerelease precedes main release
        if self.is_prerelease != other.is_prerelease:
            return not self.is_prerelease

        # Either both, or neither, are prereleases, check the dates if possible
        if self.date != other.date:
            return self.date > other.date

        # Dates are the same, need a consistent ordering based on the rest of
        # the info. Compare the original versions lexicographically. This may
        # not make sense in some cases, but it doesn't make much sense to have
        # two versions with the same MMP, both prereleases and created at the
        # same time.
        return self.original > other.original

    # Could use functools.total_ordering, but mypy gets confused
    def __ge__(self, other: 'Version') -> bool:
        return self > other or self == other

    def __lt__(self, other: 'Version') -> bool:
        return not self >= other

    def __le__(self, other: 'Version') -> bool:
        return not self > other

    @property
    def normalized(self) -> str:
        """Return a normalized version string."""
        norm_mmp = tuple(str(max(n, 0)) for n in self.mmp)
        norm_str = '.'.join(norm_mmp)
        if self.prerelease is not None:
            norm_str += '-' + self.prerelease
        return norm_str

    @staticmethod
    def from_version_str(
            version_str: str, date: pendulum.DateTime, commit_sha: str
    ) -> 'Version':
        """Create a version from a version string."""
        # Strip the leading 'v', and spaces, if any.
        v = version_str.lower()
        if v.startswith('v'):
            v = v[1:]
        v = v.strip()

        prerelease = None
        build = None

        # Take the build meta-info, if any
        try:
            v, build = v.split('+')
        except ValueError:
            pass

        # Take the prerelease, if any
        try:
            v, prerelease = v.split('-')
        except ValueError:
            pass

        nums = v.split('.')
        # Remove any empty strings. Happens where there's trailing or leading
        # dots
        nums = [num for num in nums if num]
        major = minor = patch = -1
        extra = None
        try:
            major = int(nums[0])
            minor = int(nums[1])
            patch = int(nums[2])
            extra = '.'.join(nums[3:])
        except (ValueError, IndexError):
            pass

        return Version(
                major, minor, patch, extra, prerelease, build, version_str,
                date, commit_sha)


BIG_BANG_VERSION = Version(
        0, 0, 0, None, None, None, GIT_EMPTY_TREE, pendulum.datetime(1, 1, 1),
        GIT_EMPTY_TREE)


def _sorted_tuple(lst: List[Version]) -> Tuple[Version, ...]:
    return tuple(sorted(lst))


@attr.s(auto_attribs=True, frozen=True)
class RepoVersions(Model):
    """Collection of versions for a repository."""
    repo_id: str
    versions: Tuple[Version, ...] = attr.ib(converter=_sorted_tuple)

    @property
    def id(self) -> str:
        return self.repo_id

    def __iter__(self) -> Iterator[Version]:
        """Iterate through the versions in sorted order."""
        return iter(self.versions)

    def __len__(self) -> int:
        """Get the number of versions."""
        return len(self.versions)

    @overload
    def __getitem__(self, index: int) -> Version:
        ...

    @overload
    def __getitem__(self, index: slice) -> Tuple[Version, ...]:
        ...

    def __getitem__(
            self, index: Union[int, slice]
    ) -> Union[Version, Tuple[Version, ...]]:
        """Index in the version list."""
        return self.versions[index]

    @lru_cache
    def get(self, version_mmp: MMP) -> Optional[Version]:
        """Get the main version for an MMP tuple."""
        for v in self.versions:
            if v.mmp == version_mmp and not v.is_prerelease:
                return v
        return None


@attr.s(auto_attribs=True, frozen=True)
class AnalyzedRepoVersions(Model):
    """Analysis results of RepoVersions."""
    versions: RepoVersions

    def _fraction(self, predicate: Callable[[Version], bool]) -> float:
        """Calculate a fraction according to a predicate."""
        if len(self.versions) == 0:
            return 0.0
        return (len(self.filter_versions(predicate))
                / float(len(self.versions)))

    @cached_property
    def fraction_like_semantic(self) -> float:
        """Get the percentage of semantic-like versions.

        Percentage of the repo's versions that look like semantic versions."""
        return self._fraction(attrgetter('is_semantic_version'))

    @cached_property
    def fraction_has_build_meta(self) -> float:
        """Get the percentage of versions with build metadata."""
        return self._fraction(attrgetter('has_build_meta'))

    @cached_property
    def fraction_prereleases(self) -> float:
        """Get the percentage of versions that are prereleases."""
        return self._fraction(attrgetter('is_prerelease'))

    @cached_property
    def fraction_unstable(self) -> float:
        """Get the percentage of versions that are unstable."""
        return self._fraction(attrgetter('is_initial_dev'))

    @cached_property
    def versions_to_prereleases(self) -> Dict[Version, List[Version]]:
        """Get a mapping from versions to their pre-releases."""
        mapping: Dict[Version, List[Version]] = defaultdict(list)
        for version in self.prereleases:
            main_v = self.versions.get(version.mmp)
            if main_v is not None:
                mapping[main_v].append(version)

        return mapping

    @cached_property
    def time_between_versions(self) -> Dict[Version, pendulum.Duration]:
        """Get a mapping between a version and the time it took to release.

        This does not include the first version.
        """
        deltas: OrderedDict[Version, pendulum.Duration] = OrderedDict()
        # zip drops the last elements of the longer list
        for prev, nxt in zip(self.versions, self.versions[1:]):
            deltas[nxt] = nxt.date - prev.date

        return deltas

    @lru_cache
    def time_between(self, v1: Version, v2: Version) -> pendulum.Duration:
        """Get the time between two versions."""
        versions_from_excl = dropwhile(lambda v: v <= v1, self.versions)
        versions_to_incl = takewhile(lambda v: v <= v2, versions_from_excl)
        durations = self.time_between_versions
        total_duration = pendulum.Duration(0)
        # Could use sum(...), but mypy gets confused?
        for v in versions_to_incl:
            total_duration += durations[v]

        return total_duration

    @lru_cache
    def time_between_version_bumps(
            self, bumps: Tuple[Bump, ...]
    ) -> Dict[Bump, pendulum.Duration]:
        """Get the durations between versions bumps."""
        bump_deltas: OrderedDict[Bump, pendulum.Duration] = OrderedDict()
        for (m1, m2) in bumps:
            bump_deltas[(m1, m2)] = self.time_between(m1, m2)
        return bump_deltas

    @cached_property
    def time_from_prerelease(self) -> Dict[Version, pendulum.Duration]:
        """Get the times between the first prerelease and the main release."""
        v_to_pre = self.versions_to_prereleases
        bump_deltas: OrderedDict[Version, pendulum.Duration] = OrderedDict()
        for main_v, pres in v_to_pre.items():
            if not pres:
                continue
            bump_deltas[main_v] = self.time_between(pres[0], main_v)
        return bump_deltas

    @property
    def first_version(self) -> Optional[Version]:
        """Get the first version."""
        try:
            return self.versions[0]
        except IndexError:
            return None

    def filter_versions(
            self, pred: Callable[[Version], bool]
    ) -> Tuple[Version, ...]:
        """Get all versions that match a predicate."""
        return tuple(v for v in self.versions if pred(v))

    @property
    def majors(self) -> Tuple[Version, ...]:
        """Get the first major versions, i.e., v1.0.0, v2.0.0, ...."""
        return self.filter_versions(attrgetter('is_major_version'))

    @property
    def minors(self) -> Tuple[Version, ...]:
        """Get the first minor versions, i.e., v1.1.0, v1.2.0, ...."""
        return self.filter_versions(attrgetter('is_minor_version'))

    @property
    def patches(self) -> Tuple[Version, ...]:
        """Get the first patch versions, i.e., v1.0.1, v1.1.1, ...."""
        return self.filter_versions(attrgetter('is_patch_version'))

    @property
    def major_to_major_bumps(self) -> Tuple[Bump, ...]:
        """Get all major -> major bumps, e.g.. v1.0.0 -> v2.0.0."""
        return tuple(
                self.get_bumps(self.majors, attrgetter('is_major_version')))

    @property
    def minor_to_major_bumps(self) -> Tuple[Bump, ...]:
        """Get all minor -> major bumps, e.g.. v1.1.0 -> v2.0.0."""
        non_patch = self.get_bumps(
                self.majors, lambda v: not v.is_patch_version)
        majors = self.get_bumps(self.majors, attrgetter('is_major_version'))
        return tuple(non_patch - majors)

    @property
    def patch_to_major_bumps(self) -> Tuple[Bump, ...]:
        """Get all patch -> major bumps, e.g.. v1.0.9 -> v2.0.0."""
        # NOTE: Using is_patch_version as a predicate won't work, it'll return
        # old patches too!
        bumps = self.get_bumps(self.majors, lambda _: True)
        non_patch = self.get_bumps(
                self.majors, lambda v: not v.is_patch_version)
        return tuple(bumps - non_patch)

    @property
    def minor_to_minor_bumps(self) -> Tuple[Bump, ...]:
        """Get all minor -> minor bumps, e.g.. v1.0.0 -> v1.1.0."""
        return tuple(
                self.get_bumps(self.minors, lambda v: not v.is_patch_version))

    @property
    def patch_to_minor_bumps(self) -> Tuple[Bump, ...]:
        """Get all patch -> minor bumps, e.g.. v1.0.1 -> v1.1.0."""
        bumps = self.get_bumps(self.minors, lambda _: True)
        non_patch = self.get_bumps(
                self.minors, lambda v: not v.is_patch_version)
        return tuple(bumps - non_patch)

    @property
    def patch_to_patch_bumps(self) -> Tuple[Bump, ...]:
        """Get all patch -> patch bumps, e.g.. v1.0.0 -> v1.0.1."""
        return tuple(self.get_bumps(self.patches, lambda _: True))

    def get_bumps(
            self,
            versions: Tuple[Version, ...], pred: Callable[[Version], bool]
    ) -> Set[Bump]:
        """Get the last bump to a list of versions."""
        bumps = set()
        for v in versions:
            before = self.versions_before(v)[::-1]
            for v0 in before:
                if pred(v0):
                    bumps.add((v0, v))
                    break
        return bumps

    @property
    def prereleases(self) -> Tuple[Version, ...]:
        """Get the prereleases."""
        return self.filter_versions(attrgetter('is_prerelease'))

    def versions_before(self, v: Version) -> Tuple[Version, ...]:
        """Get all versions preceding a given version."""
        return tuple(takewhile(lambda v2: v2 < v, self.versions))

    @property
    def started_as_unstable(self) -> bool:
        """Check whether the repo started as unstable.

        I.e., its first version has a 0-major.
        """
        first = self.first_version
        return first is not None and first.is_initial_dev

    @cached_property
    def first_stable(self) -> Optional[Version]:
        """Get the first stable version."""
        for v in self.versions:
            if not v.is_initial_dev:
                return v

        return None

    @property
    def is_now_stable(self) -> bool:
        """Check whether the role is now stable.

        I.e., its latest version does not have a 0-major.
        """
        return self.first_stable is not None

    @property
    def time_until_stable(self) -> pendulum.Duration:
        if self.first_stable is None:
            raise ValueError(
                    'Cannot calculate time until stable: No stable release')
        return self.time_between(self.first_version, self.first_stable)

    @property
    def id(self) -> str:
        return self.versions.repo_id


@attr.s(auto_attribs=True, frozen=True)
class FileDiff:
    file_path: PurePosixPath
    insertions: int
    deletions: int

    @classmethod
    def create(
            cls, file_path: str, stat_dict: 'git.util.StatDict'
    ) -> 'FileDiff':
        return cls(
                PurePosixPath(file_path), stat_dict['insertions'],
                stat_dict['deletions'])


@attr.s(auto_attribs=True, frozen=True)
class VersionDiff(Model):
    v1: Version
    v2: Version

    commits: Tuple[Commit, ...]
    insertions: int
    deletions: int
    touched_files: Tuple[FileDiff, ...]

    @property
    def num_commits(self) -> int:
        return len(self.commits)

    @property
    def num_files_changed(self) -> int:
        return len(self.touched_files)

    @property
    def id(self) -> str:
        return self.v1.id + '..' + self.v2.id

    @classmethod
    def create(cls, repo: git.Repo, v1: Version, v2: Version) -> 'VersionDiff':
        # rev-spec v1..v2 makes sure we only include commits after v1.
        # If, for some reason, v1 is not a parent of v2, it will give all
        # commits "from" the first common parent (excl.) "to" v2 (incl.)
        commits = tuple(
                Commit(
                        raw.hexsha, raw.summary, raw.authored_date,
                        raw.author.name, raw.author.email)
                for raw in repo.iter_commits(f'{v1.original}..{v2.original}'))
        diff_stats = git.Stats._list_from_string(
                repo,
                repo.git.diff(v1.commit_sha, v2.commit_sha, numstat=True))
        return cls(
                v1, v2, commits, diff_stats.total['insertions'],
                diff_stats.total['deletions'],
                tuple(
                        FileDiff.create(p, stats)
                        for p, stats in diff_stats.files.items()))


@attr.s(auto_attribs=True, frozen=True)
class RepoVersionDiffs(Model):
    role_id: str

    # TODO(ROpdebee): Deduplicate?
    major_to_major: Tuple[VersionDiff, ...]
    minor_to_minor: Tuple[VersionDiff, ...]
    bumps: Tuple[VersionDiff, ...]
    to_major: Tuple[VersionDiff, ...]
    to_minor: Tuple[VersionDiff, ...]

    @property
    def id(self) -> str:
        return self.role_id

    @staticmethod
    def diff_consecutives(
            repo: git.Repo, versions: Sequence[Version],
            include_initial: bool = True
    ) -> Tuple[VersionDiff, ...]:
        if not versions:
            return tuple()

        version_diffs: Iterator[VersionDiff] = (
                VersionDiff.create(repo, v1, v2)
                for (v1, v2) in zip(versions, versions[1:]))
        # Prepend with the diff between the initial commit and the version.
        if include_initial:
            version_diffs = chain(
                    [VersionDiff.create(repo, BIG_BANG_VERSION, versions[0])],
                    version_diffs)
        return tuple(version_diffs)

    @staticmethod
    def diff_with_prev(
            repo: git.Repo, incl_versions: Sequence[Version],
            repo_versions: AnalyzedRepoVersions
    ) -> Tuple[VersionDiff, ...]:
        return tuple(
                VersionDiff.create(repo, before[-1], v2)
                for v2 in incl_versions
                if (before := repo_versions.versions_before(v2)))

    @classmethod
    def create(
            cls, versions: AnalyzedRepoVersions, repo: git.Repo
    ) -> 'RepoVersionDiffs':
        major_to_major = cls.diff_consecutives(repo, versions.majors)
        minor_to_minor = cls.diff_consecutives(repo, versions.minors)
        bumps = cls.diff_consecutives(
                repo, versions.versions.versions, include_initial=True)
        to_major = cls.diff_with_prev(repo, versions.majors, versions)
        to_minor = cls.diff_with_prev(repo, versions.minors, versions)
        return cls(
                versions.id, major_to_major, minor_to_minor, bumps,
                to_major, to_minor)
