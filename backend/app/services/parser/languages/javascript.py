import re
from pathlib import Path
from typing import List, Dict, Any
from app.services.parser.languages.base import BaseLanguageParser

class JavaScriptParser(BaseLanguageParser):
    def parse(self, file_path: Path, code_content: str) -> List[Dict[str, Any]]:
        entities = []
        if not code_content.strip():
            return entities

        lines = code_content.splitlines()
        
        # Regexes for imports
        import_regexes = [
            re.compile(r"import\s+.*?\s+from\s+['\"]([^'\"]+)['\"]"),
            re.compile(r"import\s+['\"]([^'\"]+)['\"]"),
            re.compile(r"require\(['\"]([^'\"]+)['\"]\)")
        ]
        
        dependencies = []
        for line in lines:
            for regex in import_regexes:
                match = regex.search(line)
                if match:
                    dep = match.group(1)
                    # Get package name (ignore relative imports)
                    if not dep.startswith('.'):
                        dependencies.append(dep.split('/')[0])
        
        # Deduplicate dependencies
        dependencies = list(set(dependencies))

        # Basic parser using regex to find functions and class declarations,
        # then using braces balancing to extract the exact block boundaries.
        class_pattern = re.compile(r'(?:export\s+)?class\s+(\w+)')
        func_pattern = re.compile(r'(?:export\s+)?(?:async\s+)?function\s+(\w+)\s*\(')
        arrow_func_pattern = re.compile(r'(?:export\s+)?const\s+(\w+)\s*=\s*(?:async\s*)?\(.*?\)\s*=>\s*\{')

        line_count = len(lines)
        i = 0
        while i < line_count:
            line = lines[i]
            
            class_match = class_pattern.search(line)
            func_match = func_pattern.search(line)
            arrow_match = arrow_func_pattern.search(line)
            
            matched = False
            entity_name = ""
            entity_type = ""
            start_line = i + 1
            
            if class_match:
                entity_name = class_match.group(1)
                entity_type = "class"
                matched = True
            elif func_match:
                entity_name = func_match.group(1)
                entity_type = "function"
                matched = True
            elif arrow_match:
                entity_name = arrow_match.group(1)
                entity_type = "function"
                matched = True
                
            if matched:
                # Find the closing brace for this entity block
                brace_count = 0
                started = False
                end_line = start_line
                
                for j in range(i, line_count):
                    curr_line = lines[j]
                    if '{' in curr_line:
                        brace_count += curr_line.count('{')
                        started = True
                    if '}' in curr_line:
                        brace_count -= curr_line.count('}')
                    
                    if started and brace_count <= 0:
                        end_line = j + 1
                        i = j  # Move outer pointer forward
                        break
                        
                if not started:
                    # Single line statement or bracketless arrow function
                    end_line = start_line
                
                content = "\n".join(lines[start_line - 1 : end_line])
                entities.append({
                    "name": entity_name,
                    "type": entity_type,
                    "start_line": start_line,
                    "end_line": end_line,
                    "content": content,
                    "dependencies": dependencies
                })
            i += 1

        # If nothing found, index the entire file as a module
        if not entities:
            entities.append({
                "name": file_path.name,
                "type": "module",
                "start_line": 1,
                "end_line": len(lines) or 1,
                "content": code_content,
                "dependencies": dependencies
            })
            
        return entities
