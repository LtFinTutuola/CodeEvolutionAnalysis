"""
Node 1: Configuration Manager & Git Scope Initialization

Responsibilities:
- Load config.yaml
- Prepare a pristine git workspace (stash, reset, clean, checkout)
- Collect the chronologically ordered list of commit hashes to analyze
"""

import os
import yaml
from src.utils import execute_git, logger


def node_1_config_manager(state):
    logger.info("=" * 60)
    logger.info("NODE 1: Configuration Manager & Git Scope")
    logger.info("=" * 60)

    # ── Load configuration ───────────────────────────────────────────────────
    config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "config.yaml")
    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    repo_path = config["repo_path"]
    target_branch = config["target_branch"]
    since_filter = config["since_filter"]

    if not repo_path or not os.path.isdir(repo_path):
        raise ValueError(f"Invalid repo_path in config.yaml: '{repo_path}'")

    logger.info(f"Repository   : {repo_path}")
    logger.info(f"Target Branch: {target_branch}")
    logger.info(f"Since Filter : {since_filter}")

    # ── Ensure pristine workspace ────────────────────────────────────────────
    # Remove stale git index lock if present
    lock_file = os.path.join(repo_path, ".git", "index.lock")
    if os.path.exists(lock_file):
        logger.info("Removing stale git index lock...")
        try:
            os.remove(lock_file)
        except OSError:
            pass

    # Stash any uncommitted changes
    status = execute_git("git status --porcelain", cwd=repo_path, check=False)
    if status:
        logger.info("Local changes detected. Stashing...")
        execute_git("git stash --include-untracked", cwd=repo_path, check=False)

    # Hard reset and clean to ensure pristine state
    execute_git("git reset --hard HEAD", cwd=repo_path, check=True)
    execute_git("git clean -fd", cwd=repo_path, check=True)

    # Checkout target branch and update it
    logger.info(f"Checking out and pulling latest changes for branch: {target_branch}")
    execute_git(f"git checkout {target_branch}", cwd=repo_path, check=True)
    execute_git(f"git pull origin {target_branch}", cwd=repo_path, check=True)

    # ── Collect commit hashes ────────────────────────────────────────────────
    since_flag = ""
    if str(since_filter).strip() != "-1":
        since_flag = f'--since="{since_filter}"'

    # --format="%H" gives one hash per line, oldest first with --reverse
    git_log_cmd = f'git log --format="%H" --reverse {since_flag} {target_branch}'
    log_output = execute_git(git_log_cmd, cwd=repo_path, check=True)

    commits = [h.strip().strip('"') for h in log_output.splitlines() if h.strip()]

    logs = [
        f"CONFIG LOADED: repo_path={repo_path}, target_branch={target_branch}, since_filter={since_filter}",
        f"COLLECTED {len(commits)} commits to process."
    ]

    return {
        "config": config,
        "commits_to_process": commits,
        "extraction_logs": logs,
    }
