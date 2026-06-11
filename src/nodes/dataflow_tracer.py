"""
Data-Flow Tracer — Tree-Sitter-based data-flow analysis for C# code fragments.

Uses tree-sitter with the C# grammar to build lightweight data-flow graphs (DFGs)
and compute divergence between old/new code versions.

The DFG captures:
- Variable declarations → usage chains (def → use)
- Assignment mutations → downstream references
- Function call argument passing
"""

import logging

logger = logging.getLogger("DroidAgent")

try:
    import tree_sitter_c_sharp as tscsharp
    from tree_sitter import Language, Parser
    _TS_AVAILABLE = True
except ImportError:
    _TS_AVAILABLE = False
    logger.warning(
        "tree-sitter or tree-sitter-c-sharp not available. "
        "DataFlowTracer will return 0.0 for all divergence queries."
    )


class DataFlowTracer:
    """
    Fault-tolerant data-flow tracer using Tree-Sitter C# grammar.

    Builds lightweight directed graphs of data dependencies and computes
    Jaccard distance on edge sets to measure data-flow divergence.

    Falls back to 0.0 (no divergence) if parsing fails or tree-sitter
    is not available — ensuring the pipeline never breaks.
    """

    _instance = None

    @classmethod
    def get_instance(cls):
        """Lazy singleton accessor."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        self._parser = None
        self._language = None
        if _TS_AVAILABLE:
            try:
                self._language = Language(tscsharp.language())
                self._parser = Parser(self._language)
                logger.info("DataFlowTracer initialized with Tree-Sitter C# grammar.")
            except Exception as e:
                logger.warning(f"Failed to initialize Tree-Sitter parser: {e}")
                self._parser = None

    def parse_fragment(self, code: str):
        """Parse a C# code fragment into a tree-sitter Tree."""
        if not self._parser or not code:
            return None
        try:
            return self._parser.parse(code.encode("utf-8"))
        except Exception:
            return None

    def build_local_dfg(self, code: str) -> set:
        """
        Build a lightweight data-flow graph from a C# code fragment.

        Returns a set of (source, target) tuples representing data-flow edges:
        - Variable declaration → all uses of that variable
        - Assignment → all subsequent uses of the assigned variable

        The graph is intentionally approximate — it captures local def-use chains
        within a method body without full semantic analysis.
        """
        tree = self.parse_fragment(code)
        if tree is None:
            return set()

        try:
            root = tree.root_node
            edges = set()

            # Collect all variable declarations and assignments
            definitions = {}  # variable_name → defining context
            usages = {}       # variable_name → [usage contexts]

            self._walk_for_definitions(root, definitions)
            self._walk_for_usages(root, usages)

            # Build def → use edges
            for var_name in definitions:
                if var_name in usages:
                    for usage_context in usages[var_name]:
                        edges.add((var_name, usage_context))

            # Build cross-variable flow edges (assignments from one var to another)
            self._walk_for_assignments(root, edges)

            return edges

        except Exception:
            return set()

    def _walk_for_definitions(self, node, definitions: dict):
        """Walk the tree collecting variable declarations."""
        # Variable declarator: `int x = ...`
        if node.type == "variable_declarator":
            name_node = node.child_by_field_name("name")
            if name_node:
                var_name = name_node.text.decode("utf-8")
                definitions[var_name] = f"decl:{var_name}"

        # Parameter: `void Foo(int x)`
        elif node.type == "parameter":
            name_node = node.child_by_field_name("name")
            if name_node:
                var_name = name_node.text.decode("utf-8")
                definitions[var_name] = f"param:{var_name}"

        # For-each variable: `foreach (var x in ...)`
        elif node.type == "foreach_statement":
            # The left child is the type, the identifier is the loop variable
            for child in node.children:
                if child.type == "identifier":
                    var_name = child.text.decode("utf-8")
                    definitions[var_name] = f"foreach:{var_name}"
                    break

        for child in node.children:
            self._walk_for_definitions(child, definitions)

    def _walk_for_usages(self, node, usages: dict):
        """Walk the tree collecting identifier usages (reads)."""
        if node.type == "identifier":
            # Skip if this is a definition site (left side of declaration/assignment)
            parent = node.parent
            if parent and parent.type in ("variable_declarator", "parameter"):
                name_field = parent.child_by_field_name("name")
                if name_field and name_field.id == node.id:
                    # This is the definition, not a usage
                    for child in node.children:
                        self._walk_for_usages(child, usages)
                    return

            var_name = node.text.decode("utf-8")
            # Build a context string that captures HOW the variable is used
            context = self._build_usage_context(node)
            if var_name not in usages:
                usages[var_name] = []
            usages[var_name].append(context)

        for child in node.children:
            self._walk_for_usages(child, usages)

    def _walk_for_assignments(self, node, edges: set):
        """Walk for assignment expressions to build cross-variable flow edges."""
        if node.type == "assignment_expression":
            left = node.child_by_field_name("left")
            right = node.child_by_field_name("right")

            if left and right:
                left_name = self._extract_identifier(left)
                right_names = self._extract_all_identifiers(right)

                if left_name:
                    for rname in right_names:
                        if rname != left_name:
                            edges.add((rname, f"assign:{left_name}"))

        for child in node.children:
            self._walk_for_assignments(child, edges)

    def _build_usage_context(self, node) -> str:
        """Build a context string describing how an identifier is used."""
        parent = node.parent
        if parent is None:
            return "standalone"

        if parent.type == "argument":
            # Used as a function argument
            grandparent = parent.parent
            if grandparent and grandparent.type == "argument_list":
                invocation = grandparent.parent
                if invocation and invocation.type == "invocation_expression":
                    func_node = invocation.child_by_field_name("function")
                    if func_node:
                        return f"arg:{func_node.text.decode('utf-8')}"
            return "arg:unknown"

        elif parent.type == "member_access_expression":
            return f"member_access:{parent.text.decode('utf-8')[:50]}"

        elif parent.type == "assignment_expression":
            return "assignment"

        elif parent.type == "binary_expression":
            return f"binop:{parent.type}"

        elif parent.type == "return_statement":
            return "return"

        return f"use:{parent.type}"

    def _extract_identifier(self, node) -> str:
        """Extract the primary identifier from a node."""
        if node.type == "identifier":
            return node.text.decode("utf-8")
        for child in node.children:
            result = self._extract_identifier(child)
            if result:
                return result
        return ""

    def _extract_all_identifiers(self, node) -> list:
        """Extract all identifiers from a subtree."""
        identifiers = []
        if node.type == "identifier":
            identifiers.append(node.text.decode("utf-8"))
        for child in node.children:
            identifiers.extend(self._extract_all_identifiers(child))
        return identifiers

    def compute_dataflow_divergence(self, old_code: str, new_code: str) -> float:
        """
        Compute the data-flow divergence between old and new code versions.

        Uses the Jaccard distance on DFG edge sets:
            D_dataflow = 1 - |E_old ∩ E_new| / |E_old ∪ E_new|

        Returns:
            0.0 if data flows are identical
            1.0 if completely divergent
            0.0 as fallback if parsing fails (fault-tolerant)
        """
        if not _TS_AVAILABLE:
            return 0.0

        try:
            old_edges = self.build_local_dfg(old_code)
            new_edges = self.build_local_dfg(new_code)

            # Handle empty edge sets
            if not old_edges and not new_edges:
                return 0.0

            union = old_edges | new_edges
            intersection = old_edges & new_edges

            if len(union) == 0:
                return 0.0

            jaccard_similarity = len(intersection) / len(union)
            return round(1.0 - jaccard_similarity, 6)

        except Exception as e:
            logger.warning(f"DataFlowTracer error (falling back to 0.0): {e}")
            return 0.0
