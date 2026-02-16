import argparse
import sys
import asyncio
from .ui import DjangoTUI
from .engine import DjangoProject, SecurityScanner

def main():
    parser = argparse.ArgumentParser(description="Django TUI - Comprehensive Management Tool")
    parser.add_argument("path", nargs="?", default=".", help="Path to the Django project")
    parser.add_argument("--scan", action="store_true", help="Run a security scan and exit")
    parser.add_argument("--check", action="store_true", help="Run Django check and exit")

    args = parser.parse_args()

    project = DjangoProject(args.path)
    if not project.is_valid():
        print(f"Error: No Django project found at {args.path}")
        sys.exit(1)

    if args.scan:
        scanner = SecurityScanner(project)
        report = scanner.scan()
        print(f"Security Score: {report['score']}/100")
        for finding in report['findings']:
            print(f"[{finding['severity']}] {finding['msg']}")
    elif args.check:
        from .engine import CommandRunner
        runner = CommandRunner(project)
        loop = asyncio.get_event_loop()
        res = loop.run_until_complete(runner.run("check"))
        print(res.stdout + res.stderr)
    else:
        app = DjangoTUI(args.path)
        app.run()

if __name__ == "__main__":
    main()
