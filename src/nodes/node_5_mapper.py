"""
Node 5: Mapper (Overlay, Time Decay & Impact Scoring)

Responsibilities:
- Ingest the Baseline (from Node 1b) and Filtered Historical Diffs (from Node 4).
- Temporarily convert the Baseline into a dictionary for O(1) lookups.
- Iterate chronologically over the historical diffs and overlay them onto the baseline.
- For each diff, calculate:
    1. Time Decay multiplier (weighted average of repo-lifespan and object-lifespan decay)
    2. Final Impact = diff_score × time_multiplier
    3. Accumulate impact_score per active method
- Dead Code Paradox: if a historical diff involves a method that no longer exists,
  DO NOT add it to the active method map. Instead, sum its final_impact to
  legacy_impact_score on the parent_object.
- Per-commit auditability: each commit entry stores a 'scores' sub-object with
  diff_score and lifespan_time_multiplier.
"""

from datetime import datetime
from src.utils import logger
from src.nodes.node_1b_baseline_manager import get_project_name


def _parse_date(date_str):
    """
    Parse a Git commit date string to a datetime object.
    Handles ISO-like formats: '2024-01-15 10:30:00 +0200'
    Returns None if parsing fails.
    """
    if not date_str:
        return None
    try:
        # Git %ci format: '2024-01-15 10:30:00 +0200'
        # Strip the timezone offset for naive datetime comparison
        clean = date_str.strip()
        # Try ISO format first
        if "T" in clean:
            return datetime.fromisoformat(clean)
        # Git %ci format: remove timezone offset
        parts = clean.rsplit(" ", 1)
        if len(parts) == 2 and (parts[1].startswith("+") or parts[1].startswith("-")):
            return datetime.strptime(parts[0], "%Y-%m-%d %H:%M:%S")
        return datetime.strptime(clean, "%Y-%m-%d %H:%M:%S")
    except (ValueError, TypeError):
        logger.warning(f"Failed to parse date: '{date_str}', defaulting to None")
        return None


def calculate_time_multiplier(commit_date_str, repo_first_date_str, repo_last_date_str):
    """
    Calculate a Time Decay multiplier ∈ [0, 1].

    The most recent a diff is, the closer its multiplier is to 1.0.
    The older a diff is, the closer its multiplier is to 0.0.
    This penalizes ancient changes (now "framework" code) and highlights current "Hot Zones".

    Formula:
        lifespan_decay = (commit_date - repo_first) / (repo_last - repo_first)

    Returns:
        float: lifespan_time_multiplier
    """
    commit_dt = _parse_date(commit_date_str)
    repo_first_dt = _parse_date(repo_first_date_str)
    repo_last_dt = _parse_date(repo_last_date_str)

    # Edge case: if any critical date is missing, return neutral multiplier
    if not commit_dt or not repo_first_dt or not repo_last_dt:
        return 1.0

    # ── Lifespan Decay ────────────────────────────────────────────────────
    # How old is this commit relative to the entire repo history?
    total_span = (repo_last_dt - repo_first_dt).total_seconds()
    if total_span <= 0:
        # Single-commit repo or same-day first/last
        lifespan_decay = 1.0
    else:
        commit_age = (commit_dt - repo_first_dt).total_seconds()
        lifespan_decay = max(0.0, min(1.0, commit_age / total_span))

    return lifespan_decay


def node_5_mapper(state):
    logger.info("=" * 60)
    logger.info("NODE 5: Mapper (Overlay, Time Decay & Impact Scoring)")
    logger.info("=" * 60)

    config = state["config"]
    repo_path = config["repo_path"]
    baseline_objects = state.get("baseline_objects", [])
    parsed_hunks = state.get("parsed_hunks", [])
    logs = state.get("extraction_logs", [])

    # ── Load Time Decay configuration ────────────────────────────────────
    repo_first_date = state.get("repo_first_commit_date", "")
    repo_last_date = state.get("repo_last_commit_date", "")

    logger.info(f"Loaded {len(baseline_objects)} baseline objects.")
    logger.info(f"Loaded {len(parsed_hunks)} historical diff hunks.")
    logger.info(f"Repo temporal boundaries: first={repo_first_date}, last={repo_last_date}")

    # ── Convert Baseline to O(1) lookup dictionary ───────────────────────
    mapping_dict = {}
    for obj in baseline_objects:
        obj_id = obj["logical_object"]
        # Initialize impact scoring fields
        obj["impact_score"] = 0.0
        obj["legacy_impact_score"] = 0.0
        mapping_dict[obj_id] = obj

    orphans_created = 0
    dead_code_impacts = 0

    # ── Process hunks chronologically ────────────────────────────────────
    for hunk in parsed_hunks:
        obj_id = hunk["logical_object"]
        commit_hash = hunk["commit_hash"]
        commit_date = hunk["commit_date"]
        commit_desc = hunk["commit_description"]
        file_path = hunk["file_path"]
        parent_obj = hunk["parent_object"]
        diff_score = hunk.get("diff_score", 0.0)

        # ── Apply Signature Change scoring ───────────────────────
        if hunk.get("is_signature_change", False):
            diff_score = config.get("signature_changed_diff_score", 0.10)
        # ── Apply Auto-Calibration for Added/Removed methods ─────────
        elif hunk.get("is_new_or_dead", False):
            obj_type = hunk.get("object_type", "method")
            min_scores = config.get("min_creation_scores", {})
            base_score = float(min_scores.get(obj_type, 0.05))
            
            if obj_type == "field":
                diff_score = base_score
            else:
                threshold_key = f"max_{obj_type}_threshold"
                specific_threshold = config.get(threshold_key, 17.0)
                
                raw_score = hunk.get("raw_complexity_score", 0)
                scale_factor = min(1.0, float(raw_score) / max(1.0, float(specific_threshold)))
                
                diff_score = base_score + (scale_factor * (1.0 - base_score))


        # Ensure the project field is resolved dynamically
        project = get_project_name(file_path, repo_path)

        # ── Calculate Time Decay multiplier ──────────────────────────
        lifespan_mult = calculate_time_multiplier(
            commit_date, repo_first_date, repo_last_date
        )

        # ── Final Impact = diff_score × time_multiplier ──────────────
        final_impact = diff_score * lifespan_mult

        # ── Build per-commit auditability scores ─────────────────────
        commit_obj = {
            "commit_hash": commit_hash,
            "commit_description": commit_desc,
            "commit_date": commit_date,
            "scores": {
                "diff_score": round(diff_score, 6),
                "lifespan_time_multiplier": round(lifespan_mult, 6)
            }
        }

        if obj_id in mapping_dict:
            # ── Active method: accumulate impact ─────────────────────
            target = mapping_dict[obj_id]
            target["hit_count"] += 1
            if not target["first_seen_date"]:
                target["first_seen_date"] = commit_date
            target["last_seen_date"] = commit_date
            target["commits"].append(commit_obj)
            target["impact_score"] += final_impact

            logs.append(
                f"  MAPPED active: {obj_id} | diff_score={diff_score:.4f} × "
                f"time_mult={lifespan_mult:.4f} = impact={final_impact:.4f}"
            )
        else:
            # ── Dead Code Paradox ────────────────────────────────────
            # The method no longer exists in the current codebase.
            # DO NOT add it to the active method map.
            # Instead, sum its final_impact to legacy_impact_score on parent_object.
            dead_code_impacts += 1

            # Find or create the parent object entry to accumulate legacy impact
            if parent_obj and parent_obj in mapping_dict:
                mapping_dict[parent_obj]["legacy_impact_score"] += final_impact
                logs.append(
                    f"  DEAD CODE: {obj_id} → legacy impact {final_impact:.4f} "
                    f"added to parent {parent_obj}"
                )
            elif parent_obj:
                # Parent class doesn't exist yet in the mapping — create a class-level entry
                orphans_created += 1
                mapping_dict[parent_obj] = {
                    "logical_object": parent_obj,
                    "parent_object": "",
                    "project": project,
                    "first_seen_date": commit_date,
                    "last_seen_date": commit_date,
                    "hit_count": 0,
                    "commits": [],
                    "is_dead_code": False,
                    "impact_score": 0.0,
                    "legacy_impact_score": final_impact,
                }
                logs.append(
                    f"  DEAD CODE: {obj_id} → created parent entry {parent_obj} "
                    f"with legacy impact {final_impact:.4f}"
                )
            else:
                # No parent available — log and discard
                logs.append(
                    f"  DEAD CODE ORPHAN: {obj_id} has no parent_object, "
                    f"impact {final_impact:.4f} discarded"
                )

    logs.append(f"MAPPED {len(parsed_hunks)} hunks onto the baseline.")
    logs.append(f"DEAD CODE impacts distributed: {dead_code_impacts}")
    logs.append(f"PARENT ENTRIES created for dead code: {orphans_created}")

    logger.info(f"Mapping complete. Dead code impacts: {dead_code_impacts}, Parent entries created: {orphans_created}")
    logger.info("Node 5 Finished.")

    # Flatten the mapping_dict to a list before passing to Node 6
    final_census = list(mapping_dict.values())

    return {
        "census_entries": final_census,
        "extraction_logs": logs
    }
