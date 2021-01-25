"""Abstract classes."""
from __future__ import annotations

from typing import (
    Any,
    Collection,
    Callable,
    Dict,
    Final,
    Generic,
    List,
    Mapping,
    Optional,
    Sequence,
    Tuple,
    Type,
    TypeVar,
    cast,
    get_args,
    get_origin,
    overload,
    Union,
    TYPE_CHECKING,
)

from abc import ABC, abstractmethod
from itertools import chain, product
from operator import attrgetter, itemgetter
from textwrap import indent

import ansible.playbook as anspb

from . import base, diff, mixins
# Backup, since it clashes in method definition type hints if the diff method
# is already defined in the class body.
from . import diff as diff_mod
from .types import AnsTaskOrBlock, Value
from .provenance import GraphvizMixin, SMGraph, pformat

if TYPE_CHECKING:
    from .role import Task, HandlerTask, Block, HandlerBlock, TaskFile, HandlerFile, DefaultVariable, RoleVariable, DefaultVarFile, RoleVarFile

# TODO: Should probably be cleaned up, this module is getting fairly large.
#       Perhaps use more specific mixins in the diff module to do the diffing
#       logic for each object type?


_FileType = TypeVar(
        '_FileType', bound='ContainerFile')  # type: ignore[type-arg]


class ContainerFile(
        mixins.ObjectContainerMixin[mixins.ObjectWithParentType],
        base.BaseFile,
        GraphvizMixin
):
    """A RoleContainerFile is a role file that contains multiple objects.

    Roles consist of multiple directories which contain different object
    types. These directories can contain multiple files, each with their own
    objects, but all with the same object type.
    """

    def gv_visit(self, g: SMGraph) -> None:
        g.add_node(self, label=self.file_name)
        self.gv_visit_children(g, 'content', [self])

    def __repr__(self) -> str:
        r = f'{self.__class__.__name__} ({self.file_name}):'
        el_repr = '\n'.join(repr(e) for e in self)
        el_repr = indent(el_repr, ' ' * 4)
        return f'{r}\n{el_repr}'

    @classmethod
    def _match_files(
            cls: Type[_FileType],
            files_v1: Sequence[_FileType],
            files_v2: Sequence[_FileType]
    ) -> Tuple[
            List[_FileType],  # Added files
            List[_FileType],  # Removed files
            Sequence[Tuple[_FileType, _FileType]]]:  # Matched files
        added_files: List[_FileType] = []
        removed_files: List[_FileType] = []
        matched_files: List[Tuple[_FileType, _FileType]] = []

        name_to_new_files = {f.file_name: f for f in files_v2}

        for file in files_v1:
            if file.file_name in name_to_new_files:
                matched_files.append((file, name_to_new_files[file.file_name]))
                del name_to_new_files[file.file_name]
            else:
                removed_files.append(file)
        added_files.extend(name_to_new_files.values())

        return (added_files, removed_files, matched_files)

    @classmethod
    def _match_file_relocations(
            cls: Type[_FileType],
            added: List[_FileType],
            removed: List[_FileType],
            calc_sim: Callable[[_FileType, _FileType], float]
    ) -> Tuple[
            List[_FileType],  # Truly added files
            List[_FileType],  # Truly removed files
            Sequence[Tuple[_FileType, _FileType]]]:  # Relocated files
        # Attempt to match added files to removed files, which would be a
        # relocation
        # Calculate a similarity score for each pair of added and removed files
        # so that we can prioritize the absolute best matches first.
        relocations: List[Tuple[_FileType, _FileType]] = []
        candidates = product(added, removed)
        sims = [(addf, remf, calc_sim(remf, addf))
                for addf, remf in candidates]
        # See DiffableMixin._diff_multiple_internal
        sims = sorted(sims[::-1], key=itemgetter(2), reverse=True)
        for addf, remf, score in sims:
            if score < diff.SIMILARITY_THRESHOLD:
                # Reached threshold, no good matches anymore
                break
            if not added or not removed:
                # All processed
                break
            if addf not in added or remf not in removed:
                # Already matched previously
                continue
            added.remove(addf)
            removed.remove(remf)
            relocations.append((remf, addf))

        return added, removed, relocations

    @classmethod
    def _create_file_relocation_diff(
            cls: Type[_FileType], f1: _FileType, f2: _FileType
    ) -> diff_mod.Relocation:
        file_relocation_t = cast(
                Type[diff.Relocation],
                getattr(diff, f'{cls.__name__}Relocation'))
        return file_relocation_t(
                obj_id=f1.file_name, prev_loc=f1.file_name,
                new_loc=f2.file_name)

    def _create_file_addition(self) -> Sequence[diff_mod.Addition]:
        file_addition_t = cast(
                Type[diff.Addition],
                getattr(diff, f'{self.__class__.__name__}Addition'))
        diffs = [file_addition_t(obj_id=self.file_name, add_val=self)]
        for e in self:
            diffs.extend(self._create_element_addition(e))
        return diffs

    def _create_file_removal(self) -> Sequence[diff_mod.Removal]:
        file_removal_t = cast(
                Type[diff.Removal],
                getattr(diff, f'{self.__class__.__name__}Removal'))
        diffs = [file_removal_t(obj_id=self.file_name, rem_val=self)]
        for e in self:
            diffs.extend(self._create_element_removal(e))
        return diffs

    @abstractmethod
    def _create_element_addition(
            self, el: mixins.ObjectWithParentType
    ) -> Sequence[diff_mod.Addition]:
        ...

    @abstractmethod
    def _create_element_removal(
            self, el: mixins.ObjectWithParentType
    ) -> Sequence[diff_mod.Removal]:
        ...


_AVType = TypeVar('_AVType', 'AbstractVariable[DefaultVarFile]', 'AbstractVariable[RoleVarFile]')
_CVType = TypeVar('_CVType', 'DefaultVariable', 'RoleVariable')
_AVFile = TypeVar(
        '_AVFile', 'AbstractVariableFile[DefaultVariable]', 'AbstractVariableFile[RoleVariable]')
_CVFile = TypeVar('_CVFile', 'DefaultVarFile', 'RoleVarFile')


class AbstractVariableFile(
        ContainerFile[_CVType],
        diff.DiffableMixin
):
    """Role files containing variables."""

    @classmethod
    def _structure(cls: Type[AbstractVariableFile[_CVType]], obj: Dict[str, Any], eltype: Type[_CVType]) -> AbstractVariableFile[_CVType]:
        file_name = obj['file_name']
        content = [eltype(name=name, value=value) for name, value in obj['content'].items()]
        return cls(file_name=file_name, elements=content)

    @classmethod
    def _from_ans_object(cls: Type[AbstractVariableFile[_CVType]], file_name: str, content: Mapping[str, Value], eltype: Type[_CVType]) -> AbstractVariableFile[_CVType]:
        return cls(file_name=file_name, elements=[eltype(name=name, value=value) for name, value in content.items()])

    def unstructure(self) -> Dict[str, Any]:
        return {
            'file_name': self.file_name,
            'content': {var.name: var.value for var in self}
        }

    def diff(
            self: _AVFile, other: _AVFile
    ) -> Sequence[diff_mod.Diff]:
        if not isinstance(other, type(self)):
            raise NotImplementedError

        var_type_name = self.__class__.__name__.replace('sFile', 'Variable')
        var_added_t = getattr(diff, f'{var_type_name}Addition')
        var_removed_t = getattr(diff, f'{var_type_name}Removal')

        # This has no elements => All variables in other are added
        if len(self) == 0:
            return [
                var_added_t(obj_id=v.id, add_val=v)
                for v in other]

        # Other has no elements => All variables in self are removed
        if len(other) == 0:
            return [
                var_removed_t(obj_id=v.id, rem_val=v)
                for v in self]

        # Sort both variable lists by name and try to match in order
        vars1 = list(sorted(self, key=attrgetter('name')))
        vars2 = list(sorted(other, key=attrgetter('name')))

        diffs: List[diff.Diff] = []
        i1 = i2 = 0
        while i1 < len(vars1) and i2 < len(vars2):
            v1 = vars1[i1]
            v2 = vars2[i2]
            if v1.name == v2.name:
                # Either no change, or equivalent variables with different
                # values => OK, check the next pair
                diffs.extend(v1.diff(v2))
                i1 += 1
                i2 += 1
            else:
                # v1 and v2 are unrelated, so one of the two is definitely
                # added/removed. Determine which one, and take the other for
                # future comparisons.
                if v1.name < v2.name:
                    # There can be no variable in vars2 that can ever match v1,
                    # so it is definitely removed. v2 can still be equivalent
                    # to e.g. vars1[i1+1] though
                    diffs.append(var_removed_t(obj_id=v1.id, rem_val=v1))
                    i1 += 1
                else:
                    # Analogous for v2: Definitely added
                    diffs.append(var_added_t(obj_id=v2.id, add_val=v2))
                    i2 += 1
        while i1 < len(vars1):
            v1 = vars1[i1]
            diffs.append(var_removed_t(obj_id=v1.id, rem_val=v1))
            i1 += 1
        while i2 < len(vars2):
            v2 = vars2[i2]
            diffs.append(var_added_t(obj_id=v2.id, add_val=v2))
            i2 += 1

        return diffs

    def similarity_score(
            self: _AVFile, other: _AVFile
    ) -> Tuple[float, Sequence[diff_mod.Diff]]:
        """Calculate the similarity between two files, and return the diffs.

        The similarity score is a number between 0 and 1, inclusive. Higher
        scores mean more similar.
        """
        diffs = self.diff(other)
        max_num_vars = max(len(self), len(other))
        num_added = sum(1 for d in diffs if isinstance(d, diff.Addition))
        num_removed = sum(1 for d in diffs if isinstance(d, diff.Removal))
        assert (len(other) - num_added) == (len(self) - num_removed)
        num_shared = len(self) - num_removed

        # Similarity is the proportion of shared variables among the files
        # Penalize for an edited value
        total_sim = float(num_shared)
        total_sim -= sum(.25 for d in diffs if isinstance(d, diff.Edit))
        if not max_num_vars:
            return (1.0, diffs)
        return (total_sim / max_num_vars, diffs)

    def _create_element_addition(
            self, e: _CVType
    ) -> Sequence[diff_mod.Addition]:
        var_type_name = self.__class__.__name__.replace('File', 'iable')
        var_addition_t = cast(
                Type[diff.Addition],
                getattr(diff, f'{var_type_name}Addition'))
        assert isinstance(e, AbstractVariable)
        return [var_addition_t(obj_id=e.id, add_val=e)]

    def _create_element_removal(
            self, e: _CVType
    ) -> Sequence[diff_mod.Removal]:
        var_type_name = self.__class__.__name__.replace('File', 'iable')
        var_removal_t = cast(
                Type[diff.Removal],
                getattr(diff, f'{var_type_name}Removal'))
        assert isinstance(e, AbstractVariable)
        return [var_removal_t(obj_id=e.id, rem_val=e)]

    @classmethod
    def _match_var_relocations(
            cls, old_diffs: Sequence[diff_mod.Diff]
    ) -> Sequence[diff_mod.Diff]:
        # Preprocess: Extract additions and removals
        var_type_name = cls.__name__.replace('File', 'iable')
        var_relocation_t = getattr(diff, f'{var_type_name}Relocation')

        new_diffs: List[diff.Diff] = []
        additions: List[diff.Addition] = []
        removals: List[diff.Removal] = []

        for d in old_diffs:
            if isinstance(d, diff.VariableDiff):
                if isinstance(d, diff.Addition):
                    additions.append(d)
                elif isinstance(d, diff.Removal):
                    removals.append(d)
                else:
                    new_diffs.append(d)
            else:
                new_diffs.append(d)

        ad: diff.Addition  # Helping mypy
        for ad in additions:
            if (rd := cls._find_matching_removal(ad, removals)) is not None:
                r, ds = rd
                assert isinstance(r.removed_value, AbstractVariable)
                assert isinstance(ad.added_value, AbstractVariable)
                new_diffs.append(var_relocation_t(
                        obj_id=r.removed_value.id,
                        prev_loc=r.removed_value.id,
                        new_loc=ad.added_value.id))
                new_diffs.extend(ds)
                removals.remove(r)
            else:
                # No matching deleted var found in another file, it's truly new
                new_diffs.append(ad)
        new_diffs.extend(removals)
        return new_diffs

    @classmethod
    def _find_matching_removal(
            cls,
            addition: diff_mod.Addition,
            removals: Sequence[diff_mod.Removal]
    ) -> Optional[Tuple[diff_mod.Removal, Sequence[diff_mod.Diff]]]:
        """Find a removal matching the given addition in the list."""
        assert isinstance(addition.added_value, AbstractVariable)
        for r in removals:
            assert isinstance(r.removed_value, AbstractVariable)
            if r.removed_value.name == addition.added_value.name:
                return (r, r.removed_value.diff(addition.added_value))
        return None

    @classmethod
    def diff_multiple(
            cls: Type[_AVFile],
            files_v1: Sequence[_AVFile],
            files_v2: Sequence[_AVFile]
    ) -> Sequence[diff_mod.Diff]:
        # Match files
        added, removed, matched = cls._match_files(files_v1, files_v2)

        # Diff files that have confidently been matched
        diffs: List[diff.Diff] = []
        for (f1, f2) in matched:
            diffs.extend(f1.diff(f2))

        # Find file relocations
        added, removed, relocated = cls._match_file_relocations(
                added, removed, lambda f1, f2: f1.similarity_score(f2)[0])

        # Diff the relocated files and add a file relocation diff.
        for f1, f2 in relocated:
            diffs.extend(f1.diff(f2))
            diffs.append(cls._create_file_relocation_diff(f1, f2))

        # Create file additions and removals, as well as additions and removals
        # for contained variables
        diffs.extend(chain(*(af._create_file_addition() for af in added)))
        diffs.extend(chain(*(rf._create_file_removal() for rf in removed)))

        # Finally, match variable relocations between files and return the
        # diffs
        return cls._match_var_relocations(diffs)


class AbstractVariable(
        mixins.ChildObjectMixin[_CVFile],
        diff.DiffableMixin,
        base.BaseVariable
):
    """Abstract class for variables with parents.

    ChildObjectMixin cannot be mixed into BaseVariable, as this leads to
    issues with type variables.
    """
    @property
    def id(self) -> str:
        return cast(base.BaseFile, self.parent).file_name + ':' + self.name

    def __repr__(self) -> str:
        r = self.__class__.__name__
        r += f'{{ {self.name} = {pformat(self.value)} }}'
        return r

    def diff(
            self: _AVType, other: _AVType
    ) -> Sequence[diff.Diff]:
        if not isinstance(other, type(self)):
            raise NotImplementedError

        assert self.name == other.name

        # No change
        if self.value == other.value:
            return []
        # Changed value => DefaultVariableEdit/ConstantVariableEdit
        return [getattr(diff, self.__class__.__name__ + 'Edit')(
                obj_id=self.id, prev_val=self.value, new_val=other.value)]


_ABFile = TypeVar('_ABFile', 'AbstractBlockFile[Block]', 'AbstractBlockFile[HandlerBlock]')
_ABType = TypeVar(
        '_ABType',
        'AbstractBlock[Task, Block, TaskFile]',
        'AbstractBlock[HandlerTask, HandlerBlock, HandlerFile]')
_ATType = TypeVar('_ATType', 'AbstractTask[Block]', 'AbstractTask[HandlerBlock]')
_CBFile = TypeVar('_CBFile', 'TaskFile', 'HandlerFile')
_CBType = TypeVar('_CBType', 'Block', 'HandlerBlock')
_CTType = TypeVar('_CTType', 'Task', 'HandlerTask')


class AbstractBlockFile(
        ContainerFile[_CBType],
        diff.DiffableMixin,
        ABC,
):
    """Role files containing blocks."""

    @classmethod
    def _structure(cls: Type[AbstractBlockFile[_CBType]], obj: Dict[str, Any], eltype: Type[_CBType]) -> AbstractBlockFile[_CBType]:
        file_name = obj['file_name']
        content = [cast(_CBType, eltype.structure(cobj)) for cobj in obj['content']]
        return cls(file_name=file_name, elements=content)

    @classmethod
    def _from_ans_object(cls: Type[AbstractBlockFile[_CBType]], file_name: str, content: Sequence[anspb.block.Block], eltype: Type[_CBType]) -> AbstractBlockFile[_CBType]:
        return cls(file_name=file_name, elements=[eltype.from_ans_object(ds=cobj) for cobj in content])

    def unstructure(self) -> Dict[str, Any]:
        return {
            'file_name': self.file_name,
            'content': [obj.unstructure() for obj in self]
        }

    def get_path_to(self, ch: _ABType) -> str:
        return f'{self.file_name}[{self.index(ch)}]'

    def diff(
            self: _ABFile, other: _ABFile
    ) -> Sequence[diff_mod.Diff]:
        if not isinstance(other, type(self)):
            raise NotImplementedError

        # Actual type of the block is not in this module, import it here to
        # prevent cyclic imports
        from . import role
        block_type_name = self.get_block_type_name()
        block_type = cast(
                Type[AbstractBlock],  # type: ignore[type-arg]
                getattr(role, block_type_name))

        return block_type.diff_multiple(self, other)

    @classmethod
    def diff_multiple(
            cls: Type[_ABFile],
            files_v1: Sequence[_ABFile],
            files_v2: Sequence[_ABFile]
    ) -> Sequence[diff_mod.Diff]:
        # Match files
        added, removed, matched = cls._match_files(files_v1, files_v2)

        # Diff files that have confidently been matched
        diffs: List[diff.Diff] = []
        for (f1, f2) in matched:
            diffs.extend(f1.diff(f2))

        # Find file relocations
        added, removed, relocated = cls._match_file_relocations(
                added, removed, lambda f1, f2: f1.similarity_score(f2))

        # Diff the relocated files and add a file relocation diff.
        for f1, f2 in relocated:
            diffs.extend(f1.diff(f2))
            diffs.append(cls._create_file_relocation_diff(f1, f2))

        # Create file additions and removals, as well as additions and removals
        # for contained blocks
        diffs.extend(chain(*(af._create_file_addition() for af in added)))
        diffs.extend(chain(*(rf._create_file_removal() for rf in removed)))

        # Match all relocated blocks and tasks
        diffs = cls._match_block_relocations(diffs)
        diffs = cls._match_task_relocations(diffs)

        # Remove redundant relocations, e.g. relocations of a task if its
        # parent block was relocated too
        return cls._remove_redundant_relocations(diffs)

    def similarity_score(
            self: _ABFile, other: _ABFile
    ) -> float:
        if not isinstance(other, type(self)):
            raise NotImplementedError

        return super()._sim_score_internal(
            self._elements, other._elements,
            lambda c1, c2: c1.is_relocated(c2),
            lambda c1, c2: c1.similarity_score(c2))

    @classmethod
    def get_block_type_name(cls) -> str:
        return cls.__name__.replace('File', 'Block').replace('Task', '')

    def _create_element_addition(
            self, e: _CBType
    ) -> Sequence[diff_mod.Addition]:
        assert isinstance(e, AbstractBlock)
        return e.create_additions()

    def _create_element_removal(
            self, e: _CBType
    ) -> Sequence[diff_mod.Removal]:
        assert isinstance(e, AbstractBlock)
        return e.create_removals()

    @classmethod
    def _create_element_relocation(
            cls, e1: _CBType, e2: _CBType
    ) -> diff_mod.Relocation:
        block_type_name = cls.get_block_type_name()
        addition_t = cast(
                Type[diff.Relocation],
                getattr(diff, f'{block_type_name}Relocation'))
        return addition_t(obj_id=e1.id, prev_loc=e1.id, new_loc=e2.id)

    @classmethod
    def _match_block_relocations(
            cls, old_diffs: Sequence[diff_mod.Diff]
    ) -> List[diff_mod.Diff]:
        # Preprocess: Extract diffs to blocks
        block_diffs: List[diff.Diff] = []
        other_diffs: List[diff.Diff] = []

        block_type_name = cls.get_block_type_name()
        from . import role
        block_type = getattr(role, block_type_name)
        block_diff_t = getattr(diff, f'{block_type_name}Diff')

        for d in old_diffs:
            if isinstance(d, block_diff_t):
                block_diffs.append(d)
            else:
                other_diffs.append(d)

        return list(chain(
                other_diffs, block_type.match_relocations(block_diffs)))

    @classmethod
    def _match_task_relocations(
            cls, old_diffs: Sequence[diff_mod.Diff]
    ) -> List[diff_mod.Diff]:
        # Preprocess: Extract diffs to blocks
        task_diffs: List[diff.Diff] = []
        other_diffs: List[diff.Diff] = []

        block_type_name = cls.get_block_type_name()
        from . import role
        block_type = getattr(role, block_type_name)
        task_type = block_type._get_task_type()
        task_diff_t = getattr(diff, f'{task_type.__name__}Diff')

        for d in old_diffs:
            if isinstance(d, task_diff_t):
                task_diffs.append(d)
            else:
                other_diffs.append(d)

        return list(chain(
                other_diffs, task_type.match_relocations(task_diffs)))

    @classmethod
    def _remove_redundant_relocations(
            cls, old_diffs: Sequence[diff_mod.Diff]
    ) -> Sequence[diff_mod.Diff]:
        # Take all relocations, except for file relocations (these cannot be
        # redundant)
        relos = [
                d for d in old_diffs
                if isinstance(d, diff.Relocation)]
        non_file_relos = [
                d for d in relos if not isinstance(d, diff.BaseTasksFileDiff)]
        all_relos = {(d.previous_location, d.new_location) for d in relos}

        new_diffs = list(old_diffs)

        def parent_path(path: str) -> str:
            # Could throw, but shouldn't get a filename
            file_end_idx = path.index('[')
            parts = path[file_end_idx:].split('.')
            assert parts, f'Got filename: {path}'
            return path[:file_end_idx] + '.'.join(parts[:-1])

        def self_path(path: str) -> str:
            file_end_idx = path.index('[')
            return path[file_end_idx:].split('.')[-1]

        for relo in non_file_relos:
            prev = cast(str, relo.previous_location)
            new = cast(str, relo.new_location)
            parent_relo = (parent_path(prev), parent_path(new))
            if parent_relo in all_relos and self_path(prev) == self_path(new):
                # Parent was relocated, we haven't been relocated in the
                # parent => This relocation is redundant
                new_diffs.remove(relo)

        return new_diffs


class AbstractBlock(
        mixins.KeywordsMixin,
        mixins.ObjectContainerMixin[Union[_CTType, _CBType]],
        mixins.ChildObjectMixin[Union[_CBType, _CBFile]],
        diff.DiffableMixin,
        base.BaseBlock,
        ans_type=anspb.block.Block,
        extra_kws={'block', 'rescue', 'always', 'when'}
):
    def __init__(
            self, *args: object, **kwargs: Any
    ) -> None:
        super().__init__(*args, **kwargs, elements=[])
        # Initialize the elements ourselves
        task_lists = [self.block, self.rescue, self.always]
        self._elements = tuple(
                chain(*(tl for tl in task_lists if tl is not None)))
        for task in self:
            task.parent = self  # type: ignore[assignment]

    @classmethod
    def structure(cls: Type[AbstractBlock[_CTType, _CBType, Any]], obj: Any) -> AbstractBlock[_CTType, _CBType, Any]:
        def convert(thing: Any) -> Any:
            if 'block' in thing:
                return cls.structure(thing)
            return cls._get_task_type().structure(thing)
        def convert_all(things: List[Any]) -> List[Any]:
            return [convert(thing) for thing in things]

        for attr in ('block', 'rescue', 'always'):
            if attr in obj:
                obj[attr] = convert_all(obj[attr])
        return cls(kws=obj)


    def unstructure(self) -> Any:
        partial = cast(Dict[str, Any], super().unstructure())
        if 'content' in partial:
            del partial['content']  # From object container, don't want to serialize it.
        for attr in ('block', 'rescue', 'always'):
            if attr in partial:
                partial[attr] = [o.unstructure() for o in partial[attr]]
        return partial

    @overload
    @classmethod
    def _element_factory(cls: Type[AbstractBlock[_CTType, _CBType, _CBFile]], ans_obj: anspb.task.Task) -> _CTType:
        ...
    @overload
    @classmethod
    def _element_factory(cls: Type[AbstractBlock[_CTType, _CBType, _CBFile]], ans_obj: anspb.block.Block) -> _CBType:
        ...

    @classmethod
    def _element_factory(cls: Type[AbstractBlock[_CTType, _CBType, _CBFile]], ans_obj: AnsTaskOrBlock) -> Union[_CTType, _CBType]:
        # Nested blocks are the same block type, with this block as parent
        if (isinstance(ans_obj, anspb.block.Block)
                and isinstance(ans_obj._parent, anspb.block.Block)):
            return cast(_CBType, cls.from_ans_object(ds=ans_obj))

        # Nested blocks that are the result of a static import of a file are
        # removed and replaced by the task that imported it (its parent)
        if isinstance(ans_obj, anspb.block.Block):
            assert ans_obj._parent is not None
            ans_obj = ans_obj._parent

        assert isinstance(ans_obj, anspb.task.Task)
        object_type = cls._get_task_type()
        return object_type.from_ans_object(ds=ans_obj)


    @classmethod
    def _task_list_transformer(
            cls: Type[AbstractBlock[_CTType, _CBType, _CBFile]], ans_objs: Sequence[AnsTaskOrBlock]
    ) -> Sequence[Union[_CTType, _CBType]]:
        return tuple(cls._element_factory(e) for e in ans_objs)

    def __repr__(self) -> str:
        r = f'{self.__class__.__name__} {{'
        kw_reprs: List[str] = []
        for kw in self._interested_kw_names - {'block', 'rescue', 'always'}:
            kw_reprs.append(f'{kw} = {pformat(getattr(self, kw))}; ')
        for kw in self._misc_kw_names:
            if kw in self.misc_keywords:
                kw_reprs.append(f'{kw} = {pformat(self.misc_keywords[kw])}; ')
        tls = ('block', 'rescue', 'always')
        for tl in tls:
            kw_reprs.append(f'{tl}:')
            for t in getattr(self, tl):
                kw_reprs.append(indent(repr(t), ' ' * 4))
        kw_repr = indent('\n'.join(kw_reprs), ' ' * 4)
        r = f'{r}\n{kw_repr}\n}}'
        return r

    @classmethod
    def _get_task_type(cls) -> Type[_CTType]:
        bases: Sequence[type] = cls.__orig_bases__  # type: ignore[attr-defined]
        abs_base = next(
                orig_base for orig_base in bases
                if ((base := get_origin(orig_base)) is not None  # type: ignore[has-type]
                    and issubclass(base, AbstractBlock)))  # type: ignore[has-type]
        task_type = get_args(abs_base)[0]
        assert isinstance(task_type, type) and issubclass(task_type, AbstractTask), 'Wrongly subclassed AbstractBlock? Make sure the first type arg is a Task.'
        return task_type  # type: ignore[return-value]

    @classmethod
    def _transform_block(cls, ans_objs: Sequence[AnsTaskOrBlock]) -> Sequence[Union['_CTType', '_CBType']]:
        return cls._task_list_transformer(ans_objs)
    @classmethod
    def _transform_rescue(cls, ans_objs: Sequence[AnsTaskOrBlock]) -> Sequence[Union['_CTType', '_CBType']]:
        return cls._task_list_transformer(ans_objs)
    @classmethod
    def _transform_always(cls, ans_objs: Sequence[AnsTaskOrBlock]) -> Sequence[Union['_CTType', '_CBType']]:
        return cls._task_list_transformer(ans_objs)

    _block_default = tuple
    _rescue_default = tuple
    _always_default = tuple

    def gv_visit(self, g: SMGraph) -> None:
        lbl = pformat(self.name)
        g.add_node(self, label=lbl)
        self.gv_visit_children(g, 'block')
        self.gv_visit_children(g, 'rescue')
        self.gv_visit_children(g, 'always')

    @property
    def id(self) -> str:
        if isinstance(self.parent, AbstractBlock):
            return self.parent.id + '.' + self.parent.get_path_to(self)
        assert isinstance(self.parent, AbstractBlockFile)
        return f'{self.parent.file_name}[{self.parent.index(self)}]'

    def get_path_to(self, child: mixins.ObjectWithParentType) -> str:
        if child in self.block:
            cont_name = 'block'
        elif child in self.rescue:
            cont_name = 'rescue'
        else:
            assert child in self.always
            cont_name = 'always'

        return f'{cont_name}[{getattr(self, cont_name).index(child)}]'

    def similarity_score(self: _ABType, other: _ABType) -> float:
        if not isinstance(other, type(self)):
            raise NotImplementedError

        all1 = list(chain(self.block, self.rescue, self.always))
        all2 = list(chain(other.block, other.rescue, other.always))

        return super()._sim_score_internal(
            all1, all2,
            lambda c1, c2: type(c1) == type(c2) and c1.is_relocated(c2),  # type: ignore[arg-type]
            lambda c1, c2:
                c1.similarity_score(c2)  # type: ignore[arg-type]
                if type(c1) == type(c2) else 0)

    def _diff_self(
            self: _ABType, other: _ABType
    ) -> Sequence[diff_mod.Diff]:
        interested_kws = (
                self._interested_kw_names - {'block', 'rescue', 'always'})
        misc_kws = (
                self._misc_kw_names - {'block', 'rescue', 'always'})
        kws = (interested_kws | misc_kws)
        attrs1 = {
                kw: getattr(self, kw) for kw in interested_kws}
        attrs1.update({
                kw: self.misc_keywords[kw] for kw in misc_kws
                if kw in self.misc_keywords})
        attrs2 = {
                kw: getattr(other, kw) for kw in interested_kws}
        attrs2.update({
                kw: other.misc_keywords[kw] for kw in misc_kws
                if kw in other.misc_keywords})

        # Remove unchanged kws
        for kw in kws:
            if kw in attrs1 and kw in attrs2 and attrs1[kw] == attrs2[kw]:
                del attrs1[kw]
                del attrs2[kw]

        if attrs1 or attrs2:
            # Edit has taken place
            edit_t = cast(
                Type[diff.Edit],
                getattr(diff, self.__class__.__name__ + 'Edit'))
            return [edit_t(
                    obj_id=self.id, prev_val=attrs1, new_val=attrs2)]

        # No change
        assert not attrs1 and not attrs2
        return []

    def diff(self: _ABType, other: _ABType) -> Sequence[diff_mod.Diff]:
        if not isinstance(other, type(self)):
            raise NotImplementedError

        all1 = list(chain(self.block, self.rescue, self.always))
        all2 = list(chain(other.block, other.rescue, other.always))

        from . import role
        task_type_name = self.__class__.__name__.replace('Block', 'Task')
        task_type = getattr(role, task_type_name)

        tasks1 = [t for t in all1 if isinstance(t, AbstractTask)]
        tasks2 = [t for t in all2 if isinstance(t, AbstractTask)]
        blocks1 = [t for t in all1 if isinstance(t, AbstractBlock)]
        blocks2 = [t for t in all2 if isinstance(t, AbstractBlock)]

        task_diffs = task_type.diff_multiple(tasks1, tasks2)
        block_diffs = self.diff_multiple(blocks1, blocks2)

        # Check if we can already remove addition/removal diffs and replace
        # them by relocations. This is kind of matching inter-block relocations
        # but isn't yet considering tasks/blocks that have moved to a newly
        # inserted block, which is handled at the file level only after all
        # blocks have been relocated.
        task_diffs = task_type.match_relocations(task_diffs)
        block_diffs = self.match_relocations(block_diffs)

        return list(chain(task_diffs, block_diffs, self._diff_self(other)))

    @classmethod
    def match_relocations(
            cls, old_diffs: Sequence[diff_mod.Diff]
    ) -> Sequence[diff_mod.Diff]:
        relocation_t = cast(
                Type[diff.Relocation],
                getattr(diff, cls.__name__ + 'Relocation'))
        addition_t = getattr(diff, cls.__name__ + 'Addition')
        removal_t = getattr(diff, cls.__name__ + 'Removal')

        return super()._match_relocations_internal(
                old_diffs, addition_t, removal_t,
                lambda r, a: relocation_t(
                        obj_id=r.id, prev_loc=r.id, new_loc=a.id),
                lambda t1, t2: t1.similarity_score(t2))

    def is_relocated(
            self: _ABType, other: _ABType, fully_qualified: bool = False
    ) -> bool:
        if fully_qualified:
            return self.id != other.id
        return bool(
                self.parent.get_path_to(self)
                != other.parent.get_path_to(other))

    def create_additions(self) -> Sequence[diff_mod.Addition]:
        block_addition_t = cast(
                Type[diff.Addition],
                getattr(diff, self.__class__.__name__ + 'Addition'))
        task_addition_t = cast(
                Type[diff.Addition],
                getattr(diff, self._get_task_type().__name__ + 'Addition'))

        adds: List[diff.Addition] = []
        adds.append(block_addition_t(obj_id=self.id, add_val=self))
        for child in self:
            if isinstance(child, AbstractBlock):
                adds.extend(child.create_additions())
            else:
                assert isinstance(child, AbstractTask), type(child)
                adds.append(task_addition_t(obj_id=child.id, add_val=child))
        return adds

    def create_removals(self) -> Sequence[diff_mod.Removal]:
        block_removal_t = cast(
                Type[diff.Removal],
                getattr(diff, self.__class__.__name__ + 'Removal'))
        task_removal_t = cast(
                Type[diff.Removal],
                getattr(diff, self._get_task_type().__name__ + 'Removal'))

        rems: List[diff.Removal] = []
        rems.append(block_removal_t(obj_id=self.id, rem_val=self))
        for child in self:
            if isinstance(child, AbstractBlock):
                rems.extend(child.create_removals())
            else:
                assert isinstance(child, AbstractTask)
                rems.append(task_removal_t(obj_id=child.id, rem_val=child))
        return rems

    @classmethod
    def diff_multiple(
            cls: Type[_ABType],
            blocks1: Sequence[_CBType], blocks2: Sequence[_CBType]
    ) -> Sequence[diff_mod.Diff]:
        block_relocation_t = cast(
                Type[diff.Relocation],
                getattr(diff, cls.__name__ + 'Relocation'))

        return super()._diff_multiple_internal(
                blocks1, blocks2,  # type: ignore[arg-type]
                cls.create_additions, cls.create_removals,
                lambda b1, b2: block_relocation_t(
                        obj_id=b1.id, prev_loc=b1.id, new_loc=b2.id),
                lambda b1, b2: b1.is_relocated(b2),
                lambda b1, b2: b1.similarity_score(b2))


class AbstractTask(
        mixins.KeywordsMixin,
        mixins.ChildObjectMixin[_CBType],
        diff.DiffableMixin,
        base.BaseTask,
        ans_type=anspb.task.Task,
        extra_kws={'args', 'action', 'loop', 'loop_control', 'when'}):

    def gv_visit(self, g: SMGraph) -> None:
        g.add_node(self, '')
        self.gv_visit_keywords(g)

    def __repr__(self) -> str:
        r = f'{self.__class__.__name__} {{'
        kw_reprs: List[str] = []
        for kw in self._interested_kw_names:
            kw_reprs.append(f'{kw} = {pformat(getattr(self, kw))}; ')
        for kw in self._misc_kw_names:
            if kw in self.misc_keywords:
                kw_reprs.append(f'{kw} = {pformat(self.misc_keywords[kw])}; ')
        kw_repr = indent('\n'.join(kw_reprs), ' ' * 4)
        r = f'{r}\n{kw_repr}\n}}'
        return r

    @property
    def id(self) -> str:
        assert isinstance(self.parent, AbstractBlock)
        return self.parent.id + '.' + self.parent.get_path_to(self)

    def diff(self: _ATType, other: _ATType) -> Sequence[diff_mod.Diff]:
        if not isinstance(other, type(self)):
            raise NotImplementedError

        # If any of the important kws have changed, report an important change,
        # otherwise log a miscellaneous edit.
        important_edit_t = getattr(diff, self.__class__.__name__ + 'Edit')
        misc_edit_t = getattr(diff, self.__class__.__name__ + 'MiscEdit')

        all_kws = self._interested_kw_names | self._misc_kw_names
        attrs1 = {
                kw: getattr(self, kw) for kw in self._interested_kw_names}
        attrs1.update({
                kw: self.misc_keywords[kw] for kw in self._misc_kw_names
                if kw in self.misc_keywords})
        attrs2 = {
                kw: getattr(other, kw) for kw in self._interested_kw_names}
        attrs2.update({
                kw: other.misc_keywords[kw] for kw in self._misc_kw_names
                if kw in other.misc_keywords})

        # Remove unchanged kws
        for kw in all_kws:
            if kw in attrs1 and kw in attrs2 and attrs1[kw] == attrs2[kw]:
                del attrs1[kw]
                del attrs2[kw]

        if (attrs1.keys() & self._interested_kw_names
                or attrs2.keys() & self._interested_kw_names):
            # An important kw was added/removed/was changed, report it
            return [important_edit_t(
                    obj_id=self.id, prev_val=attrs1, new_val=attrs2)]
        if attrs1 or attrs2:
            # Analogous for misc. keywords
            return [misc_edit_t(
                    obj_id=self.id, prev_val=attrs1, new_val=attrs2)]

        # No change
        assert not attrs1 and not attrs2
        return []

    @classmethod
    def diff_multiple(
            cls: Type[_ATType], tasks1: Sequence[_CTType], tasks2: Sequence[_CTType]
    ) -> Sequence[diff_mod.Diff]:
        task_relocation_t = cast(
                Type[diff.Relocation],
                getattr(diff, cls.__name__ + 'Relocation'))
        task_addition_t = cast(
                Type[diff.Addition],
                getattr(diff, cls.__name__ + 'Addition'))
        task_removal_t = cast(
                Type[diff.Removal],
                getattr(diff, cls.__name__ + 'Removal'))

        return super()._diff_multiple_internal(
                tasks1, tasks2,  # type: ignore[arg-type]
                lambda t: [task_addition_t(obj_id=t.id, add_val=t)],
                lambda t: [task_removal_t(obj_id=t.id, rem_val=t)],
                lambda t1, t2: task_relocation_t(
                        obj_id=t1.id, prev_loc=t1.id, new_loc=t2.id),
                lambda t1, t2: t1.is_relocated(t2),
                lambda t1, t2: t1.similarity_score(t2))

    def is_relocated(
            self: _ATType, other: _ATType, fully_qualified: bool = False
    ) -> bool:
        if fully_qualified:
            return self.id != other.id
        return bool(
                self.parent.get_path_to(self)
                != other.parent.get_path_to(other))

    @classmethod
    def match_relocations(
            cls, old_diffs: Sequence[diff_mod.Diff]
    ) -> Sequence[diff_mod.Diff]:
        relocation_t = cast(
                Type[diff.Relocation],
                getattr(diff, cls.__name__ + 'Relocation'))
        addition_t = getattr(diff, cls.__name__ + 'Addition')
        removal_t = getattr(diff, cls.__name__ + 'Removal')

        return super()._match_relocations_internal(
                old_diffs, addition_t, removal_t,
                lambda r, a: relocation_t(
                        obj_id=r.id, prev_loc=r.id, new_loc=a.id),
                lambda t1, t2: t1.similarity_score(t2))

    def similarity_score(self: _ATType, other: _ATType) -> float:
        if not isinstance(other, type(self)):
            raise NotImplementedError

        all_kws = (
                {kw for kw in self._interested_kw_names if getattr(self, kw) is not None}
                | {kw for kw in other._interested_kw_names if getattr(other, kw) is not None}
                | self.misc_keywords.keys()
                | other.misc_keywords.keys())
        main_kw_matches = sum(
                1 for kw in self._interested_kw_names
                if (getattr(self, kw) == getattr(other, kw)
                        and getattr(self, kw) is not None))
        misc_kw_matches = sum(
                1 for kw in self._misc_kw_names
                if (kw in self.misc_keywords and kw in other.misc_keywords
                    and self.misc_keywords[kw] == other.misc_keywords[kw]))
        return (main_kw_matches + misc_kw_matches) / len(all_kws)

    @classmethod
    def structure(cls: Type[AbstractTask[_CBType]], obj: Dict[str, Value]) -> AbstractTask[_CBType]:
        return cls(kws=obj)
