"""AST-based code skeleton extraction using tree-sitter.

Extracts function/class/interface/method signatures from source files
to create a compact token-efficient skeleton for routing.
"""

import os
from pathlib import Path
from typing import List, Dict

from tree_sitter import Node
from tree_sitter_language_pack import get_parser


# Map file extensions to tree-sitter language names
EXTENSION_TO_LANG: Dict[str, str] = {
    ".ts": "typescript",
    ".tsx": "tsx",
    ".js": "javascript",
    ".jsx": "javascript",
    ".py": "python",
    ".dart": "dart",
    ".go": "go",
    ".rs": "rust",
}

# Node types to collect signatures for (per language)
TARGET_NODE_TYPES = {
    "function",
    "class",
    "method",
    "interface",
    "function_definition",
    "class_definition",
    "method_definition",
    "interface_declaration",
    "function_declaration",
    "method_declaration",
}


def _get_signature_first_line(node: Node, source: bytes) -> str:
    """Extract the first line of a node's signature from source bytes."""
    start_byte = node.start_byte
    # Find end of first line after node start
    text = source[start_byte:].decode("utf-8", errors="replace")
    first_line = text.splitlines()[0] if "\n" in text else text
    return first_line.strip()


def _traverse_collect_signatures(node: Node, source: bytes, max_sigs: int) -> List[str]:
    """Recursively traverse AST, collect signatures of target node types."""
    signatures: List[str] = []

    def visit(n: Node) -> None:
        if len(signatures) >= max_sigs:
            return

        if n.type in TARGET_NODE_TYPES:
            sig = _get_signature_first_line(n, source)
            if sig:
                signatures.append(sig)

        for child in n.children:
            visit(child)

    visit(node)
    return signatures


def extract_ast_skeleton(file_path: str) -> str:
    """Extract AST skeleton (function/class signatures) from a source file.

    Args:
        file_path: Path to the source file.

    Returns:
        Formatted string skeleton with file path and signatures, or empty
        string for unsupported languages/parsing errors.
    """
    ext = Path(file_path).suffix.lower()
    lang = EXTENSION_TO_LANG.get(ext)
    if not lang:
        return ""

    try:
        parser = get_parser(lang)
        if not parser:
            return ""

        with open(file_path, "rb") as f:
            source = f.read()

        tree = parser.parse(source)
        signatures = _traverse_collect_signatures(tree.root_node, source, max_sigs=12)

        # Deduplicate signatures to avoid duplicate entries from nested matching
        seen = set()
        unique_signatures = []
        for sig in signatures:
            if sig not in seen:
                seen.add(sig)
                unique_signatures.append(sig)
        signatures = unique_signatures

        if not signatures:
            return f"// {file_path}\n"

        lines = [f"// {file_path}"]
        for sig in signatures:
            lines.append(f"- {sig}")

        return "\n".join(lines) + "\n"

    except Exception:
        return ""


def scan_project_codebase(root_dir: str, ignore_dirs: set[str]) -> list[str]:
    """Scan a project directory recursively for supported source files,
    extracting AST skeletons.

    Args:
        root_dir: Root directory to start scan from.
        ignore_dirs: Set of directory names to ignore (e.g. {".git", "__pycache__"}).

    Returns:
        List of skeletons (strings), one per supported file.
    """
    skeletons: list[str] = []
    root_path = Path(root_dir)

    for dirpath, dirnames, filenames in os.walk(root_path):
        # Filter out ignored directories (modify in-place for os.walk)
        dirnames[:] = [d for d in dirnames if d not in ignore_dirs]

        for filename in filenames:
            ext = Path(filename).suffix.lower()
            if ext not in EXTENSION_TO_LANG:
                continue

            file_path = Path(dirpath) / filename
            skeleton = extract_ast_skeleton(str(file_path))
            if skeleton:
                skeletons.append(skeleton)

    return skeletons
