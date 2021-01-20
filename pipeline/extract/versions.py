"""Version stages."""
from typing import Iterable, List

import git
import pendulum

from tqdm import tqdm

from config import ExtractVersionConfig
from models.git import GitRepoPath
from models.version import Version, RepoVersions
from pipeline.base import ResultMap, Stage
from pipeline.collect.clone import Clone


class ExtractVersions(
        Stage[RepoVersions, ExtractVersionConfig],
        requires=Clone
):
    """Extract the versions from the git repositories."""

    def run(self, clone: ResultMap[GitRepoPath]) -> ResultMap[RepoVersions]:
        repos: Iterable[GitRepoPath] = clone.values()
        if self.config.progress:
            repos = tqdm(repos)

        return ResultMap(map(self.extract_versions, repos))

    def extract_versions(self, repo_path: GitRepoPath) -> RepoVersions:
        repo = git.Repo(self.config.output_directory / repo_path.path)
        versions: List[Version] = []
        for tagref in repo.tags:
            versions.append(self.create_version_from_tag(tagref))

        return RepoVersions(repo_path.role_id, versions)

    def create_version_from_tag(
            self, tagref: git.refs.tag.TagReference
    ) -> Version:
        """Create a version from a tag."""
        if tagref.tag is None or self.config.always_use_commit_date:
            timestamp = tagref.commit.committed_date
        else:
            timestamp = tagref.tag.tagged_date
        return Version.from_version_str(
                tagref.name, pendulum.from_timestamp(timestamp),
                tagref.commit.hexsha)

    def report_results(self, results: ResultMap[RepoVersions]) -> None:
        len_all_versions = sum(
                len(versions.versions) for versions in results.values())
        wrong_parsed = [v for repo in results.values()
                        for v in repo.versions
                        if not v.was_parsed_correctly]
        print('--- Extract versions ---')
        print(f'Extracted {len_all_versions} versions')
        print(f'{len(wrong_parsed)} had problems parsing')
        if wrong_parsed:
            print(', '.join(v.original for v in wrong_parsed))

    @property
    def cache_file_name(self) -> str:
        return 'tag_versions.json'
