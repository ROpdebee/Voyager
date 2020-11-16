"""Experiments with structural model."""

from typing import TYPE_CHECKING

import sys

from pathlib import Path

from models.structural.role import (
        Block,
        HandlerBlock,
        HandlerTask,
        Role,
        Task,
)

if __name__ != '__main__':
    sys.exit('Cannot import this experiment script')


role_dir = Path(sys.argv[1]).resolve()
role_name = role_dir.name
role_base_dir = role_dir.parent

r = Role.load(role_dir, role_base_dir)

mf = r.meta_file
cf = r.constants_files[0]
df = r.defaults_files[0]
hf = r.handlers_files[0]
tf = r.tasks_files[0]

print('--- Meta ---')
print(mf.metablock.misc_keywords)
print(mf.metablock.platforms)
print(mf.metablock.dependencies)
if TYPE_CHECKING:
    reveal_type(mf.metablock.dependencies)

print('--- Constants ---')
print(f'Number of constants files: {len(r.constants_files)}')
try:
    c = cf[0]
    print(f'{c.name}: {c.value}')
except IndexError:
    print('No constants')

print('--- Defaults ---')
print(f'Number of defaults files: {len(r.defaults_files)}')
try:
    d = df[0]
    print(f'{d.name}: {d.value}')
except IndexError:
    print('No defaults')


print('--- Task Blocks ---')
print(f'Number of task files: {len(r.tasks_files)}')
b: Block = tf[0]
print(b.block)
print(b.rescue)
print(b.always)
if TYPE_CHECKING:
    reveal_type(b.block)
    reveal_type(b.rescue)
    reveal_type(b.always)

print('--- Task ---')
print(b.block[0].name)
if TYPE_CHECKING:
    reveal_type(b.block[0].name)
if isinstance(b.block[0], Task):
    print(b.block[0].action)

print('--- Handler Blocks ---')
print(f'Number of handlers files: {len(r.handlers_files)}')
hb: HandlerBlock = hf[0]
print(hb.block)
print(hb.rescue)
print(hb.always)
if TYPE_CHECKING:
    reveal_type(hb.block)
    reveal_type(hb.rescue)
    reveal_type(hb.always)


print('--- Handler ---')
print(hb.block[0].name)
if TYPE_CHECKING:
    reveal_type(hb.block[0].name)
    if isinstance(hb.block[0], HandlerTask):
        reveal_type(hb.block[0].listen)
if isinstance(hb.block[0], HandlerTask):
    print(hb.block[0].action)
    print(hb.block[0].listen)

if r.broken_files:
    print()
    print(f'{len(r.broken_files)} files could not be parsed')
    for file_path, err in r.broken_files:
        print(f'{file_path}: {err}')