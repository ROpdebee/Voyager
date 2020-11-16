"""Structural model for roles."""
from __future__ import annotations

from typing import (
        Callable,
        List,
        Mapping,
        Optional,
        Sequence,
        Tuple,
        Union,
        cast
)

from itertools import chain

from contextlib import redirect_stderr, redirect_stdout
from functools import partial
from os import devnull
from pathlib import Path

import ansible as ans
import ansible.inventory.manager as ansinvmgr
import ansible.parsing.yaml.objects as ansobj
import ansible.playbook as anspb
import ansible.playbook.handler as anspbh
import ansible.playbook.role as ansrole
import ansible.playbook.role.include as ansrinc

from . import abstract, base, diff, mixins
from .types import AnsTaskOrBlock, Value
from .provenance import GraphvizMixin, SMGraph, pformat


FileList = Sequence[mixins.FileType]
BrokenFile = Tuple[Path, ans.errors.AnsibleError]
Platform = Tuple[str, str]


class MetaFile(base.BaseFile, GraphvizMixin, diff.DiffableMixin):
    """Files in the meta folder."""
    def __init__(
            self,
            file_name: str,
            ds: ansrole.metadata.RoleMetadata
    ) -> None:
        super().__init__(file_name)
        self._metablock = MetaBlock(ds, self)

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
            self, ds: ansrole.metadata.RoleMetadata, parent: MetaFile
    ) -> None:
        super().__init__(ds=ds, parent=parent)

        self._platforms = self._extract_platforms(ds)

    @property
    def platforms(self) -> Sequence[Platform]:
        return self._platforms

    def _extract_platforms(
            self, ds: ansrole.metadata.RoleMetadata
    ) -> Sequence[Platform]:
        gi = ds.galaxy_info
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

    def _transform_galaxy_info(
            self, gi: Mapping[str, Value]
    ) -> Mapping[str, Value]:
        return {k: v for k, v in gi.items() if k != 'platforms'}

    def _transform_dependencies(
            self, deps: Sequence[ansrole.include.RoleInclude]
    ) -> Sequence[str]:
        return tuple(ri.get_name() for ri in deps)

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
        abstract.AbstractVariable['DefaultsFile']
):
    """Variables in defaults/*.yml."""
    pass


class ConstantVariable(
        base.ConstantsTrait,
        abstract.AbstractVariable['ConstantsFile']
):
    """Variables in vars/*.yml."""
    pass


class DefaultsFile(
        base.DefaultsTrait,
        abstract.AbstractVariableFile[DefaultVariable]
):
    def __init__(
            self, file_name: str, vars: Mapping[str, Value]
    ) -> None:
        super().__init__(
                file_name=file_name, vars=vars,
                var_factory=partial(DefaultVariable, parent=self))


class ConstantsFile(
        base.ConstantsTrait,
        abstract.AbstractVariableFile[ConstantVariable]
):
    def __init__(
            self, file_name: str, vars: Mapping[str, Value]
    ) -> None:
        super().__init__(
                file_name=file_name, vars=vars,
                var_factory=partial(ConstantVariable, parent=self))


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


class Block(
        base.TasksTrait,
        abstract.AbstractBlock[
            Union['Block', Task],
            Union['Block', 'TasksFile']]
):
    pass


class HandlerBlock(
        base.HandlersTrait,
        abstract.AbstractBlock[
            Union['HandlerBlock', HandlerTask],
            Union['HandlerBlock', 'HandlersFile']]
):
    pass


class TasksFile(
        base.TasksTrait,
        abstract.AbstractBlockFile[Block]
):
    def __init__(
            self, file_name: str, block_list: Sequence[AnsTaskOrBlock]
    ) -> None:
        super().__init__(
                file_name=file_name, block_list=block_list,
                block_factory=partial(Block, parent=self))


class HandlersFile(
        base.HandlersTrait,
        abstract.AbstractBlockFile[HandlerBlock]
):
    def __init__(
            self, file_name: str, block_list: Sequence[AnsTaskOrBlock]
    ) -> None:
        super().__init__(
                file_name=file_name, block_list=block_list,
                block_factory=partial(HandlerBlock, parent=self))


class Role(GraphvizMixin, diff.DiffableMixin, gv_shape='ellipse'):
    def __init__(
            self, role_name: str, meta_file: MetaFile,
            defaults: FileList[DefaultsFile], consts: FileList[ConstantsFile],
            tasks: FileList[TasksFile], handlers: FileList[HandlersFile],
            broken_files: Sequence[BrokenFile]
    ) -> None:
        self._role_name = role_name
        self._mf = meta_file
        self._df = defaults
        self._cf = consts
        self._tf = tasks
        self._hf = handlers
        self._broken_files = broken_files

    @property
    def role_name(self) -> str:
        return self._role_name

    @property
    def meta_file(self) -> MetaFile:
        return self._mf

    @property
    def defaults_files(self) -> FileList[DefaultsFile]:
        return self._df

    @property
    def constants_files(self) -> FileList[ConstantsFile]:
        return self._cf

    @property
    def tasks_files(self) -> FileList[TasksFile]:
        return self._tf

    @property
    def handlers_files(self) -> FileList[HandlersFile]:
        return self._hf

    @property
    def broken_files(self) -> Sequence[BrokenFile]:
        return self._broken_files

    def gv_visit(self, g: SMGraph) -> None:
        g.add_node(self, label=self.role_name)
        self.gv_visit_child(g, 'meta_file')
        self.gv_visit_children(g, 'defaults', self.defaults_files)
        self.gv_visit_children(g, 'constants', self.constants_files)
        self.gv_visit_children(g, 'tasks', self.tasks_files)
        self.gv_visit_children(g, 'handlers', self.handlers_files)

    def diff(self, other: Role) -> Sequence[diff.Diff]:
        mdiff = self._mf.diff(other._mf)
        ddiff = DefaultsFile.diff_multiple(self._df, other._df)
        cdiff = ConstantsFile.diff_multiple(self._cf, other._cf)
        tdiff = TasksFile.diff_multiple(self._tf, other._tf)
        hdiff = HandlersFile.diff_multiple(self._hf, other._hf)
        return list(chain(mdiff, ddiff, cdiff, tdiff, hdiff))

    @classmethod
    def _load_role(cls, role_path: Path, deps_path: Path) -> ansrole.Role:
        dummy_play = anspb.play.Play()
        dl = ans.parsing.dataloader.DataLoader()
        var_mgr = ans.vars.manager.VariableManager(
                loader=dl, inventory=ansinvmgr.InventoryManager(dl))
        # HACK: We need to get Ansible to load roles in the dependency path,
        # which may differ from the path of the role itself. Hijack the
        # configuration to insert this path in the search list.
        if not str(deps_path) in ans.constants.DEFAULT_ROLES_PATH:
            ans.constants.DEFAULT_ROLES_PATH.append(str(deps_path))
        # Shut up the deprecation warnings, it clutters the output
        ans.constants.DEPRECATION_WARNINGS = False
        role_def = ansrinc.RoleInclude.load(
                str(role_path), dummy_play,
                variable_manager=var_mgr)
        with open(devnull, 'w') as fnull:
            with redirect_stderr(fnull), redirect_stdout(fnull):
                return ansrole.Role.load(role_def, dummy_play)

    @classmethod
    def _load_files(
            cls, files_dir: Path, main: Optional[mixins.SourceType],
            factory: Callable[[Path, mixins.SourceType], mixins.FileType],
            loader: Callable[[Path], mixins.SourceType]
    ) -> Tuple[FileList[mixins.FileType], Sequence[BrokenFile]]:
        fl = []
        broken: List[BrokenFile] = []
        if main:
            fl.append(factory(files_dir / 'main.yml', main))
        # Force the directory iterator to raise exception early, so that we
        # don't mistakenly catch an exception from a loader
        try:
            all_files = list(files_dir.iterdir())
        except OSError:
            all_files = []

        for file in all_files:
            if file.name == 'main.yml' and main is not None:
                continue
            if file.is_dir():
                files, broken_files = cls._load_files(
                        file, None, factory, loader)
                fl.extend(files)
                broken.extend(broken_files)
            elif file.suffix.lower() in ('.yml', '.yaml', '.json'):
                try:
                    fl.append(factory(file, loader(file)))
                except ans.errors.AnsibleError as err:
                    broken.append((file, err))
        return fl, broken

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

    @classmethod
    def load(cls, role_path: Path, deps_path: Path) -> Role:
        role_path = role_path.resolve()
        deps_path = deps_path.resolve()
        role = cls._load_role(role_path, deps_path)
        meta = MetaFile('meta/main.yml', role._metadata)

        def obj_fact_factory(
                obj_fact: Callable[[str, mixins.SourceType], mixins.FileType]
        ) -> Callable[[Path, mixins.SourceType], mixins.FileType]:
            return lambda p, o: obj_fact(str(p.relative_to(role_path)), o)

        var_loader = partial(cls._load_vars, r=role)
        task_loader = partial(cls._load_tasks, r=role)
        handler_loader = partial(cls._load_tasks, r=role, handlers=True)

        dfs, bdfs = cls._load_files(
                role_path / 'defaults', role._default_vars,
                obj_fact_factory(DefaultsFile), var_loader)
        cfs, bcfs = cls._load_files(
                role_path / 'vars', role._role_vars,
                obj_fact_factory(ConstantsFile), var_loader)
        tfs, btfs = cls._load_files(
                role_path / 'tasks', role._task_blocks,
                obj_fact_factory(TasksFile), task_loader)
        hfs, bhfs = cls._load_files(
                role_path / 'handlers', role._handler_blocks,
                obj_fact_factory(HandlersFile), handler_loader)
        return cls(
                role_path.name, meta, dfs, cfs, tfs, hfs,
                tuple(chain(bdfs, bcfs, btfs, bhfs)))
