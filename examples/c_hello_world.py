"""
This example shows how you can combine python scripting with makefile-like features.
"""

from pathlib import Path
from bob import Target, Recipe, build, generate_compiledb
from bob.utils import get_root_dir
from shutil import rmtree
from platform import system

# Equivalent to Path(__file__).resolve().parent
ROOT: Path = get_root_dir() / "c-hello-world"
SRCDIR: Path = ROOT / "src"
OUTDIR: Path = ROOT / "build"
SRCFILE: Path = SRCDIR / "main.c"
OUTFILE: Path = OUTDIR / f"hello_world{'.exe' if system() == 'Windows' else ''}"

if not ROOT.exists():
    ROOT.mkdir()
if not SRCDIR.exists():
    SRCDIR.mkdir()
if not OUTDIR.exists():
    OUTDIR.mkdir()

Target(
    SRCFILE,
    Recipe(
        lambda: SRCFILE.write_text(
            (
                "#include <stdio.h>\n"
                "int main(void) {\n"
                '\tprintf("Hello, World\\n");\n'
                "return 0;\n"
                "}\n"
            )
        )
    ),
)

Target(OUTFILE, Recipe("gcc").add_output(OUTFILE).add(SRCFILE), SRCFILE)
Target("clean", Recipe(lambda: rmtree(ROOT)), phony=True)
Target("run", Recipe(OUTFILE), phony=True)
build(targets=[OUTFILE])

# Can be also called with the -c flag
# generate_compiledb(root=ROOT)
