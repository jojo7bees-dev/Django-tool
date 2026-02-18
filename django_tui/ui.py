from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.widgets import Header, Footer, Static, ListView, ListItem, Label, Button, DataTable, Input, Log, Tree
from textual.screen import Screen
from .engine import DjangoProject, ProjectAnalyzer, SecurityScanner, CommandRunner, SettingsManager, DependencyManager

class CommandRunnerScreen(Screen):
    def __init__(self, project: DjangoProject):
        super().__init__()
        self.project = project
        self.runner = CommandRunner(project)

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal():
            with Vertical(id="sidebar"):
                yield Label("Commands")
                yield ListView(
                    ListItem(Label("check"), id="cmd-check"),
                    ListItem(Label("makemigrations"), id="cmd-makemigrations"),
                    ListItem(Label("migrate"), id="cmd-migrate"),
                    ListItem(Label("runserver"), id="cmd-runserver"),
                    ListItem(Label("shell"), id="cmd-shell"),
                    id="command-list"
                )
            with Vertical(id="main-area"):
                yield Label("Arguments:")
                yield Input(placeholder="e.g. --noinput", id="cmd-args")
                yield Button("Run Command", variant="success", id="run-btn")
                yield Log(id="cmd-log")
        yield Footer()

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "run-btn":
            command_list = self.query_one("#command-list", ListView)
            selected = command_list.highlighted_child
            if selected:
                command = str(selected.query_one(Label).renderable)
                args_input = self.query_one("#cmd-args", Input).value
                args = args_input.split() if args_input else []

                log = self.query_one("#cmd-log", Log)
                log.write(f"> Running: python manage.py {command} {' '.join(args)}\n")

                def log_callback(line, is_err):
                    log.write(f"{'[ERR] ' if is_err else ''}{line}\n")

                await self.runner.run(command, *args, callback=log_callback)

class SettingsEditorScreen(Screen):
    def __init__(self, project: DjangoProject):
        super().__init__()
        self.project = project
        self.manager = SettingsManager(project)

    def compose(self) -> ComposeResult:
        yield Header()
        with Container(id="settings-container"):
            with Horizontal(classes="settings-header"):
                yield Label("Settings Editor")
                yield Button("Undo Last Change", id="btn-undo-settings", variant="warning")
            profiles = self.project.discover_profiles()
            if profiles:
                yield Label(f"Detected Profiles: {', '.join(profiles)}")
            yield Horizontal(
                Label("DEBUG:", id="label-debug"),
                Button("Toggle", id="toggle-debug"),
                Static(str(self.manager.get_setting("DEBUG")), id="val-debug")
            )
            yield Label("ALLOWED_HOSTS:")
            yield Input(value=str(self.manager.get_setting("ALLOWED_HOSTS")), id="input-hosts")
            yield Button("Save Hosts", id="save-hosts")

            yield Label("INSTALLED_APPS:")
            self.apps_table = DataTable(id="apps-table")
            yield self.apps_table

            yield Label("Add App:")
            yield Horizontal(
                Input(placeholder="app_name", id="new-app-name"),
                Button("Add", id="add-app-btn")
            )

            yield Label("MIDDLEWARE:")
            self.middleware_table = DataTable(id="middleware-table")
            yield self.middleware_table

            yield Label("Add Middleware:")
            yield Horizontal(
                Input(placeholder="middleware.class.Path", id="new-middleware"),
                Button("Add", id="add-middleware-btn")
            )

            yield Label("DATABASES (Default):")
            db = self.manager.get_setting("DATABASES") or {}
            default_db = db.get("default", {})
            yield Static(f"Engine: {default_db.get('ENGINE')}\nName: {default_db.get('NAME')}", classes="db-info")

        yield Footer()

    def on_mount(self) -> None:
        # Apps Table
        table = self.query_one("#apps-table", DataTable)
        table.add_columns("App Name")
        apps = self.manager.get_setting("INSTALLED_APPS") or []
        for app in apps:
            table.add_row(app)

        # Middleware Table
        m_table = self.query_one("#middleware-table", DataTable)
        m_table.add_columns("Middleware Path")
        mws = self.manager.get_setting("MIDDLEWARE") or []
        for mw in mws:
            m_table.add_row(mw)

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "toggle-debug":
            current = self.manager.get_setting("DEBUG")
            new_val = not current
            self.manager.update_setting("DEBUG", new_val)
            self.query_one("#val-debug", Static).update(str(new_val))
        elif event.button.id == "save-hosts":
            val = self.query_one("#input-hosts", Input).value
            try:
                # Basic eval for list/string
                import ast
                hosts = ast.literal_eval(val)
                self.manager.update_setting("ALLOWED_HOSTS", hosts)
                self.notify("Saved ALLOWED_HOSTS")
            except Exception as e:
                self.notify(f"Error: {e}", severity="error")
        elif event.button.id == "add-app-btn":
            app_name = self.query_one("#new-app-name", Input).value
            if app_name:
                self.manager.add_to_list("INSTALLED_APPS", app_name)
                self.query_one("#apps-table", DataTable).add_row(app_name)
                self.query_one("#new-app-name", Input).value = ""
                self.notify(f"Added {app_name}")
        elif event.button.id == "add-middleware-btn":
            mw_path = self.query_one("#new-middleware", Input).value
            if mw_path:
                self.manager.add_to_list("MIDDLEWARE", mw_path)
                self.query_one("#middleware-table", DataTable).add_row(mw_path)
                self.query_one("#new-middleware", Input).value = ""
                self.notify(f"Added Middleware: {mw_path}")
        elif event.button.id == "btn-undo-settings":
            if self.manager.undo_last_change():
                self.notify("Undo successful! Please refresh screen to see changes.")
            else:
                self.notify("No backup found to undo.", severity="error")

class MigrationManagerScreen(Screen):
    def __init__(self, project: DjangoProject):
        super().__init__()
        self.project = project
        self.runner = CommandRunner(project)

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="migration-container"):
            yield Label("Migration Manager")
            with Horizontal():
                yield Button("Show Migrations", id="btn-show-migrations")
                yield Button("Make Migrations", id="btn-make-migrations")
                yield Button("Migrate", variant="primary", id="btn-migrate")

            yield Label("Backup & Restore:")
            with Horizontal():
                yield Button("Backup Data (JSON)", id="btn-dumpdata")
                yield Button("Restore Data (JSON)", id="btn-loaddata")
                yield Button("SQLite DB Backup", id="btn-sqlite-backup")

            yield Label("SQL Preview (app_label migration_name):")
            yield Horizontal(
                Input(placeholder="e.g. auth 0001", id="input-sqlmigrate"),
                Button("View SQL", id="btn-sqlmigrate")
            )
            yield Log(id="migration-log")
        yield Footer()

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        log = self.query_one("#migration-log", Log)
        if event.button.id == "btn-show-migrations":
            log.write("> python manage.py showmigrations\n")
            res = await self.runner.run("showmigrations")
            log.write(res.stdout + res.stderr + "\n")
        elif event.button.id == "btn-make-migrations":
            log.write("> python manage.py makemigrations\n")
            await self.runner.run("makemigrations", callback=lambda line, err: log.write(line + "\n"))
        elif event.button.id == "btn-migrate":
            log.write("> python manage.py migrate\n")
            await self.runner.run("migrate", callback=lambda line, err: log.write(line + "\n"))
        elif event.button.id == "btn-sqlmigrate":
            val = self.query_one("#input-sqlmigrate", Input).value
            if val:
                args = val.split()
                if len(args) >= 2:
                    log.write(f"> python manage.py sqlmigrate {args[0]} {args[1]}\n")
                    res = await self.runner.run("sqlmigrate", *args)
                    log.write(res.stdout + res.stderr + "\n")
                else:
                    self.notify("Format: app_label migration_name", severity="warning")
        elif event.button.id == "btn-dumpdata":
            log.write("> python manage.py dumpdata --indent 2 > backup.json\n")
            # We'll run it and capture output to write to file manually for safety
            res = await self.runner.run("dumpdata", "--indent", "2")
            if res.returncode == 0:
                (self.project.root_path / "backup.json").write_text(res.stdout)
                log.write("Backup saved to backup.json\n")
            else:
                log.write(f"Error: {res.stderr}\n")
        elif event.button.id == "btn-loaddata":
            if (self.project.root_path / "backup.json").exists():
                log.write("> python manage.py loaddata backup.json\n")
                await self.runner.run("loaddata", "backup.json", callback=lambda l, e: log.write(l + "\n"))
            else:
                self.notify("backup.json not found", severity="error")
        elif event.button.id == "btn-sqlite-backup":
            import shutil
            db_path = self.project.root_path / "db.sqlite3"
            if db_path.exists():
                shutil.copy(db_path, str(db_path) + ".bak")
                log.write("db.sqlite3 backed up to db.sqlite3.bak\n")
            else:
                self.notify("db.sqlite3 not found", severity="error")

class DependencyScreen(Screen):
    def __init__(self, project: DjangoProject):
        super().__init__()
        self.project = project
        self.manager = DependencyManager(project)

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal():
            with Vertical(id="dep-sidebar"):
                yield Button("Refresh List", id="btn-refresh-deps")
                yield Button("Run Security Audit", id="btn-audit")
                yield Label("Install Package:")
                yield Input(placeholder="package-name", id="input-install")
                yield Button("Install", id="btn-install")
            with Vertical(id="dep-main"):
                yield DataTable(id="deps-table")
                yield Log(id="dep-log")
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#deps-table", DataTable)
        table.add_columns("Package", "Version")
        self.run_worker(self.refresh_packages())

    async def refresh_packages(self):
        table = self.query_one("#deps-table", DataTable)
        table.clear()
        packages = await self.manager.get_packages()
        for pkg in packages:
            table.add_row(pkg['name'], pkg['version'])

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        log = self.query_one("#dep-log", Log)
        if event.button.id == "btn-refresh-deps":
            await self.refresh_packages()
        elif event.button.id == "btn-audit":
            log.write("> Running pip-audit...\n")
            res = await self.manager.run_audit()
            log.write(res + "\n")
        elif event.button.id == "btn-install":
            pkg = self.query_one("#input-install", Input).value
            if pkg:
                log.write(f"> Installing {pkg}...\n")
                success = await self.manager.install_package(pkg)
                log.write("Success!\n" if success else "Failed!\n")
                await self.refresh_packages()

class ORMExplorerScreen(Screen):
    def __init__(self, project: DjangoProject):
        super().__init__()
        self.project = project
        self.runner = CommandRunner(project)
        self.analyzer = ProjectAnalyzer(project)
        self.offset = 0
        self.limit = 10

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal():
            with Vertical(id="orm-sidebar"):
                yield Label("Models")
                structure = self.analyzer.get_project_structure()
                items = []
                for app in structure.get('apps', []):
                    for model in app['models']:
                        model_name = model['name']
                        items.append(ListItem(Label(f"{app['label']}.{model_name}"), id=f"model-{model_name}"))
                yield ListView(*items, id="orm-model-list")

            with Vertical(id="orm-main"):
                yield Label("Query Builder")
                yield Input(placeholder="filter: e.g. id=1", id="orm-filter")
                yield Horizontal(
                    Input(placeholder="order_by", id="orm-order"),
                    Input(placeholder="limit", id="orm-limit", value="10"),
                    classes="orm-row"
                )
                with Horizontal(classes="orm-row"):
                    yield Button("Execute Query", variant="success", id="btn-orm-run")
                    yield Button("Prev", id="btn-orm-prev")
                    yield Button("Next", id="btn-orm-next")
                    yield Label("Offset: 0", id="lbl-orm-offset")
                yield DataTable(id="orm-results")
                yield Log(id="orm-log")
        yield Footer()

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id in ["btn-orm-run", "btn-orm-prev", "btn-orm-next"]:
            if event.button.id == "btn-orm-prev":
                self.offset = max(0, self.offset - self.limit)
            elif event.button.id == "btn-orm-next":
                self.offset += self.limit
            else:
                self.offset = 0 # Reset on new run
                try:
                    self.limit = int(self.query_one("#orm-limit", Input).value or 10)
                except:
                    self.limit = 10

            self.query_one("#lbl-orm-offset", Label).update(f"Offset: {self.offset}")

            model_list = self.query_one("#orm-model-list", ListView)
            selected = model_list.highlighted_child
            if not selected:
                self.notify("Please select a model first", severity="warning")
                return

            model_name = str(selected.query_one(Label).renderable)
            app_label, model_cls = model_name.split('.')

            filter_val = self.query_one("#orm-filter", Input).value
            order_val = self.query_one("#orm-order", Input).value
            limit_val = self.query_one("#orm-limit", Input).value

            log = self.query_one("#orm-log", Log)

            script = f"""
import django; django.setup()
from django.apps import apps
model = apps.get_model('{app_label}', '{model_cls}')
qs = model.objects
if "{filter_val}":
    try:
        f = eval("dict(" + "{filter_val}".replace("=", ":") + ")")
        qs = qs.filter(**f)
    except: pass
if "{order_val}": qs = qs.order_by("{order_val}")
limit = int("{self.limit}")
offset = int("{self.offset}")
results = list(qs.values()[offset:offset+limit])
import json; print(json.dumps(results, default=str))
"""
            res = await self.runner.run("shell", "-c", script)
            if res.returncode == 0:
                try:
                    import json
                    data = json.loads(res.stdout)
                    table = self.query_one("#orm-results", DataTable)
                    table.clear(columns=True)
                    if data:
                        table.add_columns(*data[0].keys())
                        for row in data:
                            table.add_row(*row.values())
                    else:
                        self.notify("No results found")
                except Exception as e:
                    log.write(f"Error parsing results: {e}\n{res.stdout}\n")
            else:
                log.write(f"Error: {res.stderr}\n")

class SchemaScreen(Screen):
    def __init__(self, project: DjangoProject):
        super().__init__()
        self.project = project
        self.analyzer = ProjectAnalyzer(project)

    def compose(self) -> ComposeResult:
        yield Header()
        yield Container(
            Label("Database Schema (Models & Fields)"),
            Tree("Project", id="schema-tree"),
            id="schema-container"
        )
        yield Footer()

    def on_mount(self) -> None:
        tree = self.query_one("#schema-tree", Tree)
        tree.root.expand()

        # We need more info from analyzer for fields
        os.environ.setdefault("DJANGO_SETTINGS_MODULE", self.project.settings_module)
        import django
        django.setup()
        from django.apps import apps

        for app_config in apps.get_app_configs():
            if not app_config.name.startswith('django.'):
                app_node = tree.root.add(app_config.label, expand=True)
                for model in app_config.get_models():
                    model_node = app_node.add(model.__name__)
                    fields_node = model_node.add("Fields")
                    for field in model._meta.get_fields():
                        if not field.is_relation:
                            fields_node.add(f"{field.name} ({field.get_internal_type()})")

                    rels_node = model_node.add("Relationships")
                    for field in model._meta.get_fields():
                        if field.is_relation:
                            rel_type = "M2M" if field.many_to_many else ("O2O" if field.one_to_one else "FK")
                            related = field.related_model.__name__ if field.related_model else "Self"
                            rels_node.add(f"{field.name} [{rel_type}] -> {related}")

class TestRunnerScreen(Screen):
    def __init__(self, project: DjangoProject):
        super().__init__()
        self.project = project
        self.runner = CommandRunner(project)

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="test-container"):
            yield Label("Test Runner (pytest)")
            with Horizontal(classes="row"):
                yield Button("Run All Tests", id="btn-run-tests")
                yield Button("Run with Coverage", id="btn-run-cov")
            yield Log(id="test-log")
        yield Footer()

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        log = self.query_one("#test-log", Log)
        if event.button.id == "btn-run-tests":
            log.write("> pytest\n")
            # Using sys.executable to ensure we use the same environment
            import sys
            cmd = [sys.executable, "-m", "pytest"]
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(self.project.root_path)
            )
            stdout, stderr = await process.communicate()
            log.write(stdout.decode() + stderr.decode() + "\n")
        elif event.button.id == "btn-run-cov":
            log.write("> pytest --cov\n")
            self.notify("Coverage requires pytest-cov to be installed", severity="info")

class AIAssistantScreen(Screen):
    def __init__(self, project: DjangoProject):
        super().__init__()
        self.project = project
        self.analyzer = ProjectAnalyzer(project)
        self.manager = SettingsManager(project)

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="ai-container"):
            yield Label("Django AI Assistant (Optimizations)")
            yield Button("Run Analysis", variant="primary", id="btn-ai-run")
            yield Log(id="ai-log")
        yield Footer()

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-ai-run":
            log = self.query_one("#ai-log", Log)
            log.clear()
            log.write("Analyzing project for optimizations...\n")

            suggestions = []

            # 1. DEBUG check
            debug = self.manager.get_setting("DEBUG")
            if debug:
                suggestions.append("⚠️ [CRITICAL] DEBUG is True. Consider setting to False for production.")

            # 2. Database Indexing
            structure = self.analyzer.get_project_structure()
            if structure.get("models_count", 0) > 10:
                suggestions.append("ℹ️ [PERFORMANCE] You have many models. Ensure database indexes are optimized.")

            # 3. Cache Check
            caches = self.manager.get_setting("CACHES")
            if not caches or "LocMemCache" in str(caches):
                suggestions.append("ℹ️ [SCALING] Using local memory cache. For production, consider Redis or Memcached.")

            # 4. Security Score
            scanner = SecurityScanner(self.project)
            report = scanner.scan()
            if report['score'] < 80:
                suggestions.append(f"⚠️ [SECURITY] Score is {report['score']}/100. Visit Security Scan for details.")

            if not suggestions:
                log.write("✅ Project looks well-optimized!\n")
            else:
                for s in suggestions:
                    log.write(s + "\n")

class RefactorScreen(Screen):
    def __init__(self, project: DjangoProject):
        super().__init__()
        self.project = project
        self.manager = SettingsManager(project)

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="refactor-container"):
            yield Label("Smart Refactor Tools (Experimental)")
            yield Label("Rename App:")
            yield Input(placeholder="old_name", id="old-app-name")
            yield Input(placeholder="new_name", id="new-app-name-ref")
            yield Button("Rename App", variant="warning", id="btn-rename-app")
            yield Log(id="refactor-log")
        yield Footer()

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-rename-app":
            old = self.query_one("#old-app-name", Input).value
            new = self.query_one("#new-app-name-ref", Input).value
            log = self.query_one("#refactor-log", Log)
            if old and new:
                log.write(f"Renaming {old} to {new}...\n")
                results = self.manager.rename_app(old, new)
                for r in results:
                    log.write(f"- {r}\n")
                self.notify("Rename operation finished. Check logs.")

class DevOpsScreen(Screen):
    def __init__(self, project: DjangoProject):
        super().__init__()
        self.project = project
        self.runner = CommandRunner(project)

    def compose(self) -> ComposeResult:
        yield Header()
        with Container(id="devops-container"):
            yield Label("DevOps & Server Management")
            with Horizontal(classes="devops-row"):
                yield Button("Generate Dockerfile", id="btn-gen-docker")
                yield Button("Generate Docker Compose", id="btn-gen-compose")

            yield Label("Development Server")
            with Horizontal(classes="devops-row"):
                yield Button("Run Server", id="btn-run-server")
                yield Button("Stop Server", id="btn-stop-server", variant="error")

            yield Label("Gunicorn / Uvicorn (Preview)")
            yield Static("gunicorn command: gunicorn project.wsgi")

            yield Log(id="devops-log")
        yield Footer()

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        from .utils import save_docker_configs
        log = self.query_one("#devops-log", Log)
        if event.button.id == "btn-gen-docker" or event.button.id == "btn-gen-compose":
            save_docker_configs(self.project.root_path, self.project.project_name)
            log.write("Dockerfile and docker-compose.yml generated!\n")
        elif event.button.id == "btn-run-server":
            log.write("Starting runserver in background...\n")
            # We use runner.run which waits, so for a real background server
            # we'd need a different approach, but for TUI we'll show it running.
            await self.runner.run("runserver", callback=lambda l, e: log.write(l + "\n"))

class Dashboard(Screen):
    def __init__(self, project: DjangoProject):
        super().__init__()
        self.project = project
        self.analyzer = ProjectAnalyzer(project)
        self.scanner = SecurityScanner(project)
        self.runner = CommandRunner(project)

    def compose(self) -> ComposeResult:
        structure = self.analyzer.get_project_structure()
        report = self.scanner.scan()

        yield Header()
        yield Container(
            Static(f"# Django Project: {self.project.project_name}", classes="title"),
            Horizontal(
                Static(f"Django Version: {structure.get('django_version', 'N/A')}", classes="box"),
                Static(f"Security Score: {report['score']}/100", classes="box"),
                Static(f"Models: {structure.get('models_count', 0)}", classes="box"),
            ),
            Static("## Git Status", classes="subtitle"),
            Static("Loading Git status...", id="git-status-box", classes="git-box"),
            Static("## Project Health & Security", classes="subtitle"),
            Static("Checking health...", id="health-box", classes="health-box"),
            Static("## Apps", classes="subtitle"),
            ListView(*[ListItem(Label(app['name'])) for app in structure.get('apps', [])]),
            id="dashboard-content"
        )
        yield Footer()

    def on_mount(self) -> None:
        self.run_worker(self.update_git_status())
        self.run_worker(self.update_health_status())

    async def update_git_status(self):
        status = await self.runner.get_git_status()
        self.query_one("#git-status-box", Static).update(status or "Git repository clean or no changes.")

    async def update_health_status(self):
        circles = self.analyzer.check_circular_dependencies()
        scanner = SecurityScanner(self.project)
        report = scanner.scan()

        status = []
        if circles:
            status.extend(circles)
        else:
            status.append("✅ No circular dependencies detected.")

        if report['findings']:
            status.append(f"⚠️ Found {len(report['findings'])} security concerns.")
        else:
            status.append("✅ Security settings look good.")

        self.query_one("#health-box", Static).update("\n".join(status))

class DjangoTUI(App):
    CSS = """
    Screen {
        background: #1e1e1e;
    }
    #sidebar {
        width: 30;
        border-right: tall $primary;
    }
    #main-area {
        padding: 1;
    }
    #cmd-log {
        height: 1fr;
        border: solid $accent;
        margin-top: 1;
    }
    #refactor-container {
        padding: 1;
    }
    #refactor-log {
        height: 1fr;
        border: solid $accent;
        margin-top: 1;
    }
    #ai-container {
        padding: 1;
    }
    #ai-log {
        height: 1fr;
        border: solid $accent;
        margin-top: 1;
    }
    #settings-container {
        padding: 2;
    }
    #settings-container Horizontal {
        height: auto;
        align: left middle;
        margin-bottom: 1;
    }
    .settings-header {
        height: auto;
        padding: 1;
        border-bottom: solid $primary;
    }
    #settings-container Label {
        width: 20;
    }
    .db-info {
        border: dashed white;
        padding: 1;
        margin-top: 1;
    }
    #migration-container {
        padding: 1;
    }
    #migration-log {
        height: 1fr;
        border: solid $accent;
        margin-top: 1;
    }
    #dep-sidebar {
        width: 30;
        padding: 1;
        border-right: tall $primary;
    }
    #dep-main {
        padding: 1;
    }
    #deps-table {
        height: 1fr;
    }
    #dep-log {
        height: 10;
        border: solid $accent;
    }
    #orm-container {
        padding: 2;
    }
    #orm-sidebar {
        width: 30;
        border-right: tall $primary;
    }
    #orm-main {
        padding: 1;
    }
    .orm-row {
        height: auto;
    }
    #orm-results {
        height: 1fr;
    }
    #orm-log {
        height: 5;
        border: solid $accent;
    }
    #schema-container {
        padding: 1;
    }
    #devops-container {
        padding: 1;
    }
    .devops-row {
        height: auto;
        margin-bottom: 1;
    }
    #devops-log {
        height: 1fr;
        border: solid $accent;
    }
    #test-container {
        padding: 1;
    }
    #test-log {
        height: 1fr;
        border: solid $accent;
        margin-top: 1;
    }
    .git-box {
        border: solid yellow;
        padding: 1;
        margin: 1;
        height: 5;
    }
    .health-box {
        border: solid orange;
        padding: 1;
        margin: 1;
        height: 7;
    }
    .box {
        border: solid green;
        padding: 1;
        margin: 1;
        width: 1fr;
    }
    .title {
        color: #4da6ff;
        margin: 1;
    }
    .subtitle {
        color: #ffcc00;
        margin: 1;
    }
    #dashboard-content {
        padding: 1;
    }
    """

    def __init__(self, project_path: str = "."):
        super().__init__()
        self.project = DjangoProject(project_path)

    BINDINGS = [
        ("d", "switch_screen('dashboard')", "Dashboard"),
        ("c", "switch_screen('commands')", "Commands"),
        ("s", "switch_screen('settings')", "Settings"),
        ("m", "switch_screen('migrations')", "Migrations"),
        ("p", "switch_screen('dependencies')", "Packages"),
        ("o", "switch_screen('orm')", "ORM"),
        ("v", "switch_screen('schema')", "Schema"),
        ("x", "switch_screen('devops')", "DevOps"),
        ("t", "switch_screen('tests')", "Tests"),
        ("a", "switch_screen('ai')", "AI"),
        ("r", "switch_screen('refactor')", "Refactor"),
    ]

    def on_mount(self) -> None:
        self.install_screen(Dashboard(self.project), name="dashboard")
        self.install_screen(CommandRunnerScreen(self.project), name="commands")
        self.install_screen(SettingsEditorScreen(self.project), name="settings")
        self.install_screen(MigrationManagerScreen(self.project), name="migrations")
        self.install_screen(DependencyScreen(self.project), name="dependencies")
        self.install_screen(ORMExplorerScreen(self.project), name="orm")
        self.install_screen(SchemaScreen(self.project), name="schema")
        self.install_screen(DevOpsScreen(self.project), name="devops")
        self.install_screen(TestRunnerScreen(self.project), name="tests")
        self.install_screen(AIAssistantScreen(self.project), name="ai")
        self.install_screen(RefactorScreen(self.project), name="refactor")
        self.push_screen("dashboard")

if __name__ == "__main__":
    app = DjangoTUI("test_project")
    app.run()
