import os
import sys
import subprocess
import asyncio
import ast
import libcst as cst
from pathlib import Path
from typing import List, Optional, Dict, Any, Union

class DjangoProject:
    def __init__(self, root_path: str = "."):
        self.root_path = Path(root_path).resolve()
        self.manage_py = self._find_manage_py()
        self.settings_module = self._find_settings_module()
        self.project_name = self._get_project_name()

    def _find_manage_py(self) -> Optional[Path]:
        for path in [self.root_path] + list(self.root_path.parents):
            manage_py = path / "manage.py"
            if manage_py.exists():
                return manage_py
        return None

    def _find_settings_module(self) -> Optional[str]:
        if not self.manage_py:
            return None

        # Try to find settings by reading manage.py
        try:
            content = self.manage_py.read_text()
            for line in content.splitlines():
                if "DJANGO_SETTINGS_MODULE" in line and "=" in line:
                    module = line.split("=")[1].strip().strip("'\"").strip()
                    if module:
                        return module
        except Exception:
            pass

        # Fallback: look for settings.py in subdirectories
        for p in self.manage_py.parent.glob("*/settings.py"):
            return f"{p.parent.name}.settings"

        return None

    def _get_project_name(self) -> str:
        if self.settings_module:
            return self.settings_module.split('.')[0]
        if self.manage_py:
            return self.manage_py.parent.name
        return "Unknown"

    def is_valid(self) -> bool:
        return self.manage_py is not None and self.manage_py.exists()

    def get_settings_path(self) -> Optional[Path]:
        if not self.settings_module or not self.manage_py:
            return None

        parts = self.settings_module.split('.')
        path = self.manage_py.parent.joinpath(*parts).with_suffix('.py')
        if path.exists():
            return path

        # Handle cases where settings might be a package
        pkg_path = self.manage_py.parent.joinpath(*parts, "__init__.py")
        if pkg_path.exists():
            return pkg_path

        return None

class CommandRunner:
    def __init__(self, project: DjangoProject):
        self.project = project

    async def run(self, command: str, *args: str, callback=None) -> subprocess.CompletedProcess:
        if not self.project.is_valid():
            raise ValueError("Invalid Django project")

        cmd = [sys.executable, str(self.project.manage_py), command] + list(args)

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(self.project.manage_py.parent)
        )

        async def _read_stream(stream, is_stderr=False):
            while True:
                line = await stream.readline()
                if not line:
                    break
                decoded_line = line.decode().rstrip()
                if callback:
                    if asyncio.iscoroutinefunction(callback):
                        await callback(decoded_line, is_stderr)
                    else:
                        callback(decoded_line, is_stderr)

        stdout_lines = []
        stderr_lines = []

        async def capture_stdout(line, is_err):
            if not is_err: stdout_lines.append(line)
            if callback: await callback(line, is_err) if asyncio.iscoroutinefunction(callback) else callback(line, is_err)

        async def capture_stderr(line, is_err):
            if is_err: stderr_lines.append(line)
            if callback: await callback(line, is_err) if asyncio.iscoroutinefunction(callback) else callback(line, is_err)

        # Re-implementing to capture and stream
        # This is a bit tricky with readline.
        # Let's simplify for now and use communicate if no callback,
        # but if callback we stream.

        if callback:
            await asyncio.gather(
                _read_stream(process.stdout, False),
                _read_stream(process.stderr, True)
            )
            returncode = await process.wait()
            return subprocess.CompletedProcess(args=cmd, returncode=returncode, stdout="", stderr="")
        else:
            stdout, stderr = await process.communicate()
            return subprocess.CompletedProcess(
                args=cmd,
                returncode=process.returncode,
                stdout=stdout.decode() if stdout else "",
                stderr=stderr.decode() if stderr else ""
            )

    async def get_git_status(self) -> str:
        try:
            cmd = ["git", "status", "--short"]
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(self.project.root_path)
            )
            stdout, _ = await process.communicate()
            return stdout.decode()
        except Exception:
            return "Git not found or not a repo"

    def discover_custom_commands(self) -> List[str]:
        commands = []
        if not self.project.manage_py:
            return []

        project_dir = self.project.manage_py.parent
        for app_dir in project_dir.glob("*"):
            if app_dir.is_dir() and (app_dir / "__init__.py").exists():
                commands_dir = app_dir / "management" / "commands"
                if commands_dir.exists():
                    for cmd_file in commands_dir.glob("*.py"):
                        if cmd_file.name != "__init__.py":
                            commands.append(cmd_file.stem)
        return sorted(list(set(commands)))

class SettingsManager:
    def __init__(self, project: DjangoProject):
        self.project = project
        self.settings_path = project.get_settings_path()

    def get_setting(self, key: str) -> Any:
        if not self.settings_path: return None
        content = self.settings_path.read_text()
        tree = ast.parse(content)
        for node in tree.body:
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == key:
                        try:
                            return ast.literal_eval(node.value)
                        except Exception:
                            return None
        return None

    def update_setting(self, key: str, value: Any):
        if not self.settings_path: return
        content = self.settings_path.read_text()
        tree = cst.parse_module(content)

        class UpdateTransformer(cst.CSTTransformer):
            def __init__(self, key, value):
                self.key = key
                self.value = value
                self.found = False

            def leave_Assign(self, original_node: cst.Assign, updated_node: cst.Assign) -> cst.Assign:
                for target in original_node.targets:
                    if isinstance(target.target, cst.Name) and target.target.value == self.key:
                        self.found = True
                        new_value = cst.parse_expression(repr(self.value))
                        return updated_node.with_changes(value=new_value)
                return updated_node

        transformer = UpdateTransformer(key, value)
        modified_tree = tree.visit(transformer)

        if not transformer.found:
            new_assign = cst.parse_statement(f"{key} = {repr(value)}\n")
            modified_tree = modified_tree.with_changes(
                body=list(modified_tree.body) + [new_assign]
            )

        self.settings_path.write_text(modified_tree.code)

    def add_to_list(self, key: str, item: str):
        current_list = self.get_setting(key) or []
        if isinstance(current_list, list) and item not in current_list:
            current_list.append(item)
            self.update_setting(key, current_list)

    def remove_from_list(self, key: str, item: str):
        current_list = self.get_setting(key)
        if isinstance(current_list, list) and item in current_list:
            current_list.remove(item)
            self.update_setting(key, current_list)

class DependencyManager:
    def __init__(self, project: DjangoProject):
        self.project = project
        self.root = project.root_path

    async def get_packages(self) -> List[Dict[str, str]]:
        cmd = [sys.executable, "-m", "pip", "list", "--format=json"]
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, _ = await process.communicate()
        if stdout:
            import json
            return json.loads(stdout)
        return []

    async def install_package(self, package: str) -> bool:
        cmd = [sys.executable, "-m", "pip", "install", package]
        process = await asyncio.create_subprocess_exec(*cmd)
        await process.wait()
        return process.returncode == 0

    async def uninstall_package(self, package: str) -> bool:
        cmd = [sys.executable, "-m", "pip", "uninstall", "-y", package]
        process = await asyncio.create_subprocess_exec(*cmd)
        await process.wait()
        return process.returncode == 0

    async def run_audit(self) -> str:
        cmd = [sys.executable, "-m", "pip_audit"]
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()
        return stdout.decode() + stderr.decode()

    def create_venv(self, name: str = ".venv"):
        import venv
        venv.create(self.root / name, with_pip=True)

class ProjectAnalyzer:
    def __init__(self, project: DjangoProject):
        self.project = project

    def get_project_structure(self) -> Dict[str, Any]:
        structure = {
            "apps": [],
            "models_count": 0,
            "project_name": self.project.project_name,
            "django_version": "Unknown"
        }

        # Setup Django to use internal registry
        try:
            os.environ.setdefault("DJANGO_SETTINGS_MODULE", self.project.settings_module)
            import django
            sys.path.insert(0, str(self.project.manage_py.parent))
            django.setup()

            from django.apps import apps
            from django.conf import settings

            structure["django_version"] = django.get_version()

            for app_config in apps.get_app_configs():
                # Only include local apps (heuristically)
                if not app_config.name.startswith('django.'):
                    app_info = {
                        "name": app_config.name,
                        "label": app_config.label,
                        "path": app_config.path,
                        "models": []
                    }
                    for model in app_config.get_models():
                        app_info["models"].append(model.__name__)
                        structure["models_count"] += 1
                    structure["apps"].append(app_info)
        except Exception as e:
            structure["error"] = str(e)

        return structure

class SecurityScanner:
    def __init__(self, project: DjangoProject):
        self.project = project
        self.manager = SettingsManager(project)

    def scan(self) -> Dict[str, Any]:
        report = {
            "score": 100,
            "findings": []
        }

        checks = [
            ("DEBUG", False, "DEBUG should be False in production", 20),
            ("SECRET_KEY", None, "SECRET_KEY should not be empty", 30),
            ("ALLOWED_HOSTS", None, "ALLOWED_HOSTS should not be empty", 10),
            ("DATABASES", None, "Ensure database passwords are secure", 10),
            ("SECURE_SSL_REDIRECT", True, "SECURE_SSL_REDIRECT should be True", 5),
            ("SESSION_COOKIE_SECURE", True, "SESSION_COOKIE_SECURE should be True", 5),
            ("CSRF_COOKIE_SECURE", True, "CSRF_COOKIE_SECURE should be True", 5),
        ]

        for key, expected, msg, weight in checks:
            val = self.manager.get_setting(key)
            if key == "SECRET_KEY":
                if not val or len(val) < 10:
                    report["findings"].append({"key": key, "msg": msg, "severity": "High"})
                    report["score"] -= weight
            elif key == "ALLOWED_HOSTS":
                if not val or "*" in val:
                    report["findings"].append({"key": key, "msg": msg, "severity": "Medium"})
                    report["score"] -= weight
            elif val != expected:
                report["findings"].append({"key": key, "msg": msg, "severity": "Info" if weight < 10 else "High"})
                report["score"] -= weight

        report["score"] = max(0, report["score"])
        return report

class Plugin:
    def __init__(self, name: str):
        self.name = name

    async def on_event(self, event: str, **kwargs):
        pass

class PluginManager:
    def __init__(self):
        self.plugins: List[Plugin] = []
        self.hooks: Dict[str, List[Any]] = {}

    def register(self, plugin: Plugin):
        self.plugins.append(plugin)
        print(f"Registered plugin: {plugin.name}")

    async def emit(self, event: str, **kwargs):
        for plugin in self.plugins:
            await plugin.on_event(event, **kwargs)

        if event in self.hooks:
            for hook in self.hooks[event]:
                if asyncio.iscoroutinefunction(hook):
                    await hook(**kwargs)
                else:
                    hook(**kwargs)

    def add_hook(self, event: str, callback: Any):
        if event not in self.hooks:
            self.hooks[event] = []
        self.hooks[event].append(callback)
