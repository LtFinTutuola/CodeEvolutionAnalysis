"""
Node 4: Semantic Filter (Gatekeeper & Anti-Move)

Responsibilities:
1. Noise Filter   — Drop hunks below the noise_cutoff_threshold (character delta)
2. Net Lines      — Calculate exact added/removed lines on sanitized code
3. Move Detection — Within the same commit, detect add+delete pairs that share
                    the same signature → elide them as spatial refactoring
"""

import hashlib
from collections import defaultdict
from src.utils import get_diff_char_count, calculate_net_lines, logger


def node_4_semantic_filter(state):
    logger.info("=" * 60)
    logger.info("NODE 4: Semantic Filter (Gatekeeper & Anti-Move)")
    logger.info("=" * 60)

    config = state["config"]
    parsed_hunks = state["parsed_hunks"]
    noise_cutoff = config.get("noise_cutoff_threshold", 10)
    logs = state.get("extraction_logs", [])

    if not parsed_hunks:
        logger.warning("No parsed hunks to filter.")
        return {"parsed_hunks": []}

    # ── Pass 1: Noise Filter ─────────────────────────────────────────────────
    logger.info(f"Pass 1: Noise filter (threshold = {noise_cutoff} chars)")
    after_noise = []
    noise_dropped = 0

    for hunk in parsed_hunks:
        char_delta = get_diff_char_count(hunk["clean_old"], hunk["clean_new"])
        if char_delta < noise_cutoff:
            noise_dropped += 1
            logs.append(
                f"  DISCARDED semantic hunk (below noise threshold {noise_cutoff}): "
                f"{hunk['logical_object']} in commit {hunk['commit_hash']} (char delta = {char_delta})"
            )
            continue
        logs.append(
            f"  COLLECTED semantic hunk (survived noise filter): "
            f"{hunk['logical_object']} in commit {hunk['commit_hash']} (char delta = {char_delta})"
        )
        after_noise.append(hunk)

    logger.info(
        f"  Noise filter: {noise_dropped} hunks dropped, "
        f"{len(after_noise)} surviving."
    )

    # ── Pass 2: Net Lines Calculation ────────────────────────────────────────
    logger.info("Pass 2: Calculating net added/removed lines")
    for hunk in after_noise:
        added, removed = calculate_net_lines(hunk["clean_old"], hunk["clean_new"])
        hunk["added_lines"] = added
        hunk["removed_lines"] = removed

    # ── Pass 3: Move Detection (Anti-Move) ───────────────────────────────────
    logger.info("Pass 3: Move detection (within same commit boundary)")

    # Group hunks by commit_hash
    by_commit = defaultdict(list)
    for hunk in after_noise:
        by_commit[hunk["commit_hash"]].append(hunk)

    final_hunks = []
    moves_elided = 0

    for commit_hash, commit_hunks in by_commit.items():
        # Separate pure additions (no old code) and pure deletions (no new code)
        additions = {}   # semantic_hash -> hunk
        deletions = {}   # semantic_hash -> hunk
        mixed = []       # hunks that have both old and new code (modifications)

        for hunk in commit_hunks:
            has_old = bool(hunk["clean_old"].strip())
            has_new = bool(hunk["clean_new"].strip())

            if has_old and not has_new:
                # Pure deletion
                sem_hash = _semantic_hash(hunk["clean_old"])
                deletions[sem_hash] = hunk
            elif has_new and not has_old:
                # Pure addition
                sem_hash = _semantic_hash(hunk["clean_new"])
                additions[sem_hash] = hunk
            else:
                # Modification (both old and new exist)
                mixed.append(hunk)

        # Check for matching add/delete pairs (same semantic hash = code move)
        matched_add_hashes = set()
        matched_del_hashes = set()

        for sem_hash in additions:
            if sem_hash in deletions:
                # Same code added somewhere and deleted elsewhere → spatial refactoring
                matched_add_hashes.add(sem_hash)
                matched_del_hashes.add(sem_hash)
                moves_elided += 1
                logs.append(
                    f"  DISCARDED semantic hunk (move detected/elided - exact code match): "
                    f"{additions[sem_hash]['logical_object']} in commit {commit_hash}"
                )

        # Also check by signature match (same method name moved between files)
        add_by_sig = {h["logical_object"]: (k, h) for k, h in additions.items() if k not in matched_add_hashes}
        del_by_sig = {h["logical_object"]: (k, h) for k, h in deletions.items() if k not in matched_del_hashes}

        for sig in add_by_sig:
            if sig in del_by_sig:
                matched_add_hashes.add(add_by_sig[sig][0])
                matched_del_hashes.add(del_by_sig[sig][0])
                moves_elided += 1
                logs.append(
                    f"  DISCARDED semantic hunk (move detected/elided - signature match): "
                    f"{sig} in commit {commit_hash}"
                )

        # Keep only non-matched hunks
        for hunk in commit_hunks:
            has_old = bool(hunk["clean_old"].strip())
            has_new = bool(hunk["clean_new"].strip())

            if has_old and not has_new:
                sem_hash = _semantic_hash(hunk["clean_old"])
                if sem_hash in matched_del_hashes:
                    continue
            elif has_new and not has_old:
                sem_hash = _semantic_hash(hunk["clean_new"])
                if sem_hash in matched_add_hashes:
                    continue

            logs.append(
                f"  COLLECTED semantic hunk (kept after move filter): "
                f"{hunk['logical_object']} in commit {commit_hash} (+{hunk['added_lines']}/-{hunk['removed_lines']})"
            )
            final_hunks.append(hunk)

    logger.info(f"  Move detection: {moves_elided} add/delete pairs elided.")
    logger.info(
        f"Semantic filter complete: {len(parsed_hunks)} → {len(final_hunks)} hunks "
        f"({len(parsed_hunks) - len(final_hunks)} total removed)."
    )
    logger.info("Node 4 Finished.")

    return {
        "parsed_hunks": final_hunks,
        "extraction_logs": logs,
    }


def _semantic_hash(code: str) -> str:
    """
    Compute a deterministic hash of sanitized code for move detection.
    Strips all whitespace to make the hash position-independent.
    """
    import re
    normalized = re.sub(r"\s+", "", code)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()
