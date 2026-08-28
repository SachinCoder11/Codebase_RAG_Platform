from pathlib import Path
from typing import List, Dict, Any
from app.services.parser.languages.base import BaseLanguageParser

class DotNetParser(BaseLanguageParser):
    def parse(self, file_path: Path, code_content: str) -> List[Dict[str, Any]]:
        raise NotImplementedError(
            ".NET parser scheduled for future release."
        )
