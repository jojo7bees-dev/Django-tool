# Django TUI

A comprehensive TUI management tool for Django projects.

## Features

- **Command Orchestration**: Run management commands asynchronously with real-time output.
- **Dynamic Settings Controller**: Safely modify `settings.py` while preserving comments and formatting using `libcst`.
- **Dependency Manager**: List packages and run security audits via `pip-audit`.
- **Project Inspector**: Analyze project structure, apps, and models.
- **Security Scanner**: Evaluate project security settings and get a score.
- **ORM Explorer**: Build and execute interactive queries against your project's models.
- **Database Schema View**: Tree view of your project's models and fields.
- **DevOps Integration**: Generate Dockerfiles and manage server processes.
- **Git Integration**: View repository status directly in the dashboard.

## Installation

```bash
pip install textual rich django libcst pip-audit
```

## Usage

Run the TUI from your Django project root:

```bash
python -m django_tui.main
```

Or run a quick security scan:

```bash
python -m django_tui.main --scan
```

## Shortcuts

- `d`: Dashboard
- `c`: Commands
- `s`: Settings
- `m`: Migrations
- `p`: Packages
- `o`: ORM Explorer
- `v`: Schema View
- `x`: DevOps
