"""
Shared utility functions for the Semantic Census Pipeline.

Ported and adapted from DroidAgent v1's shared_functions.py and shared_constants.py.
"""

import os
import re
import subprocess
import difflib
import logging
from typing import List, Tuple

# ── Logging ──────────────────────────────────────────────────────────────────
log_dir = "log"
os.makedirs(log_dir, exist_ok=True)

from datetime import datetime

_run_ts = datetime.now().strftime("%Y%m%d_%H%M%S")
_log_file = os.path.join(log_dir, f"census_run_{_run_ts}.log")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(_log_file, encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("SemanticCensus")

# ── Global Sentinel (must match the C# server) ──────────────────────────────
SENTINEL = "===END_OF_CODE==="


# ── Git Execution ────────────────────────────────────────────────────────────
def execute_git(cmd: str, cwd: str, check: bool = True) -> str:
    """
    Run a git command in the given working directory.
    Returns stripped stdout on success, empty string on failure (when check=False).
    """
    logger.info(f"Executing Git: {cmd}")
    try:
        res = subprocess.run(
            cmd,
            cwd=cwd,
            shell=True,
            text=True,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            check=check,
        )
        return res.stdout.strip() if res.stdout else ""
    except subprocess.CalledProcessError as e:
        logger.error(f"Git command failed: {cmd} — {e.stderr}")
        if check:
            raise
        return ""


# ── Diff Metrics ─────────────────────────────────────────────────────────────
def get_diff_char_count(clean_old: str, clean_new: str) -> int:
    """
    Calculate the character-level delta between two sanitized code strings.
    Whitespace is fully collapsed before comparison.
    """
    if not clean_old and not clean_new:
        return 0
    str_old = re.sub(r"\s+", "", clean_old)
    str_new = re.sub(r"\s+", "", clean_new)
    if str_old == str_new:
        return 0
    diff = difflib.ndiff(str_old, str_new)
    changed_chars = sum(1 for d in diff if d.startswith("+ ") or d.startswith("- "))
    return changed_chars


def get_changed_line_numbers(old_text: str, new_text: str) -> Tuple[List[int], List[int]]:
    """
    Given two versions of a file, compute the 1-based line numbers that changed.
    Returns (old_changed_lines, new_changed_lines).
    """
    old_lines: List[int] = []
    new_lines: List[int] = []

    diff = list(difflib.unified_diff(
        old_text.splitlines(),
        new_text.splitlines(),
        n=0,
        lineterm="",
    ))

    curr_old = 0
    curr_new = 0

    for line in diff:
        if line.startswith("@@"):
            m = re.match(r"@@ -(\d+),?(\d*) \+(\d+),?(\d*) @@", line)
            if m:
                curr_old = int(m.group(1))
                curr_new = int(m.group(3))
        elif line.startswith("-"):
            if curr_old > 0:
                old_lines.append(curr_old)
                curr_old += 1
        elif line.startswith("+"):
            if curr_new > 0:
                new_lines.append(curr_new)
                curr_new += 1
        elif line.startswith(" "):
            curr_old += 1
            curr_new += 1

    return sorted(set(old_lines)), sorted(set(new_lines))


def minify_code(text: str) -> str:
    """Collapse redundant whitespace in a code string."""
    if not text:
        return text
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"(?m)^[ \t]+", "", text)
    return text.strip()


def calculate_net_lines(clean_old: str, clean_new: str) -> Tuple[int, int]:
    """
    Compute added and removed lines between two sanitized code blocks.
    Returns (added_lines, removed_lines).
    """
    old_set = [l.strip() for l in clean_old.splitlines() if l.strip()] if clean_old else []
    new_set = [l.strip() for l in clean_new.splitlines() if l.strip()] if clean_new else []

    diff = list(difflib.unified_diff(old_set, new_set, n=0, lineterm=""))

    added = 0
    removed = 0
    for line in diff:
        if line.startswith("+++") or line.startswith("---") or line.startswith("@@"):
            continue
        if line.startswith("+"):
            added += 1
        elif line.startswith("-"):
            removed += 1

    return added, removed


# ── Lazy Singletons ──────────────────────────────────────────────────────────
_ROSLYN_SERVER = None
_GIT_BATCHER = None


def get_roslyn_server(target_framework: str = "net10.0"):
    """Return the singleton RoslynServer instance, starting it on first call."""
    global _ROSLYN_SERVER
    if _ROSLYN_SERVER is None:
        from src.roslyn_server_wrapper import RoslynServerWrapper
        tool_dir = os.path.abspath("./roslyn_server")
        _ROSLYN_SERVER = RoslynServerWrapper(tool_dir, target_framework)
    return _ROSLYN_SERVER


def get_git_batcher(repo_path: str):
    """Return the singleton GitBatcher instance, starting it on first call."""
    global _GIT_BATCHER
    if _GIT_BATCHER is None:
        from src.git_batcher import GitBatcher
        _GIT_BATCHER = GitBatcher(repo_path)
    return _GIT_BATCHER


def shutdown_subprocesses():
    """Gracefully terminate all persistent subprocesses."""
    global _ROSLYN_SERVER, _GIT_BATCHER
    if _ROSLYN_SERVER is not None:
        _ROSLYN_SERVER.stop()
        _ROSLYN_SERVER = None
    if _GIT_BATCHER is not None:
        _GIT_BATCHER.stop()
        _GIT_BATCHER = None
    logger.info("All subprocesses terminated.")

# ── Auditability System ──────────────────────────────────────────────────────

import json

class _AuditEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        try:
            return super().default(obj)
        except TypeError:
            return str(obj)

def audit_snapshot(state_or_data, node_name: str, stage_description: str, config: dict):
    """
    Dumps a snapshot of the current state or data to a JSONL log file, 
    if audit_mode is enabled in the configuration.
    This enables a complete timeline to track the evolution of data.
    """
    if not config.get("audit_mode", False):
        return
    
    timestamp = datetime.now().isoformat()
    snapshot = {
        "timestamp": timestamp,
        "node_name": node_name,
        "stage_description": stage_description,
        "data_snapshot": state_or_data
    }
    
    audit_file = os.path.join(log_dir, f"audit_snapshots_{_run_ts}.jsonl")
    try:
        with open(audit_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(snapshot, cls=_AuditEncoder, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.error(f"Failed to write audit snapshot for {node_name} at {stage_description}: {e}")
