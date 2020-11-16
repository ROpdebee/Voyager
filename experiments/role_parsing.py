# Trying to get the role parsing to work
from typing import Any, Dict, Sequence, Union

import sys

from pathlib import Path
from pprint import pprint

from ansible.playbook.base import Base
from ansible.playbook.play import Play
from ansible.playbook.role import Role
from ansible.playbook.block import Block
from ansible.playbook.task import Task
from ansible.playbook.task_include import TaskInclude
from ansible.playbook.role.include import RoleInclude
from ansible.vars.manager import VariableManager
from ansible.parsing.dataloader import DataLoader

if __name__ != '__main__':
    sys.exit('Cannot import this experiment script')


def recursive_dump(o: Any) -> Any:
    if isinstance(o, Base):
        return o.__class__.__name__, recursive_dump(o.dump_attrs())
    if isinstance(o, list):
        return [recursive_dump(oi) for oi in o]
    if isinstance(o, dict):
        return {k: recursive_dump(v) for k, v in o.items()}
    return o


role_dir = Path(sys.argv[1])
role_name = role_dir.name
role_base_dir = role_dir.parent
dummy_play = Play()
role_def = RoleInclude.load(
        role_name, dummy_play, current_role_path=str(role_base_dir),
        variable_manager=VariableManager(loader=DataLoader()))
print(role_def.get_name())
print(role_def.get_role_path())


def dump_block(b: Block) -> Dict[str, Any]:
    name = b.__class__.__name__ + ':' + str(id(b))
    if b._parent is not None:
        name += ' (parent: ' + b._parent.__class__.__name__
        if isinstance(b._parent, TaskInclude):
            name += str(b._parent.args)
        name += ')'
    return {
        name: dump_block_tasks(b.block)}


def dump_blocks(bl: Sequence[Block]) -> Dict[str, Any]:
    return {k: v for b in bl for k, v in dump_block(b).items()}


def dump_block_tasks(
        tl: Sequence[Union[Block, Task]]
) -> Sequence[Dict[str, Any]]:
    return [dump(t) for t in tl]


def dump_task(t: Task) -> Dict[str, Any]:
    return {t.__class__.__name__ + ':' + t.action: t.args}


def dump(o: Base) -> Dict[str, Any]:
    if isinstance(o, Block):
        return dump_block(o)
    elif isinstance(o, Task):
        return dump_task(o)
    else:
        return {o.__class__.__name__: None}


role = Role.load(role_def, dummy_play)
pprint(recursive_dump(role.get_task_blocks()))
pprint(dump_blocks(role.get_task_blocks()))
# print('Serial')
# pprint(role.serialize())
pprint(role.get_vars())
pprint(role.get_inherited_vars())


def find_blocks(b: Any, cur_depth: int = 0) -> int:
    if isinstance(b, Block):
        cur_depth += 1
        if b.rescue:
            print(b.rescue)
        if cur_depth > 1:
            if b.block and isinstance(b.block[0], Task):
                print(b.block[0].get_path())
            print(b._parent)
        return max(
                find_blocks(b.block, cur_depth),
                find_blocks(b.rescue, cur_depth),
                find_blocks(b.always, cur_depth))
    if isinstance(b, list) and b:
        return max(find_blocks(e, cur_depth) for e in b)
    return cur_depth


print(find_blocks(role._task_blocks))
print(find_blocks(role._handler_blocks))
