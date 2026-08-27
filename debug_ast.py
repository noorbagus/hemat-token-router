
import sys
from tree_sitter import Node
from tree_sitter_language_pack import get_parser

file_path = sys.argv[1]
lang = sys.argv[2]

from pathlib import Path
ext = Path(file_path).suffix.lower()

with open(file_path, "rb") as f:
    source = f.read()

parser = get_parser(lang)
tree = parser.parse(source)

def print_all_node_types(node: Node, indent: int = 0):
    prefix = "  " * indent
    print(f"{prefix}{node.type}")
    for child in node.children:
        print_all_node_types(child, indent + 1)

print_all_node_types(tree.root_node)
