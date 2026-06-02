"""
Node 6: Exporter (Final Dump & Teardown)

Responsibilities:
- Serialize the census_dictionary to the output JSON file
- Gracefully terminate all persistent subprocesses (GitBatcher, RoslynServer)
- Log final summary statistics
"""

import os
import json
from src.utils import shutdown_subprocesses, logger


def node_6_exporter(state):
    logger.info("=" * 60)
    logger.info("NODE 6: Exporter (Final Dump & Teardown)")
    logger.info("=" * 60)

    config = state["config"]
    census = state.get("census_dictionary", {})
    output_path = config.get("output_json_path", "output/census.json")

    # ── Ensure output directory exists ───────────────────────────────────────
    output_dir = os.path.dirname(output_path)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)

    # ── Serialize census to JSON ─────────────────────────────────────────────
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(census, f, indent=2, ensure_ascii=False)

    file_size_kb = os.path.getsize(output_path) / 1024.0

    # ── Summary ──────────────────────────────────────────────────────────────
    total_classes = len(census)
    total_methods = sum(len(c.get("methods", {})) for c in census.values())
    total_events = sum(
        sum(m["hit_count"] for m in c.get("methods", {}).values())
        for c in census.values()
    )

    logger.info(f"Census exported to: {output_path} ({file_size_kb:.1f} KB)")
    logger.info(f"Final census: {total_classes} classes, {total_methods} methods, "
                f"{total_events} modification events.")

    # ── Teardown: terminate subprocesses ─────────────────────────────────────
    shutdown_subprocesses()

    logger.info("Node 6 Finished. Pipeline complete.")

    return state
