"""Gap documentation: primitives MISSING from filekit v0.2.3.

Each test in this file asserts that a specific primitive is NOT available
in the current codebase. These tests PASS today (documenting the gap) and
must FAIL (or be deleted) once the corresponding feature lands.

The phase in which each gap closes:

  Phase 4 (paths):
    (none -- the path enrichments don't add new names)

  Phase 5 (metadata):
    - dazzle_filekit.metadata module (new)
    - metadata.collect_file_metadata with SDDL ACLs
    - metadata.apply_file_metadata with ctime restoration
    - metadata.restore_windows_creation_time
    - metadata.is_win32_available

  Phase 6 (primitives):
    - operations.atomic_write_text
    - operations.atomic_write_json
    - operations.copy_tree_preserving_links
    - utils.compat.is_wsl

  Phase 7 (ADS + junction fix):
    - platform.windows.detect_alternate_streams
    - platform.windows.has_significant_ads
    - validation.is_junction (fix, not new)

When a gap closes, either flip the assertion (``not hasattr`` -> ``hasattr``)
or delete the test entirely. DO NOT silently skip.
"""

import importlib

import pytest


# Phase 5 metadata gaps — CLOSED in v0.2.4. See
# tests/characterization/test_metadata_behavior.py::TestFilekitMetadataModuleV024
# for the locked-in assertions of the new capabilities.


# Phase 6 primitive gaps -- CLOSED in v0.2.4. See
# tests/test_operations_primitives_v024.py for locked-in assertions.


# Phase 7 ADS + junction gaps -- CLOSED in v0.2.4. See
# tests/test_ads_and_junction_v024.py for locked-in assertions.
