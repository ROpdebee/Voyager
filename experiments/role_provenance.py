"""Experiments with structural model provenance."""

import sys

from pathlib import Path

from models.structural.role import Role

if __name__ != '__main__':
    sys.exit('Cannot import this experiment script')


role_dir = Path(sys.argv[1]).resolve()
role_name = role_dir.name
role_base_dir = role_dir.parent

r = Role.load(role_dir, role_base_dir)

print(r.dump_to_dot(role_base_dir / (role_name + '.dot'), 'pdf'))
