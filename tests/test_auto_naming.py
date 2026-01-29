"""Test the auto-naming logic."""
import re

# Mock the dependencies
class MockPath:
    def __init__(self, path_str):
        self._path = path_str.replace('\\', '/')
        self._parts = tuple(p for p in self._path.split('/') if p)

    @property
    def name(self):
        return self._parts[-1] if self._parts else ''

    @property
    def parts(self):
        return self._parts

    @property
    def parent(self):
        if len(self._parts) <= 1:
            return self
        return MockPath('/'.join(self._parts[:-1]))

    def __eq__(self, other):
        return self._path == other._path if isinstance(other, MockPath) else False

    def __str__(self):
        return self._path

def normalize_cross_platform_path(p):
    return MockPath(p)

def debug_log(msg):
    pass

GENERIC_FOLDER_NAMES = {
    'home', 'user', 'users', 'code', 'projects', 'project', 'work',
    'dev', 'development', 'src', 'source', 'app', 'apps', 'local',
    'current', 'main', 'master', 'opt', 'var', 'tmp', 'temp',
    'desktop', 'documents', 'downloads', 'repos', 'repository',
    'github', 'gitlab', 'bitbucket', 'workspace', 'workspaces',
}
DRIVE_LETTERS = {'c', 'd', 'e', 'f', 'g', 'h', 'z'}

def _sanitize_folder_name(name):
    sanitized = re.sub(r'[^a-zA-Z0-9_-]', '-', name.lower())
    sanitized = re.sub(r'-+', '-', sanitized)
    return sanitized.strip('-')

def derive_session_name_from_cwd(cwd):
    """Strategy: non-generic folder -> use it; otherwise -> path from nearest non-generic ancestor (with drive letter)"""
    if not cwd:
        return None
    path = normalize_cross_platform_path(cwd)

    # Use path.parts to get all components including drive letter
    try:
        all_parts = path.parts
    except AttributeError:
        path_str = str(path).replace('\\', '/')
        all_parts = [p for p in path_str.split('/') if p]

    # Collect last 4 meaningful parts with metadata
    parts = []  # (sanitized, raw, is_drive)
    for part in all_parts[-4:]:
        raw = part.rstrip(':\\/')
        sanitized = _sanitize_folder_name(raw)
        if sanitized:
            is_drive = sanitized in DRIVE_LETTERS
            parts.append((sanitized, raw.lower(), is_drive))

    if not parts:
        return None

    # Strategy 1: Non-generic current folder (not drive) -> use it alone
    current_name, current_raw, current_is_drive = parts[-1]
    if current_raw not in GENERIC_FOLDER_NAMES and not current_is_drive and len(current_name) >= 3:
        return current_name[:50]

    # Strategy 2: Find nearest non-generic ancestor (not drive), use path from there
    start_idx = 0
    for i in range(len(parts) - 2, -1, -1):
        _, raw, is_drive = parts[i]
        if raw not in GENERIC_FOLDER_NAMES and not is_drive:
            start_idx = i
            break

    path_parts = [s for s, r, d in parts[start_idx:] if len(s) >= 1]
    if path_parts:
        path_name = '--'.join(path_parts)
        if len(path_name) > 50:
            path_name = path_name[:50].rsplit('--', 1)[0]
        return path_name
    return None

if __name__ == '__main__':
    # Test cases - (path, expected_name)
    test_cases = [
        (r'C:\code\claude-code-task-manager', 'claude-code-task-manager'),  # Non-generic folder
        (r'C:\code', 'c--code'),                                            # Generic + drive -> include drive
        (r'C:\code\local', 'c--code--local'),                               # All generic -> include drive
        (r'C:\code\my-project\local', 'my-project--local'),                 # Has non-generic parent
        (r'C:\Users\Extreme\Documents', 'extreme--documents'),              # Has non-generic parent
        ('/home/dev/projects/my-app', 'my-app'),                            # Non-generic folder
        ('/opt/STAGING/current', 'staging--current'),                       # Has non-generic parent
        (r'Z:\code\project', 'z--code--project'),                             # All generic on Z drive
        (r'Z:\code', 'z--code'),                                            # Generic on Z drive
    ]

    print("Path -> Auto-generated Name")
    print("-" * 70)
    for path, expected in test_cases:
        result = derive_session_name_from_cwd(path)
        status = "OK" if result == expected else f"FAIL (expected: {expected})"
        print(f'{path:45} -> {result:20} {status}')
