"""Script to gather statistics about the dataset."""
from typing import Dict, Set

import json
import sys
from pathlib import Path

import pendulum

dataset_dir = Path(sys.argv[1])
struct_diff_csv = dataset_dir / 'metrics_diffs_releases.csv'
roles_json = dataset_dir / 'roles.json'
repos_json = dataset_dir / 'repo_paths.json'

struct_diff_lines = struct_diff_csv.read_text().splitlines()[1:]
struct_diffs = [role_line.split(',') for role_line in struct_diff_lines]

roles_info = json.loads(roles_json.read_text())

roles = {role_line[0] for role_line in struct_diffs}
authors = {roles_info[role_id]['github_user'] for role_id in roles}

print(f'{len(roles)} unique roles by {len(authors)} unique authors')
print(f'{len(struct_diffs)} version increments')

last_modified = max(
        pendulum.parse(role['modified']) for role in roles_info.values())
print(f'Dataset date: {last_modified}')

all_authors = {role['github_user'] for role in roles_info.values()}
print(f'Discovery: {len(roles_info)} roles of {len(all_authors)} authors.')

cloned = json.loads(repos_json.read_text())
success = len(cloned)
failed = len(roles_info) - success
authors = {role['owner'] for role in cloned.values()}
print(f'Cloned: {success} success, {failed} failed, {len(authors)} authors')

# Versions
unique_v: Dict[str, Set[str]] = {}
for r in struct_diffs:
    rid, v1, v2 = r[:3]
    if rid in unique_v:
        unique_v[rid].add(v1)
        unique_v[rid].add(v2)
    else:
        unique_v[rid] = {v1, v2}

num_unique_v = sum(len(vers) for vers in unique_v.values())
num_incs = len(struct_diffs)
num_roles = len(unique_v)
num_authors = len({roles_info[rid]['github_user'] for rid in unique_v.keys()})
print(
        f'Versions: {num_unique_v} unique versions, {num_incs} increments, '
        f'{num_roles} roles, {num_authors} authors')

# Versions
unique_v = {}
num_incs = 0
for r in struct_diffs:
    rid, v1, v2 = r[:3]
    if not r[4]:
        continue
    num_incs += 1
    if rid in unique_v:
        unique_v[rid].add(v1)
        unique_v[rid].add(v2)
    else:
        unique_v[rid] = {v1, v2}

num_unique_v = sum(len(vers) for vers in unique_v.values())
num_roles = len(unique_v)
num_authors = len({roles_info[rid]['github_user'] for rid in unique_v.keys()})
print(
        f'Structural: {num_unique_v} unique versions, {num_incs} increments, '
        f'{num_roles} roles, {num_authors} authors')
