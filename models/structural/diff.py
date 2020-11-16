"""Structural diffing."""
from typing import (
        Callable,
        List,
        Optional,
        Sequence,
        Set,
        Tuple,
        Type,
        TypeVar,
        cast
)

from itertools import chain, product
from operator import itemgetter
from textwrap import indent

from .provenance import pformat

_SelfType = TypeVar('_SelfType', bound='DiffableMixin')
_ChildType = TypeVar('_ChildType')


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


class FileDiff(Diff):
    """Diff to a file itself."""


###
# Variable diffs
###


class VariableDiff(Diff):
    """Diff in a variable."""


class DefaultVariableDiff(VariableDiff):
    """Diff in a default variable."""


class ConstantVariableDiff(VariableDiff):
    """Diff in a constant variable."""


_ = _create_ortho_diffs(
        (DefaultVariableDiff, ConstantVariableDiff),
        (Addition, Removal, Edit, Relocation))


class VarFileDiff(FileDiff):
    """Diff to a file in vars or defaults."""


class DefaultsFileDiff(VarFileDiff):
    """Diff to a file in defaults/."""


class ConstantsFileDiff(VarFileDiff):
    """Diff to a file in vars/."""


_ = _create_ortho_diffs(
        (DefaultsFileDiff, ConstantsFileDiff),
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
        (Addition, Removal, Edit, MiscEdit, Relocation))


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


class TasksFileDiff(BaseTasksFileDiff):
    """Diff in a task block."""


class HandlersFileDiff(BaseTasksFileDiff):
    """Diff in a handler block."""


_ = _create_ortho_diffs(
        (TasksFileDiff, HandlersFileDiff),
        (Addition, Removal, Relocation))


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
