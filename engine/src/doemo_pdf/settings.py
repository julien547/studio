"""Shared deployment setting for the future template administration page."""

import os
from pathlib import Path
import re

DEFAULT_TEMPLATES_ROOT = Path("/var/lib/doemo-studio/templates")


def templates_dir(client="doemo"):
    """Resolve one collection; caller must separately authorize client access."""
    root = Path(os.environ.get("DOEMO_TEMPLATES_ROOT") or DEFAULT_TEMPLATES_ROOT)
    if not root.is_absolute():
        raise ValueError("DOEMO_TEMPLATES_ROOT doit être un chemin absolu.")
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", client):
        raise ValueError("Identifiant de collection de trames invalide.")
    directory = root / client
    if directory.is_symlink() or directory.resolve().parent != root.resolve():
        raise ValueError("La collection de trames doit être un sous-dossier direct sans lien symbolique.")
    return directory
