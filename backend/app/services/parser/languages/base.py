from abc import ABC, abstractmethod
from pathlib import Path
from typing import List, Dict, Any

class BaseLanguageParser(ABC):
    @abstractmethod
    def parse(self, file_path: Path, code_content: str) -> List[Dict[str, Any]]:
        """
        Parses code content and extracts structural entities.
        
        Returns:
            List of dicts: [
                {
                    "name": str,
                    "type": str,  # "class", "function", "method", "module"
                    "start_line": int,
                    "end_line": int,
                    "content": str,
                    "dependencies": List[str],
                    "class_name": str (optional)
                }
            ]
        """
        pass
