"""
Node 5: Mapper (Overlay and Orphan Management)

Responsibilities:
- Ingest the Baseline (from Node 1b) and Filtered Historical Diffs (from Node 4).
- Temporarily convert the Baseline into a dictionary for O(1) lookups.
- Iterate chronologically over the historical diffs and overlay them onto the baseline.
- If a logical object exists, increment hit count and append commit.
- If a logical object DOES NOT exist (Dead Code), create it on the fly and mark as is_dead_code=True.
- Return the flat dictionary.
"""

from src.utils import logger
from src.nodes.node_1b_baseline_manager import get_project_name


def node_5_mapper(state):
    logger.info("=" * 60)
    logger.info("NODE 5: Mapper (Overlay & Orphan Management)")
    logger.info("=" * 60)

    config = state["config"]
    repo_path = config["repo_path"]
    baseline_objects = state.get("baseline_objects", [])
    parsed_hunks = state.get("parsed_hunks", [])
    logs = state.get("extraction_logs", [])

    logger.info(f"Loaded {len(baseline_objects)} baseline objects.")
    logger.info(f"Loaded {len(parsed_hunks)} historical diff hunks.")

    # Convert Baseline to O(1) lookup dictionary
    mapping_dict = {}
    for obj in baseline_objects:
        obj_id = obj["logical_object"]
        mapping_dict[obj_id] = obj

    orphans_created = 0

    for hunk in parsed_hunks:
        obj_id = hunk["logical_object"]
        commit_hash = hunk["commit_hash"]
        commit_date = hunk["commit_date"]
        commit_desc = hunk["commit_description"]
        file_path = hunk["file_path"]
        
        # Ensure the project field is resolved dynamically
        project = get_project_name(file_path, repo_path)

        commit_obj = {
            "commit_hash": commit_hash,
            "commit_description": commit_desc,
            "commit_date": commit_date
        }

        if obj_id in mapping_dict:
            target = mapping_dict[obj_id]
            target["hit_count"] += 1
            if not target["first_seen_date"]:
                target["first_seen_date"] = commit_date
            target["last_seen_date"] = commit_date
            target["commits"].append(commit_obj)
        else:
            # The Dead Code Paradox
            orphans_created += 1
            mapping_dict[obj_id] = {
                "logical_object": obj_id,
                "parent_object": hunk["parent_object"],
                "project": project,
                "first_seen_date": commit_date,
                "last_seen_date": commit_date,
                "hit_count": 1,
                "commits": [commit_obj],
                "is_dead_code": True
            }

    logs.append(f"MAPPED {len(parsed_hunks)} hunks onto the baseline.")
    logs.append(f"IDENTIFIED {orphans_created} dead code (orphan) objects.")

    logger.info(f"Mapping complete. Orphans (Dead Code) created: {orphans_created}")
    logger.info("Node 5 Finished.")

    # Flatten the mapping_dict to a list before passing to Node 6
    final_census = list(mapping_dict.values())

    return {
        "census_entries": final_census,
        "extraction_logs": logs
    }
