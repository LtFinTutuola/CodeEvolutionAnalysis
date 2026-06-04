using System;
using System.IO;
using System.Linq;
using System.Text;
using System.Collections.Generic;
using System.Security.Cryptography;
using Microsoft.CodeAnalysis;
using Microsoft.CodeAnalysis.CSharp;
using Microsoft.CodeAnalysis.CSharp.Syntax;

namespace SemanticMapper
{
    class Program
    {
        const string Sentinel = "===END_OF_CODE===";
        private static readonly CSharpParseOptions ParseOptions =
            new CSharpParseOptions(preprocessorSymbols: new[] { "MonoDroid" });

        // ── Semantic Identity ───────────────────────────────────────────────

        /// <summary>
        /// Returns the fully qualified path: Namespace.Class.Member(Args)
        /// Traverses the parent chain to build a deterministic aggregation key.
        /// </summary>
        private static string GetSemanticIdentity(SyntaxNode node)
        {
            var parts = new List<string>();
            var current = node;

            while (current != null)
            {
                string? part = current switch
                {
                    MethodDeclarationSyntax m => m.Identifier.Text,
                    PropertyDeclarationSyntax p => p.Identifier.Text,
                    ConstructorDeclarationSyntax c => "Constructor",
                    ClassDeclarationSyntax cls => cls.Identifier.Text,
                    StructDeclarationSyntax s => s.Identifier.Text,
                    RecordDeclarationSyntax r => r.Identifier.Text,
                    InterfaceDeclarationSyntax i => i.Identifier.Text,
                    NamespaceDeclarationSyntax ns => ns.Name.ToString(),
                    FileScopedNamespaceDeclarationSyntax fns => fns.Name.ToString(),
                    _ => null
                };

                if (part != null)
                    parts.Add(part);

                current = current.Parent;
            }

            parts.Reverse();
            return string.Join(".", parts);
        }

        /// <summary>
        /// Returns the fully qualified identity of the parent class/struct/record.
        /// </summary>
        private static string GetParentIdentity(SyntaxNode node)
        {
            var parent = node.Parent;
            while (parent != null &&
                   !(parent is ClassDeclarationSyntax) &&
                   !(parent is StructDeclarationSyntax) &&
                   !(parent is RecordDeclarationSyntax) &&
                   !(parent is InterfaceDeclarationSyntax))
            {
                parent = parent.Parent;
            }
            return parent != null ? GetSemanticIdentity(parent) : "";
        }

        private static string GetFullSignature(SyntaxNode node)
        {
            return node switch
            {
                MethodDeclarationSyntax m => $"{m.Modifiers} {m.ReturnType} {m.Identifier}{m.ParameterList}".Trim(),
                PropertyDeclarationSyntax p => $"{p.Modifiers} {p.Type} {p.Identifier} {GetAccessors(p)}".Trim(),
                ConstructorDeclarationSyntax c => $"{c.Modifiers} {c.Identifier}{c.ParameterList}".Trim(),
                ClassDeclarationSyntax c => $"{c.Modifiers} class {c.Identifier}".Trim(),
                StructDeclarationSyntax s => $"{s.Modifiers} struct {s.Identifier}".Trim(),
                RecordDeclarationSyntax r => $"{r.Modifiers} record {r.Identifier}".Trim(),
                InterfaceDeclarationSyntax i => $"{i.Modifiers} interface {i.Identifier}".Trim(),
                _ => ""
            };
        }

        private static string GetAccessors(PropertyDeclarationSyntax p)
        {
            if (p.AccessorList != null)
            {
                var accessors = p.AccessorList.Accessors.Select(a => $"{a.Modifiers} {a.Keyword};".Trim());
                return "{ " + string.Join(" ", accessors) + " }";
            }
            else if (p.ExpressionBody != null)
            {
                return "{ get; }";
            }
            return "";
        }

        // ── Trivia Stripping ────────────────────────────────────────────────

        /// <summary>
        /// Returns true if the trivia is a comment or preprocessor directive.
        /// </summary>
        private static bool IsCommentOrDirective(SyntaxTrivia t)
        {
            var kind = t.Kind();
            return kind == SyntaxKind.SingleLineCommentTrivia ||
                kind == SyntaxKind.MultiLineCommentTrivia ||
                kind == SyntaxKind.SingleLineDocumentationCommentTrivia ||
                kind == SyntaxKind.MultiLineDocumentationCommentTrivia ||
                kind == SyntaxKind.DocumentationCommentExteriorTrivia ||
                kind == SyntaxKind.XmlComment ||
                kind == SyntaxKind.DisabledTextTrivia ||
                t.IsDirective;
        }

        /// <summary>
        /// Aggressively strip all comment trivia from a syntax node and normalize whitespace.
        /// Returns a flattened, continuous string suitable for character-level comparison.
        /// </summary>
        private static string StripTrivia(SyntaxNode? node)
        {
            if (node == null) return "";

            var cleanNode = node.ReplaceTrivia(
                node.DescendantTrivia(descendIntoTrivia: true)
                    .Concat(node.GetLeadingTrivia())
                    .Concat(node.GetTrailingTrivia())
                    .Where(IsCommentOrDirective),
                (original, _) => SyntaxFactory.ElasticMarker
            );

            return cleanNode.NormalizeWhitespace().ToFullString();
        }

        // ── String Literal Masking (Phase 2.1) ──────────────────────────────

        private class CosmeticChangesRewriter : CSharpSyntaxRewriter
        {
            public override SyntaxNode? VisitVariableDeclaration(VariableDeclarationSyntax node)
            {
                var visited = (VariableDeclarationSyntax?)base.VisitVariableDeclaration(node);
                if (visited == null) return null;
                if (!visited.Type.IsKind(SyntaxKind.IdentifierName) || ((IdentifierNameSyntax)visited.Type).Identifier.Text != "var")
                {
                    return visited.WithType(SyntaxFactory.IdentifierName("var").WithTriviaFrom(visited.Type));
                }
                return visited;
            }

            public override SyntaxNode? VisitForEachStatement(ForEachStatementSyntax node)
            {
                var visited = (ForEachStatementSyntax?)base.VisitForEachStatement(node);
                if (visited == null) return null;
                if (!visited.Type.IsKind(SyntaxKind.IdentifierName) || ((IdentifierNameSyntax)visited.Type).Identifier.Text != "var")
                {
                    return visited.WithType(SyntaxFactory.IdentifierName("var").WithTriviaFrom(visited.Type));
                }
                return visited;
            }

            public override SyntaxNode? VisitImplicitArrayCreationExpression(ImplicitArrayCreationExpressionSyntax node)
            {
                var visited = (ImplicitArrayCreationExpressionSyntax?)base.VisitImplicitArrayCreationExpression(node);
                if (visited == null) return null;
                return SyntaxFactory.CollectionExpression(
                    SyntaxFactory.SeparatedList<CollectionElementSyntax>(
                        visited.Initializer.Expressions.Select(e => (CollectionElementSyntax)SyntaxFactory.ExpressionElement(e))
                    )
                ).WithTriviaFrom(visited);
            }

            public override SyntaxNode? VisitArrayCreationExpression(ArrayCreationExpressionSyntax node)
            {
                var visited = (ArrayCreationExpressionSyntax?)base.VisitArrayCreationExpression(node);
                if (visited == null) return null;
                if (visited.Initializer != null)
                {
                    return SyntaxFactory.CollectionExpression(
                        SyntaxFactory.SeparatedList<CollectionElementSyntax>(
                            visited.Initializer.Expressions.Select(e => (CollectionElementSyntax)SyntaxFactory.ExpressionElement(e))
                        )
                    ).WithTriviaFrom(visited);
                }
                return visited;
            }

            public override SyntaxNode? VisitObjectCreationExpression(ObjectCreationExpressionSyntax node)
            {
                var visited = (ObjectCreationExpressionSyntax?)base.VisitObjectCreationExpression(node);
                if (visited == null) return null;
                return visited.WithType(SyntaxFactory.IdentifierName("var").WithTriviaFrom(visited.Type));
            }

            public override SyntaxNode? VisitImplicitObjectCreationExpression(ImplicitObjectCreationExpressionSyntax node)
            {
                var visited = (ImplicitObjectCreationExpressionSyntax?)base.VisitImplicitObjectCreationExpression(node);
                if (visited == null) return null;
                return SyntaxFactory.ObjectCreationExpression(SyntaxFactory.IdentifierName("var"))
                    .WithArgumentList(visited.ArgumentList)
                    .WithInitializer(visited.Initializer)
                    .WithTriviaFrom(visited);
            }

            public override SyntaxNode? VisitMethodDeclaration(MethodDeclarationSyntax node)
            {
                var visited = (MethodDeclarationSyntax?)base.VisitMethodDeclaration(node);
                if (visited == null) return null;
                
                if (!visited.Modifiers.Any(m => m.IsKind(SyntaxKind.PublicKeyword) || m.IsKind(SyntaxKind.PrivateKeyword) || m.IsKind(SyntaxKind.ProtectedKeyword) || m.IsKind(SyntaxKind.InternalKeyword)))
                {
                    visited = visited.AddModifiers(SyntaxFactory.Token(SyntaxKind.PrivateKeyword));
                }

                if (visited.ExpressionBody != null)
                {
                    var returnStatement = SyntaxFactory.ReturnStatement(visited.ExpressionBody.Expression);
                    var block = SyntaxFactory.Block(returnStatement);
                    return visited.WithExpressionBody(null).WithSemicolonToken(SyntaxFactory.Token(SyntaxKind.None)).WithBody(block);
                }
                return visited;
            }

            public override SyntaxNode? VisitPropertyDeclaration(PropertyDeclarationSyntax node)
            {
                var visited = (PropertyDeclarationSyntax?)base.VisitPropertyDeclaration(node);
                if (visited == null) return null;

                if (!visited.Modifiers.Any(m => m.IsKind(SyntaxKind.PublicKeyword) || m.IsKind(SyntaxKind.PrivateKeyword) || m.IsKind(SyntaxKind.ProtectedKeyword) || m.IsKind(SyntaxKind.InternalKeyword)))
                {
                    visited = visited.AddModifiers(SyntaxFactory.Token(SyntaxKind.PrivateKeyword));
                }

                if (visited.ExpressionBody != null)
                {
                    var getter = SyntaxFactory.AccessorDeclaration(SyntaxKind.GetAccessorDeclaration)
                        .WithBody(SyntaxFactory.Block(SyntaxFactory.ReturnStatement(visited.ExpressionBody.Expression)));
                    return visited.WithExpressionBody(null)
                                  .WithSemicolonToken(SyntaxFactory.Token(SyntaxKind.None))
                                  .WithAccessorList(SyntaxFactory.AccessorList(SyntaxFactory.SingletonList(getter)));
                }
                return visited;
            }

            public override SyntaxNode? VisitClassDeclaration(ClassDeclarationSyntax node)
            {
                var visited = (ClassDeclarationSyntax?)base.VisitClassDeclaration(node);
                if (visited == null) return null;
                if (!visited.Modifiers.Any(m => m.IsKind(SyntaxKind.PublicKeyword) || m.IsKind(SyntaxKind.PrivateKeyword) || m.IsKind(SyntaxKind.ProtectedKeyword) || m.IsKind(SyntaxKind.InternalKeyword)))
                {
                    visited = visited.AddModifiers(SyntaxFactory.Token(SyntaxKind.InternalKeyword));
                }
                return visited;
            }

            public override SyntaxNode? VisitLocalDeclarationStatement(LocalDeclarationStatementSyntax node)
            {
                var visited = (LocalDeclarationStatementSyntax?)base.VisitLocalDeclarationStatement(node);
                if (visited == null) return null;
                if (visited.UsingKeyword.IsKind(SyntaxKind.UsingKeyword))
                {
                    return SyntaxFactory.UsingStatement(
                        declaration: visited.Declaration,
                        expression: null,
                        statement: SyntaxFactory.Block()
                    ).WithTriviaFrom(visited);
                }
                return visited;
            }

            public override SyntaxNode? VisitIsPatternExpression(IsPatternExpressionSyntax node)
            {
                var visited = (IsPatternExpressionSyntax?)base.VisitIsPatternExpression(node);
                if (visited == null) return null;
                if (visited.Pattern is ConstantPatternSyntax cp && cp.Expression.IsKind(SyntaxKind.NullLiteralExpression))
                {
                    return SyntaxFactory.BinaryExpression(SyntaxKind.EqualsExpression, visited.Expression, cp.Expression).WithTriviaFrom(visited);
                }
                if (visited.Pattern is UnaryPatternSyntax up && up.IsKind(SyntaxKind.NotPattern) && up.Pattern is ConstantPatternSyntax cp2 && cp2.Expression.IsKind(SyntaxKind.NullLiteralExpression))
                {
                    return SyntaxFactory.BinaryExpression(SyntaxKind.NotEqualsExpression, visited.Expression, cp2.Expression).WithTriviaFrom(visited);
                }
                return visited;
            }

            public override SyntaxNode? VisitSwitchExpression(SwitchExpressionSyntax node)
            {
                var visited = (SwitchExpressionSyntax?)base.VisitSwitchExpression(node);
                if (visited == null) return null;
                return SyntaxFactory.InvocationExpression(SyntaxFactory.IdentifierName("<CONDITIONAL_BRANCH>")).WithTriviaFrom(visited);
            }

            public override SyntaxNode? VisitSwitchStatement(SwitchStatementSyntax node)
            {
                var visited = (SwitchStatementSyntax?)base.VisitSwitchStatement(node);
                if (visited == null) return null;
                return SyntaxFactory.ExpressionStatement(
                    SyntaxFactory.InvocationExpression(SyntaxFactory.IdentifierName("<CONDITIONAL_BRANCH>"))
                ).WithTriviaFrom(visited);
            }

            public override SyntaxNode? VisitInterpolatedStringExpression(InterpolatedStringExpressionSyntax node)
            {
                return SyntaxFactory.LiteralExpression(SyntaxKind.StringLiteralExpression, SyntaxFactory.Literal("<STR_BUILDER>")).WithTriviaFrom(node);
            }

            public override SyntaxNode? VisitInvocationExpression(InvocationExpressionSyntax node)
            {
                var visited = (InvocationExpressionSyntax?)base.VisitInvocationExpression(node);
                if (visited == null) return null;
                
                if (visited.Expression is MemberAccessExpressionSyntax ma && ma.Name.Identifier.Text == "Format")
                {
                    if (ma.Expression is IdentifierNameSyntax id && id.Identifier.Text == "String")
                        return SyntaxFactory.LiteralExpression(SyntaxKind.StringLiteralExpression, SyntaxFactory.Literal("<STR_BUILDER>")).WithTriviaFrom(visited);
                    if (ma.Expression is PredefinedTypeSyntax pt && pt.Keyword.IsKind(SyntaxKind.StringKeyword))
                        return SyntaxFactory.LiteralExpression(SyntaxKind.StringLiteralExpression, SyntaxFactory.Literal("<STR_BUILDER>")).WithTriviaFrom(visited);
                }
                return visited;
            }

            public override SyntaxNode? VisitBinaryExpression(BinaryExpressionSyntax node)
            {
                var visited = (BinaryExpressionSyntax?)base.VisitBinaryExpression(node);
                if (visited == null) return null;

                if (node.IsKind(SyntaxKind.AddExpression) || node.IsKind(SyntaxKind.AddAssignmentExpression))
                {
                    if (node.Left.IsKind(SyntaxKind.StringLiteralExpression) || node.Right.IsKind(SyntaxKind.StringLiteralExpression) ||
                        node.Left.IsKind(SyntaxKind.InterpolatedStringExpression) || node.Right.IsKind(SyntaxKind.InterpolatedStringExpression))
                    {
                        return SyntaxFactory.LiteralExpression(SyntaxKind.StringLiteralExpression, SyntaxFactory.Literal("<STR_BUILDER>")).WithTriviaFrom(node);
                    }
                }
                return visited;
            }

            public override SyntaxNode? VisitArgument(ArgumentSyntax node)
            {
                var visited = (ArgumentSyntax?)base.VisitArgument(node);
                if (visited == null) return null;
                
                if (visited.NameColon != null)
                {
                    return visited.WithNameColon(null).WithTriviaFrom(visited);
                }
                return visited;
            }

            public override SyntaxNode? VisitAssignmentExpression(AssignmentExpressionSyntax node)
            {
                var visited = (AssignmentExpressionSyntax?)base.VisitAssignmentExpression(node);
                if (visited == null) return null;

                if (node.IsKind(SyntaxKind.CoalesceAssignmentExpression))
                {
                    return SyntaxFactory.AssignmentExpression(
                        SyntaxKind.SimpleAssignmentExpression,
                        visited.Left,
                        SyntaxFactory.BinaryExpression(SyntaxKind.CoalesceExpression, visited.Left, visited.Right)
                    ).WithTriviaFrom(visited);
                }

                return visited;
            }
        }

        /// <summary>
        /// Clone an AST and replace all string literal expressions with a neutral
        /// token ("<STR>") to sterilize aesthetic/hardcoded diffs. We measure only
        /// control flow and architectural churn, not string content changes.
        /// Also masks interpolated strings and character literals.
        /// </summary>
        private static SyntaxNode MaskStringLiterals(SyntaxNode node)
        {
            // Replace StringLiteralExpression nodes
            var masked = node.ReplaceNodes(
                node.DescendantNodes().OfType<LiteralExpressionSyntax>()
                    .Where(n => n.Kind() == SyntaxKind.StringLiteralExpression ||
                                n.Kind() == SyntaxKind.CharacterLiteralExpression),
                (original, _) => SyntaxFactory.LiteralExpression(
                    SyntaxKind.StringLiteralExpression,
                    SyntaxFactory.Literal("<STR>"))
            );

            // Replace InterpolatedStringExpression nodes with a plain string literal
            masked = masked.ReplaceNodes(
                masked.DescendantNodes().OfType<InterpolatedStringExpressionSyntax>(),
                (original, _) => SyntaxFactory.LiteralExpression(
                    SyntaxKind.StringLiteralExpression,
                    SyntaxFactory.Literal("<STR>"))
            );

            return masked;
        }

        private static SyntaxNode MaskAst(SyntaxNode node)
        {
            var stringMasked = MaskStringLiterals(node);
            var rewriter = new CosmeticChangesRewriter();
            return rewriter.Visit(stringMasked) ?? stringMasked;
        }

        // ── AST Hash Short-Circuit (Phase 2.2) ─────────────────────────────

        /// <summary>
        /// Compute a deterministic SHA256 hash of a masked, trivia-stripped AST node.
        /// Used for fast equality checks: if hash(old) == hash(new), diff_score = 0.0.
        /// This bypasses the expensive TSED calculation for unchanged methods.
        /// </summary>
        private static string ComputeAstHash(SyntaxNode? node)
        {
            if (node == null) return "";

            var masked = MaskAst(node);
            var stripped = masked.NormalizeWhitespace().ToFullString();

            // Remove all remaining whitespace for position-independent hashing
            stripped = System.Text.RegularExpressions.Regex.Replace(stripped, @"\s+", "");

            using var sha256 = SHA256.Create();
            var hashBytes = sha256.ComputeHash(Encoding.UTF8.GetBytes(stripped));
            return Convert.ToHexString(hashBytes);
        }

        // ── TSED: Zhang-Shasha Tree Edit Distance (Phase 2.3) ──────────────

        /// <summary>
        /// A node in the flattened postorder representation of an AST,
        /// used as input for the Zhang-Shasha algorithm.
        /// </summary>
        private struct TsedNode
        {
            public string Label;          // SyntaxKind name (e.g., "MethodDeclaration", "IfStatement")
            public int LeftmostLeaf;      // Index of the leftmost leaf descendant (1-indexed in postorder)
            public int ChildrenCount;
        }

        /// <summary>
        /// Flatten a Roslyn SyntaxNode tree into a postorder-indexed array
        /// suitable for Zhang-Shasha computation.
        /// Labels are SyntaxKind names; string literals are already masked.
        /// </summary>
        private static List<TsedNode> FlattenToPostorder(SyntaxNode root)
        {
            var result = new List<TsedNode>();
            var leftmostLeaves = new Dictionary<SyntaxNode, int>();
            PostorderTraverse(root, result, leftmostLeaves);
            return result;
        }

        private static void PostorderTraverse(
            SyntaxNode node,
            List<TsedNode> result,
            Dictionary<SyntaxNode, int> leftmostLeaves)
        {
            var children = node.ChildNodes().ToList();

            foreach (var child in children)
            {
                PostorderTraverse(child, result, leftmostLeaves);
            }

            // This node's postorder index (1-based)
            int myIndex = result.Count + 1;

            // Leftmost leaf: if leaf node, it's itself; otherwise, inherit from first child
            int leftmostLeaf;
            if (children.Count == 0)
            {
                leftmostLeaf = myIndex;
            }
            else
            {
                leftmostLeaf = leftmostLeaves[children[0]];
            }

            leftmostLeaves[node] = leftmostLeaf;

            result.Add(new TsedNode
            {
                Label = node.Kind().ToString(),
                LeftmostLeaf = leftmostLeaf,
                ChildrenCount = children.Count
            });
        }

        /// <summary>
        /// Compute the Zhang-Shasha Tree Edit Distance between two postorder-flattened trees.
        /// Insert/delete/relabel costs are all 1.
        /// Returns the raw edit distance (unnormalized integer).
        /// </summary>
        private static int ZhangShashaDistance(List<TsedNode> t1, List<TsedNode> t2)
        {
            int m = t1.Count;
            int n = t2.Count;

            if (m == 0) return n;
            if (n == 0) return m;

            // Identify key roots: nodes i where l(i) != l(parent(i))
            // In postorder, key roots are nodes whose leftmost leaf index differs from parent's
            var keyRoots1 = GetKeyRoots(t1);
            var keyRoots2 = GetKeyRoots(t2);

            // Tree distance matrix (1-indexed)
            var td = new int[m + 1, n + 1];

            foreach (var i in keyRoots1)
            {
                foreach (var j in keyRoots2)
                {
                    ComputeForestDistance(t1, t2, i, j, td);
                }
            }

            return td[m, n];
        }

        private static List<int> GetKeyRoots(List<TsedNode> tree)
        {
            int size = tree.Count;
            // A key root is a node whose leftmostLeaf value is unique among ancestors
            // Simple approach: collect nodes with unique leftmostLeaf values,
            // keeping the one with the highest index (deepest ancestor in postorder)
            var lmlToMaxIndex = new Dictionary<int, int>();
            for (int i = 0; i < size; i++)
            {
                int lml = tree[i].LeftmostLeaf;
                lmlToMaxIndex[lml] = i + 1; // 1-indexed
            }
            var roots = lmlToMaxIndex.Values.ToList();
            roots.Sort();
            return roots;
        }

        private static void ComputeForestDistance(
            List<TsedNode> t1, List<TsedNode> t2,
            int i, int j, int[,] td)
        {
            int li = t1[i - 1].LeftmostLeaf;
            int lj = t2[j - 1].LeftmostLeaf;

            // Forest distance matrix for this subproblem
            var fd = new int[i - li + 2, j - lj + 2];

            fd[0, 0] = 0;
            for (int x = 1; x <= i - li + 1; x++)
                fd[x, 0] = fd[x - 1, 0] + 1; // delete cost
            for (int y = 1; y <= j - lj + 1; y++)
                fd[0, y] = fd[0, y - 1] + 1; // insert cost

            for (int x = li; x <= i; x++)
            {
                for (int y = lj; y <= j; y++)
                {
                    int xIdx = x - li + 1;
                    int yIdx = y - lj + 1;

                    int lx = t1[x - 1].LeftmostLeaf;
                    int ly = t2[y - 1].LeftmostLeaf;

                    if (lx == li && ly == lj)
                    {
                        // Both are in the same "subtree alignment"
                        int renameCost = t1[x - 1].Label == t2[y - 1].Label ? 0 : 1;
                        fd[xIdx, yIdx] = Math.Min(
                            Math.Min(
                                fd[xIdx - 1, yIdx] + 1,      // delete
                                fd[xIdx, yIdx - 1] + 1),     // insert
                            fd[xIdx - 1, yIdx - 1] + renameCost // relabel
                        );
                        td[x, y] = fd[xIdx, yIdx];
                    }
                    else
                    {
                        // Use previously computed tree distance
                        int tdX = lx - 1;
                        int tdY = ly - 1;
                        fd[xIdx, yIdx] = Math.Min(
                            Math.Min(
                                fd[xIdx - 1, yIdx] + 1,
                                fd[xIdx, yIdx - 1] + 1),
                            fd[lx - li, ly - lj] + td[x, y]
                        );
                    }
                }
            }
        }

        /// <summary>
        /// Calculate the TSED-based diff_score between two AST nodes.
        /// Applies string masking, hash short-circuit, and Zhang-Shasha.
        /// Returns a normalized score ∈ [0, 1]:
        ///   0.0 = identical trees, 1.0 = entirely different trees.
        /// 
        /// Short-circuit rules:
        ///   - Both null → 0.0
        ///   - One null (pure creation/deletion) → 1.0
        ///   - Same AST hash (handles method reordering within file) → 0.0
        /// </summary>
        private static double CalculateDiffScore(SyntaxNode? oldNode, SyntaxNode? newNode)
        {
            // Both null: no change
            if (oldNode == null && newNode == null) return 0.0;

            // Pure creation or pure deletion
            if (oldNode == null || newNode == null) return 1.0;

            // Mask string literals and cosmetic changes before comparison
            var maskedOld = MaskAst(oldNode);
            var maskedNew = MaskAst(newNode);

            // Hash short-circuit: identical masked ASTs → 0.0
            string hashOld = ComputeAstHash(oldNode);
            string hashNew = ComputeAstHash(newNode);
            if (hashOld == hashNew) return 0.0;

            // Full TSED calculation
            var tree1 = FlattenToPostorder(maskedOld);
            var tree2 = FlattenToPostorder(maskedNew);

            if (tree1.Count == 0 && tree2.Count == 0) return 0.0;
            if (tree1.Count == 0 || tree2.Count == 0) return 1.0;

            int editDistance = ZhangShashaDistance(tree1, tree2);
            int maxSize = Math.Max(tree1.Count, tree2.Count);

            // Normalize to [0, 1]
            double score = (double)editDistance / maxSize;
            return Math.Min(1.0, Math.Max(0.0, score));
        }

        // ── Semantic Token Extraction ────────────────────────────────────────

        private static readonly HashSet<SyntaxKind> LogicalTokenKinds = new HashSet<SyntaxKind>
        {
            // Operators
            SyntaxKind.PlusToken, SyntaxKind.MinusToken, SyntaxKind.AsteriskToken, SyntaxKind.SlashToken, SyntaxKind.PercentToken,
            SyntaxKind.EqualsEqualsToken, SyntaxKind.ExclamationEqualsToken, SyntaxKind.LessThanToken, SyntaxKind.LessThanEqualsToken,
            SyntaxKind.GreaterThanToken, SyntaxKind.GreaterThanEqualsToken, SyntaxKind.AmpersandAmpersandToken, SyntaxKind.BarBarToken,
            SyntaxKind.AmpersandToken, SyntaxKind.BarToken, SyntaxKind.CaretToken, SyntaxKind.TildeToken, SyntaxKind.ExclamationToken,
            SyntaxKind.EqualsToken, SyntaxKind.PlusEqualsToken, SyntaxKind.MinusEqualsToken, SyntaxKind.AsteriskEqualsToken,
            SyntaxKind.SlashEqualsToken, SyntaxKind.PercentEqualsToken, SyntaxKind.AmpersandEqualsToken, SyntaxKind.BarEqualsToken,
            SyntaxKind.CaretEqualsToken, SyntaxKind.LessThanLessThanToken, SyntaxKind.GreaterThanGreaterThanToken,
            SyntaxKind.LessThanLessThanEqualsToken, SyntaxKind.GreaterThanGreaterThanEqualsToken, SyntaxKind.QuestionQuestionToken,
            SyntaxKind.QuestionQuestionEqualsToken, SyntaxKind.QuestionToken, SyntaxKind.ColonToken, SyntaxKind.DotToken, SyntaxKind.CommaToken,

            // Control Flow
            SyntaxKind.IfKeyword, SyntaxKind.ElseKeyword, SyntaxKind.SwitchKeyword, SyntaxKind.CaseKeyword, SyntaxKind.DefaultKeyword,
            SyntaxKind.ForKeyword, SyntaxKind.ForEachKeyword, SyntaxKind.WhileKeyword, SyntaxKind.DoKeyword, SyntaxKind.BreakKeyword,
            SyntaxKind.ContinueKeyword, SyntaxKind.GotoKeyword, SyntaxKind.ReturnKeyword, SyntaxKind.YieldKeyword, SyntaxKind.ThrowKeyword,
            SyntaxKind.TryKeyword, SyntaxKind.CatchKeyword, SyntaxKind.FinallyKeyword, SyntaxKind.LockKeyword, SyntaxKind.UsingKeyword,
            SyntaxKind.AwaitKeyword,

            // Literals
            SyntaxKind.NumericLiteralToken, SyntaxKind.StringLiteralToken, SyntaxKind.TrueKeyword, SyntaxKind.FalseKeyword,
            SyntaxKind.NullKeyword, SyntaxKind.CharacterLiteralToken
        };

        private static List<string> GetLogicalTokens(SyntaxNode? node)
        {
            if (node == null) return new List<string>();

            return node.DescendantTokens()
                       .Where(t => LogicalTokenKinds.Contains(t.Kind()))
                       .Select(t => t.ValueText)
                       .ToList();
        }

        private static bool IsLogicalChange(SyntaxNode? oldNode, SyntaxNode? newNode)
        {
            var oldTokens = GetLogicalTokens(oldNode);
            var newTokens = GetLogicalTokens(newNode);

            if (oldTokens.Count != newTokens.Count) return true;

            for (int i = 0; i < oldTokens.Count; i++)
            {
                if (oldTokens[i] != newTokens[i]) return true;
            }

            return false;
        }

        // ── Semantic Node Extraction ────────────────────────────────────────

        /// <summary>
        /// Given code and 1-based line numbers, find the semantic nodes
        /// (method, property, constructor) that contain those lines.
        /// </summary>
        private static List<SyntaxNode> GetSemanticNodes(string code, List<int> lines)
        {
            if (string.IsNullOrWhiteSpace(code)) return new List<SyntaxNode>();

            var tree = CSharpSyntaxTree.ParseText(code, ParseOptions);
            var root = tree.GetRoot();
            var semanticNodes = new HashSet<SyntaxNode>();

            foreach (var lineNum in lines)
            {
                var text = tree.GetText();
                if (lineNum <= 0 || lineNum > text.Lines.Count) continue;

                var line = text.Lines[lineNum - 1];
                var node = root.FindNode(line.Span);

                // Walk up to the nearest semantic boundary
                while (node != null &&
                       !(node is MethodDeclarationSyntax) &&
                       !(node is PropertyDeclarationSyntax) &&
                       !(node is ConstructorDeclarationSyntax) &&
                       !(node is ClassDeclarationSyntax))
                {
                    node = node.Parent;
                }

                if (node != null)
                {
                    if (node is ClassDeclarationSyntax classNode)
                    {
                        // If we landed on a class, pick the member intersecting the line
                        foreach (var member in classNode.Members)
                        {
                            if ((member is MethodDeclarationSyntax ||
                                 member is PropertyDeclarationSyntax ||
                                 member is ConstructorDeclarationSyntax) &&
                                member.Span.IntersectsWith(line.Span))
                            {
                                semanticNodes.Add(member);
                            }
                        }
                    }
                    else
                    {
                        semanticNodes.Add(node);
                    }
                }
            }

            return semanticNodes.OrderBy(n => n.SpanStart).ToList();
        }

        /// <summary>
        /// Simplified identity for matching across old/new trees.
        /// Matches by method name + parameter types, ensuring method reordering
        /// within a file does NOT produce false diffs.
        /// </summary>
        private static string GetLocalIdentity(SyntaxNode node)
        {
            return node switch
            {
                MethodDeclarationSyntax m =>
                    $"method:{m.Identifier.Text}({string.Join(",", m.ParameterList.Parameters.Select(p => p.Type?.ToString()))})",
                PropertyDeclarationSyntax p => $"prop:{p.Identifier.Text}",
                ConstructorDeclarationSyntax c =>
                    $"ctor:({string.Join(",", c.ParameterList.Parameters.Select(p => p.Type?.ToString()))})",
                _ => node.ToString().Substring(0, Math.Min(50, node.ToString().Length))
            };
        }

        // ── CENSUS_EXTRACT Command ──────────────────────────────────────────

        /// <summary>
        /// Process a CENSUS_EXTRACT command: match old/new semantic nodes,
        /// return fully-qualified signatures, sanitized code pairs, and TSED diff_score.
        /// 
        /// Method reordering robustness: Methods are matched by GetLocalIdentity
        /// (name + parameter types), not by position. If a method is merely moved
        /// within the file, it matches correctly and the hash short-circuit
        /// produces diff_score = 0.0.
        /// </summary>
        private static string ProcessCensusExtract(
            string oldCode, string newCode,
            List<int> oldLns, List<int> newLns)
        {
            var oldNodes = GetSemanticNodes(oldCode, oldLns);
            var newNodes = GetSemanticNodes(newCode, newLns);

            var oldTree = string.IsNullOrWhiteSpace(oldCode)
                ? null : CSharpSyntaxTree.ParseText(oldCode, ParseOptions).GetRoot();
            var newTree = string.IsNullOrWhiteSpace(newCode)
                ? null : CSharpSyntaxTree.ParseText(newCode, ParseOptions).GetRoot();

            var results = new List<object>();
            var processedNewIdentities = new HashSet<string>();

            // Process old nodes first, matching to new nodes by local identity
            foreach (var oldNode in oldNodes)
            {
                var localId = GetLocalIdentity(oldNode);
                SyntaxNode? matchedNew = null;

                if (newTree != null)
                {
                    matchedNew = newTree.DescendantNodes()
                        .FirstOrDefault(n =>
                            (n is MethodDeclarationSyntax ||
                             n is PropertyDeclarationSyntax ||
                             n is ConstructorDeclarationSyntax) &&
                            GetLocalIdentity(n) == localId);
                }

                if (matchedNew != null)
                    processedNewIdentities.Add(localId);

                // Calculate TSED diff_score with masking and short-circuit
                double diffScore = CalculateDiffScore(oldNode, matchedNew);

                results.Add(new
                {
                    full_signature = GetFullSignature(oldNode),
                    signature = GetSemanticIdentity(oldNode),
                    parent_signature = GetParentIdentity(oldNode),
                    sanitized_old_code = StripTrivia(oldNode),
                    sanitized_new_code = StripTrivia(matchedNew),
                    is_logical_change = IsLogicalChange(oldNode, matchedNew),
                    diff_score = diffScore
                });
            }

            // Process new-only nodes (additions)
            foreach (var newNode in newNodes)
            {
                var localId = GetLocalIdentity(newNode);
                if (processedNewIdentities.Contains(localId)) continue;

                SyntaxNode? matchedOld = null;
                if (oldTree != null)
                {
                    matchedOld = oldTree.DescendantNodes()
                        .FirstOrDefault(n =>
                            (n is MethodDeclarationSyntax ||
                             n is PropertyDeclarationSyntax ||
                             n is ConstructorDeclarationSyntax) &&
                            GetLocalIdentity(n) == localId);
                }

                // Calculate TSED diff_score with masking and short-circuit
                double diffScore = CalculateDiffScore(matchedOld, newNode);

                results.Add(new
                {
                    full_signature = GetFullSignature(newNode),
                    signature = GetSemanticIdentity(newNode),
                    parent_signature = GetParentIdentity(newNode),
                    sanitized_old_code = StripTrivia(matchedOld),
                    sanitized_new_code = StripTrivia(newNode),
                    is_logical_change = IsLogicalChange(matchedOld, newNode),
                    diff_score = diffScore
                });
            }

            return System.Text.Json.JsonSerializer.Serialize(results);
        }

        // ── BASELINE_EXTRACT Command ────────────────────────────────────────

        /// <summary>
        /// Process a BASELINE_EXTRACT command: extract all semantic nodes from the code.
        /// </summary>
        private static string ProcessBaselineExtract(string code)
        {
            if (string.IsNullOrWhiteSpace(code)) return "[]";

            var tree = CSharpSyntaxTree.ParseText(code, ParseOptions);
            var root = tree.GetRoot();

            var members = root.DescendantNodes().Where(n => 
                n is MethodDeclarationSyntax ||
                n is PropertyDeclarationSyntax ||
                n is ConstructorDeclarationSyntax).ToList();

            var results = new List<object>();

            foreach (var node in members)
            {
                results.Add(new
                {
                    signature = GetSemanticIdentity(node),
                    parent_signature = GetParentIdentity(node)
                });
            }

            return System.Text.Json.JsonSerializer.Serialize(results);
        }

        // ── Main Entry Point ────────────────────────────────────────────────

        static void Main(string[] args)
        {
            Console.InputEncoding = Encoding.UTF8;
            Console.OutputEncoding = Encoding.UTF8;

            Console.WriteLine("READY");

            while (true)
            {
                string? commandLine = Console.ReadLine();
                if (commandLine == null || commandLine == "EXIT") break;

                try
                {
                    if (commandLine.StartsWith("CENSUS_EXTRACT|||"))
                    {
                        var parts = commandLine.Split(new[] { "|||" }, StringSplitOptions.None);
                        var oldLns = parts.Length > 1 && !string.IsNullOrWhiteSpace(parts[1])
                            ? parts[1].Split(new[] { ',' }, StringSplitOptions.RemoveEmptyEntries)
                                .Select(int.Parse).ToList()
                            : new List<int>();
                        var newLns = parts.Length > 2 && !string.IsNullOrWhiteSpace(parts[2])
                            ? parts[2].Split(new[] { ',' }, StringSplitOptions.RemoveEmptyEntries)
                                .Select(int.Parse).ToList()
                            : new List<int>();

                        var codeBuilder = new StringBuilder();
                        while (true)
                        {
                            var line = Console.ReadLine();
                            if (line == null || line == Sentinel) break;
                            codeBuilder.AppendLine(line);
                        }

                        var combined = codeBuilder.ToString();
                        var codeParts = combined.Split(
                            new[] { "---DELIMITER---" }, StringSplitOptions.None);
                        var oldCode = codeParts[0].Trim();
                        var newCode = codeParts.Length > 1 ? codeParts[1].Trim() : "";

                        var result = ProcessCensusExtract(oldCode, newCode, oldLns, newLns);
                        Console.WriteLine(result);
                    }
                    else if (commandLine.StartsWith("BASELINE_EXTRACT|||"))
                    {
                        var codeBuilder = new StringBuilder();
                        while (true)
                        {
                            var line = Console.ReadLine();
                            if (line == null || line == Sentinel) break;
                            codeBuilder.AppendLine(line);
                        }

                        var result = ProcessBaselineExtract(codeBuilder.ToString());
                        Console.WriteLine(result);
                    }
                }
                catch (Exception ex)
                {
                    Console.Error.WriteLine($"Error: {ex.Message}\n{ex.StackTrace}");
                }
                finally
                {
                    Console.WriteLine(Sentinel);
                }
            }
        }
    }
}
