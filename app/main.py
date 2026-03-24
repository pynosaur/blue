import argparse
import sys
from pathlib import Path

from app.core.linter import (
    Linter, load_config, write_default_config, format_issues, DEFAULT_CONFIG
)
from app.utils.doc_reader import show_docs


def get_config_path() -> Path:
    return Path.home() / '.config' / 'plack' / 'plack.yaml'


def main():
    parser = argparse.ArgumentParser(
        prog='plack',
        description='Simple Python linter with YAML configuration'
    )

    parser.add_argument(
        'paths',
        nargs='*',
        help='Files or directories to lint'
    )

    parser.add_argument(
        '-d', '--config',
        metavar='PATH',
        help='Path to YAML config file'
    )

    parser.add_argument(
        '--reset',
        action='store_true',
        help='Reset to default configuration'
    )

    parser.add_argument(
        '--show-config',
        action='store_true',
        help='Show current configuration'
    )

    parser.add_argument(
        '-r', '--recursive',
        action='store_true',
        default=True,
        help='Recursively lint directories (default: true)'
    )

    parser.add_argument(
        '--no-recursive',
        action='store_true',
        help='Do not recursively lint directories'
    )

    parser.add_argument(
        '-l', '--line-length',
        type=int,
        metavar='N',
        help='Override max line length'
    )

    parser.add_argument(
        '--no-color',
        action='store_true',
        help='Disable colored output'
    )

    parser.add_argument(
        '-q', '--quiet',
        action='store_true',
        help='Only show issue count'
    )

    parser.add_argument(
        '-v', '--version',
        action='store_true',
        help='Show version'
    )

    parser.add_argument(
        '--docs',
        action='store_true',
        help='Show documentation'
    )

    parser.add_argument(
        '--apply',
        action='store_true',
        help='Auto-fix issues (trailing whitespace, blank lines, final newline)'
    )

    args = parser.parse_args()

    if args.version:
        print('plack 0.4.0')
        return 0

    if args.docs:
        show_docs()
        return 0

    config_path = get_config_path()

    if args.reset:
        config_path.parent.mkdir(parents=True, exist_ok=True)
        write_default_config(str(config_path))
        print(f'Default config written to {config_path}')
        return 0

    config = DEFAULT_CONFIG.copy()

    if args.config:
        custom_path = Path(args.config)
        if not custom_path.exists():
            print(f'Error: Config file not found: {args.config}', file=sys.stderr)
            return 1
        if custom_path.suffix not in ('.yaml', '.yml'):
            print('Error: Config file must be .yaml or .yml', file=sys.stderr)
            return 1
        try:
            config.update(load_config(args.config))
        except Exception as e:
            print(f'Error loading config: {e}', file=sys.stderr)
            return 1
    elif config_path.exists():
        try:
            config.update(load_config(str(config_path)))
        except Exception:
            pass

    if args.line_length:
        config['line_length'] = args.line_length

    if args.show_config:
        print('Current configuration:')
        for key, value in sorted(config.items()):
            print(f'  {key}: {value}')
        return 0

    if not args.paths:
        args.paths = ['.']

    recursive = not args.no_recursive
    linter = Linter(config)

    if args.apply:
        total_fixes = 0
        all_fixes = []
        for path in args.paths:
            p = Path(path)
            if p.is_file():
                count, fixes = linter.fix_file(str(p))
                total_fixes += count
                all_fixes.extend(fixes)
            elif p.is_dir():
                count, fixes = linter.fix_directory(str(p), recursive=recursive)
                total_fixes += count
                all_fixes.extend(fixes)
            else:
                print(f'Warning: {path} not found', file=sys.stderr)

        GREEN = '\033[32m'
        RESET = '\033[0m'
        if not args.quiet:
            for fix in all_fixes:
                print(f'{GREEN}Fixed:{RESET} {fix}')
        print(f'\n{GREEN}{total_fixes} fixes applied{RESET}')
        return 0

    all_issues = []

    for path in args.paths:
        p = Path(path)
        if p.is_file():
            all_issues.extend(linter.lint_file(str(p)))
        elif p.is_dir():
            all_issues.extend(linter.lint_directory(str(p), recursive=recursive))
        else:
            print(f'Warning: {path} not found', file=sys.stderr)

    if args.quiet:
        if all_issues:
            print(f'{len(all_issues)} issues')
            return 1
        return 0

    if all_issues:
        output = format_issues(all_issues, color=not args.no_color)
        print(output)
        print(f'\n{len(all_issues)} issues found')
        return 1

    print('No issues found')
    return 0


if __name__ == '__main__':
    sys.exit(main())
