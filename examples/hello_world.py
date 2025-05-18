"""
This shows the really basics of the library.
You define Targets with name, recipe, dependenciesand if its a phony target.
Recipes can be python functions, or a shell command.
Phony targets don't generate files.
"""

from bob import Target, Recipe, build
from platform import system

if system() == "Windows":
    Target(
        name="hello",
        recipe=Recipe(input="echo hello world", raw=True),
        dependencies=None,
        phony=True,
    )
else:
    Target(
        name="hello",
        recipe=Recipe(input=["echo", "hello world"]),
        dependencies=None,
        phony=True,
    )


Target(
    name="hello_from_python",
    recipe=Recipe(lambda: print("hello from python")),
    dependencies=None,
    phony=True,
)

# Passing keyword arguments to build so all targets are executed
# This is equivalent to python hello_world.py --always_make
# To get all available options run `python hello_world.py -h`
build(always_make=True)
