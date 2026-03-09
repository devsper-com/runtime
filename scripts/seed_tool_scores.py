#!/usr/bin/env python3
"""
Seed the default tool score DB with sample data so 'hivemind tools' and
'hivemind analytics' show a populated table. Optional: run before test_tool_scoring_full.sh.
Usage: uv run python scripts/seed_tool_scores.py
"""

from hivemind.tools.scoring import get_default_score_store

def main():
    store = get_default_score_store()
    # read_file: mostly success, some failures
    for _ in range(8):
        store.record("read_file", "general", True, 50)
    for _ in range(2):
        store.record("read_file", "general", False, 10, "FileNotFoundError")
    # write_file: all success, fast
    for _ in range(12):
        store.record("write_file", "general", True, 30)
    # list_directory: mixed
    for _ in range(5):
        store.record("list_directory", "general", True, 80)
    for _ in range(3):
        store.record("list_directory", "general", False, 5, "PermissionError")
    print("Seeded: read_file, write_file, list_directory")
    print("Run: hivemind tools")
    print("Run: hivemind analytics")

if __name__ == "__main__":
    main()
