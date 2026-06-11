import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.linter import (
    Linter, LintIssue, load_config, parse_yaml, write_default_config,
    DEFAULT_CONFIG, format_issues
)


class TestLinter(unittest.TestCase):

    def setUp(self):
        self.linter = Linter()
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def write_temp_file(self, content: str, name: str = 'test.py') -> str:
        path = os.path.join(self.temp_dir, name)
        with open(path, 'w') as f:
            f.write(content)
        return path

    def test_line_length_ok(self):
        code = 'x = 1\n'
        path = self.write_temp_file(code)
        issues = self.linter.lint_file(path)
        line_issues = [e for e in issues if e.code == 'L001']
        self.assertEqual(len(line_issues), 0)

    def test_line_length_exceeded(self):
        code = 'result = some_function(argument_one, argument_two, argument_three, argument_four, argument_five)\n'
        path = self.write_temp_file(code)
        issues = self.linter.lint_file(path)
        line_issues = [e for e in issues if e.code == 'L001']
        self.assertEqual(len(line_issues), 1)

    def test_trailing_whitespace(self):
        code = 'x = 1   \n'
        path = self.write_temp_file(code)
        issues = self.linter.lint_file(path)
        ws_issues = [e for e in issues if e.code == 'W001']
        self.assertEqual(len(ws_issues), 1)

    def test_no_trailing_whitespace(self):
        code = 'x = 1\n'
        path = self.write_temp_file(code)
        issues = self.linter.lint_file(path)
        ws_issues = [e for e in issues if e.code == 'W001']
        self.assertEqual(len(ws_issues), 0)

    def test_too_many_blank_lines(self):
        code = 'x = 1\n\n\n\n\ny = 2\n'
        path = self.write_temp_file(code)
        issues = self.linter.lint_file(path)
        blank_issues = [e for e in issues if e.code == 'B001']
        self.assertEqual(len(blank_issues), 1)

    def test_acceptable_blank_lines(self):
        code = 'x = 1\n\n\ny = 2\n'
        path = self.write_temp_file(code)
        issues = self.linter.lint_file(path)
        blank_issues = [e for e in issues if e.code == 'B001']
        self.assertEqual(len(blank_issues), 0)

    def test_tab_indentation_issue(self):
        code = '\tx = 1\n'
        path = self.write_temp_file(code)
        issues = self.linter.lint_file(path)
        indent_issues = [e for e in issues if e.code == 'I001']
        self.assertEqual(len(indent_issues), 1)

    def test_space_indentation_ok(self):
        code = '    x = 1\n'
        path = self.write_temp_file(code)
        issues = self.linter.lint_file(path)
        indent_issues = [e for e in issues if e.code == 'I001']
        self.assertEqual(len(indent_issues), 0)

    def test_wrong_indent_size(self):
        code = '   x = 1\n'
        path = self.write_temp_file(code)
        issues = self.linter.lint_file(path)
        indent_issues = [e for e in issues if e.code == 'I002']
        self.assertEqual(len(indent_issues), 1)

    def test_no_final_newline(self):
        code = 'x = 1'
        path = self.write_temp_file(code)
        issues = self.linter.lint_file(path)
        newline_issues = [e for e in issues if e.code == 'N001']
        self.assertEqual(len(newline_issues), 1)

    def test_final_newline_present(self):
        code = 'x = 1\n'
        path = self.write_temp_file(code)
        issues = self.linter.lint_file(path)
        newline_issues = [e for e in issues if e.code == 'N001']
        self.assertEqual(len(newline_issues), 0)

    def test_multiline_string_content_not_flagged(self):
        code = (
            'ART = """\n'
            ' x\n'
            '   y  \n'
            '\n'
            '\n'
            '\n'
            '\n'
            ' z\n'
            '"""\n'
            'x = 1\n'
        )
        path = self.write_temp_file(code)
        issues = self.linter.lint_file(path)
        codes = {e.code for e in issues}
        self.assertNotIn('I002', codes)
        self.assertNotIn('W001', codes)
        self.assertNotIn('B001', codes)

    def test_fix_preserves_multiline_string_content(self):
        body = ' x\n   y  \n\n\n\n\n z\n'
        code = f'ART = """\n{body}"""\nx = 1   \n'
        path = self.write_temp_file(code)
        count, fixes = self.linter.fix_file(path)
        result = Path(path).read_text()
        self.assertIn(body, result)
        self.assertIn('x = 1\n', result)

    def test_build_dirs_skipped(self):
        build_dir = Path(self.temp_dir) / 'main.build'
        build_dir.mkdir()
        (build_dir / 'junk.py').write_text('x = 1   ')
        bazel_dir = Path(self.temp_dir) / 'bazel-out'
        bazel_dir.mkdir()
        (bazel_dir / 'junk.py').write_text('x = 1   ')
        (Path(self.temp_dir) / 'real.py').write_text('y = 2   \n')
        issues = self.linter.lint_directory(self.temp_dir)
        files = {e.file for e in issues}
        self.assertEqual(len(files), 1)
        self.assertTrue(list(files)[0].endswith('real.py'))

    def test_file_not_found(self):
        issues = self.linter.lint_file('/nonexistent/file.py')
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0].code, 'E001')

    def test_non_python_file_ignored(self):
        path = self.write_temp_file('hello world', 'test.txt')
        issues = self.linter.lint_file(path)
        self.assertEqual(len(issues), 0)

    def test_custom_config(self):
        linter = Linter({'line_length': 40})
        code = '# this is a long comment that should be reported by the linter\n'
        path = self.write_temp_file(code)
        issues = linter.lint_file(path)
        line_issues = [e for e in issues if e.code == 'L001']
        self.assertEqual(len(line_issues), 1)


class TestParseYaml(unittest.TestCase):

    def test_parse_simple(self):
        content = 'line_length: 100\nindent_size: 2'
        result = parse_yaml(content)
        self.assertEqual(result['line_length'], 100)
        self.assertEqual(result['indent_size'], 2)

    def test_parse_bool(self):
        content = 'trailing_whitespace: true\ntab_indent: false'
        result = parse_yaml(content)
        self.assertTrue(result['trailing_whitespace'])
        self.assertFalse(result['tab_indent'])

    def test_parse_comments(self):
        content = '# comment\nline_length: 80'
        result = parse_yaml(content)
        self.assertEqual(result['line_length'], 80)
        self.assertNotIn('#', result)


class TestLoadConfig(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_load_yaml(self):
        path = os.path.join(self.temp_dir, 'config.yaml')
        with open(path, 'w') as f:
            f.write('line_length: 120\n')
        result = load_config(path)
        self.assertEqual(result['line_length'], 120)

    def test_load_yml(self):
        path = os.path.join(self.temp_dir, 'config.yml')
        with open(path, 'w') as f:
            f.write('line_length: 100\n')
        result = load_config(path)
        self.assertEqual(result['line_length'], 100)

    def test_wrong_extension(self):
        path = os.path.join(self.temp_dir, 'config.json')
        with open(path, 'w') as f:
            f.write('{}')
        with self.assertRaises(ValueError):
            load_config(path)

    def test_file_not_found(self):
        with self.assertRaises(FileNotFoundError):
            load_config('/nonexistent.yaml')


class TestWriteDefaultConfig(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_write_config(self):
        path = os.path.join(self.temp_dir, 'blue.yaml')
        write_default_config(path)
        self.assertTrue(os.path.exists(path))
        with open(path) as f:
            content = f.read()
        self.assertIn('line_length: 88', content)


class TestFormatIssues(unittest.TestCase):

    def test_format_no_issues(self):
        result = format_issues([])
        self.assertEqual(result, '')

    def test_format_single_issue(self):
        issues = [LintIssue('test.py', 1, 1, 'E001', 'Test issue')]
        result = format_issues(issues, color=False)
        self.assertIn('test.py:1:1:', result)
        self.assertIn('E001', result)

    def test_format_multiple_issues(self):
        issues = [
            LintIssue('test.py', 1, 1, 'E001', 'Issue 1'),
            LintIssue('test.py', 2, 1, 'W001', 'Warning 1'),
        ]
        result = format_issues(issues, color=False)
        lines = result.split('\n')
        self.assertEqual(len(lines), 2)


class TestLintDirectory(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.linter = Linter()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_lint_directory(self):
        path1 = os.path.join(self.temp_dir, 'test1.py')
        path2 = os.path.join(self.temp_dir, 'test2.py')
        with open(path1, 'w') as f:
            f.write('x = 1\n')
        with open(path2, 'w') as f:
            f.write('y = 2    \n')

        issues = self.linter.lint_directory(self.temp_dir)
        ws_issues = [e for e in issues if e.code == 'W001']
        self.assertEqual(len(ws_issues), 1)

    def test_lint_recursive(self):
        subdir = os.path.join(self.temp_dir, 'sub')
        os.makedirs(subdir)
        path = os.path.join(subdir, 'test.py')
        with open(path, 'w') as f:
            f.write('x = 1    \n')

        issues = self.linter.lint_directory(self.temp_dir, recursive=True)
        ws_issues = [e for e in issues if e.code == 'W001']
        self.assertEqual(len(ws_issues), 1)

    def test_lint_non_recursive(self):
        subdir = os.path.join(self.temp_dir, 'sub')
        os.makedirs(subdir)
        path = os.path.join(subdir, 'test.py')
        with open(path, 'w') as f:
            f.write('x = 1    \n')

        issues = self.linter.lint_directory(self.temp_dir, recursive=False)
        self.assertEqual(len(issues), 0)


if __name__ == '__main__':
    unittest.main()
