from typing import TypedDict, List, Dict, Any


class AgentState(TypedDict):
    """
    LangGraph state definition for the Semantic Census Pipeline.

    Each field flows between nodes as part of the shared state dictionary.
    Nodes return partial dicts to update only the keys they own.
    """

    # Loaded configuration parameters from config.yaml
    config: Dict[str, Any]

    # Chronologically ordered list of commit hashes to analyze
    commits_to_process: List[str]

    # Raw diff payloads optimized for AST analysis.
    # Each entry: {commit_hash, commit_date, file_path, old_text, new_text, old_lines, new_lines}
    raw_diffs: List[Dict[str, Any]]

    # Semantic nodes returned by the Roslyn parser.
    # Each entry: {commit_hash, commit_date, file_path, signature, parent_signature,
    #              clean_old, clean_new, added_lines, removed_lines}
    parsed_hunks: List[Dict[str, Any]]

    # Global census dictionary aggregating statistics grouped by classes and methods.
    # Structure: {
    #   "Namespace.ClassName": {
    #       "hit_count": int,
    #       "methods": {
    #           "Namespace.ClassName.MethodName(Args)": {
    #               "hit_count": int,
    #               "first_seen_date": str,
    #               "history": [
    #                   {"date": str, "commit_hash": str, "added_lines": int, "removed_lines": int}
    #               ]
    #           }
    #       }
    #   }
    # }
    census_dictionary: Dict[str, Any]
