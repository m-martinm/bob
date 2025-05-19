from .core import Target, Recipe, build, generate_compiledb
from .utils import congifure_logging

__all__ = ["Target", "Recipe", "build", "generate_compiledb"]
__version__ = "0.1.0"

congifure_logging()

