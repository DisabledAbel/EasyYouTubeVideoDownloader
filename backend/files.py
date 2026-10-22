from pathlib import Path


def directory_bytes(directory: Path) -> int:
    """Measure a working directory while the downloader renames temporary files."""
    total = 0
    for path in directory.iterdir():
        try:
            if path.is_file():
                total += path.stat().st_size
        except FileNotFoundError:
            # A .part file can become its completed filename during this scan.
            continue
    return total
