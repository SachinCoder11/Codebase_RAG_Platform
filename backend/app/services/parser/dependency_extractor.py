import re
import json
from pathlib import Path
from typing import List, Dict

class DependencyExtractor:
    @staticmethod
    def extract_python_dependencies(file_path: Path) -> List[str]:
        deps = []
        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith('#') or line.startswith('-r'):
                        continue
                    # Strip version specs e.g. fastapi>=0.100.0
                    match = re.match(r"^([a-zA-Z0-9_\-\[\]]+)", line)
                    if match:
                        deps.append(match.group(1))
        except Exception:
            pass
        return deps

    @staticmethod
    def extract_js_dependencies(file_path: Path) -> List[str]:
        deps = []
        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                data = json.load(f)
                dependencies = data.get("dependencies", {})
                dev_dependencies = data.get("devDependencies", {})
                deps.extend(list(dependencies.keys()))
                deps.extend(list(dev_dependencies.keys()))
        except Exception:
            pass
        return deps

    @staticmethod
    def extract_java_dependencies(file_path: Path) -> List[str]:
        deps = []
        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
            # Simple regex search for <artifactId> inside <dependency> blocks
            dep_blocks = re.findall(r"<dependency>[\s\S]*?</dependency>", content)
            for block in dep_blocks:
                match = re.search(r"<artifactId>(.*?)</artifactId>", block)
                if match:
                    deps.append(match.group(1))
        except Exception:
            pass
        return deps

    @classmethod
    def extract_all(cls, workspace_path: Path) -> List[str]:
        """
        Scans workspace for dependency manifest files and parses them.
        """
        dependencies = set()
        
        # Python requirements
        req_txt = workspace_path / "requirements.txt"
        if req_txt.exists():
            dependencies.update(cls.extract_python_dependencies(req_txt))

        # Node package
        pkg_json = workspace_path / "package.json"
        if pkg_json.exists():
            dependencies.update(cls.extract_js_dependencies(pkg_json))

        # Java Maven
        pom_xml = workspace_path / "pom.xml"
        if pom_xml.exists():
            dependencies.update(cls.extract_java_dependencies(pom_xml))
            
        return list(dependencies)
