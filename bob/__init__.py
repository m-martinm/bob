from .core import Target, Recipe, build, generate_compiledb
from .utils import _configure_logging, get_system_info, get_root_dir
from pathlib import Path

__all__ = ["Target", "Recipe", "build", "generate_compiledb", "Path", "get_system_info", "get_root_dir"]
__version__ = "0.1.0"

_configure_logging()

