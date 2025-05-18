import threading
from typing import Callable, Self, Union
from pathlib import Path
from collections.abc import Iterable
from collections import defaultdict
from .utils import get_latest_timestamp
import logging
from threading import Thread, Lock
from queue import Queue, Empty, ShutDown
import argparse
import subprocess
from enum import Enum
import sys
import shlex

_registry: list["Target"] = list()

class Recipe:
    """
    A recipe can be multiple things.
        1. A python callable object, so a function which gets called.
        2. A list which gets passed to subprocess.run with check=True
        3. A str which gets passed to subprocess.run with check=True and shell=True
           NOTE: You have to pass raw=True to the contructor
        4. You can construct a recipe with just the program name and add flags with methods. (Recommended)
           NOTE: Internally this is translated to the 2. option.
    """

    class RecipeType(Enum):
        CallableRecipe = 0
        ListRecipe = 1
        RawRecipe = 2
        DefaultRecipe = 3

    def __init__(self, input: Union[Callable, list, str, Path], raw: bool = False) -> None:
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

    def __repr__(self):
        return f"<Recipe type={self.type.name} input={self.input}>"
    
    def __str__(self) -> str:
        match self.type:
            case Recipe.RecipeType.CallableRecipe:
                return f"<Callable: {getattr(self.input, '__name__', repr(self.input))}>"
            case Recipe.RecipeType.RawRecipe:
                return self.input # pyright: ignore
            case Recipe.RecipeType.ListRecipe | Recipe.RecipeType.DefaultRecipe:
                return shlex.join(self.input) # pyright: ignore
            case _:
                return "<unknown recipe>"

    def run(self, _silent=False, _check=True):
        if not _silent:
            logging.getLogger("bob.cmd").info(str(self))

        match self.type:
            case Recipe.RecipeType.CallableRecipe:
                self.input()  # pyright: ignore
            case Recipe.RecipeType.RawRecipe:
                subprocess.run(self.input, shell=True, check=_check, capture_output=_silent)  # pyright: ignore
            case Recipe.RecipeType.ListRecipe | Recipe.RecipeType.DefaultRecipe:
                subprocess.run(self.input, check=_check, capture_output=_silent)  # pyright: ignore
            case _:
                raise RuntimeError("Recipe is not valid.")

    # def set_program(self, prog: str | Path):
    #     if self.type not in [
    #         Recipe.RecipeType.DefaultRecipe,
    #         Recipe.RecipeType.ListRecipe,
    #     ]:
    #         raise RuntimeError(
    #             "You can only set the program for DefaultRecipe or ListRecipe"
    #         )
    #
    #     self.input[0] = str(prog)  # pyright: ignore

    def add(self, *args):
        if self.type not in [
            Recipe.RecipeType.DefaultRecipe,
            Recipe.RecipeType.ListRecipe,
        ]:
            raise RuntimeError("You can only add to DefaultRecipe or ListRecipe")

        self.input.extend(map(str, args))  # pyright: ignore
        return self

    def add_include(self, *args):
        """Same as add(), only difference that it add the -I prefix for each arg."""
        if self.type not in [
            Recipe.RecipeType.DefaultRecipe,
            Recipe.RecipeType.ListRecipe,
        ]:
            raise RuntimeError("You can only add to DefaultRecipe or ListRecipe")

        self.input.extend(map(lambda a: f"-I{str(a)}", args))  # pyright: ignore
        return self

    def add_libinclude(self, *args):
        """Same as add(), only difference that it add the -L prefix for each arg."""
        if self.type not in [
            Recipe.RecipeType.DefaultRecipe,
            Recipe.RecipeType.ListRecipe,
        ]:
            raise RuntimeError("You can only add to DefaultRecipe or ListRecipe")

        self.input.extend(map(lambda a: f"-L{str(a)}", args))  # pyright: ignore
        return self

    def add_link(self, *args):
        """Same as add(), only difference that it add the -l prefix for each arg."""
        if self.type not in [
            Recipe.RecipeType.DefaultRecipe,
            Recipe.RecipeType.ListRecipe,
        ]:
            raise RuntimeError("You can only add to DefaultRecipe or ListRecipe")

        self.input.extend(map(lambda a: f"-l{str(a)}", args))  # pyright: ignore
        return self

    def clone(self):
        from copy import deepcopy

        return Recipe(deepcopy(self.input), raw=self.raw)


class Target:
    def __init__(
        self,
        name: str | Path | Iterable[str | Path],
        recipe: None | Recipe,
        dependencies: "None | Target | Path | Iterable[Self | Path]" = None,
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
            raise TypeError()  # TODO:

        if not (recipe is None or isinstance(recipe, Recipe)):
            raise TypeError("recipe can be only None or Recipe")

        self.recipe = recipe

        self.phony = phony
        _registry.append(self)

    def __repr__(self):
        return f"Target({self.name=}, {self.dependencies=}, {self.recipe=}, {self.phony=})"

    def resolve_dependencies(self):
        new = []
        for dep in self.dependencies:
            if isinstance(dep, Target):
                new.append(dep)
            if isinstance(dep, Path):
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
                    new.append(dep)
            else:
                raise TypeError(f"Invalid dependency type: {type(dep)}")
        logging.debug(f"{self.name} resolved dependencies: {new}")
        self.dependencies = new

    def should_build(self) -> bool:
        if self.phony:
            return True

        ret = False
        timestamp = get_latest_timestamp(self.name)  # pyright: ignore
        logging.debug(f"Timestamp of {self.name}: {timestamp}")
        if timestamp is None:
            return True
        for d in self.dependencies:  # pyright: ignore
            inp = d
            if isinstance(d, Target):
                if d.phony:
                    return True
                inp = d.name
            other_ts = get_latest_timestamp(inp)  # pyright: ignore
            logging.debug(f"Timestamp of {inp}: {other_ts}")
            if other_ts is not None and timestamp <= other_ts:
                return True

        return ret


def build_dependency_graph(targets: list[Target]):
    graph = defaultdict(list)  # dependency -> list of dependents
    in_degree = defaultdict(int)  # target -> number of dependencies [ready = 0]
    visited = set()
    stack = set()

    def walk(t: Target):
        if t in stack:
            error_msg = " -> ".join(str(x.name) for x in stack) + f" -> {t.name}"
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
                continue
            else:
                raise TypeError(f"Invalid dependency type: {type(dep)}")

        stack.remove(t)

    for t in targets:
        logging.debug("Walking %s", t.name)
        walk(t)

    return graph, in_degree


def _parse_arguments(**kwargs) -> dict:
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

    parser.set_defaults(**kwargs)
    args = parser.parse_args()
    args = vars(args)
    if args["debug"]:
        logging.basicConfig(format="%(message)s", level=logging.DEBUG)
    else:
        logging.basicConfig(format="%(message)s", level=logging.WARNING)

    cmd_logger = logging.getLogger("bob.cmd")
    cmd_logger.propagate = False
    cmd_logger.setLevel(logging.INFO)  # always print

    stream = logging.StreamHandler(sys.stdout)
    stream.setFormatter(logging.Formatter("%(message)s"))  # no prefix
    cmd_logger.addHandler(stream)

    return args


def build(**kwargs):
    """Should be called once at the end.
    There are three possibilities:
    1. Targets(s) are provided, they will be executed.
    2. None is provided, the function checks the command line arguments
       for target names.
    3. No command line arguments are provided, the first target in _registry is built.
    """

    options = _parse_arguments(**kwargs)
    targets = options.get("targets", [])
    if len(targets) == 0 and len(_registry) > 0:
        targets = [_registry[0]]

    graph, in_degree = build_dependency_graph(targets)

    queue = Queue()
    lock = Lock()
    scheduled = set()
    fatal_error_event = threading.Event()

    for target, value in in_degree.items():
        if value == 0:
            queue.put(target)
            scheduled.add(target)

    def worker():
        while True:
            if fatal_error_event.is_set():
                logging.debug("Fatal event encountered, exiting thread.")
                return

            try:
                t: Target = queue.get(timeout=1)
            except (Empty, ShutDown):
                return

            if t.recipe is not None:
                if t.should_build():
                    logging.debug(f"Building {t.name}")
                    try:
                        t.recipe.run()
                    except subprocess.CalledProcessError as e:
                        logging.critical(f"Recipe failed in target {t.name}: {e.cmd} (exit code: {e.returncode})")
                        fatal_error_event.set()
                        queue.task_done()
                        return
                    except Exception as e:
                        logging.critical(f"Error in {t.name}: {e}")
                        fatal_error_event.set()
                        queue.task_done()
                        return
                else:
                    logging.debug(f"Skipping {t.name}")

            with lock:
                for dependent in graph[t]:
                    in_degree[dependent] -= 1
                    if in_degree[dependent] == 0 and dependent not in scheduled:
                        queue.put(dependent)
                        scheduled.add(dependent)
            queue.task_done()

    threads = [
        Thread(target=worker) for _ in range(options.get("jobs", 1))
    ]  # TODO: Get workers from command line
    for t in threads:
        t.start()
    queue.join()
    for t in threads:
        t.join()

    if fatal_error_event.is_set():
        logging.error("Build failed due to a critical error.")
        return 1
    else:
        logging.debug("Build successfull.")
        return 0
