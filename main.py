"""
Semantic Census Pipeline — Entry Point

Orchestrates the LangGraph pipeline that analyzes a C# enterprise codebase
by mining Git history and mapping changes to Roslyn AST nodes.
"""

from src.utils import logger
from src.agent import app


def main():
    logger.info("=" * 60)
    logger.info("Semantic Census Pipeline — Starting")
    logger.info("=" * 60)

    # Initial state: all fields empty. Node 1 will populate config & commits.
    initial_state = {
        "config": {},
        "baseline_objects": [],
        "commits_to_process": [],
        "raw_diffs": [],
        "parsed_hunks": [],
        "census_entries": [],
        "extraction_logs": [],
    }

    try:
        result = app.invoke(initial_state)
        logger.info("=" * 60)
        logger.info("Pipeline Finished Successfully!")
        logger.info("=" * 60)
    except Exception as e:
        logger.error(f"Pipeline failed with error: {e}", exc_info=True)
        # Ensure subprocesses are cleaned up even on failure
        from src.utils import shutdown_subprocesses
        shutdown_subprocesses()
        raise


if __name__ == "__main__":
    main()
