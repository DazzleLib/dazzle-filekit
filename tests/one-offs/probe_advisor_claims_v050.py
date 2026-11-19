"""Check two claims from the 2026-11-18 placement review, first hand.

1. With unctools blocked, does ``import dazzle_filekit`` still succeed?
   (filekit's docs promise it does; 0.5.0's portable.py imports unctools at
   module top.)
2. What does normalize_cross_platform_path make of an extended-length UNC
   path, ``\\\\?\\UNC\\srv\\share\\a``? (Claim: a path under the current folder.)

Reads no file of the user's and writes nothing. Each check runs in a child
Python so the block cannot leak into this process.
Usage: python tests/one-offs/probe_advisor_claims_v050.py
"""
import subprocess
import sys

BLOCKED_IMPORT = r"""
import sys
sys.modules['unctools'] = None          # any 'import unctools' now raises ImportError
try:
    import dazzle_filekit
    print('import ok; unctools imported:', sys.modules.get('unctools') is not None)
except ImportError as exc:
    print('import FAILED:', exc)
"""

PLAIN_IMPORT = r"""
import sys
import dazzle_filekit
print('unctools loaded by a plain import:', 'unctools' in sys.modules)
"""

UNC = r"""
from dazzle_filekit.paths import normalize_cross_platform_path as n
for p in ['\\\\?\\UNC\\srv\\share\\a', '\\\\?\\C:\\Users\\x', '\\\\srv\\share\\a']:
    print(repr(p), '->', repr(str(n(p, expand=False))))
"""

for title, code in (("1a. import with unctools blocked", BLOCKED_IMPORT),
                    ("1b. plain import", PLAIN_IMPORT),
                    ("2. extended-length paths through the normalizer", UNC)):
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    print(title)
    print("   " + (out.stdout.strip() or out.stderr.strip().splitlines()[-1]).replace("\n", "\n   "))
