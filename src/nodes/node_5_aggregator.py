"""
Node 5: Aggregator (Hierarchical Census)

Responsibilities:
- Build and maintain the census_dictionary from surviving parsed_hunks
- Hierarchical structure: Class → Method → History events
- Track hit counts, first-seen dates, and per-event line metrics
"""

import os
from src.utils import logger

PROJECT_CACHE = {}

def get_project_name(file_path, repo_path):
    dir_name = os.path.dirname(file_path)
    if dir_name in PROJECT_CACHE:
        return PROJECT_CACHE[dir_name]
        
    current_dir = os.path.join(repo_path, dir_name)
    
    while current_dir and len(current_dir) >= len(repo_path):
        if os.path.isdir(current_dir):
            try:
                csprojs = [f for f in os.listdir(current_dir) if f.endswith('.csproj')]
                if csprojs:
                    project = csprojs[0].replace('.csproj', '')
                    PROJECT_CACHE[dir_name] = project
                    return project
            except OSError:
                pass
        parent = os.path.dirname(current_dir)
        if parent == current_dir:
            break
        current_dir = parent
        
    parts = file_path.replace('\\', '/').split('/')
    fallback = parts[0] if parts else "Unknown"
    PROJECT_CACHE[dir_name] = fallback
    return fallback

def node_5_aggregator(state):
    logger.info("=" * 60)
    logger.info("NODE 5: Aggregator (Logical Object Census)")
    logger.info("=" * 60)

    parsed_hunks = state["parsed_hunks"]
    repo_path = state["config"]["repo_path"]
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
            "project": get_project_name(hunk.get("file_path", ""), repo_path),
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
