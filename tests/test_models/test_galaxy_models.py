"""Tests for models.galaxy."""
from typing import TextIO

import pytest

from models.galaxy import GalaxyRole


@pytest.mark.parametrize(
        'resource', ['galaxy_search_role_test.json'], indirect=['resource'])
def test_role_model(resource: TextIO) -> None:
    """Test Galaxy Role models."""
    json_str = resource.read()
    role = GalaxyRole.from_json_str(json_str)

    assert role.id == '24559'
    assert role.name == 'sublimetext-3'
    assert role.github_user == '00willo'
    assert role.github_repo == 'ansible-role_sublimetext'
    assert role.download_count == 39


@pytest.mark.parametrize(
        'resource', ['galaxy_search_role_test.json'], indirect=['resource'])
def test_role_model_serialize(resource: TextIO) -> None:
    """Test serialization of Galaxy Role models."""
    json_str = resource.read()
    role = GalaxyRole.from_json_str(json_str)

    assert GalaxyRole.from_json_str(role.to_json_str()) == role
    assert GalaxyRole.from_json_obj(role.to_json_obj()) == role
