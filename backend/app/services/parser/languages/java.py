from pathlib import Path
from typing import List, Dict, Any
from app.services.parser.languages.base import BaseLanguageParser

class JavaParser(BaseLanguageParser):
    def parse(self, file_path: Path, code_content: str) -> List[Dict[str, Any]]:
        raise NotImplementedError(
            "Java parser scheduled for future release."
        )
