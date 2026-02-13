"""ViennaTalksBout CLI entry point.

Usage:
    python -m viennatalksbout            # Web UI + pipeline (default)
    python -m viennatalksbout --ingest   # Pipeline-only mode (no web server)
"""

import sys

if "--ingest" in sys.argv:
    from viennatalksbout.ingest import main
else:
    from viennatalksbout.web import main

main()
