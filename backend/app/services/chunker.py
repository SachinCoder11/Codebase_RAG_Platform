from pathlib import Path
from typing import List, Dict, Any

class Chunker:
    MAX_CHUNK_CHARS = 3000  # Approx 750 tokens
    OVERLAP_CHARS = 300     # Approx 75 tokens

    @classmethod
    def chunk_entities(cls, workspace_path: Path, entities: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Takes raw extracted entities and processes them into appropriately sized chunks.
        """
        chunks = []

        for entity in entities:
            content = entity["content"]
            char_count = len(content)

            # Map entity types to chunk types
            # entity types: "class", "function", "method", "module"
            # chunk types: "class", "function", "doc", "config", "code"
            chunk_type = entity.get("chunk_type", "code")
            if chunk_type == "code":
                if entity["type"] == "class":
                    chunk_type = "class"
                elif entity["type"] in ["function", "method"]:
                    chunk_type = "function"
                else:
                    chunk_type = "code"

            # Check if block is small enough to keep intact
            if char_count <= cls.MAX_CHUNK_CHARS:
                chunks.append({
                    "content": content,
                    "file_path": entity["file_path"],
                    "language": entity["language"],
                    "chunk_type": chunk_type,
                    "class_name": entity.get("class_name"),
                    "function_name": entity["name"] if entity["type"] in ["function", "method"] else None,
                    "start_line": entity["start_line"],
                    "end_line": entity["end_line"],
                    "dependencies": entity.get("dependencies", [])
                })
            else:
                # Split large content with overlap
                start_char = 0
                part_idx = 1
                lines = content.splitlines()
                
                # Approximate start/end lines for chunks
                total_lines = len(lines)
                avg_line_len = char_count / total_lines if total_lines > 0 else 1

                while start_char < char_count:
                    end_char = start_char + cls.MAX_CHUNK_CHARS
                    if end_char > char_count:
                        end_char = char_count

                    sub_content = content[start_char:end_char]
                    
                    # Prepend context metadata to help similarity search retain scope
                    context_header = f"// File: {entity['file_path']} | Type: {chunk_type.upper()}"
                    if entity.get("class_name"):
                        context_header += f" | Class: {entity['class_name']}"
                    if entity["type"] in ["function", "method"]:
                        context_header += f" | Function: {entity['name']}"
                    context_header += f" | Part: {part_idx}\n"
                    
                    full_chunk_text = context_header + sub_content

                    # Approximate lines
                    chunk_start_line = entity["start_line"] + int(start_char / avg_line_len)
                    chunk_end_line = entity["start_line"] + int(end_char / avg_line_len)
                    chunk_end_line = min(chunk_end_line, entity["end_line"])

                    chunks.append({
                        "content": full_chunk_text,
                        "file_path": entity["file_path"],
                        "language": entity["language"],
                        "chunk_type": chunk_type,
                        "class_name": entity.get("class_name"),
                        "function_name": entity["name"] if entity["type"] in ["function", "method"] else None,
                        "start_line": chunk_start_line,
                        "end_line": chunk_end_line,
                        "dependencies": entity.get("dependencies", [])
                    })

                    start_char += (cls.MAX_CHUNK_CHARS - cls.OVERLAP_CHARS)
                    part_idx += 1

        return chunks
