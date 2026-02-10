"""ViennaTalksBout CLI entry point.

Usage:
    python -m viennatalksbout          # Full ingestion pipeline (stream → extract → store)
    python -m viennatalksbout.ingest   # Same as above (explicit module)
"""

from viennatalksbout.ingest import main

if __name__ == "__main__":
    main()
