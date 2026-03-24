import os
import re
from pathlib import Path
from typing import Dict, List, Tuple, Optional

from app.core.formatter import LineBreaker

DEFAULT_CONFIG = {
    'line_length': 88,
    'indent_size': 4,
    'max_blank_lines': 2,
    'trailing_whitespace': True,
    'final_newline': True,
    'tab_indent': False,
}


class LintError:
    def __init__(self, file: str, line: int, col: int, code: str, message: str):
        self.file = file
        self.line = line
        self.col = col
        self.code = code
        self.message = message

    def __str__(self):
        return f"{self.file}:{self.line}:{self.col}: {self.code} {self.message}"

    def __repr__(self):
        return self.__str__()


class Linter:
    def __init__(self, config: Optional[Dict] = None):
        self.config = DEFAULT_CONFIG.copy()
        if config:
            self.config.update(config)

    def lint_file(self, filepath: str) -> List[LintError]:
        errors = []
        path = Path(filepath)

        if not path.exists():
            return [LintError(filepath, 0, 0, 'E001', 'File not found')]

        if not path.suffix == '.py':
            return []

        try:
            content = path.read_text(encoding='utf-8')
        except Exception as e:
            return [LintError(filepath, 0, 0, 'E002', f'Cannot read file: {e}')]

        lines = content.split('\n')

        errors.extend(self._check_line_length(filepath, lines))
        errors.extend(self._check_trailing_whitespace(filepath, lines))
        errors.extend(self._check_blank_lines(filepath, lines))
        errors.extend(self._check_indentation(filepath, lines))
        errors.extend(self._check_final_newline(filepath, content))

        return sorted(errors, key=lambda e: (e.line, e.col))

    def _check_line_length(self, filepath: str, lines: List[str]) -> List[LintError]:
        errors = []
        max_len = self.config['line_length']

        for i, line in enumerate(lines, 1):
            if len(line) > max_len:
                errors.append(LintError(
                    filepath, i, max_len + 1, 'L001',
                    f'Line too long ({len(line)} > {max_len})'
                ))

        return errors

    def _check_trailing_whitespace(self, filepath: str, lines: List[str]) -> List[LintError]:
        if not self.config['trailing_whitespace']:
            return []

        errors = []
        for i, line in enumerate(lines, 1):
            stripped = line.rstrip()
            if len(line) != len(stripped) and line:
                errors.append(LintError(
                    filepath, i, len(stripped) + 1, 'W001',
                    'Trailing whitespace'
                ))

        return errors

    def _check_blank_lines(self, filepath: str, lines: List[str]) -> List[LintError]:
        errors = []
        max_blank = self.config['max_blank_lines']
        blank_count = 0
        blank_start = 0

        for i, line in enumerate(lines, 1):
            if not line.strip():
                if blank_count == 0:
                    blank_start = i
                blank_count += 1
            else:
                if blank_count > max_blank:
                    errors.append(LintError(
                        filepath, blank_start, 1, 'B001',
                        f'Too many blank lines ({blank_count} > {max_blank})'
                    ))
                blank_count = 0

        return errors

    def _check_indentation(self, filepath: str, lines: List[str]) -> List[LintError]:
        errors = []
        indent_size = self.config['indent_size']
        use_tabs = self.config['tab_indent']

        for i, line in enumerate(lines, 1):
            if not line.strip():
                continue

            leading = len(line) - len(line.lstrip())
            if leading == 0:
                continue

            if use_tabs:
                if ' ' in line[:leading]:
                    errors.append(LintError(
                        filepath, i, 1, 'I001',
                        'Expected tabs, found spaces'
                    ))
            else:
                if '\t' in line[:leading]:
                    errors.append(LintError(
                        filepath, i, 1, 'I001',
                        'Expected spaces, found tabs'
                    ))
                elif leading % indent_size != 0:
                    errors.append(LintError(
                        filepath, i, 1, 'I002',
                        f'Indentation not multiple of {indent_size}'
                    ))

        return errors

    def _check_final_newline(self, filepath: str, content: str) -> List[LintError]:
        if not self.config['final_newline']:
            return []

        if content and not content.endswith('\n'):
            lines = content.split('\n')
            return [LintError(
                filepath, len(lines), len(lines[-1]) + 1, 'N001',
                'No newline at end of file'
            )]

        return []

    def _in_hidden_dir(self, filepath: Path) -> bool:
        for part in filepath.parts:
            if part.startswith('.') and part not in ('.', '..'):
                return True
        return False

    def lint_directory(self, dirpath: str, recursive: bool = True) -> List[LintError]:
        errors = []
        path = Path(dirpath)

        if not path.exists():
            return [LintError(dirpath, 0, 0, 'E001', 'Directory not found')]

        pattern = '**/*.py' if recursive else '*.py'

        for pyfile in path.glob(pattern):
            if pyfile.is_file() and not self._in_hidden_dir(pyfile):
                errors.extend(self.lint_file(str(pyfile)))

        return errors

    def fix_file(self, filepath: str) -> Tuple[int, List[str]]:
        path = Path(filepath)
        if not path.exists() or path.suffix != '.py':
            return 0, []

        try:
            content = path.read_text(encoding='utf-8')
        except Exception:
            return 0, []

        lines = content.split('\n')
        fixed = []
        fixes_applied = []

        for i, line in enumerate(lines):
            original = line
            if line.rstrip() != line:
                line = line.rstrip()
                fixes_applied.append(f'{filepath}:{i+1} Fixed trailing whitespace')
            fixed.append(line)

        new_content = '\n'.join(fixed)

        if self.config['final_newline'] and new_content and not new_content.endswith('\n'):
            new_content += '\n'
            fixes_applied.append(f'{filepath}: Added final newline')

        max_blank = self.config['max_blank_lines']
        result_lines = new_content.split('\n')
        compressed = []
        blank_count = 0

        for line in result_lines:
            if not line.strip():
                blank_count += 1
                if blank_count <= max_blank:
                    compressed.append(line)
            else:
                blank_count = 0
                compressed.append(line)

        if len(compressed) != len(result_lines):
            fixes_applied.append(f'{filepath}: Reduced excessive blank lines')

        new_content = '\n'.join(compressed)
        if new_content and not new_content.endswith('\n') and self.config['final_newline']:
            new_content += '\n'

        breaker = LineBreaker(
            max_length=self.config['line_length'],
            indent_size=self.config['indent_size']
        )
        new_content, line_fixes = breaker.fix_long_lines(new_content)
        for fix in line_fixes:
            fixes_applied.append(f'{filepath}: {fix}')

        if new_content and not new_content.endswith('\n') and self.config['final_newline']:
            new_content += '\n'

        if new_content != content:
            path.write_text(new_content, encoding='utf-8')

        return len(fixes_applied), fixes_applied

    def fix_directory(self, dirpath: str, recursive: bool = True) -> Tuple[int, List[str]]:
        total_fixes = 0
        all_fixes = []
        path = Path(dirpath)

        if not path.exists():
            return 0, []

        pattern = '**/*.py' if recursive else '*.py'

        for pyfile in path.glob(pattern):
            if pyfile.is_file() and not self._in_hidden_dir(pyfile):
                count, fixes = self.fix_file(str(pyfile))
                total_fixes += count
                all_fixes.extend(fixes)

        return total_fixes, all_fixes


def load_config(config_path: str) -> Dict:
    path = Path(config_path)

    if not path.exists():
        raise FileNotFoundError(f'Config file not found: {config_path}')

    if path.suffix not in ('.yaml', '.yml'):
        raise ValueError('Config file must be .yaml or .yml')

    content = path.read_text(encoding='utf-8')
    return parse_yaml(content)


def parse_yaml(content: str) -> Dict:
    config = {}
    for line in content.split('\n'):
        line = line.strip()
        if not line or line.startswith('#'):
            continue

        if ':' in line:
            key, value = line.split(':', 1)
            key = key.strip()
            value = value.strip()

            if value.lower() == 'true':
                config[key] = True
            elif value.lower() == 'false':
                config[key] = False
            elif value.isdigit():
                config[key] = int(value)
            else:
                config[key] = value

    return config


def write_default_config(path: str) -> None:
    config_content = """line_length: 88
indent_size: 4
max_blank_lines: 2
trailing_whitespace: true
final_newline: true
tab_indent: false
"""
    Path(path).write_text(config_content, encoding='utf-8')


def format_errors(errors: List[LintError], color: bool = True) -> str:
    if not errors:
        return ''

    RED = '\033[31m' if color else ''
    YELLOW = '\033[33m' if color else ''
    CYAN = '\033[36m' if color else ''
    RESET = '\033[0m' if color else ''

    lines = []
    for err in errors:
        if err.code.startswith('E'):
            code_color = RED
        elif err.code.startswith('W'):
            code_color = YELLOW
        else:
            code_color = CYAN

        lines.append(f"{err.file}:{err.line}:{err.col}: {code_color}{err.code}{RESET} {err.message}")

    return '\n'.join(lines)
