from .core import Target, Recipe, build, generate_compiledb
from .utils import _configure_logging

__all__ = ["Target", "Recipe", "build", "generate_compiledb"]
__version__ = "0.1.0"

_configure_logging()

