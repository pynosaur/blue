import ast
import re
from typing import List, Tuple, Optional


class SmartFormatter:
    def __init__(self, max_length: int = 88, indent_size: int = 4):
        self.max_length = max_length
        self.indent_size = indent_size

    def format_file(self, content: str) -> Tuple[str, List[str]]:
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
            if len(line) > self.max_length and not self._is_unfixable(line):
                fixed, was_fixed = self._smart_break(line, i + 1)
                if was_fixed:
                    fixes.append(f'Line {i + 1}: Reformatted long line')
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

    def _is_unfixable(self, line: str) -> bool:
        stripped = line.strip()
        if stripped.startswith('#'):
            return True
        if stripped.startswith(('"""', "'''")):
            return True
        if '"""' in stripped or "'''" in stripped:
            return True
        return False

    def _get_indent(self, line: str) -> str:
        return line[:len(line) - len(line.lstrip())]

    def _smart_break(self, line: str, lineno: int) -> Tuple[str, bool]:
        indent = self._get_indent(line)
        cont_indent = indent + ' ' * self.indent_size
        stripped = line.strip()

        try:
            tree = ast.parse(stripped)
            if tree.body:
                node = tree.body[0]
                if isinstance(node, ast.Expr):
                    node = node.value

                result = self._format_node(node, indent, cont_indent)
                if result and self._validate(result):
                    return result, True
        except SyntaxError:
            pass

        strategies = [
            self._break_function_call,
            self._break_assignment,
            self._break_chained_calls,
            self._break_list_or_dict,
            self._break_binary_op,
            self._break_comparison,
            self._break_at_comma,
        ]

        for strategy in strategies:
            result = strategy(line, indent, cont_indent)
            if result and self._validate(result):
                return result, True

        return line, False

    def _format_node(self, node: ast.AST, indent: str, cont_indent: str) -> Optional[str]:
        if isinstance(node, ast.Call):
            return self._format_call(node, indent, cont_indent)
        if isinstance(node, ast.Assign):
            return self._format_assign(node, indent, cont_indent)
        if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
            return self._format_collection(node, indent, cont_indent)
        if isinstance(node, ast.Dict):
            return self._format_dict(node, indent, cont_indent)
        if isinstance(node, ast.BoolOp):
            return self._format_boolop(node, indent, cont_indent)
        return None

    def _format_call(self, node: ast.Call, indent: str, cont_indent: str) -> Optional[str]:
        if not node.args and not node.keywords:
            return None

        func_str = ast.unparse(node.func)
        args = []

        for arg in node.args:
            args.append(ast.unparse(arg))
        for kw in node.keywords:
            if kw.arg:
                args.append(f'{kw.arg}={ast.unparse(kw.value)}')
            else:
                args.append(f'**{ast.unparse(kw.value)}')

        lines = [f'{indent}{func_str}(']
        for i, arg in enumerate(args):
            suffix = ',' if i < len(args) - 1 else ','
            lines.append(f'{cont_indent}{arg}{suffix}')
        lines.append(f'{indent})')

        return '\n'.join(lines)

    def _format_assign(self, node: ast.Assign, indent: str, cont_indent: str) -> Optional[str]:
        targets = ' = '.join(ast.unparse(t) for t in node.targets)
        value = node.value

        if isinstance(value, ast.Call):
            value_result = self._format_call(value, '', ' ' * self.indent_size)
        elif isinstance(value, (ast.List, ast.Tuple, ast.Set)):
            value_result = self._format_collection(value, '', ' ' * self.indent_size)
        elif isinstance(value, ast.Dict):
            value_result = self._format_dict(value, '', ' ' * self.indent_size)
        elif isinstance(value, ast.BoolOp):
            value_result = self._format_boolop(value, '', ' ' * self.indent_size)
        else:
            return None

        if not value_result:
            return None

        call_result = value_result

        if call_result:
            call_lines = call_result.split('\n')
            call_lines[0] = f'{indent}{targets} = {call_lines[0].lstrip()}'
            for i in range(1, len(call_lines)):
                call_lines[i] = indent + call_lines[i]
            return '\n'.join(call_lines)
        return None

    def _format_collection(self, node: ast.AST, indent: str, cont_indent: str) -> Optional[str]:
        if isinstance(node, ast.List):
            open_b, close_b = '[', ']'
            elts = node.elts
        elif isinstance(node, ast.Tuple):
            open_b, close_b = '(', ')'
            elts = node.elts
        elif isinstance(node, ast.Set):
            open_b, close_b = '{', '}'
            elts = node.elts
        else:
            return None

        if not elts:
            return None

        lines = [f'{indent}{open_b}']
        for i, elt in enumerate(elts):
            suffix = ',' if i < len(elts) - 1 else ','
            lines.append(f'{cont_indent}{ast.unparse(elt)}{suffix}')
        lines.append(f'{indent}{close_b}')

        return '\n'.join(lines)

    def _format_dict(self, node: ast.Dict, indent: str, cont_indent: str) -> Optional[str]:
        if not node.keys:
            return None

        lines = [f'{indent}{{']
        for i, (k, v) in enumerate(zip(node.keys, node.values)):
            suffix = ',' if i < len(node.keys) - 1 else ','
            if k is None:
                lines.append(f'{cont_indent}**{ast.unparse(v)}{suffix}')
            else:
                lines.append(f'{cont_indent}{ast.unparse(k)}: {ast.unparse(v)}{suffix}')
        lines.append(f'{indent}}}')

        return '\n'.join(lines)

    def _format_boolop(self, node: ast.BoolOp, indent: str, cont_indent: str) -> Optional[str]:
        op_str = ' and ' if isinstance(node.op, ast.And) else ' or '
        values = [ast.unparse(v) for v in node.values]

        if len(values) < 2:
            return None

        lines = [f'{indent}(']
        lines.append(f'{cont_indent}{values[0]}')
        for v in values[1:]:
            lines.append(f'{cont_indent}{op_str.strip()} {v}')
        lines.append(f'{indent})')

        return '\n'.join(lines)

    def _break_function_call(self, line: str, indent: str, cont_indent: str) -> Optional[str]:
        stripped = line.strip()
        match = re.match(r'^(\w+(?:\.\w+)*)\((.*)\)$', stripped, re.DOTALL)
        if not match:
            return None

        func_name = match.group(1)
        args_str = match.group(2)
        args = self._smart_split(args_str, ',')

        if len(args) < 2:
            return None

        lines = [f'{indent}{func_name}(']
        for i, arg in enumerate(args):
            suffix = ',' if i < len(args) - 1 else ','
            lines.append(f'{cont_indent}{arg.strip()}{suffix}')
        lines.append(f'{indent})')

        return '\n'.join(lines)

    def _break_assignment(self, line: str, indent: str, cont_indent: str) -> Optional[str]:
        stripped = line.strip()
        eq_pos = stripped.find(' = ')
        if eq_pos == -1:
            return None

        target = stripped[:eq_pos]
        value = stripped[eq_pos + 3:]

        if '(' in value:
            value_result = self._break_function_call(value, '', ' ' * self.indent_size)
            if value_result:
                value_lines = value_result.split('\n')
                value_lines[0] = f'{indent}{target} = {value_lines[0].lstrip()}'
                for i in range(1, len(value_lines)):
                    value_lines[i] = indent + value_lines[i]
                return '\n'.join(value_lines)

        return None

    def _break_chained_calls(self, line: str, indent: str, cont_indent: str) -> Optional[str]:
        stripped = line.strip()
        if ').(' not in stripped and ').' not in stripped:
            return None

        parts = []
        current = ''
        depth = 0

        for i, c in enumerate(stripped):
            if c in '([{':
                depth += 1
                current += c
            elif c in ')]}':
                depth -= 1
                current += c
                if depth == 0 and i + 1 < len(stripped) and stripped[i + 1] == '.':
                    parts.append(current)
                    current = ''
            else:
                current += c

        if current:
            parts.append(current)

        if len(parts) < 2:
            return None

        lines = [f'{indent}{parts[0]}']
        for part in parts[1:]:
            lines.append(f'{cont_indent}{part}')

        return '\n'.join(lines)

    def _break_list_or_dict(self, line: str, indent: str, cont_indent: str) -> Optional[str]:
        stripped = line.strip()

        for open_b, close_b in [('[', ']'), ('{', '}')]:
            if stripped.startswith(open_b) and stripped.endswith(close_b):
                inner = stripped[1:-1]
                items = self._smart_split(inner, ',')

                if len(items) < 2:
                    return None

                lines = [f'{indent}{open_b}']
                for i, item in enumerate(items):
                    suffix = ',' if i < len(items) - 1 else ','
                    lines.append(f'{cont_indent}{item.strip()}{suffix}')
                lines.append(f'{indent}{close_b}')

                return '\n'.join(lines)

        return None

    def _break_binary_op(self, line: str, indent: str, cont_indent: str) -> Optional[str]:
        stripped = line.strip()

        for op in [' and ', ' or ', ' | ', ' & ', ' + ', ' - ']:
            parts = self._smart_split(stripped, op.strip())
            if len(parts) >= 2:
                lines = []
                for i, part in enumerate(parts):
                    if i == 0:
                        lines.append(f'{indent}{part.strip()}')
                    else:
                        lines.append(f'{cont_indent}{op.strip()} {part.strip()}')
                return '\n'.join(lines)

        return None

    def _break_comparison(self, line: str, indent: str, cont_indent: str) -> Optional[str]:
        stripped = line.strip()

        for op in [' == ', ' != ', ' >= ', ' <= ', ' > ', ' < ', ' is ', ' in ']:
            if op in stripped:
                parts = stripped.split(op, 1)
                if len(parts) == 2:
                    return f'{indent}{parts[0].strip()}\n{cont_indent}{op.strip()} {parts[1].strip()}'

        return None

    def _break_at_comma(self, line: str, indent: str, cont_indent: str) -> Optional[str]:
        stripped = line.strip()
        parts = self._smart_split(stripped, ',')

        if len(parts) < 2:
            return None

        lines = []
        current = indent

        for i, part in enumerate(parts):
            part = part.strip()
            suffix = ',' if i < len(parts) - 1 else ''
            test = current + part + suffix

            if len(test) > self.max_length and current != indent:
                lines.append(current.rstrip(', '))
                current = cont_indent + part + suffix + ' '
            else:
                current = test + ' '

        if current.strip():
            lines.append(current.rstrip())

        if len(lines) > 1:
            return '\n'.join(lines)
        return None

    def _smart_split(self, s: str, delimiter: str) -> List[str]:
        parts = []
        current = ''
        depth = 0
        in_string = False
        string_char = None

        i = 0
        while i < len(s):
            c = s[i]

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
            elif depth == 0 and s[i:i+len(delimiter)] == delimiter:
                if current.strip():
                    parts.append(current.strip())
                current = ''
                i += len(delimiter) - 1
            else:
                current += c
            i += 1

        if current.strip():
            parts.append(current.strip())

        return parts

    def _validate(self, code: str) -> bool:
        try:
            ast.parse(code)
            return all(len(line) <= self.max_length for line in code.split('\n'))
        except SyntaxError:
            return False


class LineBreaker:
    def __init__(self, max_length: int = 88, indent_size: int = 4):
        self._formatter = SmartFormatter(max_length, indent_size)
        self.max_length = max_length
        self.indent_size = indent_size

    def fix_long_lines(self, content: str) -> Tuple[str, List[str]]:
        return self._formatter.format_file(content)
