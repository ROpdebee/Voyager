"""Version stages."""
from typing import Iterable, List, Tuple, Optional, Iterator

import git
import pendulum

from tqdm import tqdm

from config import MainConfig
from models.git import GitRepo, GitRepoMetadata, GitCommit, GitTag
from pipeline.base import ResultMap, Stage
from pipeline.collect.clone import Clone


class ExtractGitMetadata(Stage[GitRepoMetadata, MainConfig], requires=Clone):
    """Extract the versions from the git repositories."""

    dataset_dir_name = 'RepositoryMetadata'

    def run(self, clone: ResultMap[GitRepo]) -> ResultMap[GitRepoMetadata]:
        repos: Iterable[GitRepo] = clone.values()
        if self.config.progress:
            repos = tqdm(repos, total=len(clone))

        return ResultMap(map(self.extract_meta, repos))

    def extract_meta(self, git_repo: GitRepo) -> GitRepoMetadata:
        repo_ref = git.Repo(self.config.output_directory / git_repo.path)

        return GitRepoMetadata(
                repo_owner=git_repo.owner, repo_name=git_repo.name,
                tags=[git_tag for tag in repo_ref.tags if (git_tag := GitTag.from_git_tag(tag)) is not None],
                commits=self.get_commits(repo_ref))

    def get_commits(self, repo_ref: git.Repo) -> List[GitCommit]:
        try:
            return [GitCommit.from_git_commit(commit)
                    for commit in repo_ref.iter_commits()]
        except ValueError as e:
            tqdm.write(f'{e}. Empty repo? {repo_ref}')
            return []

    def report_results(self, results: ResultMap[GitRepoMetadata]) -> None:
        len_all_tags = sum(len(meta.tags) for meta in results.values())
        len_all_commits = sum(len(meta.commits) for meta in results.values())
        print('--- Extract Git Metadata ---')
        print(f'Extracted {len_all_tags} tags and {len_all_commits} commits from {len(results)} repos')
