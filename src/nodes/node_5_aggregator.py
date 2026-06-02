"""
Node 5: Aggregator (Hierarchical Census)

Responsibilities:
- Build and maintain the census_dictionary from surviving parsed_hunks
- Hierarchical structure: Class → Method → History events
- Track hit counts, first-seen dates, and per-event line metrics
"""

from src.utils import logger


def node_5_aggregator(state):
    logger.info("=" * 60)
    logger.info("NODE 5: Aggregator (Logical Object Census)")
    logger.info("=" * 60)

    parsed_hunks = state["parsed_hunks"]
    logs = state.get("extraction_logs", [])
    census_entries = state.get("census_entries") or []

    if not parsed_hunks:
        logger.warning("No hunks to aggregate.")
        return {"census_entries": census_entries}

    for hunk in parsed_hunks:
        entry = {
            "commit_description": hunk.get("commit_description", "No description"),
            "commit_hash": hunk["commit_hash"],
            "commit_date": hunk.get("commit_date", ""),
            "signature": hunk.get("full_signature", ""),
            "logical_object": hunk["logical_object"],
            "parent_object": hunk.get("parent_signature", ""),
            "added_lines": hunk.get("added_lines", 0),
            "removed_lines": hunk.get("removed_lines", 0),
        }
        census_entries.append(entry)

    logs.append(f"AGGREGATOR: Processed {len(parsed_hunks)} hunks into {len(census_entries)} logical object entries.")

    logger.info(f"Census totals: {len(census_entries)} logical object entries.")
    logger.info("Node 5 Finished.")

    return {
        "census_entries": census_entries,
        "extraction_logs": logs,
    }
