import ast
import re
from typing import List, Tuple, Optional


class LineBreaker:
    def __init__(self, max_length: int = 88, indent_size: int = 4):
        self.max_length = max_length
        self.indent_size = indent_size

    def fix_long_lines(self, content: str) -> Tuple[str, List[str]]:
        fixes = []
        try:
            ast.parse(content)
        except SyntaxError:
            return content, []

        lines = content.split('\n')
        result = []
        i = 0

        while i < len(lines):
            line = lines[i]
            if len(line) > self.max_length and not self._is_string_or_comment(line):
                fixed, was_fixed = self._break_line(line, i + 1)
                if was_fixed:
                    fixes.append(f'Line {i + 1}: Split long line')
                    result.extend(fixed.split('\n'))
                else:
                    result.append(line)
            else:
                result.append(line)
            i += 1

        new_content = '\n'.join(result)

        try:
            ast.parse(new_content)
            return new_content, fixes
        except SyntaxError:
            return content, []

    def _is_string_or_comment(self, line: str) -> bool:
        stripped = line.strip()
        if stripped.startswith('#'):
            return True
        if stripped.startswith(('"""', "'''")):
            return True
        if stripped.startswith(('f"', 'f\'', 'r"', 'r\'', '"', "'")):
            quote_count = stripped.count('"') + stripped.count("'")
            if quote_count <= 2:
                return True
        return False

    def _get_indent(self, line: str) -> str:
        return line[:len(line) - len(line.lstrip())]

    def _break_line(self, line: str, lineno: int) -> Tuple[str, bool]:
        indent = self._get_indent(line)
        continuation_indent = indent + ' ' * self.indent_size

        if '(' in line:
            result = self._break_at_parens(line, indent, continuation_indent)
            if result:
                return result, True

        if ',' in line:
            result = self._break_at_commas(line, indent, continuation_indent)
            if result:
                return result, True

        for op in [' and ', ' or ', ' + ', ' - ', ' | ', ' & ']:
            if op in line:
                result = self._break_at_operator(line, op, indent, continuation_indent)
                if result:
                    return result, True

        return line, False

    def _break_at_parens(self, line: str, indent: str, cont_indent: str) -> Optional[str]:
        stripped = line.strip()

        paren_pos = self._find_breakable_paren(stripped)
        if paren_pos == -1:
            return None

        before = stripped[:paren_pos + 1]
        after = stripped[paren_pos + 1:]

        if not after or after == ')':
            return None

        close_paren = self._find_matching_close(after)
        if close_paren == -1:
            inner = after.rstrip(')')
            closing = ')' * (len(after) - len(inner))
        else:
            inner = after[:close_paren]
            closing = after[close_paren:]

        args = self._split_args(inner)
        if not args:
            return None

        lines = [indent + before]
        for i, arg in enumerate(args):
            arg = arg.strip()
            if i < len(args) - 1:
                lines.append(cont_indent + arg + ',')
            else:
                lines.append(cont_indent + arg)
        lines.append(indent + closing)

        result = '\n'.join(lines)
        if all(len(l) <= self.max_length for l in lines):
            return result

        return None

    def _break_at_commas(self, line: str, indent: str, cont_indent: str) -> Optional[str]:
        stripped = line.strip()
        parts = self._split_args(stripped)

        if len(parts) < 2:
            return None

        lines = []
        current = indent
        for i, part in enumerate(parts):
            part = part.strip()
            suffix = ',' if i < len(parts) - 1 else ''
            test = current + part + suffix

            if len(test) > self.max_length and current.strip():
                lines.append(current.rstrip(', '))
                current = cont_indent + part + suffix + ' '
            else:
                current = test + ' '

        if current.strip():
            lines.append(current.rstrip())

        if len(lines) > 1:
            return '\n'.join(lines)
        return None

    def _break_at_operator(self, line: str, op: str, indent: str, cont_indent: str) -> Optional[str]:
        stripped = line.strip()
        parts = stripped.split(op)

        if len(parts) < 2:
            return None

        lines = [indent + parts[0].rstrip() + op.rstrip()]
        for i, part in enumerate(parts[1:], 1):
            if i < len(parts) - 1:
                lines.append(cont_indent + part.strip() + op.rstrip())
            else:
                lines.append(cont_indent + part.strip())

        if all(len(l) <= self.max_length for l in lines):
            return '\n'.join(lines)
        return None

    def _find_breakable_paren(self, s: str) -> int:
        depth = 0
        in_string = False
        string_char = None

        for i, c in enumerate(s):
            if c in '"\'':
                if not in_string:
                    in_string = True
                    string_char = c
                elif c == string_char and (i == 0 or s[i-1] != '\\'):
                    in_string = False
            elif not in_string:
                if c == '(':
                    if depth == 0:
                        return i
                    depth += 1
                elif c == ')':
                    depth -= 1
        return -1

    def _find_matching_close(self, s: str) -> int:
        depth = 1
        in_string = False
        string_char = None

        for i, c in enumerate(s):
            if c in '"\'':
                if not in_string:
                    in_string = True
                    string_char = c
                elif c == string_char and (i == 0 or s[i-1] != '\\'):
                    in_string = False
            elif not in_string:
                if c == '(':
                    depth += 1
                elif c == ')':
                    depth -= 1
                    if depth == 0:
                        return i
        return -1

    def _split_args(self, s: str) -> List[str]:
        args = []
        current = ''
        depth = 0
        in_string = False
        string_char = None

        for i, c in enumerate(s):
            if c in '"\'':
                if not in_string:
                    in_string = True
                    string_char = c
                elif c == string_char and (i == 0 or s[i-1] != '\\'):
                    in_string = False
                current += c
            elif in_string:
                current += c
            elif c in '([{':
                depth += 1
                current += c
            elif c in ')]}':
                depth -= 1
                current += c
            elif c == ',' and depth == 0:
                if current.strip():
                    args.append(current.strip())
                current = ''
            else:
                current += c

        if current.strip():
            args.append(current.strip())

        return args
