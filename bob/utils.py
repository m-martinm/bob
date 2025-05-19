import logging
from pathlib import Path
import subprocess
import sys
from collections.abc import Iterable
from typing import Sequence, Union, Optional
import shutil

def congifure_logging():

    if not hasattr(congifure_logging, "called"):
        setattr(congifure_logging, "called", True)
    else:
        return

    if "bob.cmd" not in logging.Logger.manager.loggerDict:
        cmd_logger = logging.getLogger("bob.cmd")
        cmd_logger.propagate = False
        cmd_logger.setLevel(logging.INFO)
        stream = logging.StreamHandler(sys.stdout)
        stream.setFormatter(logging.Formatter("%(message)s"))
        cmd_logger.addHandler(stream)

    if "bob.log" not in logging.Logger.manager.loggerDict:
        bob_log = logging.getLogger("bob.log")
        bob_log.propagate = False
        bob_log.setLevel(logging.WARNING)
        stream = logging.StreamHandler(sys.stderr)
        stream.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))
        bob_log.addHandler(stream)

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


def get_available_compilers():
    COMPILERS = [
        "gcc",
        "g++",
        "clang",
        "clang++",
        "cl",
        "icc",
        "icpc",
        "tcc",
        "bcc32",
        "dmc",
        "wcl",
        "wcl386",
        "xlc",
        "xlC",
        "pgcc",
        "cc",
        "CC",
    ]
    return [x for x in COMPILERS if shutil.which(x) is not None]


def git_clone(
    url: str, dir: Union[Path, None] = None, args: Union[Sequence[str], None] = None, silent: bool = False
):
    if shutil.which("git") is None:
        raise RuntimeError("Git is not available on the path.")
    cmd = ["git", "clone"]
    if args is not None:
        cmd.extend(args)
        cmd.append("--")
    cmd.append(url)
    _, _, repo = url.replace("https://", "").replace(".git", "").split("/")
    if dir is None:
        dir = get_root_dir() / repo
    cmd.append(str(dir))
    logging.getLogger("bob.log").warning("HALLO")
    # try:
    #     subprocess.run(cmd, check=True, capture_output=silent)
    # except subprocess.CalledProcessError as e:
    #     logging.critical(f"Git failed: {e.cmd} (exit code: {e.returncode})")

    return dir
