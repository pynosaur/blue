# blue

Simple Python linter with YAML configuration.

## Install

```bash
pget install blue
```

## Usage

```bash
# Lint current directory
blue

# Lint specific files or directories
blue src/ tests/
blue main.py

# Use custom config
blue -d myconfig.yaml

# Reset to default config
blue --reset

# Override line length
blue -l 120 .

# Quiet mode
blue -q .
```

## Configuration

Config file at `~/.config/blue/blue.yaml`:

```yaml
line_length: 88
indent_size: 4
max_blank_lines: 2
trailing_whitespace: true
final_newline: true
tab_indent: false
```

## Issue Codes

| Code | Description |
|------|-------------|
| E001 | File not found |
| E002 | Cannot read file |
| L001 | Line too long |
| W001 | Trailing whitespace |
| B001 | Too many blank lines |
| I001 | Wrong indentation character |
| I002 | Indentation not multiple of indent_size |
| N001 | No newline at end of file |
| S001 | Syntax error |

## Options

```
-d, --config PATH    Use custom YAML config file
--reset              Reset to default configuration
--show-config        Show current configuration
-r, --recursive      Recursively lint directories (default)
--no-recursive       Do not recurse into subdirectories
-l, --line-length N  Override max line length
--no-color           Disable colored output
-q, --quiet          Only show issue count
-v, --version        Show version
--apply              Auto-fix issues in-place
--docs               Show documentation
```

## License

MIT
