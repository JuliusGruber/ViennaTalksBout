"""TalkBout CLI entry point.

Usage:
    python -m talkbout          # Full ingestion pipeline (stream → extract → store)
    python -m talkbout.ingest   # Same as above (explicit module)
"""

from talkbout.ingest import main

if __name__ == "__main__":
    main()
