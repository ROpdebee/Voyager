from typing import Callable, Optional, Tuple, cast
import typing

from itertools import product

from mypy.plugin import (
        ClassDefContext,
        DynamicClassDefContext,
        Plugin,
        SemanticAnalyzerPluginInterface
)
from mypy.nodes import (
        AssignmentStmt,
        Block,
        CallExpr,
        ClassDef,
        Context,
        Decorator,
        Expression,
        FuncDef,
        GDEF,
        MDEF,
        NameExpr,
        RefExpr,
        SetExpr,
        StrExpr,
        SymbolTable,
        SymbolTableNode,
        TupleExpr,
        TypeInfo,
        Var
)
from mypy.errorcodes import ATTR_DEFINED, CALL_ARG, MISC, VALID_TYPE
from mypy.types import (
        CallableType, Instance, NoneTyp, Type, TypeVarType, UnionType)
from mypy.typevars import fill_typevars
from mypy.mro import calculate_mro, MroError

ROLE_PKG = 'models.structural.'
KW_MIXIN_FQ_NAME = f'{ROLE_PKG}mixins.KeywordsMixin'
DYN_ORTHO_DIFF_FCT_NAME = 'models.structural.diff._create_ortho_diffs'


def add_property(
        cls_node: TypeInfo, ans_cls_node: TypeInfo, prop_node: Expression,
        api: SemanticAnalyzerPluginInterface
) -> None:
    """Add a property."""
    if not isinstance(prop_node, StrExpr):
        api.fail(
                'Keyword must be a string literal', prop_node, code=VALID_TYPE)
        return
    prop_name = prop_node.value

    try:
        ans_type = ans_cls_node[prop_name].type
    except KeyError:
        api.fail(
                f'Attribute `{prop_name}` does not exist in '
                f'{ans_cls_node.name} or its parents',
                prop_node, code=ATTR_DEFINED)
        return

    prop_type = get_transformed_type(cls_node, ans_type, prop_node, api)
    if prop_type is None:
        return

    if not has_default(cls_node, prop_node, api) and prop_type is not None:
        prop_type = make_optional(prop_type)

    new_prop = Var(prop_name, api.anal_type(prop_type))
    new_prop.info = cls_node
    new_prop.is_initialized_in_class = True
    new_prop.is_property = True

    cls_node.names[prop_name] = SymbolTableNode(MDEF, new_prop)


def has_default(
        cls_node: TypeInfo, prop_node: StrExpr,
        api: SemanticAnalyzerPluginInterface
) -> bool:
    default_name = f'_{prop_node.value}_default'
    return cls_node.get(default_name) is not None


def make_optional(typ: Type) -> Type:
    return UnionType.make_union([typ, NoneTyp()])


def find_redef_origin(
        cls_node: TypeInfo,
        transformer_name: str
) -> Optional[Type]:
    referee_name: Optional[str] = None
    for cls_def in cls_node.mro:
        for stmt in cls_def.defn.defs.body:
            if (not isinstance(stmt, AssignmentStmt)
                    or len(stmt.lvalues) != 1
                    or not isinstance(stmt.lvalues[0], NameExpr)
                    or stmt.lvalues[0].name != transformer_name
                    or not isinstance(stmt.rvalue, NameExpr)):
                continue
            if not isinstance(stmt.rvalue, NameExpr):
                continue
            if ((referee := stmt.rvalue.node) is not None
                    and isinstance(referee, FuncDef)):
                referee_name = referee.name
    if referee_name is None:
        return None
    sym = cls_node.get_method(referee_name)
    if sym is not None:
        return sym.type
    return None


def bind_type_var(cls_node: TypeInfo, typ: Type) -> Type:
    """Attempt to bind type vars."""
    # Probably a better way to do it, but I can't find it.
    if isinstance(typ, TypeVarType):
        for b in cls_node.bases:
            if not b.type.type_vars:
                continue
            try:
                type_var_idx = b.type.type_vars.index(typ.name)
            except ValueError:
                continue
            return b.args[type_var_idx]
        return typ
    if not isinstance(typ, Instance):
        return typ
    typ.args = [bind_type_var(cls_node, arg) for arg in typ.args]
    return typ


def get_transformed_type(
        cls_node: TypeInfo, ans_type: Optional[Type], prop_node: StrExpr,
        api: SemanticAnalyzerPluginInterface
) -> Optional[Type]:
    transformer_name = f'_transform_{prop_node.value}'
    transformer = cls_node.get(transformer_name)
    if transformer is None:
        return ans_type

    transformer_type: Optional[Type]
    if isinstance(transformer.node, Decorator):
        transformer_type = transformer.node.func.type
    elif isinstance(transformer.node, FuncDef):
        transformer_type = transformer.node.type
    elif (isinstance(transformer.node, Var)
            and (transformer.node.is_ready or transformer.node.is_final)):
        if transformer.node.is_ready:
            transformer_type = transformer.node.type
        else:
            transformer_type = find_redef_origin(cls_node, transformer_name)
            if transformer_type is None:
                api.fail(
                       f'Cannot resolve type of `{transformer_name}`',
                       transformer.node, code=MISC)
                return None
    else:
        api.fail(
                f'Cannot handle transformer `{transformer_name}` of type '
                + transformer.node.__class__.__name__,
                transformer.node if transformer.node is not None else cls_node,
                code=MISC)
        return None

    if not isinstance(transformer_type, CallableType):
        api.fail(
                f'Cannot infer type of `{transformer_name}`',
                transformer.node, code=MISC)
        return None

    if len(transformer_type.arg_types) != 2:
        api.fail(
                f'Expected exactly 2 arguments for {transformer_name}:'
                'self and source object', transformer.node, code=CALL_ARG)
        return None

    transformer_type = api.anal_type(transformer_type)
    if not isinstance(transformer_type, CallableType):
        return None

    ret_type = bind_type_var(cls_node, transformer_type.ret_type)
    return api.anal_type(ret_type)

    # TODO: Actual type checking


def is_kw_mixin_class(klass: TypeInfo) -> bool:
    return bool(klass.fullname == KW_MIXIN_FQ_NAME)


def is_empty_set_expr(expr: Expression) -> bool:
    return (isinstance(expr, CallExpr) and not expr.args
            and isinstance(expr.callee, NameExpr)
            and expr.callee.fullname == 'builtins.set')


def process_keywords_mixin_class(ctx: ClassDefContext) -> None:
    """Add properties for extracted keywords."""
    if not any(base for base in ctx.cls.info.mro if is_kw_mixin_class(base)):
        return

    for base in ctx.cls.info.mro:
        if not any(b for b in base.bases if is_kw_mixin_class(b.type)):
            continue
        add_kw_props(ctx.cls, base.defn, ctx.api)


def add_kw_props(
        cls: ClassDef, kw_class: ClassDef,
        api: SemanticAnalyzerPluginInterface
) -> None:
    try:
        ans_cls_expr = kw_class.keywords['ans_type']
        kw_set_expr = kw_class.keywords['extra_kws']
    except KeyError:
        api.fail(
                'Both `ans_type` and `extra_kws` are required to subclass '
                'KeywordsMixin',
                kw_class, code=CALL_ARG)
        return

    if not isinstance(ans_cls_expr, RefExpr):
        print('Wrong instance type for ans_type argument')
        return

    ans_cls_node = ans_cls_expr.node

    if not isinstance(ans_cls_node, TypeInfo):
        print('Got incorrect type for Ansible type node')
        return

    if not (isinstance(kw_set_expr, SetExpr)
            or is_empty_set_expr(kw_set_expr)):
        print('Wrong instance type for extra_kws')
        return

    # Can be an empty set, where we don't need to add any more properties.
    if isinstance(kw_set_expr, SetExpr):
        for kw_expr in kw_set_expr.items:
            add_property(cls.info, ans_cls_node, kw_expr, api)

    # Also add one for name
    add_property(cls.info, ans_cls_node, StrExpr('name'), api)


def resolve_nameexpr(
        expr: Expression, api: SemanticAnalyzerPluginInterface
) -> Optional[SymbolTableNode]:
    if not isinstance(expr, NameExpr):
        api.fail(
                'Cannot resolve this, please use a simple name', expr,
                code=MISC)
        return None
    try:
        return api.lookup_qualified(expr.name, ctx=expr)
    except KeyError:
        if api.final_iteration:
            api.fail(
                'Cannot resolve this, please use a simple name', expr,
                code=MISC)
            return None
        api.defer()
        return None


def check_class_type(
        sym: Optional[SymbolTableNode], api: SemanticAnalyzerPluginInterface,
        ctx: Context
) -> bool:
    if sym is None or not isinstance(sym.node, TypeInfo):
        api.fail('Expected a class', ctx, code=MISC)
        return False
    return True


def get_ortho_diff_name(base1: ClassDef, base2: ClassDef) -> str:
    base1_no_diff = base1.name.replace('Diff', '')
    return base1_no_diff + base2.name


def create_ortho_diff_class(
        base1: TypeInfo, base2: TypeInfo, api: SemanticAnalyzerPluginInterface,
        call_ctx: Context
) -> Tuple[str, SymbolTableNode]:
    # https://github.com/dropbox/sqlalchemy-stubs/blob/55470ceab8149db983411d5c094c9fe16343c58b/sqlmypy.py#L173-L216
    cls_name = get_ortho_diff_name(base1.defn, base2.defn)
    class_def = ClassDef(cls_name, Block([]))
    class_def.fullname = api.qualified_name(cls_name)

    info = TypeInfo(SymbolTable(), class_def, api.cur_mod_id)
    class_def.info = info
    obj = api.builtin_type('builtins.object')
    info.bases = [
            cast(Instance, fill_typevars(b))
            for b in (base1, base2)]
    try:
        calculate_mro(info)
    except MroError:
        api.fail('Unable to calculate MRO for dynamic class', call_ctx)
        info.bases = [obj]
        info.fallback_to_any = True

    return cls_name, SymbolTableNode(GDEF, info)


def add_ortho_diff_classes(ctx: DynamicClassDefContext) -> None:
    try:
        clses1 = cast(TupleExpr, ctx.call.args[0]).items
        clses2 = cast(TupleExpr, ctx.call.args[1]).items
    except IndexError:
        ctx.api.fail('Wrong arity for call', ctx.call, code=CALL_ARG)
        return
    except TypeError:
        ctx.api.fail('Wrong type for argument', ctx.call, code=CALL_ARG)
    bases = product(clses1, clses2)
    for (base1_name, base2_name) in bases:
        base1 = resolve_nameexpr(base1_name, ctx.api)
        base2 = resolve_nameexpr(base2_name, ctx.api)
        if not (check_class_type(base1, ctx.api, base1_name)
                and check_class_type(base2, ctx.api, base2_name)):
            return
        assert base1 is not None and isinstance(base1.node, TypeInfo)
        assert base2 is not None and isinstance(base2.node, TypeInfo)
        new_cls_name, new_cls = create_ortho_diff_class(
                base1.node, base2.node, ctx.api, ctx.call)
        ctx.api.add_symbol_table_node(new_cls_name, new_cls)


class MypyPlugin(Plugin):
    def get_base_class_hook(
            self, fullname: str
    ) -> Optional[Callable[[ClassDefContext], None]]:
        if fullname.startswith(ROLE_PKG):
            return process_keywords_mixin_class
        if fullname.startswith('models.structural.diff.'):
            print(fullname)
        return None

    def get_dynamic_class_hook(
            self, fullname: str
    ) -> Optional[Callable[[DynamicClassDefContext], None]]:
        if fullname == DYN_ORTHO_DIFF_FCT_NAME:
            return add_ortho_diff_classes
        return None


def plugin(version: str) -> typing.Type[Plugin]:
    # ignore version argument if the plugin works with all mypy versions.
    return MypyPlugin
