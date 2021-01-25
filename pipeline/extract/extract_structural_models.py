"""Discovery part of the pipeline."""
from typing import Any, Dict, List, Iterable, Mapping, Sequence, Set, cast, Tuple, Optional

import itertools
from pathlib import Path

import git
import pendulum
from ansible.errors import AnsibleError
from tqdm import tqdm

from config import ExtractStructuralModelsConfig
from models.role_metadata import GalaxyMetadata
from models.git import GitRepo, GitCommit, GitTag, GitRepoMetadata
from models.serialize import CONVERTER
from models.structural.role import StructuralRoleModel, MultiStructuralRoleModel
from models.version import Version
from pipeline.base import ResultMap, Stage, CacheMiss
from pipeline.collect.clone import Clone
from pipeline.extract.extract_role_metadata import ExtractRoleMetadata
from pipeline.extract.extract_git_metadata import ExtractGitMetadata


from pprint import pprint

class ExtractStructuralModels(
        Stage[MultiStructuralRoleModel, ExtractStructuralModelsConfig],
        requires=(ExtractRoleMetadata, Clone, ExtractGitMetadata)
):
    """Extract metadata from the collected roles."""

    dataset_dir_name = 'StructuralModels'

    def run(
            self,
            extract_role_metadata: ResultMap[GalaxyMetadata],
            extract_git_metadata: ResultMap[GitRepoMetadata],
            clone: ResultMap[GitRepo]
    ) -> ResultMap[MultiStructuralRoleModel]:
        """Run the stage."""
        role_repos = self.get_role_repositories(extract_role_metadata, clone, extract_git_metadata)
        num_revs = sum(len(revs) for (_, _, revs) in role_repos)
        if not self.config.commits:
            num_revs += len(role_repos)

        task_list: Iterable[Tuple[GitRepo, str, List[Tuple[str, str]]]]
        rev_pbar: Optional[tqdm]
        if self.config.progress:
            task_list = tqdm(
                    role_repos, desc='Extract structural models',
                    unit=' repos')
            rev_pbar = tqdm(
                    desc='Extract structural models', unit=' revs',
                    total=num_revs)
        else:
            task_list = role_repos
            rev_pbar = None

        results: List[MultiStructuralRoleModel] = []
        failures = 0
        for repo, role_name, revs in task_list:
            git_repo_obj = git.Repo(self.config.output_directory / 'Repositories' / repo.path)
            save_branch = git_repo_obj.active_branch
            role_models = []
            try:
                for sha1, rev in revs:
                    model = self.extract(git_repo_obj, role_name, sha1, rev, rev_pbar)
                    if model is None:
                        failures += 1
                    else:
                        role_models.append(model)

                # Also extract for the latest commit if we're extracting tags.
                if not self.config.commits:
                    save_branch.checkout(force=True)
                    model = self.extract(git_repo_obj, role_name, 'HEAD', 'HEAD', rev_pbar)
                    if model is None:
                        failures += 1
                    else:
                        role_models.append(model)
            finally:
                # Make sure to reset the repo to the HEAD from before
                save_branch.checkout(force=True)
            results.append(MultiStructuralRoleModel(role_name, role_models))
        if rev_pbar is not None:
            rev_pbar.close()

        print(f'{failures} roles failed to load')

        return ResultMap(results)

    def report_results(self, results: ResultMap[MultiStructuralRoleModel]) -> None:
        """Report statistics on gathered roles."""
        num_all_roles = sum(len(res.structural_models) for res in results.values())
        print('--- Role Structural Model Extraction ---')
        print(f'Extracted {num_all_roles} structural models for {len(results)} roles')


    def extract(self, repo: git.Repo, role_name: str, sha1: str, rev: str, rev_pbar: Optional[tqdm]) -> Optional[StructuralRoleModel]:
        try:
            repo.git.checkout(sha1, force=True)
            model = StructuralRoleModel.create(Path(repo.working_tree_dir), role_name, rev)
            if rev_pbar is not None:
                rev_pbar.update(1)
            return model
        except Exception as exc:
            tqdm.write(f'Failed to load {repo} {rev}: {exc}')
            return None

    def get_role_repositories(
            self, role_meta: ResultMap[GalaxyMetadata], clone: ResultMap[GitRepo],
            repo_meta: ResultMap[GitRepoMetadata]
    ) -> List[Tuple[GitRepo, str, List[Tuple[str, str]]]]:
        results = []
        for role in role_meta['dummy'].roles.values():
            repo_id = str(role.repository_id)
            if repo_id not in clone:
                continue
            git_repo = clone[repo_id]
            git_repo_metadata = repo_meta[f'{git_repo.owner}/{git_repo.name}']
            if self.config.commits:
                revs = [(commit.sha1, commit.sha1) for commit in git_repo_metadata.commits]
            else:
                revs = [(tag.commit_sha1, tag.name) for tag in git_repo_metadata.tags]
                revs = self._keep_only_semver(revs)

            # If there's no commits, the repo is empty, so just skip it.
            if git_repo_metadata.commits:
                results.append((git_repo, role.canonical_id, revs))

        return results

    def _keep_only_semver(self, tags: List[Tuple[str, str]]) -> List[Tuple[str, str]]:
        semver_tags: List[Tuple[Version, str, str]] = []
        for sha1, tag in tags:
            if (v := Version.from_version_str(tag, pendulum.now(), '')).is_semantic_version:
                semver_tags.append((v, sha1, tag))
        semver_tags.sort(key=lambda t: t[0])
        return [(sha1, tag) for _, sha1, tag in semver_tags]
