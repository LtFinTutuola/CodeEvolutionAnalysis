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
        if parent_hash:
            parent_hash = parent_hash.strip()

        # Skip merge commits
        parents_output = execute_git(f'git rev-list --parents -n 1 {commit_hash}', cwd=repo_path, check=False)
        if parents_output and len(parents_output.strip().split()) > 2:
            logs.append(f"  COMMIT {commit_hash}: Skipped (merge commit).")
            continue

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
        # Use -M to detect renames
        diff_cmd = (
            f"git diff -w --ignore-blank-lines --name-status -M "
            f"{parent_hash + '..' if parent_hash else ''}{commit_hash}"
        )
        changed_files_output = execute_git(diff_cmd, cwd=repo_path, check=False)
        if not changed_files_output:
            logs.append(f"  COMMIT {commit_hash}: No changed files found.")
            continue

        file_entries = [] # List of tuples (old_path, new_path)
        for line in changed_files_output.splitlines():
            line = line.strip()
            if not line:
                continue
            parts = line.split('\t')
            status = parts[0]
            
            if status.startswith('R') or status.startswith('C'):
                old_path = parts[1]
                new_path = parts[2]
                file_entries.append((old_path, new_path))
            elif status.startswith('A'):
                file_entries.append((None, parts[1]))
            elif status.startswith('D'):
                file_entries.append((parts[1], None))
            else:
                file_entries.append((parts[1], parts[1]))

        valid_entries = []
        for old_path, new_path in file_entries:
            check_path = new_path if new_path else old_path
            
            if not check_path.endswith(".cs"):
                continue
                
            if _is_excluded_file(check_path):
                logs.append(f"  DISCARDED file (excluded): {check_path}")
            else:
                valid_entries.append((old_path, new_path))

        if not valid_entries:
            logs.append(f"  COMMIT {commit_hash}: No valid C# files after exclusions.")
            continue

        for old_path, new_path in valid_entries:
            # Load raw blobs via the persistent git cat-file process
            old_text = ""
            new_text = ""
            if parent_hash and old_path:
                old_text = batcher.get_file_content(parent_hash, old_path)
            if new_path:
                new_text = batcher.get_file_content(commit_hash, new_path)

            if not old_text and not new_text:
                logs.append(f"  DISCARDED file (no content): {new_path or old_path}")
                continue
            if old_text == new_text:
                logs.append(f"  DISCARDED file (no C# changes - identical texts): {new_path or old_path}")
                continue

            # Compute exact changed line numbers
            old_lines, new_lines = get_changed_line_numbers(old_text, new_text)

            if not old_lines and not new_lines:
                logs.append(f"  DISCARDED file (no changed line coordinates): {new_path or old_path}")
                continue

            logs.append(f"  COLLECTED file: {new_path or old_path}")
            raw_diffs.append({
                "commit_hash": commit_hash,
                "commit_date": commit_date,
                "commit_description": commit_desc,
                "file_path": new_path or old_path,
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
