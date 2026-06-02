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
    logger.info("NODE 5: Aggregator (Hierarchical Census)")
    logger.info("=" * 60)

    parsed_hunks = state["parsed_hunks"]
    # Retrieve existing census (supports future batching) or initialize empty
    census = state.get("census_dictionary") or {}

    if not parsed_hunks:
        logger.warning("No hunks to aggregate.")
        return {"census_dictionary": census}

    new_classes = 0
    new_methods = 0
    updated_methods = 0

    for hunk in parsed_hunks:
        parent_sig = hunk.get("parent_signature", "UnknownClass")
        method_sig = hunk["signature"]
        commit_hash = hunk["commit_hash"]
        commit_date = hunk.get("commit_date", "")
        added_lines = hunk.get("added_lines", 0)
        removed_lines = hunk.get("removed_lines", 0)

        # ── Ensure class-level entry exists ──────────────────────────────────
        if parent_sig not in census:
            census[parent_sig] = {
                "hit_count": 0,
                "methods": {},
            }
            new_classes += 1

        class_entry = census[parent_sig]

        # ── Ensure method-level entry exists ─────────────────────────────────
        if method_sig not in class_entry["methods"]:
            class_entry["methods"][method_sig] = {
                "hit_count": 0,
                "first_seen_date": commit_date,
                "history": [],
            }
            new_methods += 1
        else:
            updated_methods += 1

        method_entry = class_entry["methods"][method_sig]

        # ── Increment hit counts and append history ──────────────────────────
        class_entry["hit_count"] += 1
        method_entry["hit_count"] += 1

        method_entry["history"].append({
            "date": commit_date,
            "commit_hash": commit_hash,
            "added_lines": added_lines,
            "removed_lines": removed_lines,
        })

    # ── Summary statistics ───────────────────────────────────────────────────
    total_classes = len(census)
    total_methods = sum(len(c["methods"]) for c in census.values())
    total_events = sum(
        sum(m["hit_count"] for m in c["methods"].values())
        for c in census.values()
    )

    logger.info(f"Census update: +{new_classes} new classes, +{new_methods} new methods, "
                f"{updated_methods} method updates.")
    logger.info(f"Census totals: {total_classes} classes, {total_methods} methods, "
                f"{total_events} total modification events.")
    logger.info("Node 5 Finished.")

    return {"census_dictionary": census}
