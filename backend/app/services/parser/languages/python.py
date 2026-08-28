import ast
from pathlib import Path
from typing import List, Dict, Any
from app.services.parser.languages.base import BaseLanguageParser

class PythonParser(BaseLanguageParser):
    def parse(self, file_path: Path, code_content: str) -> List[Dict[str, Any]]:
        entities = []
        if not code_content.strip():
            return entities
            
        try:
            tree = ast.parse(code_content)
        except SyntaxError:
            # Fallback in case of syntax errors in some files: treat file as a single module
            return [{
                "name": file_path.name,
                "type": "module",
                "start_line": 1,
                "end_line": len(code_content.splitlines()) or 1,
                "content": code_content,
                "dependencies": []
            }]

        lines = code_content.splitlines()

        # Helper to safely extract code snippet lines
        def get_source(node: ast.AST) -> str:
            start = getattr(node, 'lineno', 1) - 1
            end = getattr(node, 'end_lineno', len(lines))
            return "\n".join(lines[start:end])

        # Walk imports to collect dependencies
        imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for name in node.names:
                    imports.append(name.name.split('.')[0])
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imports.append(node.module.split('.')[0])

        # First pass: Extract class nodes
        for node in tree.body:
            if isinstance(node, ast.ClassDef):
                class_start = getattr(node, 'lineno', 1)
                class_end = getattr(node, 'end_lineno', len(lines))
                
                # Extract class structure
                entities.append({
                    "name": node.name,
                    "type": "class",
                    "start_line": class_start,
                    "end_line": class_end,
                    "content": get_source(node),
                    "dependencies": imports
                })

                # Now extract methods within class
                for sub_node in node.body:
                    if isinstance(sub_node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        m_start = getattr(sub_node, 'lineno', 1)
                        m_end = getattr(sub_node, 'end_lineno', len(lines))
                        entities.append({
                            "name": sub_node.name,
                            "type": "method",
                            "class_name": node.name,
                            "start_line": m_start,
                            "end_line": m_end,
                            "content": get_source(sub_node),
                            "dependencies": imports
                        })

            # Top level functions
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                f_start = getattr(node, 'lineno', 1)
                f_end = getattr(node, 'end_lineno', len(lines))
                entities.append({
                    "name": node.name,
                    "type": "function",
                    "start_line": f_start,
                    "end_line": f_end,
                    "content": get_source(node),
                    "dependencies": imports
                })

        # If no classes or functions were found, index the entire file as a module
        if not entities:
            entities.append({
                "name": file_path.name,
                "type": "module",
                "start_line": 1,
                "end_line": len(lines) or 1,
                "content": code_content,
                "dependencies": imports
            })

        return entities
