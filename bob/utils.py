from pathlib import Path
import sys
from collections.abc import Iterable
from typing import Union, Optional


def get_root_script():
    """Returns Path(sys.argv[0]).resolve()"""
    return Path(sys.argv[0]).resolve()


def get_root_dir():
    """Returns Path(sys.argv[0]).resolve().parent"""
    return Path(sys.argv[0]).resolve().parent


def get_latest_timestamp(inp: Union[Path, Iterable[Path]]) -> Optional[float]:
    """Returns the latest modification time (st_mtime) of a file or set of files.
    If any file doesn't exist, returns None.
    """

    def safe_stat_mtime(path: Path):
        try:
            return path.stat().st_mtime
        except (OSError, ValueError, FileNotFoundError):
            return None

    if isinstance(inp, Path):
        return safe_stat_mtime(inp)
    elif isinstance(inp, Iterable):
        latest = None
        for x in inp:
            if isinstance(x, Path):
                ts = safe_stat_mtime(x)
                if ts is None:
                    return None
                if latest is None or ts > latest:
                    latest = ts

        return latest
