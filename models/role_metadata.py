"""Models for role metadata."""
from __future__ import annotations

from typing import Any, Collection, Dict, Iterator, List, Mapping, Optional, Sequence, Union, Type, TypeVar, cast

from abc import abstractmethod
from pathlib import Path

import attr
import cattr.gen
import pendulum
import yaml

try:
    from yaml import CLoader as Loader, CDumper as Dumper
except ImportError:
    from yaml import Loader, Dumper  # type: ignore[misc]

from pprint import pprint

from models.base import Model
from models.galaxy import GalaxyAPIPage
from models.galaxy_schema import SCHEMAS
from util.misc import capitalized_to_underscored


CONVERTER = cattr.GenConverter()
CONVERTER.register_structure_hook(
        pendulum.DateTime,
        lambda ts, _: cast(pendulum.DateTime, pendulum.parse(ts)))
CONVERTER.register_unstructure_hook(
        pendulum.DateTime, lambda dt: dt.to_rfc3339_string())



class MetadataMap:
    """Maps entity IDs to their JSON-parsed objects."""

    def __init__(self, scrape_pages: Sequence[GalaxyAPIPage]) -> None:
        self.roles: Dict[int, Any] = {}
        self.namespaces: Dict[int, Any] = {}
        self.platforms: Dict[int, Any] = {}
        self.provider_namespaces: Dict[int, Any] = {}
        self.repositories: Dict[int, Any] = {}
        self.tags: Dict[int, Any] = {}
        # self.users: Dict[int, Any] = {}
        self.community_surveys: Dict[int, Any] = {}
        self.content: Dict[int, Any] = {}
        self.role_search: Dict[int, Any] = {}

        for page in scrape_pages:
            if page.page_type == 'users':
                continue
            dct = getattr(self, page.page_type)
            results = cast(
                    Sequence[Dict[str, object]], page.response['results'])
            for result in results:
                dct[result['id']] = result

    def verify_schema(self) -> None:
        """Verify that we understand the full schema."""
        for page_type, schema in SCHEMAS.items():
            self._verify_schema(
                    list(getattr(self, page_type).values()), schema, page_type)

    def _verify_schema(
            self, objs: Sequence[object], schema: Any, page_type: str,
    ) -> None:
        for obj in objs:
            try:
                self._verify_individual(obj, schema)
            except:
                print(page_type + ': Wrong schema')
                pprint(obj)
                raise

    def _verify_individual(self, obj: Any, schema: Any) -> None:
        if isinstance(schema, dict):
            # Nested dicts
            assert isinstance(obj, dict)
            leftover_keys = set(obj.keys()) - set(schema.keys())
            assert not leftover_keys, leftover_keys
            for k in obj:
                self._verify_individual(obj[k], schema[k])
        elif isinstance(schema, list):
            # Lists
            assert isinstance(obj, list)
            if not schema:
                assert not obj, 'Expected empty list'
            else:
                for subobj in obj:
                    self._verify_individual(subobj, schema[0])
        elif isinstance(schema, tuple):
            # Tuple: Multiple possibilities.
            matched = False
            for possibility in schema:
                try:
                    self._verify_individual(obj, possibility)
                    return  # Passed
                except Exception as e:
                    pass

            raise ValueError(f'Failed validation of multiple options: {schema}')
        elif schema is pendulum.DateTime:
            # Date times should be able to be parsed
            assert isinstance(obj, str), f'{obj} is not a string'
            pendulum.parse(obj)
        elif isinstance(schema, type):
            # Primitive types
            assert isinstance(obj, schema), f'{type(obj)} vs {schema}'
        else:
            # Scalar values
            assert schema == obj, f'{obj} is not {schema}'


class XrefID:
    """Model for xrefs."""

    def __init__(self, entity_type: Union[Type[GalaxyEntity], str], id: int) -> None:
        if isinstance(entity_type, type):
            self.entity_type = entity_type.__name__
        else:
            self.entity_type = entity_type
        self.entity_id = id


    def __str__(self) -> str:
        return f'{self.entity_type}:{self.entity_id}'

    def __repr__(self) -> str:
        return f'<{self.entity_type}:{self.entity_id}>'

    @classmethod
    def load(cls, s: str) -> XrefID:
        etype, eid_str = s.split(':')
        return cls(etype, int(eid_str))


CONVERTER.register_structure_hook(XrefID, lambda xref, _: XrefID.load(xref))
CONVERTER.register_unstructure_hook(XrefID, lambda x: str(x))

_EntityType = TypeVar('_EntityType', bound='GalaxyEntity')


class GalaxyEntity(Model):
    """Base class for Galaxy entity models."""

    @classmethod
    @abstractmethod
    def from_galaxy_json(cls: Type[_EntityType], json: Dict[str, Any]) -> _EntityType:  # type: ignore[misc]
        ...


def _parse_date(
        date_str: Optional[str], may_be_none: bool
) -> Optional[pendulum.DateTime]:
    if date_str is None:
        if may_be_none:
            return None
        raise ValueError('Expected date, got None, not allowed')
    datetime = pendulum.parse(date_str)
    assert isinstance(datetime, pendulum.DateTime)
    return datetime


def _extend_with_dates(
        attrs: Dict[str, Any], json: Dict[str, Any],
        mod_may_be_none: bool = False
) -> None:
    # Creation date is always set.
    attrs['creation_date'] = _parse_date(json['created'], False)
    attrs['modification_date'] = _parse_date(json['modified'], mod_may_be_none)


def _create_gh_link(user: str, repo: str) -> str:
    return f'https://github.com/{user}/{repo}'


@attr.s(auto_attribs=True)
class CommunitySurvey(GalaxyEntity):
    """Model for Galaxy community survey."""

    entity_id: int
    reviewed_repository: XrefID
    reviewer_user_id: XrefID

    score_documentation: Optional[int]
    score_does_what_it_says: Optional[int]
    score_ease_of_use: Optional[int]
    score_used_in_production: Optional[int]
    score_works_as_is: Optional[int]

    creation_date: pendulum.DateTime
    modification_date: pendulum.DateTime


    @property
    def id(self) -> str:
        return str(self.entity_id)

    @classmethod
    def from_galaxy_json(cls, json: Dict[str, Any]) -> CommunitySurvey:  # type: ignore[misc]
        # Sanity checks
        assert json['active'] is None
        assert json['content_id'] == json['repository']

        attrs: Dict[str, Any] = {}

        attrs['entity_id'] = json['id']
        attrs['reviewed_repository'] = XrefID(Repository, json['repository'])
        attrs['reviewer_user_id'] = XrefID(User, json['user'])

        attrs['score_documentation'] = json['docs']
        attrs['score_does_what_it_says'] = json['does_what_it_says']
        attrs['score_ease_of_use'] = json['ease_of_use']
        attrs['score_used_in_production'] = json['used_in_production']
        attrs['score_works_as_is'] = json['works_as_is']

        _extend_with_dates(attrs, json)

        return CommunitySurvey(**attrs)


@attr.s(auto_attribs=True)
class ContentScoreMessage(GalaxyEntity):
    """Model for task messages, contained in Content.

    Contains warning messages explaining the calculation of the scores.
    """

    entity_id: int

    is_linter_rule_violation: bool
    linter_rule_id: str
    linter_type: str

    message_text: str
    message_type: str

    rule_description: str
    rule_severity: Optional[int]

    score_type: Optional[str]

    @property
    def id(self) -> str:
        return str(self.entity_id)

    @classmethod
    def from_galaxy_json(cls, json: Dict[str, Any]) -> ContentScoreMessage:  # type: ignore[misc]
        # Sanity checks
        del json['content_id']
        json['entity_id'] = json['id']
        del json['id']
        json['rule_description'] = json['rule_desc']
        del json['rule_desc']
        return ContentScoreMessage(**json)


@attr.s(auto_attribs=True)
class Content(GalaxyEntity):
    """Model for Galaxy content."""

    entity_id: int
    content_type: str
    role_type: Optional[str]

    name: str
    original_name: str
    description: Optional[str]
    download_count: int

    score_content: Optional[float]
    score_metadata: Optional[float]
    score_quality: Optional[float]
    score_messages: List[ContentScoreMessage]

    namespace_id: XrefID
    repository_id: XrefID
    dependencies: List[str]

    creation_date: pendulum.DateTime
    modification_date: pendulum.DateTime
    import_date: Optional[pendulum.DateTime]


    @property
    def id(self) -> str:
        return str(self.entity_id)

    @classmethod
    def from_galaxy_json(cls, json: Dict[str, Any]) -> Content:  # type: ignore[misc]
        # Sanity checks
        assert json['compatibility_score'] is None
        assert json['name']
        assert json['original_name']
        smry = json['summary_fields']

        attrs: Dict[str, Any] = {}

        attrs['entity_id'] = json['id']
        attrs['content_type'] = json['content_type']
        attrs['role_type'] = json['role_type'] or None

        attrs['name'] = json['name']
        attrs['original_name'] = json['original_name']
        attrs['description'] = json['description'] or None
        attrs['download_count'] = json['download_count']

        attrs['score_content'] = json['content_score']
        attrs['score_metadata'] = json['metadata_score']
        attrs['score_quality'] = json['quality_score']
        attrs['score_messages'] = list(_create_all(
                smry['task_messages'], ContentScoreMessage).values())

        attrs['namespace_id'] = XrefID(Namespace, smry['namespace']['id'])
        attrs['repository_id'] = XrefID(Repository, smry['repository']['id'])
        attrs['dependencies'] = smry['dependencies']

        _extend_with_dates(attrs, json)
        attrs['import_date'] = _parse_date(json['imported'], True)

        return Content(**attrs)


@attr.s(auto_attribs=True)
class Namespace(GalaxyEntity):
    """Model for Galaxy namespaces."""

    entity_id: int
    is_active: bool
    name: str
    company_name: Optional[str]
    location: Optional[str]
    email: Optional[str]
    description: Optional[str]
    homepage_url: Optional[str]
    avatar_url: Optional[str]

    content_counts: Dict[str, int]
    owner_ids: List[XrefID]
    provider_namespace_ids: List[XrefID]

    creation_date: pendulum.DateTime
    modification_date: pendulum.DateTime

    @property
    def id(self) -> str:
        return str(self.entity_id)

    @classmethod
    def from_galaxy_json(cls, json: Dict[str, Any]) -> Namespace:  # type: ignore[misc]
        # Sanity checks
        assert not json['is_vendor']
        assert json['name']
        smry = json['summary_fields']

        attrs: Dict[str, Any] = {}

        attrs['entity_id'] = json['id']
        attrs['is_active'] = json['active']
        attrs['name'] = json['name']
        attrs['company_name'] = json['company'] or None
        attrs['location'] = json['location'] or None
        attrs['email'] = json['email'] or None
        attrs['description'] = json['description'] or None
        attrs['homepage_url'] = json['html_url'] or None
        attrs['avatar_url'] = json['avatar_url'] or None

        attrs['content_counts'] = smry['content_counts']
        attrs['owner_ids'] = [
                XrefID(User, owner['id']) for owner in smry['owners']]
        attrs['provider_namespace_ids'] = [
                XrefID(ProviderNamespace, pns['id'])
                for pns in smry['provider_namespaces']]

        _extend_with_dates(attrs, json)

        return Namespace(**attrs)


@attr.s(auto_attribs=True)
class ProviderNamespace(GalaxyEntity):
    """Model for Galaxy provider namespaces."""

    entity_id: int
    name: str
    display_name: Optional[str]
    company_name: Optional[str]
    location: Optional[str]
    email: Optional[str]
    description: Optional[str]
    homepage_url: Optional[str]
    avatar_url: Optional[str]
    follower_count: int

    namespace_id: Optional[XrefID]

    creation_date: pendulum.DateTime
    modification_date: pendulum.DateTime


    @property
    def id(self) -> str:
        return str(self.entity_id)

    @classmethod
    def from_galaxy_json(cls, json: Dict[str, Any]) -> ProviderNamespace:
        # Sanity checks
        assert json['active']
        assert json['name']
        smry = json['summary_fields']
        try:
            assert smry['provider']['id'] == 1
            assert smry['provider']['name'] == 'GitHub'
        except KeyError:
            pass

        attrs: Dict[str, Any] = {}

        attrs['entity_id'] = json['id']
        attrs['name'] = json['name']
        attrs['display_name'] = json['display_name'] or None
        attrs['company_name'] = json['company'] or None
        attrs['location'] = json['location'] or None
        attrs['email'] = json['email'] or None
        attrs['description'] = json['description'] or None
        attrs['homepage_url'] = json['html_url'] or None
        attrs['avatar_url'] = json['avatar_url'] or None
        attrs['follower_count'] = json['followers'] or 0

        try:
            attrs['namespace_id'] = XrefID(Namespace, smry['namespace']['id'])
        except KeyError:
            attrs['namespace_id'] = None

        _extend_with_dates(attrs, json)

        return ProviderNamespace(**attrs)


@attr.s(auto_attribs=True)
class Repository(GalaxyEntity):
    """Model for Galaxy Repository."""

    entity_id: int

    name: str
    original_name: str
    description: Optional[str]
    readme: Optional[str]

    commit_sha: Optional[str]
    commit_creation_date: Optional[pendulum.DateTime]
    commit_message: Optional[str]

    is_deprecated: bool
    is_enabled: bool
    format: Optional[str]
    download_url: str
    github_url: str
    import_branch: Optional[str]
    travis_ci_build_url: Optional[str]
    travis_ci_status_badge_url: Optional[str]
    versions: List[Dict[str, str]]

    download_count: int
    stargazers_count: int
    watchers_count: int
    forks_count: int
    open_issues_count: int

    community_survey_score: Optional[float]
    community_surveys: List[XrefID]
    quality_score: Optional[float]
    latest_quality_score_date: Optional[pendulum.DateTime]

    content_counts: Dict[str, int]
    content_ids: List[XrefID]
    provider_namespace_id: XrefID
    namespace_id: Optional[XrefID]

    last_import_created_date: Optional[pendulum.DateTime]
    last_import_modified_date: Optional[pendulum.DateTime]
    last_import_started_date: Optional[pendulum.DateTime]
    last_import_finished_date: Optional[pendulum.DateTime]
    last_import_status: Optional[str]

    creation_date: pendulum.DateTime
    modification_date: pendulum.DateTime

    @property
    def id(self) -> str:
        return str(self.entity_id)

    @classmethod
    def from_galaxy_json(cls, json: Dict[str, Any], surveys: Dict[int, CommunitySurvey]) -> Repository:  # type: ignore[misc, override]
        # Sanity checks
        assert json['active'] is None
        assert json['external_url']
        assert json['name']

        assert json['clone_url'] == json['external_url'] + '.git'

        smry = json['summary_fields']

        attrs: Dict[str, Any] = {}

        attrs['entity_id'] = json['id']
        attrs['name'] = json['name']
        attrs['original_name'] = json['original_name']
        attrs['description'] = json['description'] or None
        attrs['readme'] = json['readme'] or None

        attrs['commit_sha'] = json['commit'] or None
        attrs['commit_creation_date'] = _parse_date(
                json['commit_created'], may_be_none=True)
        attrs['commit_message'] = json['commit_message'] or None

        attrs['is_deprecated'] = json['deprecated']
        attrs['is_enabled'] = json['is_enabled']
        attrs['format'] = json['format'] or None
        attrs['download_url'] = json['download_url']
        attrs['github_url'] = json['external_url']
        attrs['import_branch'] = json['import_branch'] or None
        attrs['travis_ci_build_url'] = json['travis_build_url'] or None
        attrs['travis_ci_status_badge_url'] = json['travis_status_url'] or None
        attrs['versions'] = smry['versions']

        attrs['download_count'] = json['download_count']
        attrs['stargazers_count'] = json['stargazers_count']
        attrs['watchers_count'] = json['watchers_count']
        attrs['forks_count'] = json['forks_count']
        attrs['open_issues_count'] = json['open_issues_count']

        attrs['community_survey_score'] = json['community_score']
        attrs['community_surveys'] = [
                XrefID(CommunitySurvey, srv.entity_id)
                for srv in surveys.values()
                if srv.reviewed_repository.entity_id == json['id']]
        attrs['quality_score'] = json['quality_score']
        attrs['latest_quality_score_date'] = _parse_date(
                json['quality_score_date'], may_be_none=True)

        attrs['content_counts'] = smry['content_counts']
        attrs['content_ids'] = [
                XrefID(Content, cnt['id']) for cnt in smry['content_objects']]
        attrs['provider_namespace_id'] = XrefID(
                ProviderNamespace, smry['provider_namespace']['id'])
        try:
            attrs['namespace_id'] = XrefID(Namespace, smry['namespace']['id'])
        except KeyError:
            attrs['namespace_id'] = None

        imprt = smry['latest_import']
        if imprt:
            attrs['last_import_created_date'] = _parse_date(
                    imprt['created'], may_be_none=False)
            attrs['last_import_modified_date'] = _parse_date(
                    imprt['modified'], may_be_none=False)
            attrs['last_import_started_date'] = _parse_date(
                    imprt['started'], may_be_none=True)
            attrs['last_import_finished_date'] = _parse_date(
                    imprt['finished'], may_be_none=True)
            assert imprt['state']
            attrs['last_import_status'] = imprt['state']
        else:
            attrs['last_import_created_date'] = None
            attrs['last_import_modified_date'] = None
            attrs['last_import_started_date'] = None
            attrs['last_import_finished_date'] = None
            attrs['last_import_status'] = None

        _extend_with_dates(attrs, json)

        return Repository(**attrs)


@attr.s(auto_attribs=True)
class Platform(GalaxyEntity):
    """Model for a platform."""

    name: str
    version: str

    @property
    def id(self) -> str:
        return f'{self.name}:{self.version}'

    @classmethod
    def from_galaxy_json(cls, json: Dict[str, Any]) -> Platform:  # type: ignore[misc]
        return Platform(name=json['name'], version=json['release'])


@attr.s(auto_attribs=True)
class RoleVersion(GalaxyEntity):
    """Model for a role version."""

    entity_id: int
    version: str
    release_date: Optional[pendulum.DateTime]

    @property
    def id(self) -> str:
        return str(self.entity_id)

    @classmethod
    def from_galaxy_json(cls, json: Dict[str, Any]) -> RoleVersion:  # type: ignore[misc]
        attrs = {
            'entity_id': json['id'],
            'version': json['name'],
            'release_date': _parse_date(json.get('release_date'), may_be_none=True)
        }

        return RoleVersion(**attrs)


def _fuzzy_match(src: str, target: Optional[str]) -> None:
    assert src == target or not src and target is None, f'{src} vs {target}'

@attr.s(auto_attribs=True)
class Role(GalaxyEntity):
    """Model for Galaxy role."""

    entity_id: int
    canonical_id: str  # <namespace>.<role_name>
    name: str
    username: Optional[str]
    description: Optional[str]
    company: Optional[str]
    is_valid: bool
    license: str
    min_ansible_version: Optional[str]
    role_type: Optional[str]
    dependencies: List[str]
    supported_platforms: List[Platform]
    download_count: int
    download_rank: Optional[float]
    tags: List[str]
    versions: List[RoleVersion]

    commit_sha: str
    commit_message: str

    namespace_id: XrefID
    provider_namespace_id: XrefID
    repository_id: XrefID

    creation_date: pendulum.DateTime
    modification_date: pendulum.DateTime
    imported_date: Optional[pendulum.DateTime]

    @property
    def id(self) -> str:
        return str(self.entity_id)

    @classmethod
    def from_galaxy_json(  # type: ignore[misc, override]
            cls, json: Dict[str, Any], repos: Dict[int, Repository],
            role_pages: Dict[str, Any]
    ) -> Role:
        # Sanity checks
        assert json['active']
        assert not json['summary_fields']['videos']

        smry = json['summary_fields']
        linked_repo = repos[smry['repository']['id']]
        assert json['github_branch'] == linked_repo.import_branch
        built_gh_url = f'https://github.com/{json["github_user"]}/{json["github_repo"]}'
        assert built_gh_url == linked_repo.github_url
        _fuzzy_match(json['travis_status_url'], linked_repo.travis_ci_status_badge_url)

        role = role_pages.get(str(json['id']))
        if role is not None:
            assert role['readme'] == linked_repo.readme


        attrs: Dict[str, Any] = {}

        attrs['entity_id'] = json['id']
        attrs['canonical_id'] = smry['namespace']['name'] + '.' + json['name']
        attrs['name'] = json['name']
        attrs['username'] = json.get('username')
        attrs['description'] = json['description'] or None
        attrs['company'] = json['company'] or None
        attrs['is_valid'] = json['is_valid']
        attrs['license'] = json['license']
        attrs['min_ansible_version'] = json['min_ansible_version'] or None
        attrs['role_type'] = json['role_type'] or None
        attrs['dependencies'] = smry['dependencies']
        attrs['supported_platforms'] = [
                Platform.from_galaxy_json(pfrm) for pfrm in smry['platforms']]
        attrs['download_count'] = json['download_count']
        attrs['download_rank'] = json.get('download_rank')
        attrs['tags'] = smry['tags']
        attrs['versions'] = [
                RoleVersion.from_galaxy_json(v) for v in smry['versions']]

        attrs['commit_sha'] = json['commit']
        attrs['commit_message'] = json['commit_message']

        attrs['namespace_id'] = XrefID(Namespace, smry['namespace']['id'])
        attrs['provider_namespace_id'] = XrefID(
                    ProviderNamespace, smry['provider_namespace']['id'])
        attrs['repository_id'] = XrefID(Repository, smry['repository']['id'])

        _extend_with_dates(attrs, json)
        attrs['imported_date'] = _parse_date(json['imported'], may_be_none=True)

        return Role(**attrs)


@attr.s(auto_attribs=True)
class Tag(GalaxyEntity):
    """Model for Galaxy tags."""

    entity_id: int
    name: str

    creation_date: pendulum.DateTime
    modification_date: pendulum.DateTime

    @property
    def id(self) -> str:
        return str(self.entity_id)

    @classmethod
    def from_galaxy_json(cls, json: Dict[str, Any]) -> Tag:  # type: ignore[misc]
        # Sanity checks
        assert json['active']  # Not including it, always True
        assert not json['related']
        assert not json['summary_fields']
        assert json['url'] == f'/api/v1/tags/{json["id"]}/'
        assert isinstance(json['id'], int)
        assert isinstance(json['name'], str)

        attrs: Dict[str, Any] = {}

        attrs['entity_id'] = json['id']
        attrs['name'] = json['name']

        _extend_with_dates(attrs, json)

        return Tag(**attrs)


@attr.s(auto_attribs=True)
class User(GalaxyEntity):
    """Model for Galaxy users."""

    entity_id: int
    username: str
    full_name: Optional[str]
    is_staff: bool
    date_joined: pendulum.DateTime
    avatar_url: Optional[str]
    starred_repositories: List[str]  # GitHub links
    subscribed_repositories: List[str]  # GitHub links

    creation_date: pendulum.DateTime
    modification_date: Optional[pendulum.DateTime]

    @property
    def id(self) -> str:
        return str(self.entity_id)

    @classmethod
    def from_galaxy_json(cls, json: Dict[str, Any]) -> User:  # type: ignore[misc, override]
        # Sanity checks
        assert json['active']  # Not including it, always True
        assert json['url'] == f'/api/v1/users/{json["id"]}/'

        attrs: Dict[str, Any] = {}

        attrs['entity_id'] = json['id']
        attrs['username'] = json['username']
        attrs['full_name'] = json['full_name'] or None
        assert attrs['full_name'] != ''
        attrs['date_joined'] = _parse_date(json['date_joined'], False)
        attrs['avatar_url'] = json['avatar_url'] or None
        attrs['is_staff'] = json['staff']

        attrs['starred_repositories'] = [
                _create_gh_link(d['github_user'], d['github_repo'])
                for d in json['summary_fields']['starred']]
        attrs['subscribed_repositories'] = [
                _create_gh_link(d['github_user'], d['github_repo'])
                for d in json['summary_fields']['subscriptions']]

        _extend_with_dates(attrs, json, mod_may_be_none=True)

        return User(**attrs)



def _create_all(
        json_entities: Collection[Any],
        entity_type: Type[_EntityType],
        **extra_args: Any
) -> Dict[int, _EntityType]:
    entities = [
            entity_type.from_galaxy_json(entity_json, **extra_args)  # type: ignore[call-arg]
            for entity_json in json_entities]
    return {e.entity_id: e for e in entities}  # type: ignore[attr-defined]

@attr.s(auto_attribs=True)
class GalaxyMetadata(Model):
    """Model for Galaxy metadata."""

    community_surveys: Dict[int, CommunitySurvey]
    content: Dict[int, Content]
    namespaces: Dict[int, Namespace]
    provider_namespaces: Dict[int, ProviderNamespace]
    repositories: Dict[int, Repository]
    roles: Dict[int, Role]
    tags: Dict[int, Tag]
    # users: Dict[int, User]


    @classmethod
    def from_metamap(cls, meta_map: MetadataMap) -> GalaxyMetadata:
        attrs: Dict[str, Dict[int, GalaxyEntity]] = {}
        attrs['community_surveys'] = _create_all(
                meta_map.community_surveys.values(), CommunitySurvey)
        attrs['content'] = _create_all(
                meta_map.content.values(), Content)
        attrs['namespaces'] = _create_all(
                meta_map.namespaces.values(), Namespace)
        attrs['provider_namespaces'] = _create_all(
                meta_map.provider_namespaces.values(), ProviderNamespace)
        attrs['repositories'] = _create_all(
                meta_map.repositories.values(), Repository, surveys=attrs['community_surveys'])
        attrs['tags'] = _create_all(meta_map.tags.values(), Tag)
        # attrs['users'] = _create_all(meta_map.users.values(), User)

        roles = _create_all(
                meta_map.role_search.values(), Role, repos=attrs['repositories'],
                role_pages=meta_map.roles)
        # Roles not in search page but in roles pages
        leftover_roles = [
                r for r in meta_map.roles.values()
                if r['id'] not in roles]
        roles.update(_create_all(
                leftover_roles, Role, repos=attrs['repositories'],
                role_pages=meta_map.roles))

        attrs['roles'] = roles  # type: ignore[assignment]
        return cls(**attrs)  # type: ignore[arg-type]

    @property
    def id(self) -> str:
        """Get the ID."""
        return 'dummy'  # Unused

    def _dump_dict(self, dct: Mapping[int, GalaxyEntity], file: Path) -> None:
        file.write_text(
                yaml.dump(CONVERTER.unstructure(dct), sort_keys=True, Dumper=Dumper))

    def dump(self, directory: Path) -> Path:
        self._dump_dict(
                self.community_surveys, directory / 'CommunitySurveys.yaml')
        self._dump_dict(
                self.content, directory / 'Content.yaml')
        self._dump_dict(
                self.namespaces, directory / 'Namespaces.yaml')
        self._dump_dict(
                self.provider_namespaces, directory / 'ProviderNamespaces.yaml')
        self._dump_dict(
                self.repositories, directory / 'Repositories.yaml')
        self._dump_dict(
                self.roles, directory / 'Roles.yaml')
        self._dump_dict(
                self.tags, directory / 'Tags.yaml')
        # self._dump_dict(
        #        self.users, directory / 'Users.yaml')

        idx = {
            'CommunitySurvey': 'CommunitySurveys.yaml',
            'Content': 'Content.yaml',
            'Namespace': 'Namespaces.yaml',
            'ProviderNamespace': 'ProviderNamespaces.yaml',
            'Repository': 'Repositories.yaml',
            'Role': 'Roles.yaml',
            'Tag': 'Tags.yaml',
            # 'User': 'Users.yaml',
        }
        idx_path = (directory / 'index.yaml')
        idx_path.write_text(yaml.dump(idx))
        return idx_path

    @classmethod
    def _load_dict(cls, path: Path, entity_type: Type[_EntityType]) -> Dict[int, _EntityType]:
        return CONVERTER.structure(
                yaml.load(path.read_text(), Loader=Loader),
                Dict[int, entity_type])  # type: ignore[valid-type]

    @classmethod
    def load(cls, id: str, direc: Path) -> 'GalaxyMetadata':
        idx = yaml.safe_load((direc / 'index.yaml').read_text())
        print('loaded')

        attrs: Dict[str, Any] = {}
        for etype, efile in idx.items():
            etype_attr = capitalized_to_underscored(efile.replace('.yaml', ''))
            attrs[etype_attr] = cls._load_dict(
                    direc / efile, globals()[etype])

        return cls(**attrs)

    @classmethod
    def lazy_load(cls, id: str, direc: Path) -> 'GalaxyMetadata':
        idx = yaml.safe_load((direc / 'index.yaml').read_text())

        try:
            attrs: Dict[str, Any] = {}
            for etype_str, efile in idx.items():
                etype_attr = capitalized_to_underscored(efile.replace('.yaml', ''))
                if etype_attr == 'users':
                    continue
                attrs[etype_attr] = _LazyDict(
                        direc / efile, globals()[etype_str])
        except Exception as e:
            print(e)
            raise

        return cls(**attrs)


class _LazyDict(Mapping[int, _EntityType]):
    def __init__(self, path: Path, etype: Type[_EntityType]) -> None:
        self._storage: Optional[Dict[int, _EntityType]] = None
        self._file_path = path
        self._etype = etype


    def _ensure_loaded(self) -> None:
        if self._storage is None:
            self._storage = CONVERTER.structure(
                    yaml.load(self._file_path.read_text(), Loader=Loader),
                    Dict[int, self._etype])  # type: ignore[name-defined]


    def __len__(self) -> int:
        self._ensure_loaded()
        assert self._storage is not None
        return len(self._storage)

    def __getitem__(self, key: int) -> _EntityType:
        self._ensure_loaded()
        assert self._storage is not None
        return self._storage[key]

    def __iter__(self) -> Iterator[int]:
        self._ensure_loaded()
        assert self._storage is not None
        return iter(self._storage)
