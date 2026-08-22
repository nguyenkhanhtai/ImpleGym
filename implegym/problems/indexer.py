"""Problem indexer and repository scanner for Library Checker."""

import os
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from implegym.db.models import Problem

# Built-in curated dataset mapping Yosupo problems to implementation difficulty ratings (1..10)
DEFAULT_YOSUPO_PROBLEMS: list[dict[str, Any]] = [
    {
        "slug": "aplusb",
        "title": "A + B",
        "category": "Sample",
        "difficulty": 1,
        "statement": "Given two integers $A$ and $B$, calculate $A + B$.",
        "input_format": "Input is given from Standard Input in the following format:\n\n```\nA B\n```",
        "output_format": "Print the answer in one line.",
        "constraints": "$0 \\le A, B \\le 10^9$",
        "sample_cases": [
            {"input": "1 2\n", "output": "3\n"},
            {"input": "1000000000 1000000000\n", "output": "2000000000\n"},
        ],
        "time_limit": 2.0,
        "memory_limit_mb": 1024,
        "tags": ["sample", "basic_io"],
        "source": "yosupo",
    },
    {
        "slug": "associative_array",
        "title": "Associative Array",
        "category": "Data Structure",
        "difficulty": 2,
        "statement": "You are given an associative array $A$ indexed by non-negative integers. Initially, all values are $0$.\n\nProcess $Q$ queries of two types:\n- `0 k v`: $A[k] \\leftarrow v$\n- `1 k`: Print $A[k]$",
        "input_format": "$Q$\nQuery 1\nQuery 2\n...\nQuery Q",
        "output_format": "For each query of the second type, print the value.",
        "constraints": "$1 \\le Q \\le 10^6$, $0 \\le k \\le 10^{18}$, $0 \\le v \\le 10^{18}$",
        "sample_cases": [
            {
                "input": "4\n0 10 20\n0 20 30\n1 10\n1 30\n",
                "output": "20\n0\n",
            }
        ],
        "time_limit": 2.0,
        "memory_limit_mb": 1024,
        "tags": ["hash_map", "gp_hash_table", "data_structures"],
        "source": "yosupo",
    },
    {
        "slug": "unionfind",
        "title": "Unionfind (Disjoint Set Union)",
        "category": "Data Structure",
        "difficulty": 3,
        "statement": "Given an undirected graph with $N$ vertices and $0$ edges. Process $Q$ queries:\n- `0 u v`: Add an edge between $u$ and $v$.\n- `1 u v`: Output `1` if $u$ and $v$ are connected, `0` otherwise.",
        "input_format": "$N$ $Q$\nQuery 1\n...\nQuery Q",
        "output_format": "For each type 1 query, print `1` or `0`.",
        "constraints": "$1 \\le N, Q \\le 2 \\times 10^5$, $0 \\le u, v < N$",
        "sample_cases": [
            {
                "input": "4 7\n1 0 1\n0 0 1\n0 2 3\n1 0 1\n1 1 2\n0 0 2\n1 1 3\n",
                "output": "0\n1\n0\n1\n",
            }
        ],
        "time_limit": 2.0,
        "memory_limit_mb": 1024,
        "tags": ["dsu", "union_find", "data_structures"],
        "source": "yosupo",
    },
    {
        "slug": "staticrmq",
        "title": "Static RMQ (Range Minimum Query)",
        "category": "Data Structure",
        "difficulty": 3,
        "statement": "Given an array $A = (a_0, a_1, \\dots, a_{N-1})$, answer $Q$ queries:\nFor each query $(l, r)$, find $\\min_{l \\le i < r} a_i$.",
        "input_format": "$N$ $Q$\n$a_0$ $a_1$ ... $a_{N-1}$\n$l_0$ $r_0$\n...\n$l_{Q-1}$ $r_{Q-1}$",
        "output_format": "Print the answer for each query in order.",
        "constraints": "$1 \\le N, Q \\le 5 \\times 10^5$, $0 \\le a_i \\le 10^9$, $0 \\le l < r \\le N$",
        "sample_cases": [
            {
                "input": "5 4\n2 10 1 100 1\n0 2\n1 4\n2 3\n0 5\n",
                "output": "2\n1\n1\n1\n",
            }
        ],
        "time_limit": 2.0,
        "memory_limit_mb": 1024,
        "tags": ["sparse_table", "rmq", "data_structures"],
        "source": "yosupo",
    },
    {
        "slug": "point_add_range_sum",
        "title": "Point Add Range Sum",
        "category": "Data Structure",
        "difficulty": 4,
        "statement": "Given a sequence $A = (a_0, a_1, \\dots, a_{N-1})$, process $Q$ queries:\n- `0 p x`: $a_p \\leftarrow a_p + x$\n- `1 l r`: Compute and print $\\sum_{i=l}^{r-1} a_i$",
        "input_format": "$N$ $Q$\n$a_0$ $a_1$ ... $a_{N-1}$\nQuery 1\n...\nQuery Q",
        "output_format": "For each type 1 query, print the sum.",
        "constraints": "$1 \\le N, Q \\le 5 \\times 10^5$, $0 \\le a_i, x \\le 10^9$, $0 \\le l < r \\le N$",
        "sample_cases": [
            {
                "input": "5 5\n1 2 3 4 5\n1 0 5\n1 2 4\n0 3 10\n1 0 5\n1 0 3\n",
                "output": "15\n7\n25\n6\n",
            }
        ],
        "time_limit": 2.0,
        "memory_limit_mb": 1024,
        "tags": ["fenwick_tree", "segment_tree", "data_structures"],
        "source": "yosupo",
    },
    {
        "slug": "lca",
        "title": "Lowest Common Ancestor",
        "category": "Tree",
        "difficulty": 5,
        "statement": "Given a rooted tree with $N$ vertices numbered $0$ to $N-1$ where vertex $0$ is the root. Each vertex $i$ ($1 \\le i < N$) has parent $p_i$. Answer $Q$ queries:\nGiven $(u, v)$, find their lowest common ancestor.",
        "input_format": "$N$ $Q$\n$p_1$ $p_2$ ... $p_{N-1}$\n$u_0$ $v_0$\n...\n$u_{Q-1}$ $v_{Q-1}$",
        "output_format": "Print the LCA for each query.",
        "constraints": "$2 \\le N \\le 5 \\times 10^5$, $1 \\le Q \\le 5 \\times 10^5$, $0 \\le p_i < i$",
        "sample_cases": [
            {
                "input": "5 4\n0 0 1 1\n3 4\n0 3\n1 2\n2 4\n",
                "output": "1\n0\n0\n0\n",
            }
        ],
        "time_limit": 2.0,
        "memory_limit_mb": 1024,
        "tags": ["tree", "binary_lifting", "rmq", "euler_tour"],
        "source": "yosupo",
    },
    {
        "slug": "range_affine_range_sum",
        "title": "Range Affine Range Sum",
        "category": "Data Structure",
        "difficulty": 5,
        "statement": "Given an array $A = (a_0, \\dots, a_{N-1})$, process $Q$ queries modulo $998244353$:\n- `0 l r b c`: For all $l \\le i < r$, $a_i \\leftarrow (b \\cdot a_i + c) \\pmod{998244353}$\n- `1 l r`: Compute and print $\\sum_{i=l}^{r-1} a_i \\pmod{998244353}$",
        "input_format": "$N$ $Q$\n$a_0$ ... $a_{N-1}$\nQuery 1\n...\nQuery Q",
        "output_format": "Print the sum for each type 1 query.",
        "constraints": "$1 \\le N, Q \\le 5 \\times 10^5$, $0 \\le a_i, b, c < 998244353$",
        "sample_cases": [
            {
                "input": "5 7\n1 2 3 4 5\n1 0 5\n0 2 4 100 101\n1 0 3\n0 1 3 102 103\n1 2 5\n0 2 5 104 105\n1 0 5\n",
                "output": "15\n404\n41511\n4317767\n",
            }
        ],
        "time_limit": 2.5,
        "memory_limit_mb": 1024,
        "tags": ["lazy_segment_tree", "affine_transformation", "data_structures"],
        "source": "yosupo",
    },
    {
        "slug": "suffixarray",
        "title": "Suffix Array",
        "category": "String",
        "difficulty": 6,
        "statement": "Given a string $S$ of length $N$, output the suffix array of $S$. That is, the permutation of $0, 1, \\dots, N-1$ representing lexicographically sorted suffixes.",
        "input_format": "$S$",
        "output_format": "Print the suffix array as space-separated integers.",
        "constraints": "$1 \\le |S| \\le 5 \\times 10^5$",
        "sample_cases": [
            {
                "input": "abracadabra\n",
                "output": "10 7 0 3 5 8 1 4 6 9 2\n",
            }
        ],
        "time_limit": 2.0,
        "memory_limit_mb": 1024,
        "tags": ["string", "suffix_array", "sais"],
        "source": "yosupo",
    },
    {
        "slug": "dynamic_tree_vertex_add_path_sum",
        "title": "Dynamic Tree Vertex Add Path Sum",
        "category": "Tree",
        "difficulty": 7,
        "statement": "Given a forest of $N$ vertices, each vertex initially having value $a_i$. Process $Q$ queries:\n- `0 u v w x`: Cut edge $(u, v)$ and link edge $(w, x)$\n- `1 p x`: $a_p \\leftarrow a_p + x$\n- `2 u v`: Print the sum of values on the path between $u$ and $v$",
        "input_format": "$N$ $Q$\n$a_0$ ... $a_{N-1}$\n$u_1$ $v_1$\n...\n$u_{N-1}$ $v_{N-1}$\nQuery 1\n...\nQuery Q",
        "output_format": "Print the sum for each type 2 query.",
        "constraints": "$1 \\le N, Q \\le 2 \\times 10^5$, $0 \\le a_i, x \\le 10^9$",
        "sample_cases": [
            {
                "input": "5 6\n1 10 100 1000 10000\n0 1\n1 2\n2 3\n3 4\n2 0 4\n1 2 100000\n2 0 4\n0 1 2 1 4\n2 0 4\n2 0 3\n",
                "output": "11111\n111111\n10011\n111111\n",
            }
        ],
        "time_limit": 2.5,
        "memory_limit_mb": 1024,
        "tags": ["link_cut_tree", "dynamic_trees", "splay_tree"],
        "source": "yosupo",
    },
    {
        "slug": "dynamic_sequence_range_affine_range_sum",
        "title": "Dynamic Sequence Range Affine Range Sum",
        "category": "Data Structure",
        "difficulty": 8,
        "statement": "Maintain a sequence $A$ under insertion, deletion, reversal, range affine transformation, and range sum queries modulo $998244353$.",
        "input_format": "$N$ $Q$\n$a_0$ ... $a_{N-1}$\nQuery 1\n...\nQuery Q",
        "output_format": "Output results for each range sum query.",
        "constraints": "$1 \\le N, Q \\le 2 \\times 10^5$",
        "sample_cases": [
            {
                "input": "5 5\n1 2 3 4 5\n4 0 5\n0 2 10\n4 0 6\n2 1 4\n4 0 6\n",
                "output": "15\n25\n25\n",
            }
        ],
        "time_limit": 3.0,
        "memory_limit_mb": 1024,
        "tags": ["splay_tree", "treap", "dynamic_sequence", "data_structures"],
        "source": "yosupo",
    },
    {
        "slug": "convolution_mod",
        "title": "Convolution (Modulo 998244353)",
        "category": "Math",
        "difficulty": 8,
        "statement": "Given two sequences $A = (a_0, \\dots, a_{N-1})$ and $B = (b_0, \\dots, b_{M-1})$, compute their convolution $C = (c_0, \\dots, c_{N+M-2})$ where $c_k = \\sum_{i+j=k} a_i b_j \\pmod{998244353}$.",
        "input_format": "$N$ $M$\n$a_0$ ... $a_{N-1}$\n$b_0$ ... $b_{M-1}$",
        "output_format": "Print the sequence $C$ in one line.",
        "constraints": "$1 \\le N, M \\le 524288$, $0 \\le a_i, b_j < 998244353$",
        "sample_cases": [
            {
                "input": "4 3\n1 2 3 4\n5 6 7\n",
                "output": "5 16 34 52 45 28\n",
            }
        ],
        "time_limit": 2.0,
        "memory_limit_mb": 1024,
        "tags": ["ntt", "fft", "polynomial", "math"],
        "source": "yosupo",
    },
    {
        "slug": "general_matching",
        "title": "Matching on General Graph (Edmonds Blossom)",
        "category": "Graph",
        "difficulty": 9,
        "statement": "Given an undirected general graph $G = (V, E)$, find a maximum matching. Output the size of the matching and the matched edges.",
        "input_format": "$N$ $M$\n$u_0$ $v_0$\n...\n$u_{M-1}$ $v_{M-1}$",
        "output_format": "$K$\n$u_0$ $v_0$\n...\n$u_{K-1}$ $v_{K-1}$",
        "constraints": "$1 \\le N \\le 500$, $0 \\le M \\le \\min(N(N-1)/2, 50000)$",
        "sample_cases": [
            {
                "input": "5 5\n0 1\n1 2\n2 0\n2 3\n3 4\n",
                "output": "2\n0 1\n3 4\n",
            }
        ],
        "time_limit": 2.0,
        "memory_limit_mb": 1024,
        "tags": ["blossom_algorithm", "general_matching", "graph"],
        "source": "yosupo",
    },
    {
        "slug": "dynamic_tree_subtree_add_subtree_sum",
        "title": "Dynamic Tree Subtree Add Subtree Sum",
        "category": "Tree",
        "difficulty": 10,
        "statement": "Maintain a dynamic rooted forest under link/cut, root changes, subtree value additions, and subtree sum queries.",
        "input_format": "$N$ $Q$\n$a_0$ ... $a_{N-1}$\n$p_1$ ... $p_{N-1}$\nQuery 1\n...\nQuery Q",
        "output_format": "Output results for each subtree sum query.",
        "constraints": "$1 \\le N, Q \\le 2 \\times 10^5$",
        "sample_cases": [
            {
                "input": "4 4\n1 2 3 4\n0 0 1\n2 0\n0 2 0\n1 0 10\n2 0\n",
                "output": "10\n40\n",
            }
        ],
        "time_limit": 3.5,
        "memory_limit_mb": 1024,
        "tags": ["top_tree", "link_cut_tree", "subtree_updates", "hard_ds"],
        "source": "yosupo",
    },
]


class ProblemIndexer:
    """Indexes and synchronizes problem datasets."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def seed_default_problems(self) -> int:
        """Seed built-in problems into database if not present."""
        count = 0
        for item in DEFAULT_YOSUPO_PROBLEMS:
            stmt = select(Problem).where(Problem.slug == item["slug"])
            res = await self.session.execute(stmt)
            existing = res.scalar_one_or_none()
            if not existing:
                problem = Problem(
                    slug=item["slug"],
                    title=item["title"],
                    category=item["category"],
                    difficulty=item["difficulty"],
                    statement=item["statement"],
                    input_format=item["input_format"],
                    output_format=item["output_format"],
                    constraints=item["constraints"],
                    sample_cases=item["sample_cases"],
                    time_limit=item["time_limit"],
                    memory_limit_mb=item["memory_limit_mb"],
                    tags=item["tags"],
                    source=item["source"],
                )
                self.session.add(problem)
                count += 1
        await self.session.commit()
        return count

    async def scan_local_yosupo_repo(self, repo_dir: Path) -> int:
        """Scan a local clone of yosupo06/library-checker-problems and index problems."""
        if not repo_dir.exists() or not repo_dir.is_dir():
            return 0

        indexed_count = 0
        # Iterate over category directories (e.g. data_structure, math, graph, etc.)
        for cat_entry in os.scandir(repo_dir):
            if not cat_entry.is_dir() or cat_entry.name.startswith("."):
                continue

            for prob_entry in os.scandir(cat_entry.path):
                if not prob_entry.is_dir():
                    continue

                prob_path = Path(prob_entry.path)
                task_md = prob_path / "task.md"

                if task_md.exists():
                    slug = prob_entry.name
                    title = prob_entry.name.replace("_", " ").title()
                    category = cat_entry.name.replace("_", " ").title()

                    statement = task_md.read_text(encoding="utf-8", errors="ignore")

                    # Check if already present
                    stmt = select(Problem).where(Problem.slug == slug)
                    res = await self.session.execute(stmt)
                    if not res.scalar_one_or_none():
                        problem = Problem(
                            slug=slug,
                            title=title,
                            category=category,
                            difficulty=5,  # Default median difficulty
                            statement=statement,
                            input_format="",
                            output_format="",
                            constraints="",
                            sample_cases=[],
                            time_limit=2.0,
                            memory_limit_mb=1024,
                            tags=[cat_entry.name],
                            source="yosupo_local",
                        )
                        self.session.add(problem)
                        indexed_count += 1

        if indexed_count > 0:
            await self.session.commit()
        return indexed_count
