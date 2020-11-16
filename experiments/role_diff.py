"""Experiments with role diffing."""
from typing import Any

import sys

from pathlib import Path
from shutil import copytree
from tempfile import TemporaryDirectory

from git import Git, Repo
from ansible.errors import AnsibleError

from models.structural.role import Role

if __name__ != '__main__':
    sys.exit('Cannot import this experiment script')


role_dir = Path(sys.argv[1]).resolve()
role_name = role_dir.name
role_base_dir = role_dir.parent


def diff_it(role_dir: Path, rev1: str, rev2: str) -> Any:
    g = Git(role_dir)
    g.checkout(rev1)
    role_v1 = Role.load(role_tmp_dir, role_base_dir)
    g.checkout(rev2)
    role_v2 = Role.load(role_tmp_dir, role_base_dir)
    return [d for d in role_v1.diff(role_v2) if d]


if sys.argv[2] == 'all':
    revs = [t.name for t in Repo(role_dir).tags][::-1]
else:
    revs = sys.argv[2:]

with TemporaryDirectory() as tmpd:
    role_tmp_dir = Path(tmpd) / role_name
    copytree(role_dir, role_tmp_dir, symlinks=True)
    for rev2, rev1 in zip(revs, revs[1:]):
        header = f'{rev1} -> {rev2}'
        print(header)
        print('=' * len(header))
        print()
        try:
            diffs = diff_it(role_tmp_dir, rev1, rev2)
            for diff in sorted(diffs, key=lambda d: d.object_id):
                print(diff)
                print()
        except AnsibleError as exc:
            print(exc)
        print()
