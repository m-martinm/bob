import os
import threading
from typing import Callable, Union
from pathlib import Path
from collections.abc import Iterable
from collections import defaultdict
from .utils import get_root_dir, get_timestamps
import logging
from threading import Thread, Lock
from queue import Queue, Empty
import argparse
import subprocess
from enum import Enum
import shlex
import json

_registry: list["Target"] = list()


class Recipe:
    """
    A recipe can be multiple things.
        1. A python callable object.
        2. A list which gets passed to subprocess.run with check=True
        3. A str which gets passed to subprocess.run with check=True and shell=True
           NOTE: You have to pass raw=True to the contructor
        4. You can construct a recipe with just the program name and add flags with methods. (Recommended)
           NOTE: Internally this is translated to the 2. option.
    Examples:
        1. `Recipe(lambda: print("Hello World"))`
        2. `Recipe(["gcc", "-Iinclude", "-omain", "main.c"])`
        3. `Recipe("gcc -Iinclude -omain main.c", raw=True)`
        4. `Recipe("gcc").add_include("include").add_output("main").add("main.c")`
    """

    class RecipeType(Enum):
        CallableRecipe = 0
        ListRecipe = 1
        RawRecipe = 2
        DefaultRecipe = 3

    def __init__(self, input: Union[Callable, list, str, Path], raw: bool = False, cwd: Union[Path, None] = None):
        self.raw: bool = raw
        self.type: Recipe.RecipeType
        self.input: Union[Callable, list, str]
        if raw:
            if isinstance(input, str):
                self.type = Recipe.RecipeType.RawRecipe
                self.input = input
            else:
                raise TypeError("Only a str input can be raw.")
        else:
            if callable(input):
                self.type = Recipe.RecipeType.CallableRecipe
                self.input = input
            elif isinstance(input, list):
                self.type = Recipe.RecipeType.ListRecipe
                self.input = list(map(str, input))
            elif isinstance(input, (str, Path)):
                self.type = Recipe.RecipeType.DefaultRecipe
                self.input = [str(input)]
            else:
                raise TypeError(
                    f"{type(input)} is not supported type for Recipe input."
                )
        if cwd is None:
            cwd = Path.cwd()
        self.cwd = cwd

    def __repr__(self):
        return f"<Recipe type={self.type.name} input={self.input}>"

    def __str__(self) -> str:
        if self.type == Recipe.RecipeType.CallableRecipe:
            return f"<Callable: {getattr(self.input, '__name__', repr(self.input))}>"
        elif self.type == Recipe.RecipeType.RawRecipe:
            return self.input  # pyright: ignore
        elif self.type in (
            Recipe.RecipeType.ListRecipe,
            Recipe.RecipeType.DefaultRecipe,
        ):
            return shlex.join(self.input)  # pyright: ignore
        else:
            return "<unknown recipe>"

    def run(self, silent=False, check=True):
        logging.getLogger("bob.log").debug(f"Running {repr(self)}")
        if (
            not silent and self.type != Recipe.RecipeType.CallableRecipe
        ):  # TODO: Do we print callables?
            logging.getLogger("bob.cmd").info(str(self))

        if self.type == Recipe.RecipeType.CallableRecipe:
            current = Path.cwd()
            if current != self.cwd:
                os.chdir(self.cwd)
            else:
                current = None

            self.input()  # pyright: ignore

            if current is not None:
                os.chdir(current)

        elif self.type == Recipe.RecipeType.RawRecipe:
            subprocess.run(
                self.input,  # pyright: ignore
                shell=True,
                check=check,
                capture_output=silent,
                cwd=self.cwd
            )
        elif self.type in (
            Recipe.RecipeType.ListRecipe,
            Recipe.RecipeType.DefaultRecipe,
        ):
            subprocess.run(self.input, check=check, capture_output=silent, cwd=self.cwd)  # pyright: ignore
        else:
            raise RuntimeError("Recipe is not valid.")

    def add(self, *args):
        if self.type not in [
            Recipe.RecipeType.DefaultRecipe,
            Recipe.RecipeType.ListRecipe,
        ]:
            raise RuntimeError("You can only add to DefaultRecipe or ListRecipe")

        self.input.extend(map(str, args))  # pyright: ignore
        return self

    def add_include(self, *args):
        """Same as add(), only difference that it add the `-I` prefix for each arg."""
        if self.type not in [
            Recipe.RecipeType.DefaultRecipe,
            Recipe.RecipeType.ListRecipe,
        ]:
            raise RuntimeError("You can only add to DefaultRecipe or ListRecipe")

        self.input.extend(map(lambda a: f"-I{str(a)}", args))  # pyright: ignore
        return self

    def add_libinclude(self, *args):
        """Same as add(), only difference that it add the `-L` prefix for each arg."""
        if self.type not in [
            Recipe.RecipeType.DefaultRecipe,
            Recipe.RecipeType.ListRecipe,
        ]:
            raise RuntimeError("You can only add to DefaultRecipe or ListRecipe")

        self.input.extend(map(lambda a: f"-L{str(a)}", args))  # pyright: ignore
        return self

    def add_link(self, *args):
        """Same as add(), only difference that it add the `-l` prefix for each arg."""
        if self.type not in [
            Recipe.RecipeType.DefaultRecipe,
            Recipe.RecipeType.ListRecipe,
        ]:
            raise RuntimeError("You can only add to DefaultRecipe or ListRecipe")

        self.input.extend(map(lambda a: f"-l{str(a)}", args))  # pyright: ignore
        return self

    def add_output(self, output: Union[str, Path]):
        """Adds `output` as a str to the Recipe with a `-o` prefix."""
        if self.type not in [
            Recipe.RecipeType.DefaultRecipe,
            Recipe.RecipeType.ListRecipe,
        ]:
            raise RuntimeError("You can only add to DefaultRecipe or ListRecipe")

        self.input.append(f"-o{str(output)}")  # pyright: ignore
        return self

    def clone(self):
        from copy import deepcopy

        return Recipe(deepcopy(self.input), raw=self.raw)


class Target:
    """
    This class is the base of the library. They work like makefile targets.
    They have a name, which is an identifier for them and also represents the
    output of the target. They have a recipe, which is basically what the target
    does, for more info see the `Recipe` class. Targets can depend on other targets,
    or files.
    Phony targets are targets which do not produce a file.

    Attributes:
        name (str | Path | Iterable[str | Path]):
            They can be `str` only for phony targets.
        recipe (None | Recipe):
            A recipe which will be executed in the `build()` function.
        dependencies (None | Target | Path | Iterable[Target | Path])
            Other targets or files. They will be checked to decide when and if the
            target should be built.
        phony (bool)
            The target does not produce a file and will always be exected.
    """

    def __init__(
        self,
        name: str | Path | Iterable[str | Path],
        recipe: None | Recipe,
        dependencies: "None | Target | Path | Iterable[Target | Path]" = None,
        phony: bool = False,
    ):
        if phony:
            if not isinstance(name, str):
                raise TypeError(
                    f"{name} is not type of str, but the Target is a phony target."
                )
            else:
                self.name = [name]
        else:
            if isinstance(name, Path):
                self.name = [name]
            elif isinstance(name, Iterable) and all(
                [isinstance(x, Path) for x in name]
            ):
                self.name = list(name)
            else:
                raise TypeError(f"{name} is not type of Path or Iterable of Path.")

        if dependencies is None:
            self.dependencies = []
        elif isinstance(dependencies, (Target, Path)):
            self.dependencies = [dependencies]
        elif isinstance(dependencies, Iterable) and all(
            [isinstance(x, (Target, Path)) for x in dependencies]
        ):
            self.dependencies = list(dependencies)
        else:
            raise TypeError(f"{type(dependencies)} is not valid as dependencies.")

        if not (recipe is None or isinstance(recipe, Recipe)):
            raise TypeError("recipe can be only None or Recipe")

        self.recipe = recipe

        self.phony = phony
        _registry.append(self)

    def __repr__(self):
        return (
            f"Target({self.name=}, {self.dependencies=}, {self.recipe=}, {self.phony=})"
        )

    def __str__(self) -> str:
        return f"{' '.join(map(str, self.name))}"

    def resolve_dependencies(self):
        """
        Resolves the dependencies of `self`.

        Checks for self-dependencies and matches paths to targets.
        """
        new = []
        for dep in self.dependencies:
            if isinstance(dep, Target):
                new.append(dep)
            elif isinstance(dep, Path):
                found = False
                for t in _registry:
                    if dep in t.name:
                        if t == self:
                            raise RuntimeError(
                                f"A target cannot depend on it self. ({t})"
                            )
                        new.append(t)
                        found = True
                        break
                if not found:
                    # logging.warning(f"No Target object found for {str(dep)}") # TODO: does this make sense?
                    new.append(dep)
            else:
                raise TypeError(f"Invalid dependency type: {type(dep)}")
        logging.getLogger("bob.log").debug(f"{self} resolved dependencies: {new}")
        self.dependencies = new

    def should_build(self) -> bool:
        """
        Decides if `self` should be built, based on timestamps.

        If any of the paths in name is earlier (smaller) than any of the
        timestamps of the dependencies it returns True.

        Phony targets always return True.
        If `self` depends on a phony target it also returns True.
        Targets which as name only have a single Path which is a dir and
        exists always return False.
        """

        if self.phony:
            return True
        elif (
            len(self.name) == 1  # TODO: is this too specific?
            and isinstance(self.name[0], Path)
            and self.name[0].is_dir()
            and self.name[0].exists()
        ):
            return False

        timestamps = get_timestamps(self.name)  # pyright: ignore
        if not timestamps:
            return True

        dep_files = []
        for d in self.dependencies:  # pyright: ignore
            inp = d
            if isinstance(d, Target):
                if d.phony:
                    return True
                inp = d.name
            if isinstance(inp, Iterable) and not isinstance(inp, (str, Path)):
                dep_files.extend(inp)
            else:
                dep_files.append(inp)

        dep_timestamps = get_timestamps(dep_files)
        if not dep_timestamps:
            return False

        return min(timestamps) <= max(dep_timestamps)


def build_dependency_graph(targets: list[Target]) -> tuple[defaultdict, defaultdict]:
    """
    Builds a dependency graph.

    Returns:
        graph: Mapping from dependency to list of dependents
        in_degree: Mapping from target to number of dependencies
    """

    graph = defaultdict(list)  # dependency -> list of dependents
    in_degree = defaultdict(int)  # target -> number of dependencies [ready = 0]
    visited = set()
    stack = set()

    def walk(t: Target):
        if t in stack:
            error_msg = " -> ".join(str(x) for x in stack) + f" -> {t.name}"
            raise RuntimeError(f"Cyclic dependency: {error_msg}")
        if t in visited:
            return

        visited.add(t)
        stack.add(t)
        t.resolve_dependencies()

        in_degree.setdefault(t, 0)

        for dep in t.dependencies:
            if isinstance(dep, Target):
                graph[dep].append(t)
                in_degree[t] += 1
                walk(dep)
            elif isinstance(dep, Path):
                logging.getLogger("bob.log").debug(
                    f"Skipping dependency ({str(Path)}) of {t}."
                )
                continue  # TODO: Should a Path be added to in_degree ?
            else:
                raise TypeError(f"Invalid dependency type: {type(dep)}")

        stack.remove(t)

    for t in targets:
        logging.getLogger("bob.log").debug("Walking %s", t)
        walk(t)

    return graph, in_degree


def _parse_arguments(**kwargs) -> dict:
    """
    Internal command line parser, which tries to mimic the options of `make`.
    It is called by the `build()` function.

    It is not intended to be used by the user, but who am I to decide.

    Return a `dict` of command line arguments.
    """

    parser = argparse.ArgumentParser(description="BOB makefile")
    parser.add_argument("targets", nargs="*", help="Targets to build.")
    parser.add_argument(
        "-B",
        "--always-make",
        required=False,
        action="store_true",
        help="Unconditionally make all targets.",
    )
    parser.add_argument(
        "-d",
        "--debug",
        required=False,
        action="store_true",
        help="Print debug information.",
    )
    parser.add_argument(
        "-j",
        "--jobs",
        required=False,
        type=int,
        default=1,
        help="Number of jobs at once, defaults to 1.",
    )
    parser.add_argument(
        "-s",
        "--silent",
        required=False,
        action="store_true",
        help="Don't print commands.",
    )
    parser.add_argument(
        "-k",
        "--keep-going",
        required=False,
        action="store_true",
        help="Don't check returns of recipes, keep going even if one fails.",
    )
    parser.add_argument(
        "-n",
        "--dry-run",
        required=False,
        action="store_true",
        help="Don't execute the recipes, just print them.",
    )
    parser.add_argument(
        "-c",
        "--compile-db",
        required=False,
        action="store_true",
        help="Generates a compile_commands.json to the root directory.",
    )

    parser.set_defaults(**kwargs)
    args = parser.parse_args()
    args = vars(args)

    if args["debug"]:
        logging.getLogger("bob.log").setLevel(logging.DEBUG)

    if args["dry_run"]:
        if args["silent"]:
            logging.getLogger("bob.log").warning(
                "Turning off silent, since --dry-run was also provided."
            )
        args["silent"] = False

    return args


def build(**kwargs) -> bool:
    """
    The main entry point for the library. It does many things:
        1. Parses command line arguments
        2. Builds a dependency graph
        3. Decides which targets should be built
        4. Builds the targets based on the previous steps.

    It passes the keyword arguments to the command line argument parser, which sets these as defaults.
    This means that with command line arguments these can be overwritten.
    This functions should be only called once in the script, after all the Targets are declared.

    Returns True if the build is successfull, else False
    """

    options = _parse_arguments(**kwargs)
    targets = options.get("targets", [])

    logging.getLogger("bob.log").debug(f"Options: {options}")

    if options.get("compile_db", False):
        generate_compiledb()

    if options.get("always_make", False):
        targets = _registry
    elif len(targets) == 0 and len(_registry) > 0:
        targets = [_registry[0]]
    else:  # TODO: Check this logic, not sure if it handles everything correctly
        targets_copy = [t for t in targets]
        for idx, targ in enumerate(targets_copy):
            for treg in _registry:
                if str(targ) in map(str, treg.name):
                    targets[idx] = treg
                    break
            else:
                logging.getLogger("bob.log").warning(
                    f"{targ} is not an existing Target, skipping."
                )
                targets.remove(targ)
                continue
            break

        if len(targets) == 0:
            logging.getLogger("bob.log").critical(
                f"No valid target in {', '.join(targets_copy)}"
            )
            return False

    graph, in_degree = build_dependency_graph(targets)

    queue = Queue()
    lock = Lock()
    scheduled = set()
    fatal_error_event = threading.Event()
    should_be_built = len(in_degree.values())

    for target, value in in_degree.items():
        if value == 0:
            queue.put(target)
            scheduled.add(target)

    def worker():
        built = 0 # TODO: Check if this works (tests are still passing, seems to be faster)
        while True:
            if fatal_error_event.is_set():
                logging.getLogger("bob.log").debug(
                    "Fatal event encountered, exiting thread."
                )
                return

            if built == should_be_built:
                return

            try:
                t: Target = queue.get(timeout=1)
            except Empty:  # TODO: Could other Exceptions get thrown? 3.13: ShutDown
                return

            if t.recipe is not None:
                if t.should_build():
                    if options.get("dry_run", False):
                        logging.getLogger("bob.cmd").info(str(t.recipe))
                    else:
                        logging.getLogger("bob.log").debug(f"Building {t}")
                        try:
                            t.recipe.run(
                                silent=options.get("silent", False),
                                check=not options.get("keep_going", False),
                            )
                        except subprocess.CalledProcessError as e:
                            logging.getLogger("bob.log").critical(
                                f"Recipe failed in target {t}: {e.cmd} (exit code: {e.returncode})"
                            )
                            fatal_error_event.set()
                            break
                        except Exception as e:
                            logging.getLogger("bob.log").critical(
                                f"Unexpected error in target {t} with Recipe {repr(t.recipe)}: {e}"
                            )
                            fatal_error_event.set()
                            break
                else:
                    logging.getLogger("bob.log").debug(f"Skipping {t}")

            with lock:
                built += 1
                for dependent in graph[t]:
                    in_degree[dependent] -= 1
                    if in_degree[dependent] == 0 and dependent not in scheduled:
                        queue.put(dependent)
                        scheduled.add(dependent)
            queue.task_done()

        if (
            fatal_error_event.is_set()
        ):  # TODO: Could cause problems, not sure if this is safe.
            with lock:
                for _ in range(queue.unfinished_tasks):
                    queue.task_done()
    threads = [Thread(target=worker) for _ in range(options.get("jobs", 1))]

    for t in threads:
        t.start()
    queue.join()
    for t in threads:
        t.join()

    if fatal_error_event.is_set():
        logging.getLogger("bob.log").error("Build failed due to a critical error.")
        return False
    else:
        logging.getLogger("bob.log").debug("Build successfull.")
        return True


def generate_compiledb(
    root: Union[None, Path] = None, output: Union[None, Path] = None
):
    """
    Generates a compile_commands.json for LSPs.
    root: Root directory (will be used for directory key for each entry)
    output: You can define where to generate the output. (Default: root / "compile_commands.json")
    """

    TU_EXTENSIONS = (".c", ".cpp", ".cc", ".cxx", ".i", ".ii")
    if root is None:
        root = get_root_dir()

    if output is None:
        output = root / "compile_commands.json"
    elif isinstance(output, Path):
        if output.is_dir():
            output = output / "compile_commands.json"

    compile_db = []
    for target in _registry:
        recipe = target.recipe
        if recipe is None or recipe.type == Recipe.RecipeType.CallableRecipe:
            continue

        if recipe.type == Recipe.RecipeType.RawRecipe:
            args = shlex.split(recipe.input)  # pyright: ignore
        else:
            args = list(map(str, recipe.input))  # pyright: ignore

        for arg in args:
            if arg.endswith(TU_EXTENSIONS):
                compile_db.append(
                    {
                        "directory": str(root),
                        "arguments": args,
                        "file": arg,
                    }
                )

    with open(output, "w") as f:
        json.dump(compile_db, f, indent=2)

    logging.getLogger("bob.log").debug(f"Compile commands written to: {str(output)}")
