import logging
from pathlib import Path
from typing import List, Dict, Any
from app.services.parser.languages.python import PythonParser
from app.services.parser.languages.javascript import JavaScriptParser
from app.services.parser.languages.java import JavaParser
from app.services.parser.languages.dotnet import DotNetParser

class CodeParserAnalyzer:
    PARSERS = {
        "Python": PythonParser(),
        "JavaScript": JavaScriptParser(),
        "TypeScript": JavaScriptParser(),
        "Java": JavaParser(),
        "C#": DotNetParser()
    }

    @classmethod
    def analyze_workspace(cls, workspace_path: Path, indexed_files: List[Dict]) -> List[Dict[str, Any]]:
        """
        Iterates over discovered workspace files and parses their content.
        
        Returns:
            List of parsed entity structures.
        """
        all_entities = []

        for f_meta in indexed_files:
            file_rel_path = f_meta["file_path"]
            lang = f_meta["language"]
            abs_path = workspace_path / file_rel_path

            if not abs_path.exists():
                continue

            try:
                with open(abs_path, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
            except Exception as e:
                logging.warning(f"Could not read file {file_rel_path}: {str(e)}")
                continue

            # Check if we have an active AST parser for this language
            if lang in cls.PARSERS:
                parser = cls.PARSERS[lang]
                try:
                    entities = parser.parse(abs_path, content)
                    for entity in entities:
                        entity["file_path"] = file_rel_path
                        entity["language"] = lang
                        # If parser returned default type, categorize as code
                        if "chunk_type" not in entity:
                            entity["chunk_type"] = "code"
                        all_entities.append(entity)
                except NotImplementedError as nie:
                    logging.info(f"Skipping parser for {file_rel_path}: {str(nie)}")
                    # Treat NotImplemented languages as basic modules/code blocks
                    all_entities.append({
                        "name": abs_path.name,
                        "type": "module",
                        "chunk_type": "code",
                        "start_line": 1,
                        "end_line": len(content.splitlines()) or 1,
                        "content": content,
                        "dependencies": [],
                        "file_path": file_rel_path,
                        "language": lang
                    })
                except Exception as e:
                    logging.error(f"Error parsing file {file_rel_path} with language {lang}: {str(e)}")
            else:
                # Configuration or documentation files
                chunk_type = "config"
                if lang == "Markdown":
                    chunk_type = "doc"
                elif lang in ["JSON", "YAML", "XML", "HTML", "CSS"]:
                    chunk_type = "config"
                else:
                    chunk_type = "code"

                # Treat entire file as single chunk entity
                all_entities.append({
                    "name": abs_path.name,
                    "type": "module",
                    "chunk_type": chunk_type,
                    "start_line": 1,
                    "end_line": len(content.splitlines()) or 1,
                    "content": content,
                    "dependencies": [],
                    "file_path": file_rel_path,
                    "language": lang
                })

        return all_entities
