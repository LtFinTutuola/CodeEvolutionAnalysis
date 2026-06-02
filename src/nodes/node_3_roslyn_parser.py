"""
Node 3: Roslyn Parser (Semantic Analysis)

Responsibilities:
- Pipe raw text blobs and line coordinates to the persistent C# Roslyn server
- The server maps line numbers to AST nodes, constructs fully qualified signatures,
  and strips comments/trivia before returning sanitized code
- Populate parsed_hunks with semantic metadata
"""

from src.utils import get_roslyn_server, logger


def node_3_roslyn_parser(state):
    logger.info("=" * 60)
    logger.info("NODE 3: Roslyn Parser (Semantic Analysis)")
    logger.info("=" * 60)

    config = state["config"]
    raw_diffs = state["raw_diffs"]
    target_framework = config.get("target_framework", "net10.0")

    if not raw_diffs:
        logger.warning("No raw diffs to parse.")
        return {"parsed_hunks": []}

    server = get_roslyn_server(target_framework)
    parsed_hunks = []

    for i, diff_entry in enumerate(raw_diffs):
        if i % 50 == 0 and i > 0:
            logger.info(f"  Roslyn progress: {i}/{len(raw_diffs)} diffs processed...")

        commit_hash = diff_entry["commit_hash"]
        commit_date = diff_entry["commit_date"]
        file_path = diff_entry["file_path"]
        old_text = diff_entry["old_text"]
        new_text = diff_entry["new_text"]
        old_lines = diff_entry["old_lines"]
        new_lines = diff_entry["new_lines"]

        # Send to Roslyn server for semantic extraction
        census_results = server.census_extract(old_text, new_text, old_lines, new_lines)

        for result in census_results:
            signature = result.get("signature", "")
            parent_signature = result.get("parent_signature", "")
            clean_old = result.get("sanitized_old_code", "")
            clean_new = result.get("sanitized_new_code", "")

            # Skip entries where Roslyn couldn't resolve a signature
            if not signature:
                continue

            parsed_hunks.append({
                "commit_hash": commit_hash,
                "commit_date": commit_date,
                "file_path": file_path,
                "signature": signature,
                "parent_signature": parent_signature,
                "clean_old": clean_old,
                "clean_new": clean_new,
            })

    logger.info(
        f"Roslyn parsed {len(parsed_hunks)} semantic hunks from {len(raw_diffs)} raw diffs."
    )
    logger.info("Node 3 Finished.")

    return {"parsed_hunks": parsed_hunks}
