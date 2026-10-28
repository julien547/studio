"""Shared deployment setting for the future template administration page."""

import os
from pathlib import Path

DEFAULT_TEMPLATES_ROOT = Path("/var/lib/doemo-studio/templates")


def templates_dir(client="doemo"):
    """Resolve one collection; caller must separately authorize client access."""
    root = Path(os.environ.get("DOEMO_TEMPLATES_ROOT") or DEFAULT_TEMPLATES_ROOT)
    if not root.is_absolute():
        raise ValueError("DOEMO_TEMPLATES_ROOT doit être un chemin absolu.")
    # Same single-directory naming rules as the template administration API.
    if (not isinstance(client, str) or not 1 <= len(client) <= 101
            or not client[0].isalnum() or '..' in client
            or not all(ch.isalnum() or ch in '._ -' for ch in client)):
        raise ValueError("Identifiant de collection de trames invalide.")
    directory = root / client
    if directory.is_symlink() or directory.resolve().parent != root.resolve():
        raise ValueError("La collection de trames doit être un sous-dossier direct sans lien symbolique.")
    return directory
