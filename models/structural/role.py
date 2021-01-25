"""Structural model for roles."""
from __future__ import annotations

from typing import (
        Any,
        Callable,
        Dict,
        List,
        Mapping,
        Optional,
        Sequence,
        IO,
        Tuple,
        Union,
        cast,
        TYPE_CHECKING
)

from itertools import chain

from contextlib import redirect_stderr, redirect_stdout
from functools import partial
from os import devnull
from pathlib import Path

import attr
import cattr
import yaml
try:
    from yaml import CLoader as Loader, CDumper as Dumper
except ImportError:
    from yaml import Loader, Dumper  # type: ignore[misc]

import ansible as ans
import ansible.inventory.manager as ansinvmgr
import ansible.parsing.yaml.objects as ansobj
import ansible.playbook as anspb
import ansible.playbook.handler as anspbh
import ansible.playbook.role as ansrole
import ansible.playbook.role.include as ansrinc

from models.base import Model
from . import abstract, base, diff, mixins
from .types import AnsTaskOrBlock, Value
from .provenance import GraphvizMixin, SMGraph, pformat


FileList = Tuple[mixins.FileType, ...]
BrokenFile = Tuple[Path, str]
Platform = Tuple[str, str]

CONVERTER = cattr.GenConverter()


class MetaFile(base.BaseFile, GraphvizMixin, diff.DiffableMixin):
    """Files in the meta folder."""
    def __init__(
            self,
            file_name: str,
            metablock: MetaBlock
    ) -> None:
        super().__init__(file_name)
        self._metablock = metablock
        metablock.parent = self

    @property
    def metablock(self) -> MetaBlock:
        return self._metablock

    def gv_visit(self, g: SMGraph) -> None:
        g.add_node(self, label=self.file_name)
        self.gv_visit_child(g, 'metablock')

    def diff(self, other: MetaFile) -> Sequence[diff.Diff]:
        if not isinstance(other, MetaFile):
            raise NotImplementedError

        return self.metablock.diff(other.metablock)

    @classmethod
    def from_ans_object(cls, file_name: str, meta_ds: ansrole.metadata.RoleMetadata) -> MetaFile:
        return cls(file_name, MetaBlock.from_ans_object(ds=meta_ds))

    @classmethod
    def structure(cls, obj: Dict[str, Any]) -> MetaFile:
        return cls(obj['file_name'], MetaBlock.structure(obj['metablock']))

    def unstructure(self) -> Dict[str, object]:
        return {
            'file_name': self.file_name,
            'metablock': self.metablock.unstructure()
        }


class MetaBlock(
        mixins.ChildObjectMixin[MetaFile],
        mixins.KeywordsMixin,
        base.BaseObject,
        diff.DiffableMixin,
        ans_type=ansrole.metadata.RoleMetadata,
        extra_kws={'dependencies'}
):
    """Meta-information of the role."""
    def __init__(
            self, kws: Dict[str, Value]
    ) -> None:
        super().__init__(kws=kws)

        self._platforms = self._extract_platforms(kws)


    @classmethod
    def structure(cls, obj: Dict[str, Value]) -> MetaBlock:
        return cls(kws=obj)

    @property
    def platforms(self) -> Sequence[Platform]:
        return self._platforms

    def _extract_platforms(
            self, kws: Dict[str, Value]
    ) -> Sequence[Platform]:
        gi = kws.get('galaxy_info')
        if not isinstance(gi, dict):
            return []

        platforms = gi.get('platforms', [])
        if not isinstance(platforms, (list, tuple)):
            return []

        platforms_flat: List[Platform] = []
        for p in platforms:
            if (isinstance(p, dict) and 'name' in p and 'versions' in p
                    and isinstance(p['versions'], list)
                    and isinstance(p['name'], str)):
                platforms_flat.extend(
                    (p['name'], v) for v in p['versions']
                    if isinstance(v, str))
        return platforms_flat

    @classmethod
    def _transform_galaxy_info(
            self, gi: Mapping[str, Value]
    ) -> Mapping[str, Value]:
        return {k: v for k, v in gi.items() if k != 'platforms'}

    @classmethod
    def _transform_dependencies(
            cls, deps: Sequence[Union[str, Dict[str, str]]]
    ) -> Sequence[str]:
        return [cls._get_dep_name(dep) for dep in deps]

    @classmethod
    def _get_dep_name(cls, dep: Union[str, Dict[str, str]]) -> str:
        if isinstance(dep, str):
            return dep
        try:
            return dep['role']
        except KeyError:
            return dep['name']

    _dependencies_default = list

    def gv_visit(self, g: SMGraph) -> None:
        g.add_node(self, None)
        self.gv_visit_keywords(g)

    def diff(self, other: MetaBlock) -> Sequence[diff.Diff]:
        if not isinstance(other, MetaBlock):
            raise NotImplementedError

        diff_platforms = diff.diff_set(
                set(self.platforms), set(other.platforms),
                add_factory=lambda p: diff.PlatformAddition(
                        obj_id='meta', add_val=p),
                rem_factory=lambda p: diff.PlatformRemoval(
                        obj_id='meta', rem_val=p))
        diff_dependencies = diff.diff_set(
                set(self.dependencies), set(other.dependencies),
                add_factory=lambda p: diff.DependencyAddition(
                        obj_id='meta', add_val=p),
                rem_factory=lambda p: diff.DependencyRemoval(
                        obj_id='meta', rem_val=p))
        diff_others = []
        if (self.name != other.name):
            diff_others.append(diff.MetaEdit(
                    obj_id='meta',
                    prev_val=self.name,
                    new_val=other.name))
        if (self.misc_keywords != other.misc_keywords):
            diff_others.append(diff.MetaEdit(
                    obj_id='meta',
                    prev_val=self.misc_keywords,
                    new_val=other.misc_keywords))

        return list(chain(diff_platforms, diff_dependencies, diff_others))


class DefaultVariable(
        base.DefaultsTrait,
        abstract.AbstractVariable['DefaultVarFile']
):
    """Variables in defaults/*.yml."""
    pass


class RoleVariable(
        base.ConstantsTrait,
        abstract.AbstractVariable['RoleVarFile']
):
    """Variables in vars/*.yml."""
    pass


class DefaultVarFile(
        base.DefaultsTrait,
        abstract.AbstractVariableFile[DefaultVariable]
):
    @classmethod
    def structure(cls, obj: Dict[str, object]) -> DefaultVarFile:
        return cast(DefaultVarFile, super()._structure(obj, DefaultVariable))

    @classmethod
    def from_ans_object(cls, path: str, content: Mapping[str, Value]) -> DefaultVarFile:
        return cast(DefaultVarFile, super()._from_ans_object(path, content, DefaultVariable))


class RoleVarFile(
        base.ConstantsTrait,
        abstract.AbstractVariableFile[RoleVariable]
):
    @classmethod
    def structure(cls, obj: Dict[str, object]) -> RoleVarFile:
        return cast(RoleVarFile, super()._structure(obj, RoleVariable))

    @classmethod
    def from_ans_object(cls, path: str, content: Mapping[str, Value]) -> RoleVarFile:
        return cast(RoleVarFile, super()._from_ans_object(path, content, RoleVariable))


class Task(
        base.TasksTrait,
        abstract.AbstractTask['Block']
):
    pass


class HandlerTask(
        base.HandlersTrait,
        abstract.AbstractTask['HandlerBlock'],
        mixins.KeywordsMixin,
        ans_type=anspbh.Handler,
        extra_kws={'listen'}):
    pass


# Bug in typing? "Too many parameters for abstract.AbstractBlock"
if TYPE_CHECKING:
    class Block(
            base.TasksTrait,
            abstract.AbstractBlock['Task', 'Block', 'TaskFile']
    ):
        pass


    class HandlerBlock(
            base.HandlersTrait,
            abstract.AbstractBlock['HandlerTask', 'HandlerBlock', 'HandlerFile']
    ):
        pass
else:
    class Block(
            base.TasksTrait,
            abstract.AbstractBlock[Task]
    ):
        pass


    class HandlerBlock(
            base.HandlersTrait,
            abstract.AbstractBlock[HandlerTask]
    ):
        pass

class TaskFile(
        base.TasksTrait,
        abstract.AbstractBlockFile[Block]
):
    @classmethod
    def structure(cls, obj: Dict[str, object]) -> TaskFile:
        return cast(TaskFile, super()._structure(obj, Block))

    @classmethod
    def from_ans_object(cls, path: str, content: Sequence[anspb.block.Block]) -> TaskFile:
        return cast(TaskFile, super()._from_ans_object(path, content, Block))


class HandlerFile(
        base.HandlersTrait,
        abstract.AbstractBlockFile[HandlerBlock]
):
    @classmethod
    def structure(cls, obj: Dict[str, object]) -> HandlerFile:
        return cast(HandlerFile, super()._structure(obj, HandlerBlock))

    @classmethod
    def from_ans_object(cls, path: str, content: Sequence[anspb.block.Block]) -> HandlerFile:
        return cast(HandlerFile, super()._from_ans_object(path, content, HandlerBlock))



for tpe in (MetaFile, DefaultVarFile, RoleVarFile, HandlerFile, TaskFile):
    CONVERTER.register_structure_hook(
        tpe,
        lambda obj, cls: cls.structure(obj))  # type: ignore[attr-defined, misc, no-any-return]
    CONVERTER.register_unstructure_hook(  # type: ignore[misc]
        tpe, lambda inst: inst.unstructure())  # type: ignore[attr-defined, no-any-return]


class RoleMetadata(ansrole.metadata.RoleMetadata):
    """Custom role to disable dependency resolving."""

    def _load_dependencies(self, attr: str, ds: Any) -> List[object]:
        # Disable resolving the dependencies.
        roles = []
        if ds:
            if not isinstance(ds, list):
                raise ans.errors.AnsibleParserError('Expected role dependencies to be a list.', obj=self._ds)  # type: ignore[attr-defined, call-arg]

            for role_def in ds:
                if isinstance(role_def, str) or 'role' in role_def or 'name' in role_def:
                    roles.append(role_def)
                    continue
                try:
                    # role_def is new style: { src: 'galaxy.role,version,name', other_vars: "here" }
                    def_parsed = ansrole.requirement.RoleRequirement.role_yaml_parse(role_def)  # type: ignore[attr-defined]
                    if def_parsed.get('name'):
                        role_def['name'] = def_parsed['name']
                    roles.append(role_def)
                except ans.errors.AnsibleError as exc:
                    raise ans.errors.AnsibleParserError(str(exc), obj=role_def, orig_exc=exc)  # type: ignore[call-arg]

        return roles


class LogCapture:
    def __init__(self) -> None:
        self.logs: List[str] = []

    def write(self, buf: str) -> int:
        self.logs.append(buf)
        return len(buf)

    def flush(self) -> None:
        pass


@attr.s(auto_attribs=True)
class Role(GraphvizMixin, diff.DiffableMixin, gv_shape='ellipse'):
    role_name: str
    meta_file: MetaFile
    default_var_files: FileList[DefaultVarFile]
    role_var_files: FileList[RoleVarFile]
    task_files: FileList[TaskFile]
    handler_files: FileList[HandlerFile]
    broken_files: FileList[Tuple[str, str]]
    logs: List[str]  # Output from Ansible that was caught

    def gv_visit(self, g: SMGraph) -> None:
        g.add_node(self, label=self.role_name)
        self.gv_visit_child(g, 'meta_file')
        self.gv_visit_children(g, 'defaults', self.default_var_files)
        self.gv_visit_children(g, 'constants', self.role_var_files)
        self.gv_visit_children(g, 'tasks', self.task_files)
        self.gv_visit_children(g, 'handlers', self.handler_files)

    def diff(self, other: Role) -> Sequence[diff.Diff]:
        mdiff = self.meta_file.diff(other.meta_file)
        dvdiff = DefaultVarFile.diff_multiple(self.default_var_files, other.default_var_files)
        rvdiff = RoleVarFile.diff_multiple(self.role_var_files, other.role_var_files)
        tdiff = TaskFile.diff_multiple(self.task_files, other.task_files)
        hdiff = HandlerFile.diff_multiple(self.handler_files, other.handler_files)
        return list(chain(mdiff, dvdiff, rvdiff, tdiff, hdiff))

    @classmethod
    def _load_role(cls, role_path: Path) -> ansrole.Role:
        dummy_play = anspb.play.Play()
        dl = ans.parsing.dataloader.DataLoader()
        var_mgr = ans.vars.manager.VariableManager(
                loader=dl, inventory=ansinvmgr.InventoryManager(dl))
        role_def = ansrinc.RoleInclude.load(
                str(role_path), dummy_play,
                variable_manager=var_mgr)
        r = ansrole.Role(play=dummy_play)  # type: ignore[call-arg]
        r._role_path = str(role_path)
        r._variable_manager = var_mgr
        r._loader = dl
        return r

    @classmethod
    def _load_files(
            cls, files_dir: Path,
            factory: Callable[[Path, mixins.SourceType], mixins.FileType],
            loader: Callable[[Path], mixins.SourceType],
            top_level: bool = True,
    ) -> Tuple[FileList[mixins.FileType], Sequence[BrokenFile]]:
        fl: List[mixins.FileType] = []
        broken: List[BrokenFile] = []
        # Force the directory iterator to raise exception early, so that we
        # don't mistakenly catch an exception from a loader
        try:
            all_files = list(files_dir.iterdir())
        except OSError:
            all_files = []

        for file in all_files:
            if file.is_dir():
                files, broken_files = cls._load_files(
                        file, factory, loader, False)
                fl.extend(files)
                broken.extend(broken_files)
            elif file.suffix.lower() in ('.yml', '.yaml', '.json'):
                try:
                    if file.stem == 'main' and top_level:
                        fl.insert(0, factory(file, loader(file)))
                    else:
                        fl.append(factory(file, loader(file)))
                except ans.errors.AnsibleError as err:
                    broken.append((file, str(err)))
        return tuple(fl), broken

    @staticmethod
    def _load_vars(var_path: Path, r: ansrole.Role) -> Mapping[str, Value]:
        ds = r._load_role_yaml(
                str(var_path.parent.relative_to(Path(r._role_path))),
                var_path.name, allow_dir=False)
        if ds is None:
            return {}
        if not isinstance(ds, ansobj.AnsibleMapping):
            # Hijack AnsibleError so we can log the broken file
            raise ans.errors.AnsibleError(f'Corrupt variables: {ds}')
        return ds

    @staticmethod
    def _load_tasks(
            task_path: Path, r: ansrole.Role, handlers: bool = False
    ) -> Sequence[anspb.block.Block]:
        ds = r._load_role_yaml(
                str(task_path.parent.relative_to(Path(r._role_path))),
                task_path.name, allow_dir=False)
        # assert isinstance(ds, ansobj.AnsibleSequence), ds
        blks = anspb.helpers.load_list_of_blocks(
                cast(ansobj.AnsibleSequence, ds), play=r._play, role=r,
                loader=r._loader, variable_manager=r._variable_manager,
                use_handlers=handlers)
        return blks


    @staticmethod
    def _load_metadata_obj(role_path: Path, role: ansrole.Role) -> Tuple[ansrole.metadata.RoleMetadata, Optional[BrokenFile]]:
        metadata_dict = role._load_role_yaml('meta')
        if not metadata_dict:
            return (RoleMetadata(), None)

        if not isinstance(metadata_dict, dict):
            return (RoleMetadata(),
                    (role_path / 'meta/main.yml', f"the 'meta/main.yml' for role {role.get_name()} is not a dictionary"))  # type: ignore[attr-defined]

        try:
            return (RoleMetadata(owner=role).load_data(metadata_dict), None)  # type: ignore[call-arg, attr-defined]
        except ans.errors.AnsibleError as e:
            return RoleMetadata(), ((role_path / 'meta/main.yml'), str(e))

    @classmethod
    def load_from_ans_obj(cls, role_path: Path) -> Role:
        role_path = role_path.resolve()
        log_capture = LogCapture()
        with redirect_stdout(log_capture), redirect_stderr(log_capture):  # type: ignore[arg-type]
            role = cls._load_role(role_path)
            # Load the metadata
            meta_obj, broken_meta = cls._load_metadata_obj(role_path, role)
            meta = MetaFile.from_ans_object('meta/main.yml', meta_obj)
            broken_meta_files = []
            if broken_meta is not None:
                broken_meta_files.append(broken_meta)

            def obj_fact_factory(
                    obj_fact: Callable[[str, mixins.SourceType], mixins.FileType]
            ) -> Callable[[Path, mixins.SourceType], mixins.FileType]:
                return lambda p, o: obj_fact(str(p.relative_to(role_path)), o)

            var_loader = partial(cls._load_vars, r=role)
            task_loader = partial(cls._load_tasks, r=role)
            handler_loader = partial(cls._load_tasks, r=role, handlers=True)

            dfs, bdfs = cls._load_files(
                    role_path / 'defaults',
                    obj_fact_factory(DefaultVarFile.from_ans_object), var_loader)
            cfs, bcfs = cls._load_files(
                    role_path / 'vars',
                    obj_fact_factory(RoleVarFile.from_ans_object), var_loader)
            tfs, btfs = cls._load_files(
                    role_path / 'tasks',
                    obj_fact_factory(TaskFile.from_ans_object), task_loader)
            hfs, bhfs = cls._load_files(
                    role_path / 'handlers',
                    obj_fact_factory(HandlerFile.from_ans_object), handler_loader)

        def transform_broken(broken_file: BrokenFile) -> Tuple[str, str]:
            path, reason = broken_file
            return str(path.relative_to(role_path)), reason
        return cls(
                role_name=role_path.name, meta_file=meta, default_var_files=dfs,
                role_var_files=cfs, task_files=tfs, handler_files=hfs,
                broken_files=tuple(transform_broken(broken) for broken in chain(bdfs, bcfs, btfs, bhfs, broken_meta_files)),
                logs=log_capture.logs)



@attr.s(auto_attribs=True)
class StructuralRoleModel(Model):
    role_root: Role
    role_id: str
    role_rev: str

    @property
    def id(self) -> str:
        return f'{self.role_id}@{self.role_rev}'

    @classmethod
    def create(cls, role_path: Path, role_id: str, role_rev: str) -> 'StructuralRoleModel':
        model = cls(role_root=Role.load_from_ans_obj(role_path), role_id=role_id, role_rev=role_rev)

        # Make sure serialization and deserialization will work, catch problems early
        unstructured = CONVERTER.unstructure(model.role_root)
        assert unstructured == CONVERTER.unstructure(CONVERTER.structure(unstructured, Role))

        return model


@attr.s(auto_attribs=True)
class MultiStructuralRoleModel(Model):
    role_id: str
    structural_models: Sequence[StructuralRoleModel]

    @property
    def id(self) -> str:
        return str(self.role_id)

    def dump(self, dirpath: Path) -> Path:
        """Dump the object to disk and return its path."""
        target = dirpath / self.role_id
        target.write_text(CONVERTER.unstructure(self.structural_models))
        return target

    @classmethod
    def load(cls, id: str, file_path: Path) -> object:
        """Load an object from disk."""
        models = CONVERTER.structure(yaml.load(file_path.read_text(), Loader=Loader), List[StructuralRoleModel])
        return cls(id, models)
