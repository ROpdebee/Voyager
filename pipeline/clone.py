"""Clone stage."""
from typing import Iterable, Optional

from pathlib import Path

import git
from tqdm import tqdm

from config import CloneConfig
from models.galaxy import GalaxyRole
from models.git import GitRepoPath
from pipeline.base import ResultMap, Stage
from pipeline.discover import Discover


class CloneException(Exception):
    """Raised when a repository could not be cloned."""
    pass


class AlreadyClonedException(CloneException):
    """Raised when a repository is already cloned."""
    pass


_GH_REPO_URL_FMT = 'https://github.com/{user}/{repo}.git'


class CloneProgress(git.RemoteProgress):
    """Print progress of a clone operation in tqdm."""
    _pbar: tqdm

    def __init__(self) -> None:
        super().__init__()
        self._pbar = tqdm(desc='Initializing', position=1, leave=False)

    def __del__(self) -> None:
        self._pbar.close()

    _STAGE_NAMES = {
        git.RemoteProgress.COUNTING: 'Counting',
        git.RemoteProgress.COMPRESSING: 'Compressing',
        git.RemoteProgress.WRITING: 'Writing',
        git.RemoteProgress.RECEIVING: 'Receiving',
        git.RemoteProgress.RESOLVING: 'Resolving',
        git.RemoteProgress.FINDING_SOURCES: 'Finding sources',
        git.RemoteProgress.CHECKING_OUT: 'Checking out'
    }

    def _get_stage_name(self, op: int) -> str:
        try:
            return self._STAGE_NAMES[op]
        except KeyError:
            return 'Unknown'

    def update(
            self, op_code: int, cur_count: int,
            max_count: Optional[int] = None, message: str = ''
    ) -> None:
        op = op_code & self.OP_MASK
        is_begin = op_code & self.BEGIN

        # Set a new description message, if necessary
        if is_begin:
            stage = self._get_stage_name(op)
            # Don't refresh the progress bar, it will be refreshed later in
            # one go
            self._pbar.set_description(stage, refresh=False)

        if max_count is not None and not self._pbar.total:
            self._pbar.total = max_count

        # Update the counter
        self._pbar.update(n=(cur_count - self._pbar.n))


class Clone(Stage[GitRepoPath, CloneConfig], requires=Discover):
    """Clone the repositories for discovered Ansible roles."""

    cache_file_name: str = 'repo_paths.json'

    @property
    def repo_path(self) -> Path:
        """Get the base path to the cloned repositories."""
        return self.config.output_directory / 'repos'

    def run(self, discover: ResultMap[GalaxyRole]) -> ResultMap[GitRepoPath]:
        """Run the stage: Clone the repositories."""
        repo_paths = set()
        roles: Iterable[GalaxyRole] = discover.values()
        if self.config.progress:
            roles = tqdm(roles, desc='Cloning repos')

        for role in roles:
            user, repo = role.github_user, role.github_repo
            try:
                path = self.clone(user, repo)
            except CloneException as exc:  # pragma: no cover
                tqdm.write(f'Failed to clone repository {user}/{repo}: {exc}')
                continue

            repo_paths.add(GitRepoPath(
                    role.github_user, role.github_repo, role.id, path))
        return ResultMap(repo_paths)

    def report_results(self, results: ResultMap[GitRepoPath]) -> None:
        """Report the results."""
        print('--- Repository Cloning ---')
        print(f'Cloned {len(results)} repositories into {self.repo_path}')

    def clone(self, owner: str, name: str) -> Path:
        """Clone a given repository into the base repo path.

        Returns the path to the repo. The path is relative to main output
        directory, so it should be possible to reuse them across different
        installations.
        """
        repo_path = self.repo_path / owner / name
        if self.repo_path.resolve() not in repo_path.resolve().parents:
            # If owner or name starts with a forward slash, it might try to
            # clone into a different directory, which is a path traversal
            # vulnerability
            raise CloneException(
                    'Unable to create repo directory: '
                    f'Attempted path traversal on {repo_path}')
        try:
            repo_path.mkdir(exist_ok=True, parents=True)
        except OSError as exc:
            raise CloneException('Unable to create repo directory') from exc

        # Check whether directory is non-empty. If it is, assume the repo was
        # already cloned.
        if any(repo_path.iterdir()):
            if not self.config.resume:
                raise AlreadyClonedException(
                        'Unable to clone repo: Target directory not empty')
            return repo_path.relative_to(self.config.output_directory)

        progress: Optional[git.RemoteProgress] = None
        if self.config.progress:
            progress = CloneProgress()

        try:
            repo = git.Repo.clone_from(
                    url=_GH_REPO_URL_FMT.format(user=owner, repo=name),
                    to_path=repo_path,
                    env={'GIT_TERMINAL_PROMPT': '0'},
                    progress=progress)
        except git.exc.GitError as exc:
            raise CloneException(f'Unable to clone repo: {exc}') from exc

        # Close the cloned repository, we'll come back to it later
        repo.close()
        return repo_path.relative_to(self.config.output_directory)
