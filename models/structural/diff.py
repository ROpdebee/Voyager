"""Structural diffing."""
from __future__ import annotations

from typing import (
        Callable,
        Dict, Any,
        List,
        Optional,
        Sequence,
        Set,
        Tuple,
        Type,
        TypeVar,
        cast,
        TYPE_CHECKING
)

import abc
from itertools import chain, product
from operator import itemgetter
from textwrap import indent
from pathlib import Path
import re

from models.base import Model
from .provenance import pformat

if TYPE_CHECKING:
    from .role import StructuralRoleModel, MultiStructuralRoleModel

_SelfType = TypeVar('_SelfType', bound='DiffableMixin')
_ChildType = TypeVar('_ChildType')

import yaml
try:
    from yaml import CLoader as Loader, CDumper as Dumper
except ImportError:
    from yaml import Loader, Dumper  # type: ignore[misc]


# TODO: Customizable?
# Minimum threshold for two files/blocks/tasks to be considered equivalent.
# Compared against similarity score, which is more or less the percentage of
# objects that are similar between two candidates.
SIMILARITY_THRESHOLD = .51


class DiffableMixin:
    def diff(self: _SelfType, other: _SelfType) -> Sequence['Diff']:
        """Calculate the structural difference between self and other.

        If the two objects are equivalent, return the empty list.
        If the two objects are of different types, raise `NotImplementedError`.
        Otherwise, return a `Diff` subclass instance that describes the
        difference.
        """
        raise NotImplementedError

    def _sim_score_internal(
            self,
            children1: Sequence[_ChildType],
            children2: Sequence[_ChildType],
            is_relocated: Callable[[_ChildType, _ChildType], bool],
            calc_child_sim: Callable[[_ChildType, _ChildType], float]
    ) -> float:
        # Compute the similarity score by calculating the weighted average of
        # similarity scores of all children. Incur a penalty if a move would
        # be incurred in a certain pair.

        # All possible combinations of children to consider for matching
        max_num_el = max(len(children1), len(children2))
        if not max_num_el:
            return 0

        candidates = product(children1, children2)

        sims = [(c1, c2, calc_child_sim(c1, c2)) for c1, c2 in candidates]
        # Adjust for relocation: Incur 25% penalty is a relocation diff would
        # be necessary
        sims = [
            (c1, c2, sim * (.75 if is_relocated(c1, c2) else 1))
            for c1, c2, sim in sims]
        sims = sorted(sims[::-1], key=itemgetter(2), reverse=True)

        todo1 = set(children1)
        todo2 = set(children2)

        best_scores: List[float] = []
        for c1, c2, sim in sims:
            if not todo1 or not todo2:
                break
            if c1 in todo1 and c2 in todo2:
                best_scores.append(sim)
                todo1.remove(c1)
                todo2.remove(c2)

        assert len(best_scores) <= max_num_el
        assert len(best_scores) + max(len(todo1), len(todo2)) == max_num_el

        return sum(best_scores) / max_num_el

    @classmethod
    def _diff_multiple_internal(
            cls: Type[_SelfType],
            v1: Sequence[_SelfType], v2: Sequence[_SelfType],
            addition_t: Callable[[_SelfType], Sequence['Addition']],
            removal_t: Callable[[_SelfType], Sequence['Removal']],
            relocation_t: Callable[[_SelfType, _SelfType], 'Relocation'],
            check_relocation: Callable[[_SelfType, _SelfType], bool],
            calc_similarity: Callable[[_SelfType, _SelfType], float]
    ) -> Sequence['Diff']:
        todo1 = set(v1)
        todo2 = set(v2)
        candidates = product(v1, v2)
        sims = [(t1, t2, calc_similarity(t1, t2)) for t1, t2 in candidates]
        # Sort by similarity. We want the sort to be stable, so multiple
        # equivalent candidates will be sorted s.t. the closest two are first,
        # which is good for relocation, since we want to report the relocations
        # that are closest to one another. However, we also need to sort in
        # descending order, since we want the most similar candidates first,
        # which also reverses that stable order so that the farthest two
        # candidates are first. Hence, we reverse the candidates, which puts
        # the closest candidates last, then sort in reverse order, which places
        # the closest two first again.
        sims = sorted(sims[::-1], key=itemgetter(2), reverse=True)

        # TODO: This can perhaps be optimized a bit by assuming a prefix of the
        # given lists matches, and checking relocations similar to how its done
        # with variables.

        diffs: List[Diff] = []
        for t1, t2, sim in sims:
            if sim < SIMILARITY_THRESHOLD:
                # No more good candidates
                break
            if t1 not in todo1 or t2 not in todo2:
                # one of the two tasks is already taken, skip
                continue

            todo1.remove(t1)
            todo2.remove(t2)
            diffs.extend(t1.diff(t2))
            if check_relocation(t1, t2):
                # Relocated in block
                diffs.append(relocation_t(t1, t2))

        # Remaining tasks are added or removed, might be adjusted later at the
        # block/file level
        diffs.extend(chain(*(addition_t(t) for t in todo2)))
        diffs.extend(chain(*(removal_t(t) for t in todo1)))

        return diffs

    @classmethod
    def _match_relocations_internal(
            cls: Type[_SelfType], old_diffs: Sequence['Diff'],
            addition_t: Type['Addition'],
            removal_t: Type['Removal'],
            create_relocation: Callable[[_SelfType, _SelfType], 'Relocation'],
            calc_sim_score: Callable[[_SelfType, _SelfType], float]
    ) -> Sequence['Diff']:
        new_diffs: List[Diff] = []
        additions: List[Addition] = []
        removals: List[Removal] = []

        for d in old_diffs:
            if isinstance(d, addition_t):
                additions.append(d)
            elif isinstance(d, removal_t):
                removals.append(d)
            else:
                new_diffs.append(d)

        # Pairwise check each addition with each removal, calculate similarity,
        # ones with high similarity will be marked as relocation, others will
        # be kept as addition/removal
        candidates = product(additions, removals)
        possible_relocations: List[Tuple[Addition, Removal, float]] = []
        for a, r in candidates:
            aval = cast(_SelfType, a.added_value)
            rval = cast(_SelfType, r.removed_value)
            score = calc_sim_score(aval, rval)
            if score >= SIMILARITY_THRESHOLD:
                possible_relocations.append((a, r, score))

        possible_relocations.sort(key=itemgetter(2), reverse=True)

        for a, r, _ in possible_relocations:
            if not additions or not removals:
                break
            if a not in additions or r not in removals:
                # Already processed
                continue
            additions.remove(a)
            removals.remove(r)
            aval = cast(_SelfType, a.added_value)
            rval = cast(_SelfType, r.removed_value)
            new_diffs.extend(rval.diff(aval))
            new_diffs.append(create_relocation(rval, aval))

        # Remaining tasks are still considered added or removed, but this might
        # be adjusted again at a later stage.
        new_diffs.extend(additions)
        new_diffs.extend(removals)

        return new_diffs


class Diff:
    """Describe the difference between two objects."""
    def __init__(self, *, obj_id: object, **kwargs: object) -> None:
        self.object_id = obj_id
        assert not kwargs, 'Failed to initialize subclass: left ' + str(kwargs)

    def unstructure(self) -> Dict[str, Any]:
        return {'diff_type': self.__class__.__name__, 'object_id': self.object_id}


def _create_cls_name(obj_diff_t: Type[Diff], change_t: Type[Diff]) -> str:
    obj_name = obj_diff_t.__name__.replace('Diff', '')
    return obj_name + change_t.__name__


def _create_ortho_diffs(
        object_diff_types: Sequence[Type[Diff]],
        change_types: Sequence[Type[Diff]]
) -> Optional[str]:
    """Dynamically create orthogonal diff classes.

    NOTE: Even though this never returns a value, please assign the result
    of this call to a variable anyway. This allows our mypy plugin to recognize
    the call as a dynamic class definition, enabling it to add the dynamically
    defined classes in mypy's symbol table to enable accurate type checking.
    """
    for (obj_diff_t, change_t) in product(object_diff_types, change_types):
        cls_name = _create_cls_name(obj_diff_t, change_t)
        cls = type(cls_name, (obj_diff_t, change_t), {})
        globals()[cls_name] = cls
    return None


# TODO: Make base classes generic with type vars?

class Addition(Diff):
    """Base class for object additions."""
    def __init__(self, *, add_val: object, **kwargs: object) -> None:
        self.added_value = add_val
        super().__init__(**kwargs)

    def __repr__(self) -> str:
        edit_type = self.__class__.__name__
        add = indent(pformat(self.added_value), ' +++ ')
        obj_id = self.object_id
        return f'{edit_type}({obj_id}) :\n{add}'

    def unstructure(self) -> Dict[str, Any]:
        partial = super().unstructure()
        return {**partial, 'added_value': _maybe_unstructure(self.added_value)}


class Removal(Diff):
    """Base class for object removals."""
    def __init__(
            self, *, rem_val: object, **kwargs: object
    ) -> None:
        self.removed_value = rem_val
        super().__init__(**kwargs)

    def __repr__(self) -> str:
        edit_type = self.__class__.__name__
        rem = indent(pformat(self.removed_value), ' --- ')
        obj_id = self.object_id
        return f'{edit_type}({obj_id}) :\n{rem}'

    def unstructure(self) -> Dict[str, Any]:
        partial = super().unstructure()
        return {**partial, 'removed_value': _maybe_unstructure(self.removed_value)}


class Relocation(Diff):
    """Base class for object moves."""
    def __init__(
            self, *, prev_loc: object, new_loc: object,
            **kwargs: object
    ) -> None:
        self.previous_location = prev_loc
        self.new_location = new_loc
        super().__init__(**kwargs)

    def __repr__(self) -> str:
        edit_type = self.__class__.__name__
        objid = self.object_id
        prev = self.previous_location
        new = self.new_location
        return f'{edit_type}({objid}) :\n     {prev} --> {new}'

    def unstructure(self) -> Dict[str, Any]:
        partial = super().unstructure()
        return {**partial, 'previous_location': _maybe_unstructure(self.previous_location), 'new_location': _maybe_unstructure(self.new_location)}


class Edit(Diff):
    """Base class for object edits."""
    def __init__(
            self, *, prev_val: object, new_val: object,
            **kwargs: object
    ) -> None:
        self.previous_value = prev_val
        self.new_value = new_val
        super().__init__(**kwargs)

    def __repr__(self) -> str:
        edit_type = self.__class__.__name__
        objid = self.object_id
        prev = indent(pformat(self.previous_value), ' --- ')
        new = indent(pformat(self.new_value), ' +++ ')
        return f'{edit_type}({objid}) :\n{prev}\n\n{new}'

    def unstructure(self) -> Dict[str, Any]:
        partial = super().unstructure()
        prev_val = self.previous_value
        return {
            **partial,
            'previous_value': _maybe_unstructure(self.previous_value),
            'new_value': _maybe_unstructure(self.new_value)}


def _maybe_unstructure(obj: Any) -> Any:
    try:
        return obj.unstructure()
    except AttributeError as e:
        return obj


class FileDiff(Diff):
    """Diff to a file itself."""


###
# Variable diffs
###


class VariableDiff(Diff):
    """Diff in a variable."""


class DefaultVariableDiff(VariableDiff):
    """Diff in a default variable."""


class RoleVariableDiff(VariableDiff):
    """Diff in a constant variable."""


_ = _create_ortho_diffs(
        (DefaultVariableDiff, RoleVariableDiff),
        (Addition, Removal, Edit, Relocation))


class VarFileDiff(FileDiff):
    """Diff to a file in vars or defaults."""


class DefaultVarFileDiff(VarFileDiff):
    """Diff to a file in defaults/."""


class RoleVarFileDiff(VarFileDiff):
    """Diff to a file in vars/."""


_ = _create_ortho_diffs(
        (DefaultVarFileDiff, RoleVarFileDiff),
        (Addition, Removal, Relocation))


###
# Metadata diffs
###

class MetaDiff(Diff):
    """Diff in the meta component."""


class PlatformDiff(MetaDiff):
    """Diff in platforms."""


class DependencyDiff(MetaDiff):
    """Diff in dependencies."""


class MetaEdit(MetaDiff, Edit):
    """Uncategorized change to the meta block."""


_ = _create_ortho_diffs(
        (DependencyDiff, PlatformDiff),
        (Addition, Removal))


###
# Block and task diffs
###

class BaseTaskDiff(Diff):
    """Diff in a task (handler or task)."""


class TaskDiff(BaseTaskDiff):
    """Diff in a task."""


class HandlerTaskDiff(BaseTaskDiff):
    """Diff in a handler."""


class MiscEdit(Edit):
    """Edits to miscellaneous keywords."""


_ = _create_ortho_diffs(
        (TaskDiff, HandlerTaskDiff),
        (Addition, Removal, Edit, Relocation))


class BaseBlockDiff(Diff):
    """Diff to a block (tasks or handlers)."""


class BlockDiff(BaseBlockDiff):
    """Diff in a task block."""


class HandlerBlockDiff(BaseBlockDiff):
    """Diff in a handler block."""


_ = _create_ortho_diffs(
        (BlockDiff, HandlerBlockDiff),
        (Addition, Removal, Edit, Relocation))


class BaseTasksFileDiff(FileDiff):
    """Diff to a tasks file (tasks or handlers)."""


class TaskFileDiff(BaseTasksFileDiff):
    """Diff in a task block."""


class HandlerFileDiff(BaseTasksFileDiff):
    """Diff in a handler block."""


_ = _create_ortho_diffs(
        (TaskFileDiff, HandlerFileDiff),
        (Addition, Removal, Relocation))


def structure_diff_no_content(diff_dict: Dict[str, Any], diff_type: Type[Diff]) -> Diff:
    # if diff
    if issubclass(diff_type, Addition):
        return diff_type(obj_id=diff_dict['object_id'], add_val=diff_dict['added_value'])
    if issubclass(diff_type, Removal):
        return diff_type(obj_id=diff_dict['object_id'], rem_val=diff_dict['removed_value'])
    assert False


def structure_add(dct: Dict[str, Any], diff_type: Type[Addition]) -> Addition:
    return diff_type(add_val=dct['added_value'], obj_id=dct['object_id'])

def structure_rem(dct: Dict[str, Any], diff_type: Type[Removal]) -> Removal:
    return diff_type(rem_val=dct['removed_value'], obj_id=dct['object_id'])

def structure_edit(dct: Dict[str, Any], diff_type: Type[Edit]) -> Edit:
    return diff_type(prev_val=dct['previous_value'], new_val=dct['new_value'], obj_id=dct['object_id'])

def structure_reloc(dct: Dict[str, Any], diff_type: Type[Relocation]) -> Relocation:
    return diff_type(prev_loc=dct['previous_location'], new_loc=dct['new_location'], obj_id=dct['object_id'])


def diff_structure_factory(diff_dict: Dict[str, Any]) -> Diff:
    try:
        diff_type = globals()[diff_dict['diff_type']]
    except KeyError as e:
        raise ValueError(f'Unknown diff type: {diff_type}') from e

    if issubclass(diff_type, PlatformDiff) or issubclass(diff_type, DependencyDiff):
        return structure_diff_no_content(diff_dict, diff_type)

    if issubclass(diff_type, Addition):
        return structure_add(diff_dict, diff_type)
    if issubclass(diff_type, Removal):
        return structure_rem(diff_dict, diff_type)
    if issubclass(diff_type, Edit):
        return structure_edit(diff_dict, diff_type)
    if issubclass(diff_type, Relocation):
        return structure_reloc(diff_dict, diff_type)

    raise ValueError(f'Unknown diff type: {diff_type.__name__}')


class DiffSet:
    def __init__(self, old_rev: str, new_rev: str, diffs: Sequence[Diff]) -> None:
        self.old_rev = old_rev
        self.new_rev = new_rev
        self.diffs = diffs

    @classmethod
    def create(self, v_old: 'StructuralRoleModel', v_new: 'StructuralRoleModel') -> DiffSet:
        rev_old = v_old.role_rev
        rev_new = v_new.role_rev
        diffs = v_old.role_root.diff(v_new.role_root)
        return DiffSet(rev_old, rev_new, diffs)

    @classmethod
    def structure(cls, data: Dict[str, Any]) -> DiffSet:
        structured_diffs = [diff_structure_factory(diff) for diff in data['diffs']]
        return cls(data['old_rev'], data['new_rev'], structured_diffs)

    def unstructure(self) -> Dict[str, Any]:
        return {
            'old_rev': self.old_rev,
            'new_rev': self.new_rev,
            'diffs': [diff.unstructure() for diff in self.diffs]
        }


class StructuralRoleEvolution(Model):

    def __init__(self, role_id: str, diff_sets: Sequence[DiffSet]) -> None:
        self.role_id = role_id
        self.diff_sets = diff_sets

    @property
    def id(self) -> str:
        return self.role_id

    @classmethod
    def create(cls, models: 'MultiStructuralRoleModel') -> StructuralRoleEvolution:
        all_struct_models = models.structural_models
        if len(all_struct_models) <= 1:
            return cls(models.role_id, [])

        v1_idx = 0
        v2_idx = 1
        diff_sets = []
        while v2_idx < len(all_struct_models):
            diff_sets.append(DiffSet.create(all_struct_models[v1_idx], all_struct_models[v2_idx]))
            v1_idx += 1
            v2_idx += 1

        inst = cls(models.role_id, diff_sets)

        # Verify we can dump it
        try:
            unstructured = [diff_set.unstructure() for diff_set in inst.diff_sets]
            result = yaml.safe_dump(unstructured)
        except:
            assert False, f'Will fail to dump {models.role_id}'

        return inst

    @classmethod
    def load(cls, role_id: str, file_path: Path) -> StructuralRoleEvolution:
        data = yaml.load(file_path.read_text(), Loader=Loader)
        return cls(role_id, [DiffSet.structure(diff_set) for diff_set in data['diff_sets']])

    def dump(self, dirpath: Path) -> Path:
        data = {
            'role_id': self.role_id,
            'diff_sets': [diff_set.unstructure() for diff_set in self.diff_sets]
        }
        target = dirpath / (self.role_id + '.yaml')
        target.write_text(yaml.safe_dump(data))
        return target



###
# Helpers
###

_Object = TypeVar('_Object')


def diff_set(
        s_v1: Set[_Object], s_v2: Set[_Object], *,
        add_factory: Callable[[_Object], Addition],
        rem_factory: Callable[[_Object], Removal]
) -> Sequence[Diff]:
    common = s_v1 & s_v2
    additions = (add_factory(add) for add in s_v2 - common)
    removals = (rem_factory(rem) for rem in s_v1 - common)
    return list(chain(additions, removals))


def get_diff_category_leafs() -> Sequence[Type[Diff]]:
    cats = {c for c in globals().values()
            if isinstance(c, type) and issubclass(c, Diff)}
    bases = set(chain(*(c.__bases__ for c in cats)))
    return list(cats - bases)
