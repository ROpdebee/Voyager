# Dataset migrations
from typing import Callable, Dict, List, Sequence

import inspect
import json
import re
import shutil
import sys

from collections import defaultdict
from pathlib import Path

from tqdm import tqdm

from services.galaxy import GalaxyAPI
from models.serialize import CONVERTER
from models.galaxy import GalaxyRole
from models.git import GitRepoPath

_MigrationFunc = Callable[[Path], bool]


_VERSION_FILE_NAME = 'version.json'


class MigrationException(Exception):
    """Raised when a migration fails."""
    pass


def _log(s: str) -> None:
    tqdm.write(s)


def _get_dataset_version(dataset_path: Path) -> int:
    try:
        content = (dataset_path / _VERSION_FILE_NAME).read_text()
        v = json.loads(content)['version']
        if not isinstance(v, int):
            return 0
        return v
    except (KeyError, OSError):
        return 0


def _set_dataset_version(dataset_path: Path, version: int) -> None:
    v_dict = {'version': version}
    json_content = json.dumps(v_dict)
    try:
        (dataset_path / _VERSION_FILE_NAME).write_text(json_content)
    except OSError as exc:
        raise MigrationException('Failed to write version') from exc


def perform_migrations(dataset_path: Path) -> None:
    migrations = _get_migrations(dataset_path)
    current_v = _get_dataset_version(dataset_path)
    todo_migrations = migrations[current_v:]
    if not todo_migrations:
        return

    _log('Dataset is outdated, '
         f'performing {len(todo_migrations)} migrations')

    # Do migrations
    migrations_it = tqdm(
            todo_migrations, unit=' migrations', desc='Performing migrations')
    for migration_i, migration_func in enumerate(migrations_it):
        if not migration_func(dataset_path):
            migration_name = migration_func.__name__
            raise MigrationException(f'Failed migration to {migration_name}')

        # Continuously update version if later migration fails
        new_v = migration_i + current_v + 1
        _set_dataset_version(dataset_path, new_v)


def _get_migrations(dataset_path: Path) -> Sequence[_MigrationFunc]:
    members = inspect.getmembers(sys.modules[__name__])
    migration_funcs = {
            _get_migration_func_version(name): f
            for name, f in members
            if inspect.isfunction(f) and _is_migration_func_name(name)}
    return [
            f
            for name, f in sorted(migration_funcs.items(), key=lambda p: p[0])]


def _is_migration_func_name(name: str) -> bool:
    if not name:
        return False

    prefix = name.split('_')[0]
    return bool(re.match(r'v\d+', prefix))


def _get_migration_func_version(name: str) -> int:
    m = re.match(r'v(\d+)', name)
    assert m
    return int(m.group(1))


def v1_dataset_version(p: Path) -> bool:
    """Add the dataset version."""
    # File will be added automatically after version migration
    return True


def _clean_repo_name(name: str) -> str:
    return '-'.join(
            part for part in name.lower().split('-')
            if part not in ('ansible', 'role'))


def _deep_match(role: GalaxyRole, role_json: Dict[str, str]) -> bool:
    return (role.name == role_json['name']
            and role.github_user == role_json['github_user']
            and (role.github_repo == role_json['github_repo']
                 or (_clean_repo_name(role.github_repo)
                     == _clean_repo_name(role_json['github_repo']))))


def v2_role_namespaces(p: Path) -> bool:  # noqa: C901
    """Add namespaces to Galaxy roles."""
    with (p / 'roles.json').open('r') as json_roles_f:
        orig_roles = json.load(json_roles_f)
    roles = dict(orig_roles)  # Copy
    galaxy_api = GalaxyAPI()
    # Include deprecated roles in the results: Some of the roles we gathered
    # earlier may now be deprecated
    galaxy_it = galaxy_api.search_roles(deprecated=None)
    todo_role_ids = set(roles.keys())

    unmatched: List[GalaxyRole] = []
    for galaxy_role in tqdm(galaxy_it, unit=' roles', desc='Update roles'):
        try:
            roles[galaxy_role.id]['namespace'] = galaxy_role.namespace
            todo_role_ids.remove(galaxy_role.id)
            if not todo_role_ids:
                # Done
                break
        except KeyError:
            # OK, new role not in dataset
            unmatched.append(galaxy_role)

    # Perform a deep comparison (heuristically) of any roles whose ID has
    # changed
    for role_id in list(todo_role_ids):
        missing_role = roles[role_id]
        candidates: List[GalaxyRole] = []
        for new_role in unmatched:
            if (_deep_match(new_role, missing_role)):
                candidates.append(new_role)
        if not candidates:
            continue
        if len(candidates) > 1:
            _log(f'Unmatched role {role_id} matches multiple candidates: '
                 + ', '.join(r.id for r in candidates))
            continue
        missing_role['namespace'] = candidates[0].namespace
        todo_role_ids.remove(role_id)

    # Verify
    if todo_role_ids:
        _log('Failed to update following roles: ' + ', '.join(todo_role_ids))
        _log('Heuristically setting to GitHub owner name')
        for role_id in todo_role_ids:
            roles[role_id]['namespace'] = roles[role_id]['github_user']
    if len(orig_roles) != len(roles):
        raise MigrationException('Lengths of updated roles not equal')
    try:
        for role_id, updated_role in roles.items():
            m = CONVERTER.structure(updated_role, GalaxyRole)
            assert m.id == role_id
    except Exception as exc:
        raise MigrationException('Failed to structure role') from exc

    # Verification passed, write new file
    with (p / 'roles.json').open('w') as json_roles_f:
        json.dump(roles, json_roles_f, indent=4, sort_keys=True)

    return True


def v3_repo_directory_role_names(p: Path) -> bool:  # noqa: C901
    """Restructure repo directories to Galaxy identifiers."""
    with (p / 'roles.json').open('r') as json_roles_f:
        roles = CONVERTER.structure(
                json.load(json_roles_f), Dict[str, GalaxyRole])

    with (p / 'repo_paths.json').open('r') as json_paths_f:
        repo_paths = CONVERTER.structure(
                json.load(json_paths_f), Dict[str, GitRepoPath])

    (p / 'repos_moved').mkdir(exist_ok=True)

    # Preprocess. We can't move directly, since some roles share a repo, and
    # these need to be copied.
    targets: Dict[Path, List[Path]] = defaultdict(list)
    for repo_path in repo_paths.values():
        role = roles[repo_path.id]
        src = p / repo_path.path
        dest = p / 'repos_moved' / f'{role.namespace}.{role.name}'
        targets[src].append(dest)

    for src, dsts in tqdm(targets.items(), unit=' repos', desc='Moving repos'):
        if not src.exists():
            # Might've already been moved in a previous, interrupted migration
            continue
        if len(dsts) == 1:
            if dsts[0].exists():
                _log(f'Skipping {dsts[0]}: Exists')
                continue
            src.rename(dsts[0])
        else:
            for dst in dsts:
                if dst.exists():
                    # _log(f'Skipping {dst}: Exists')
                    continue
                shutil.copytree(src, dst)

    # Rename the directories
    _log('Renaming directories, please check repos_orig for dangling repos')
    (p / 'repos').rename(p / 'repos_orig')
    (p / 'repos_moved').rename(p / 'repos')

    # Verification + create new repo paths
    new_paths: Dict[str, GitRepoPath] = {}
    for repo_path in tqdm(repo_paths.values(), unit='repos', desc='Verifying'):
        role = roles[repo_path.id]
        new_path = p / 'repos' / f'{role.namespace}.{role.name}'
        if not new_path.exists() or not any(new_path.iterdir()):
            raise MigrationException(
                    f'Role {repo_path.id} not moved correctly')
        new_paths[repo_path.id] = GitRepoPath(
                repo_path.owner, repo_path.name, repo_path.role_id,
                new_path.relative_to(p))
    if len(new_paths) != len(repo_paths):
        raise MigrationException('Not all repos migrated')

    # Write
    with (p / 'repo_paths.json').open('w') as json_paths_f:
        json.dump(
                CONVERTER.unstructure(new_paths), json_paths_f, indent=4,
                sort_keys=True)

    return True
