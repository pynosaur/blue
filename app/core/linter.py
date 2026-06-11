import ast
import io
import os
import re
import tokenize
from pathlib import Path
from typing import Dict, List, Set, Tuple, Optional

from app.core.formatter import LineBreaker

DEFAULT_CONFIG = {
    'line_length': 88,
    'indent_size': 4,
    'max_blank_lines': 2,
    'trailing_whitespace': True,
    'final_newline': True,
    'tab_indent': False,
}

# Build artifact directories that should never be linted. These appear
# locally after Nuitka/Bazel builds and are not part of the source tree.
SKIP_DIR_NAMES = {
    'main.build',
    'main.dist',
    'main.onefile-build',
    '__pycache__',
    'node_modules',
}
SKIP_DIR_PREFIXES = ('bazel-',)


class LintIssue:
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

    def lint_file(self, filepath: str) -> List[LintIssue]:
        issues = []
        path = Path(filepath)

        if not path.exists():
            return [LintIssue(filepath, 0, 0, 'E001', 'File not found')]

        if not path.suffix == '.py':
            return []

        try:
            content = path.read_text(encoding='utf-8')
        except Exception as e:
            return [LintIssue(filepath, 0, 0, 'E002', f'Cannot read file: {e}')]

        lines = content.split('\n')
        protected = self._protected_lines(content)

        issues.extend(self._check_line_length(filepath, lines))
        issues.extend(
            self._check_trailing_whitespace(filepath, lines, protected),
        )
        issues.extend(self._check_blank_lines(filepath, lines, protected))
        issues.extend(self._check_indentation(filepath, lines, protected))
        issues.extend(self._check_final_newline(filepath, content))
        issues.extend(self._check_syntax(filepath, content))

        return sorted(issues, key=lambda e: (e.line, e.col))

    def _protected_lines(self, content: str) -> Set[int]:
        """Line numbers (1-based) that are inside multiline string
        literals. Those lines are data, not code: indentation, trailing
        whitespace, and blank-line rules must not flag or rewrite them
        (e.g. ASCII art, embedded templates)."""
        protected: Set[int] = set()
        string_types = {tokenize.STRING}
        fstring_middle = getattr(tokenize, 'FSTRING_MIDDLE', None)
        if fstring_middle is not None:
            string_types.add(fstring_middle)
        try:
            tokens = tokenize.generate_tokens(io.StringIO(content).readline)
            for tok in tokens:
                if tok.type in string_types and tok.end[0] > tok.start[0]:
                    protected.update(range(tok.start[0] + 1, tok.end[0] + 1))
        except (tokenize.TokenError, IndentationError, SyntaxError):
            pass
        return protected

    def _check_line_length(self, filepath: str, lines: List[str]) -> List[LintIssue]:
        issues = []
        max_len = self.config['line_length']
        breaker = LineBreaker(max_len, self.config['indent_size'])

        in_docstring = False
        docstring_quote = None
        bracket_depth = 0

        for i, line in enumerate(lines, 1):
            stripped = line.strip()

            if not in_docstring:
                for q in ('"""', "'''"):
                    if q in stripped:
                        if stripped.count(q) == 1:
                            in_docstring = True
                            docstring_quote = q
                        break
            else:
                if docstring_quote and docstring_quote in stripped:
                    in_docstring = False
                    docstring_quote = None

            is_continuation = bracket_depth > 0

            if not in_docstring:
                bracket_depth += breaker.count_brackets(line)

            if len(line) > max_len:
                if breaker.can_fix_line(line, in_docstring, is_continuation):
                    issues.append(LintIssue(
                        filepath, i, max_len + 1, 'L001',
                        f'Line too long ({len(line)} > {max_len})',
                    ))

        return issues

    def _check_trailing_whitespace(
        self,
        filepath: str,
        lines: List[str],
        protected: Optional[Set[int]] = None,
    ) -> List[LintIssue]:
        if not self.config['trailing_whitespace']:
            return []

        protected = protected or set()
        issues = []
        for i, line in enumerate(lines, 1):
            if i in protected:
                continue
            stripped = line.rstrip()
            if len(line) != len(stripped) and line:
                issues.append(LintIssue(
                    filepath, i, len(stripped) + 1, 'W001',
                    'Trailing whitespace'
                ))

        return issues

    def _check_blank_lines(
        self,
        filepath: str,
        lines: List[str],
        protected: Optional[Set[int]] = None,
    ) -> List[LintIssue]:
        protected = protected or set()
        issues = []
        max_blank = self.config['max_blank_lines']
        blank_count = 0
        blank_start = 0

        for i, line in enumerate(lines, 1):
            if not line.strip() and i not in protected:
                if blank_count == 0:
                    blank_start = i
                blank_count += 1
            else:
                if blank_count > max_blank:
                    issues.append(LintIssue(
                        filepath, blank_start, 1, 'B001',
                        f'Too many blank lines ({blank_count} > {max_blank})'
                    ))
                blank_count = 0

        return issues

    def _check_indentation(
        self,
        filepath: str,
        lines: List[str],
        protected: Optional[Set[int]] = None,
    ) -> List[LintIssue]:
        protected = protected or set()
        issues = []
        indent_size = self.config['indent_size']
        use_tabs = self.config['tab_indent']

        for i, line in enumerate(lines, 1):
            if i in protected or not line.strip():
                continue

            leading = len(line) - len(line.lstrip())
            if leading == 0:
                continue

            if use_tabs:
                if ' ' in line[:leading]:
                    issues.append(LintIssue(
                        filepath, i, 1, 'I001',
                        'Expected tabs, found spaces'
                    ))
            else:
                if '\t' in line[:leading]:
                    issues.append(LintIssue(
                        filepath, i, 1, 'I001',
                        'Expected spaces, found tabs'
                    ))
                elif leading % indent_size != 0:
                    issues.append(LintIssue(
                        filepath, i, 1, 'I002',
                        f'Indentation not multiple of {indent_size}'
                    ))

        return issues

    def _check_final_newline(self, filepath: str, content: str) -> List[LintIssue]:
        if not self.config['final_newline']:
            return []

        if content and not content.endswith('\n'):
            lines = content.split('\n')
            return [LintIssue(
                filepath, len(lines), len(lines[-1]) + 1, 'N001',
                'No newline at end of file'
            )]

        return []

    def _check_syntax(self, filepath: str, content: str) -> List[LintIssue]:
        try:
            ast.parse(content, filename=filepath)
        except SyntaxError as e:
            line = e.lineno or 1
            col = e.offset or 1
            msg = e.msg if e.msg else 'Syntax error'
            return [LintIssue(filepath, line, col, 'S001', msg)]
        return []

    def _in_hidden_dir(self, filepath: Path) -> bool:
        """True for files under hidden dirs or build artifact dirs."""
        for part in filepath.parts:
            if part.startswith('.') and part not in ('.', '..'):
                return True
            if part in SKIP_DIR_NAMES:
                return True
            if part.startswith(SKIP_DIR_PREFIXES):
                return True
        return False

    def _check_version_sync(
        self,
        dirpath: str,
    ) -> List[LintIssue]:
        """Check version consistency across .program, __init__, doc, main."""
        root = Path(dirpath)
        program_file = root / '.program'
        if not program_file.exists():
            return []

        try:
            prog_text = program_file.read_text(encoding='utf-8')
        except Exception:
            return []

        prog_version = None
        prog_name = None
        for line in prog_text.split('\n'):
            if line.startswith('version:'):
                prog_version = line.split(':', 1)[1].strip()
            if line.startswith('name:'):
                prog_name = line.split(':', 1)[1].strip()

        if not prog_version or not prog_name:
            return []

        versions: Dict[str, str] = {'.program': prog_version}
        issues: List[LintIssue] = []

        init_file = root / 'app' / '__init__.py'
        if init_file.exists():
            try:
                text = init_file.read_text(encoding='utf-8')
                m = re.search(
                    r'__version__\s*=\s*["\']([^"\']+)["\']',
                    text,
                )
                if m:
                    versions['app/__init__.py'] = m.group(1)
                else:
                    issues.append(LintIssue(
                        str(init_file), 1, 1, 'V003',
                        'Missing __version__ in app/__init__.py '
                        '(required when .program is present)',
                    ))
            except Exception:
                pass

        doc_file = root / 'doc' / f'{prog_name}.yaml'
        if doc_file.exists():
            try:
                text = doc_file.read_text(encoding='utf-8')
                m = re.search(
                    r'^VERSION:\s*(?:"([^"]+)"|([0-9]+(?:\.[0-9]+)*))\s*$',
                    text,
                    re.MULTILINE,
                )
                if m:
                    doc_key = f'doc/{prog_name}.yaml'
                    versions[doc_key] = m.group(1) or m.group(2) or ''
            except Exception:
                pass

        if len(set(versions.values())) > 1:
            for filepath, version in versions.items():
                if version != prog_version:
                    full = str(root / filepath)
                    issues.append(LintIssue(
                        full, 1, 1, 'V001',
                        f'Version mismatch: {version} '
                        f'(expected {prog_version} '
                        f'from .program)',
                    ))

        main_py = root / 'app' / 'main.py'
        if main_py.exists():
            try:
                text = main_py.read_text(encoding='utf-8')
                for m in re.finditer(
                    r"print\(\s*['\"]([A-Za-z0-9_-]+)\s+(\d+\.\d+\.\d+)['\"]\s*\)",
                    text,
                ):
                    n, v = m.group(1), m.group(2)
                    if n.lower() == prog_name.lower() and v != prog_version:
                        line_no = text[:m.start()].count('\n') + 1
                        issues.append(LintIssue(
                            str(main_py),
                            line_no,
                            1,
                            'V002',
                            f'Hardcoded print version {v} does not match '
                            f'.program ({prog_version}); use __version__',
                        ))
            except Exception:
                pass

        return issues

    def lint_directory(self, dirpath: str, recursive: bool = True) -> List[LintIssue]:
        issues = []
        path = Path(dirpath)

        if not path.exists():
            return [LintIssue(dirpath, 0, 0, 'E001', 'Directory not found')]

        issues.extend(self._check_version_sync(dirpath))

        pattern = '**/*.py' if recursive else '*.py'

        for pyfile in path.glob(pattern):
            if pyfile.is_file() and not self._in_hidden_dir(pyfile):
                issues.extend(self.lint_file(str(pyfile)))

        return issues

    def fix_file(self, filepath: str) -> Tuple[int, List[str]]:
        path = Path(filepath)
        if not path.exists() or path.suffix != '.py':
            return 0, []

        try:
            content = path.read_text(encoding='utf-8')
        except Exception:
            return 0, []

        lines = content.split('\n')
        protected = self._protected_lines(content)
        fixed = []
        fixes_applied = []
        indent_size = self.config['indent_size']
        use_tabs = self.config['tab_indent']

        for i, line in enumerate(lines):
            if i + 1 in protected:
                # Inside a multiline string: content is data, never
                # rewrite it (stripping/reindenting would corrupt it).
                fixed.append(line)
                continue
            original = line
            if line.rstrip() != line:
                line = line.rstrip()
                fixes_applied.append(f'{filepath}:{i+1} Fixed trailing whitespace')
            if line.strip() and not use_tabs:
                leading = len(line) - len(line.lstrip())
                if leading > 0 and '\t' not in line[:leading]:
                    remainder = leading % indent_size
                    if remainder != 0:
                        new_leading = leading + (indent_size - remainder)
                        line = ' ' * new_leading + line.lstrip()
                        fixes_applied.append(
                            f'{filepath}:{i+1} Fixed indentation'
                        )
            fixed.append(line)

        new_content = '\n'.join(fixed)

        if (
            self.config['final_newline'] and
            new_content and
            not new_content.endswith('\n')
        ):
            new_content += '\n'
            fixes_applied.append(f'{filepath}: Added final newline')

        max_blank = self.config['max_blank_lines']
        result_lines = new_content.split('\n')
        compressed = []
        blank_count = 0

        # Line numbers are unchanged so far (fixes above are 1:1), so the
        # protected set still applies: blank lines inside multiline
        # strings are content and must never be dropped.
        for idx, line in enumerate(result_lines, 1):
            if not line.strip() and idx not in protected:
                blank_count += 1
                if blank_count <= max_blank:
                    compressed.append(line)
            else:
                blank_count = 0
                compressed.append(line)

        if len(compressed) != len(result_lines):
            fixes_applied.append(f'{filepath}: Reduced excessive blank lines')

        new_content = '\n'.join(compressed)
        if (
            new_content and
            not new_content.endswith('\n') and
            self.config['final_newline']
        ):
            new_content += '\n'

        breaker = LineBreaker(
            max_length=self.config['line_length'],
            indent_size=self.config['indent_size']
        )
        new_content, line_fixes = breaker.fix_long_lines(new_content)
        for fix in line_fixes:
            fixes_applied.append(f'{filepath}: {fix}')

        if (
            new_content and
            not new_content.endswith('\n') and
            self.config['final_newline']
        ):
            new_content += '\n'

        if new_content != content:
            path.write_text(new_content, encoding='utf-8')

        return len(fixes_applied), fixes_applied

    def fix_directory(
        self,
        dirpath: str,
        recursive: bool = True,
    ) -> Tuple[int, List[str]]:
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


def format_issues(issues: List[LintIssue], color: bool = True) -> str:
    if not issues:
        return ''

    RED = '\033[31m' if color else ''
    YELLOW = '\033[33m' if color else ''
    CYAN = '\033[36m' if color else ''
    RESET = '\033[0m' if color else ''

    lines = []
    for err in issues:
        if err.code.startswith('E'):
            code_color = RED
        elif err.code.startswith('W'):
            code_color = YELLOW
        else:
            code_color = CYAN

        lines.append(
            f'{err.file}:{err.line}:{err.col}: {code_color}{err.code}{RESET} '
            f'{err.message}'
        )

    return '\n'.join(lines)
