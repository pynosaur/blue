import sys
from pathlib import Path


def find_doc_file():
    locations = [
        Path(__file__).parent.parent.parent / 'doc' / 'plack.yaml',
        Path.cwd() / 'doc' / 'plack.yaml',
        Path.home() / '.pget' / 'helpers' / 'plack' / 'doc' / 'plack.yaml',
    ]

    for loc in locations:
        if loc.exists():
            return loc

    return None


def parse_yaml_simple(content):
    result = {}
    current_key = None
    current_list = None

    for line in content.split('\n'):
        if not line.strip() or line.strip().startswith('#'):
            continue

        if line[0] not in ' \t' and ':' in line:
            if current_key and current_list is not None:
                result[current_key] = current_list

            key, _, value = line.partition(':')
            current_key = key.strip()
            value = value.strip()

            if value:
                result[current_key] = value
                current_list = None
            else:
                current_list = []
        elif current_list is not None and line.strip().startswith('-'):
            item = line.strip()[1:].strip()
            current_list.append(item)

    if current_key and current_list is not None:
        result[current_key] = current_list

    return result


def show_docs():
    doc_path = find_doc_file()

    if not doc_path:
        print('Documentation not found', file=sys.stderr)
        return

    content = doc_path.read_text(encoding='utf-8')
    data = parse_yaml_simple(content)

    CYAN = '\033[36m'
    YELLOW = '\033[33m'
    GREEN = '\033[32m'
    RESET = '\033[0m'

    if 'NAME' in data:
        print(f"{CYAN}NAME{RESET}")
        print(f"    {data['NAME']}")
        print()

    if 'VERSION' in data:
        print(f"{CYAN}VERSION{RESET}")
        print(f"    {data['VERSION']}")
        print()

    if 'DESCRIPTION' in data:
        print(f"{CYAN}DESCRIPTION{RESET}")
        print(f"    {data['DESCRIPTION']}")
        print()

    if 'USAGE' in data:
        print(f"{CYAN}USAGE{RESET}")
        print(f"    {YELLOW}{data['USAGE']}{RESET}")
        print()

    if 'OPTIONS' in data:
        print(f"{CYAN}OPTIONS{RESET}")
        if isinstance(data['OPTIONS'], list):
            for opt in data['OPTIONS']:
                print(f"    {GREEN}{opt}{RESET}")
        print()

    if 'CONFIG' in data:
        print(f"{CYAN}CONFIG{RESET}")
        if isinstance(data['CONFIG'], list):
            for item in data['CONFIG']:
                print(f"    {item}")
        print()

    if 'ISSUE_CODES' in data:
        print(f"{CYAN}ISSUE CODES{RESET}")
        if isinstance(data['ISSUE_CODES'], list):
            for code in data['ISSUE_CODES']:
                print(f"    {code}")
        print()

    if 'EXAMPLES' in data:
        print(f"{CYAN}EXAMPLES{RESET}")
        if isinstance(data['EXAMPLES'], list):
            for ex in data['EXAMPLES']:
                print(f"    {YELLOW}{ex}{RESET}")
        print()

    if 'AUTHOR' in data:
        print(f"{CYAN}AUTHOR{RESET}")
        print(f"    {data['AUTHOR']}")
        print()
