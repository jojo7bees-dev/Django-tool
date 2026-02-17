import pytest
from django_tui.engine import DjangoProject

def test_project_discovery(tmp_path):
    manage_py = tmp_path / "manage.py"
    manage_py.touch()
    project = DjangoProject(str(tmp_path))
    assert project.is_valid()
    assert project.project_name == tmp_path.name

def test_project_invalid():
    project = DjangoProject("non_existent_folder")
    assert not project.is_valid()
