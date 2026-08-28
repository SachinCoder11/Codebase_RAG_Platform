import os
import json
from pathlib import Path
from typing import Dict, List, Set, Tuple

class RepositoryScanner:
    EXCLUDE_DIRS = {
        ".git", "node_modules", "venv", ".venv", "env", "__pycache__",
        "target", "bin", "obj", "dist", "build", ".idea", ".vscode", "out"
    }
    
    EXCLUDE_FILES = {
        ".DS_Store", "thumbs.db", "package-lock.json", "yarn.lock", "pnpm-lock.yaml"
    }

    LANGUAGE_MAP = {
        ".py": "Python",
        ".js": "JavaScript",
        ".jsx": "JavaScript",
        ".ts": "TypeScript",
        ".tsx": "TypeScript",
        ".java": "Java",
        ".cs": "C#",
        ".go": "Go",
        ".md": "Markdown",
        ".json": "JSON",
        ".yaml": "YAML",
        ".yml": "YAML",
        ".xml": "XML",
        ".html": "HTML",
        ".css": "CSS"
    }

    @classmethod
    def scan_repository(cls, workspace_path: Path) -> Dict:
        """
        Recursively scans a workspace to:
        1. Catalog indexable files
        2. Detect primary languages
        3. Detect primary frameworks
        """
        indexed_files = []
        languages = {}
        frameworks = set()
        total_lines = 0

        # Framework detection cues
        has_package_json = False
        has_pom_xml = False
        has_csproj = False
        has_requirements = False

        package_json_content = {}
        requirements_content = ""

        # Recursive traversal
        for root, dirs, files in os.walk(workspace_path):
            # Prune excluded directories in-place
            dirs[:] = [d for d in dirs if d not in cls.EXCLUDE_DIRS]

            for file in files:
                if file in cls.EXCLUDE_FILES:
                    continue

                file_path = Path(root) / file
                rel_path = file_path.relative_to(workspace_path)
                ext = file_path.suffix.lower()

                # Basic meta files checks
                if file == "package.json":
                    has_package_json = True
                    try:
                        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                            package_json_content = json.load(f)
                    except:
                        pass
                elif file == "pom.xml":
                    has_pom_xml = True
                elif ext == ".csproj":
                    has_csproj = True
                elif file == "requirements.txt":
                    has_requirements = True
                    try:
                        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                            requirements_content = f.read()
                    except:
                        pass

                # Language detection & stats
                if ext in cls.LANGUAGE_MAP:
                    lang = cls.LANGUAGE_MAP[ext]
                    indexed_files.append({
                        "file_path": str(rel_path).replace("\\", "/"),
                        "language": lang,
                        "size_bytes": file_path.stat().st_size
                    })
                    
                    # Estimate line count (only for text files)
                    line_count = 0
                    try:
                        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                            line_count = sum(1 for _ in f)
                        total_lines += line_count
                    except:
                        pass

                    languages[lang] = languages.get(lang, 0) + line_count

        # Detect Frameworks from manifests or contents
        # 1. Javascript/TypeScript Frameworks
        if has_package_json:
            dependencies = {
                **package_json_content.get("dependencies", {}),
                **package_json_content.get("devDependencies", {})
            }
            if "react" in dependencies:
                frameworks.add("React")
            if "next" in dependencies:
                frameworks.add("NextJS")
            if "express" in dependencies:
                frameworks.add("Express")

        # 2. Python Frameworks
        if has_requirements:
            req_lower = requirements_content.lower()
            if "fastapi" in req_lower:
                frameworks.add("FastAPI")
            if "django" in req_lower:
                frameworks.add("Django")

        # Fallback keyword scanning in files if manifests didn't catch it
        for f_meta in indexed_files[:100]: # Scan first 100 files to avoid heavy operations
            f_path = workspace_path / f_meta["file_path"]
            if f_meta["language"] == "Python":
                try:
                    with open(f_path, "r", encoding="utf-8", errors="ignore") as pf:
                        content = pf.read()
                        if "from fastapi import" in content or "import fastapi" in content:
                            frameworks.add("FastAPI")
                        if "from django.core" in content or "import django" in content:
                            frameworks.add("Django")
                except:
                    pass
            elif f_meta["language"] == "Java":
                try:
                    with open(f_path, "r", encoding="utf-8", errors="ignore") as jf:
                        content = jf.read()
                        if "@SpringBootApplication" in content or "org.springframework.boot" in content:
                            frameworks.add("Spring Boot")
                except:
                    pass
            elif f_meta["language"] in ["JavaScript", "TypeScript"]:
                try:
                    with open(f_path, "r", encoding="utf-8", errors="ignore") as jsf:
                        content = jsf.read()
                        if "import React" in content or "from 'react'" in content:
                            frameworks.add("React")
                        if "import Link from 'next/link'" in content:
                            frameworks.add("NextJS")
                        if "require('express')" in content:
                            frameworks.add("Express")
                except:
                    pass

        # 3. .NET Frameworks
        if has_csproj:
            frameworks.add("ASP.NET")

        # 4. Spring Boot defaults
        if has_pom_xml:
            frameworks.add("Spring Boot")

        # Normalize Language percentages
        language_percentage = {}
        if total_lines > 0:
            for lang, lines in languages.items():
                pct = round((lines / total_lines) * 100)
                if pct > 0:
                    language_percentage[lang] = pct
        else:
            language_percentage = {lang: 100 for lang in languages.keys()}

        return {
            "indexed_files": indexed_files,
            "languages": language_percentage,
            "frameworks": list(frameworks),
            "total_lines": total_lines,
            "file_count": len(indexed_files)
        }
