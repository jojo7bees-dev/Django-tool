import pytest
from django_tui.engine import DjangoProject

def test_project_discovery():
    # This assumes test_project exists from previous steps
    project = DjangoProject("test_project")
    assert project.is_valid()
    assert project.project_name == "test_project"

def test_project_invalid():
    project = DjangoProject("non_existent_folder")
    assert not project.is_valid()
