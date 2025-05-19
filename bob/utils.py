import logging
import os
import errno
from pathlib import Path
import shlex
import subprocess
import sys
from collections.abc import Iterable
from typing import Sequence, Union, Optional
import shutil
import urllib.request
import urllib.parse


def _configure_logging():
    """
    Setup internal logger. Gets called in __init__.py
    You can overwrite the formatting and everything basically.
    logging.getLogger("bob.cmd") -> is used for printing to stdout, only recipes and commands
    logging.getLogger("bob.log") -> is used for everything else, prints to stderr warnings, errors, debug
    """
    if not hasattr(_configure_logging, "called"):
        setattr(_configure_logging, "called", True)
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


def is_dir_empty(dir: Path) -> bool:
    """
    Small utility, because in the stdlib there is no is_empty.
    Raises `FileNotFoundError` if `dir` is not a directory or it does not exist.
    """

    if not dir.is_dir():
        raise NotADirectoryError(str(dir))
    if not dir.exists():
        raise FileNotFoundError(errno.ENOENT, os.strerror(errno.ENOENT), str(dir))
    return not any(dir.iterdir())


def get_root_script():
    """Returns Path(sys.argv[0]).resolve()"""
    return Path(sys.argv[0]).resolve()


def get_root_dir():
    """Returns Path(sys.argv[0]).resolve().parent"""
    return Path(sys.argv[0]).resolve().parent


def get_latest_timestamp(inp: Union[Path, Iterable[Path]]) -> Optional[float]:
    """
    Returns the latest modification time (st_mtime) of a file or set of files.
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


def get_available_compilers() -> Sequence[str]:
    """Searches for common compilers in the `PATH` and return a list of the found ones."""
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


def git_clone( # TODO: Clean up this function, should propagate errors, it should be handled by target
    url: str,
    dir: Union[Path, None] = None,
    args: Union[Sequence[str], None] = None,
    silent: bool = False,
) -> Path:
    """
    Checks if `git` is in the `PATH` and passes everything to `git clone`.
    NOTE: Only works with urls in the form of https://host/user/repo.git
    Returns the Path to the cloned directory.
    Raises `NotADirectoryError` if `dir` is not empty.
    ```python
    # git clone https://host/user/repo.git <get_root_dir() / repo>
    git_clone("https://host/user/repo.git", dir=None, args=None, silent=False)
    # git clone https://host/user/repo.git --depth 1 -- ./example/
    git_clone("https://host/user/repo.git", dir=Path.cwd() / "example", args=["--depth", "1"], silent=False)
    ```
    """

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

    if dir.exists() and not is_dir_empty(dir):
        raise NotADirectoryError(str(dir))
    cmd.append(str(dir))

    if not silent:
        logging.getLogger("bob.cmd").info(shlex.join(cmd))
    try:
        subprocess.run(cmd, check=True, capture_output=silent)
    except subprocess.CalledProcessError as e:
        logging.critical(f"Git failed: {e.cmd} (exit code: {e.returncode})")

    return dir.resolve()

 # TODO: Document this function
def fetch(url: str, dest: Union[Path, None] = None, overwrite=False, silent=False) -> Path:

    if dest is None:
        parsed_url = urllib.parse.urlparse(url)
        tmp = Path(parsed_url.path)
        if len(tmp.suffixes) == 0 or tmp.name == "":
            raise RuntimeError("No dest is provided and can't interfere the filename.")
        dest = get_root_dir() / tmp.name

    if not overwrite and dest.exists():
        raise FileExistsError(f"File already exists: {str(dest)}")

    if not silent:
        logging.getLogger("bob.cmd").info(f"Fetching {str(url)} -> {str(dest)}")

    with urllib.request.urlopen(url) as resp:
        with open(dest, "wb") as f:
            f.write(resp.read())

    return dest.resolve()
