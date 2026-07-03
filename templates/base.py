from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict

class DocumentBuilder(ABC):
    """
    FR-36: Base interface for pluggable client document templates.
    Any new client format (e.g., GSTAT, AIASL) must implement this class.
    """
    
    @abstractmethod
    def add_cover_page(self, title: str):
        """Generates the client-specific cover page."""
        pass

    @abstractmethod
    def add_revision_history(self):
        """Generates the document version control table."""
        pass

    @abstractmethod
    def add_toc_placeholder(self):
        """Sets up the Table of Contents structure."""
        pass

    @abstractmethod
    def add_screen_section(self, screen_index: int, image_path: Path, content_data: Dict[str, Any]):
        """
        Formats a single screen's annotated image, procedure prose, 
        and field description table.
        """
        pass

    @abstractmethod
    def save(self, output_path: Path):
        """Saves the final .docx file to disk."""
        pass