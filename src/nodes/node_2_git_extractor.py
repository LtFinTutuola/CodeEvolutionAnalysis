"""
Node 2: Git Extractor (Fast Targeting)

Responsibilities:
- Iterate over commits_to_process
- For each commit, identify C# files with substantive non-formatting changes
- Extract raw text blobs (pre/post commit) via the persistent GitBatcher
- Compute exact modified line numbers for Roslyn mapping
"""

from src.utils import execute_git, get_git_batcher, get_changed_line_numbers, logger


def node_2_git_extractor(state):
    logger.info("=" * 60)
    logger.info("NODE 2: Git Extractor (Fast Targeting)")
    logger.info("=" * 60)

    config = state["config"]
    commits = state["commits_to_process"]
    repo_path = config["repo_path"]

    if not commits:
        logger.warning("No commits to process.")
        return {"raw_diffs": []}

    batcher = get_git_batcher(repo_path)
    raw_diffs = []
    logs = state.get("extraction_logs", [])

    for i, commit_hash in enumerate(commits):
        if i % 100 == 0 and i > 0:
            logger.info(f"  Progress: {i}/{len(commits)} commits processed...")

        # Get the parent hash (returns empty for root commits)
        parent_hash = execute_git(
            f'git rev-parse "{commit_hash}~1"', cwd=repo_path, check=False
        )

        # Get commit date for history tracking
        commit_date = execute_git(
            f'git show -s --format=%ci {commit_hash}', cwd=repo_path, check=False
        )

        # Get commit description (subject/title)
        commit_desc = execute_git(
            f'git show -s --format=%s {commit_hash}', cwd=repo_path, check=False
        )
        commit_desc = commit_desc.strip() if commit_desc else "No description"

        logs.append(f"COMMIT PROCESSING: hash={commit_hash}, date={commit_date}, desc='{commit_desc}'")

        # List C# files with substantive changes (ignoring whitespace-only diffs)
        diff_cmd = (
            f"git diff -w --ignore-blank-lines --name-only "
            f"{parent_hash + '..' if parent_hash else ''}{commit_hash}"
        )
        changed_files_output = execute_git(diff_cmd, cwd=repo_path, check=False)
        if not changed_files_output:
            logs.append(f"  COMMIT {commit_hash}: No changed files found.")
            continue

        all_changed_files = [f.strip() for f in changed_files_output.splitlines() if f.strip()]
        
        # Log all non-C# files or non-interesting files if needed, but specifically C# files are the targets
        csharp_files = [f for f in all_changed_files if f.endswith(".cs")]
        
        for f in all_changed_files:
            if not f.endswith(".cs"):
                # Non C# files are not parsed
                pass

        # Filter out auto-generated files, tests, designers
        valid_files = []
        for f in csharp_files:
            if _is_excluded_file(f):
                logs.append(f"  DISCARDED file (excluded): {f}")
            else:
                valid_files.append(f)

        if not valid_files:
            logs.append(f"  COMMIT {commit_hash}: No valid C# files after exclusions.")
            continue

        for filepath in valid_files:
            # Load raw blobs via the persistent git cat-file process
            old_text = batcher.get_file_content(parent_hash, filepath) if parent_hash else ""
            new_text = batcher.get_file_content(commit_hash, filepath)

            if not old_text and not new_text:
                logs.append(f"  DISCARDED file (no content): {filepath}")
                continue
            if old_text == new_text:
                logs.append(f"  DISCARDED file (no C# changes - identical texts): {filepath}")
                continue

            # Compute exact changed line numbers
            old_lines, new_lines = get_changed_line_numbers(old_text, new_text)

            if not old_lines and not new_lines:
                logs.append(f"  DISCARDED file (no changed line coordinates): {filepath}")
                continue

            logs.append(f"  COLLECTED file: {filepath}")
            raw_diffs.append({
                "commit_hash": commit_hash,
                "commit_date": commit_date,
                "commit_description": commit_desc,
                "file_path": filepath,
                "old_text": old_text,
                "new_text": new_text,
                "old_lines": old_lines,
                "new_lines": new_lines,
            })

    logger.info(f"Extracted {len(raw_diffs)} raw diff payloads from {len(commits)} commits.")
    logger.info("Node 2 Finished.")

    return {
        "raw_diffs": raw_diffs,
        "extraction_logs": logs,
    }


def _is_excluded_file(filepath: str) -> bool:
    """Exclude auto-generated files, tests, and designer files from analysis."""
    fp_lower = filepath.lower().replace("\\", "/")

    # Designer / resource generated files
    if fp_lower.endswith(".designer.cs") or ".g." in fp_lower:
        return True

    # Test files
    test_markers = (".test/", ".tests/", ".unittests/", "/test/", "/tests/")
    if any(marker in fp_lower for marker in test_markers):
        return True
    if fp_lower.endswith("test.cs") or fp_lower.endswith("tests.cs"):
        return True

    return False
