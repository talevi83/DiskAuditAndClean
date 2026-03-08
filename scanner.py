"""
scanner.py — Fast recursive disk scanner.
Returns the top-N largest files and folders under a given root path.
"""
from __future__ import annotations

import os
from typing import Callable, Dict, List, Optional, Set

# ── system-critical paths that must never appear in results ───────────────────
_SYS_DRIVE = os.environ.get("SystemDrive", "C:").rstrip("\\")

# Folders on the system drive that would break the OS if deleted
_PROTECTED_PREFIXES: tuple[str, ...] = tuple(
    os.path.normcase(os.path.join(_SYS_DRIVE, p))
    for p in (
        "Windows",
        "Program Files",
        "Program Files (x86)",
        "ProgramData\\Microsoft",
        "Recovery",
        "Boot",
        "EFI",
        "System Volume Information",
        "$Recycle.Bin",
        "$WinREAgent",
        "Users\\Default",
        "Users\\Public\\Documents\\My Music",
        "Users\\Public\\Documents\\My Pictures",
        "Users\\Public\\Documents\\My Videos",
    )
)

# Folder names that are protected on any drive
_PROTECTED_NAMES: Set[str] = {
    "System Volume Information",
    "$Recycle.Bin",
    "$RECYCLE.BIN",
}

# ── safe-to-delete temp / cache locations ─────────────────────────────────────
# Paths under a protected prefix that are still safe to show (whitelist)
_SAFE_TEMP_PREFIXES: tuple[str, ...] = tuple(
    os.path.normcase(os.path.join(_SYS_DRIVE, p))
    for p in (
        "Windows\\Temp",
        "Windows\\SoftwareDistribution\\Download",
        "Windows\\Prefetch",
    )
)

# Folder names that are generally safe to delete regardless of location
_SAFE_TEMP_NAMES: Set[str] = {
    "Temp", "tmp", "Tmp",
    "__pycache__",
    "node_modules",
    ".cache",
    "Cache", "cache",
    "CacheStorage",
    "Code Cache",
    "GPUCache", "GrShaderCache", "ShaderCache",
    "Logs", "logs",
    ".tmp",
    "thumbnails",
    "Crash Reports", "CrashDumps",
}

# Substrings in the path that indicate a temp/cache location
_SAFE_TEMP_PATH_PARTS: tuple[str, ...] = (
    os.sep + "AppData" + os.sep + "Local" + os.sep + "Temp",
    os.sep + "AppData" + os.sep + "Local" + os.sep + "Google" + os.sep + "Chrome" + os.sep + "User Data" + os.sep + "Default" + os.sep + "Cache",
    os.sep + "AppData" + os.sep + "Local" + os.sep + "Microsoft" + os.sep + "Edge" + os.sep + "User Data" + os.sep + "Default" + os.sep + "Cache",
    os.sep + "AppData" + os.sep + "Local" + os.sep + "Mozilla" + os.sep + "Firefox" + os.sep + "Profiles",
)


def _is_safe_temp(path: str) -> bool:
    """Return True if *path* is a known temp/cache location safe to delete."""
    norm = os.path.normcase(path)
    if any(norm == prefix or norm.startswith(prefix + os.sep) for prefix in _SAFE_TEMP_PREFIXES):
        return True
    basename = os.path.basename(path)
    if basename in _SAFE_TEMP_NAMES:
        return True
    norm_lower = norm.lower()
    return any(part.lower() in norm_lower for part in _SAFE_TEMP_PATH_PARTS)


def _is_protected(path: str) -> bool:
    """Return True if *path* is a system-critical location (not safe temp)."""
    if _is_safe_temp(path):
        return False
    norm = os.path.normcase(path)
    if any(norm == prefix or norm.startswith(prefix + os.sep) for prefix in _PROTECTED_PREFIXES):
        return True
    basename = os.path.basename(path)
    return basename in _PROTECTED_NAMES


def format_size(size_bytes: int) -> str:
    """Return a human-readable size string."""
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} PB"


class DiskScanner:
    """
    Recursively scans a directory tree and surfaces the top-N largest items.

    Items smaller than MIN_TRACK_SIZE are ignored to keep the candidate list
    manageable on large drives.
    """

    MIN_TRACK_SIZE = 1 * 1024 * 1024  # 1 MB

    def __init__(self) -> None:
        self._stop = False

    def stop(self) -> None:
        """Signal the running scan to abort cleanly."""
        self._stop = True

    def scan(
        self,
        root: str,
        top_n: int = 20,
        max_depth: int = 4,
        on_progress: Optional[Callable[[str], None]] = None,
    ) -> List[Dict]:
        """
        Scan *root* up to *max_depth* levels deep.

        Returns a list of dicts (sorted by size descending) with keys:
            name, path, size, size_str, type ("file" | "folder")
        """
        self._stop = False
        candidates: List[Dict] = []
        self._walk(root, 0, max_depth, candidates, on_progress)

        candidates = [c for c in candidates if not _is_protected(c["path"])]
        candidates.sort(key=lambda x: x["size"], reverse=True)
        result = candidates[:top_n] if top_n else candidates
        for item in result:
            item["size_str"] = format_size(item["size"])
            item["safe_delete"] = _is_safe_temp(item["path"])
        return result

    # ------------------------------------------------------------------ private

    def _walk(
        self,
        path: str,
        depth: int,
        max_depth: int,
        candidates: List[Dict],
        on_progress: Optional[Callable],
    ) -> int:
        """Recursively walk *path*, return total byte-count, populate *candidates*."""
        if self._stop:
            return 0

        if on_progress:
            on_progress(path)

        total = 0

        try:
            entries = list(os.scandir(path))
        except (PermissionError, OSError):
            return 0

        for entry in entries:
            if self._stop:
                break
            try:
                if entry.is_symlink():
                    continue

                if entry.is_file(follow_symlinks=False):
                    size = entry.stat(follow_symlinks=False).st_size
                    total += size
                    if size >= self.MIN_TRACK_SIZE:
                        candidates.append(
                            {
                                "name": entry.name,
                                "path": entry.path,
                                "size": size,
                                "type": "file",
                            }
                        )

                elif entry.is_dir(follow_symlinks=False):
                    if depth < max_depth:
                        sub_size = self._walk(
                            entry.path, depth + 1, max_depth, candidates, on_progress
                        )
                    else:
                        sub_size = self._dir_size(entry.path)
                    total += sub_size
                    if sub_size >= self.MIN_TRACK_SIZE:
                        candidates.append(
                            {
                                "name": entry.name,
                                "path": entry.path,
                                "size": sub_size,
                                "type": "folder",
                            }
                        )

            except (PermissionError, OSError):
                continue

        return total

    def _dir_size(self, path: str) -> int:
        """Return the total byte-count of a directory tree (no candidate tracking)."""
        total = 0
        try:
            for entry in os.scandir(path):
                try:
                    if entry.is_symlink():
                        continue
                    if entry.is_file(follow_symlinks=False):
                        total += entry.stat(follow_symlinks=False).st_size
                    elif entry.is_dir(follow_symlinks=False):
                        total += self._dir_size(entry.path)
                except (PermissionError, OSError):
                    continue
        except (PermissionError, OSError):
            pass
        return total
