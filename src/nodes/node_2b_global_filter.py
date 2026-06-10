"""
Node 2b: Global Filter
Responsibilities:
- Acts as a global gatekeeper before semantic mapping.
- Reads 'files_blacklist' from the config to filter out non-production code.
- Purges matching items from 'baseline_objects'.
- Purges matching items from 'raw_diffs'.
"""

from src.utils import logger, audit_snapshot

def node_2b_global_filter(state):
    logger.info("=" * 60)
    logger.info("NODE 2b: Global Filter (Gatekeeper)")
    logger.info("=" * 60)

    config = state.get("config", {})
    blacklist = config.get("files_blacklist", [])
    
    # Safety check to ensure blacklist is a list of strings, not a string of characters
    if isinstance(blacklist, str):
        blacklist = [blacklist]
    elif not isinstance(blacklist, list):
        blacklist = []

    baseline_objects = state.get("baseline_objects", [])
    raw_diffs = state.get("raw_diffs", [])
    logs = state.get("extraction_logs", [])

    if not blacklist:
        logger.info("No files_blacklist defined in config. Skipping filter.")
        return state

    logger.info(f"Loaded blacklist with {len(blacklist)} patterns.")

    import os
    # Sterilize blacklist patterns for baseline matching (strip file extensions)
    baseline_blacklist = [os.path.splitext(p)[0] for p in blacklist]

    # ── Baseline Purge ───────────────────────────────────────────────────
    original_baseline_count = len(baseline_objects)
    
    filtered_baseline = []
    for obj in baseline_objects:
        # Baseline objects are dictionaries. They only contain logical names, no file_paths.
        # Use safe .get() to avoid KeyErrors
        logical_object = obj.get("logical_object", "") if isinstance(obj, dict) else getattr(obj, "logical_object", "")
        if not any(bp in logical_object for bp in baseline_blacklist):
            filtered_baseline.append(obj)
            
    baseline_purged = original_baseline_count - len(filtered_baseline)

    # ── Diffs Purge ──────────────────────────────────────────────────────
    original_diffs_count = len(raw_diffs)
    
    filtered_diffs = []
    for diff in raw_diffs:
        # Raw diffs are dictionaries. Use safe .get() to prevent attribute errors.
        file_path = diff.get("file_path", "") if isinstance(diff, dict) else getattr(diff, "file_path", "")
        if not any(pattern in file_path for pattern in blacklist):
            filtered_diffs.append(diff)
        
    diffs_purged = original_diffs_count - len(filtered_diffs)

    logger.info(f"Purged {baseline_purged} baseline objects.")
    logger.info(f"Purged {diffs_purged} raw diffs.")
    logs.append(f"GLOBAL FILTER: Purged {baseline_purged} baseline objects and {diffs_purged} raw diffs.")

    audit_snapshot({
        "baseline_count_after": len(filtered_baseline),
        "diffs_count_after": len(filtered_diffs),
        "purged_baseline": baseline_purged,
        "purged_diffs": diffs_purged
    }, "node_2b_global_filter", "After Purge", config)

    logger.info("Node 2b Finished.")

    return {
        "baseline_objects": filtered_baseline,
        "raw_diffs": filtered_diffs,
        "extraction_logs": logs
    }
