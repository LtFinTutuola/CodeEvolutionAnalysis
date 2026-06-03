"""
Node 6: Exporter (Final Dump & Teardown)

Responsibilities:
- Serialize the census_dictionary to the output JSON file
- Gracefully terminate all persistent subprocesses (GitBatcher, RoslynServer)
- Log final summary statistics
"""

import os
import json
from datetime import datetime
from src.utils import shutdown_subprocesses, logger


def node_6_exporter(state):
    logger.info("=" * 60)
    logger.info("NODE 6: Exporter (Final Dump & Teardown)")
    logger.info("=" * 60)

    config = state["config"]
    census_entries = state.get("census_entries", [])
    output_path = config.get("output_json_path", "output/pr_census.json")
    produce_log = config.get("produce_log", False)
    logs = state.get("extraction_logs", [])

    # ── Ensure output directory exists ───────────────────────────────────────
    output_dir = os.path.dirname(output_path) or "output"
    os.makedirs(output_dir, exist_ok=True)

    # ── Timestamped Filenames ────────────────────────────────────────────────
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    census_filename = f"{timestamp}_code_mapping.json"
    log_filename = f"{timestamp}_log.txt"

    final_census_path = os.path.join(output_dir, census_filename)
    final_log_path = os.path.join(output_dir, log_filename)

    # ── Serialize census entries to JSON ─────────────────────────────────────
    with open(final_census_path, "w", encoding="utf-8") as f:
        json.dump(census_entries, f, indent=2, ensure_ascii=False)

    file_size_kb = os.path.getsize(final_census_path) / 1024.0
    logger.info(f"Census exported to: {final_census_path} ({file_size_kb:.1f} KB)")

    # ── Write log if configured ──────────────────────────────────────────────
    if produce_log:
        logs.append(f"EXPORTER: Wrote {len(census_entries)} entries to {final_census_path}.")
        with open(final_log_path, "w", encoding="utf-8") as f:
            f.write("\n".join(logs) + "\n")
        logger.info(f"Extraction log written to: {final_log_path}")

    # ── Summary ──────────────────────────────────────────────────────────────
    logger.info(f"Final census totals: {len(census_entries)} logical object entries.")

    # ── Teardown: terminate subprocesses ─────────────────────────────────────
    shutdown_subprocesses()

    logger.info("Node 6 Finished. Pipeline complete.")

    return state
