# BOB

Yep, it is another build tool which aims to solve all of the problems for C/C++ developers. :)
On a more serious note, it is a personal project, just for fun and to make my life simpler for 
simple C projects, because I am lazy to learn build tools. It is aimed for C/C++ projects but like
makefiles you can define any recipe, for any file type.

## Goals

- Keep it simple.
- Try to mimic makefiles in python.
- Keep a single file for building projects, no file hashing, no bash/batch scripts, just a single .py file.
- Try to keep everything as typesafe as you can using python, no patterns, no wildcards, no builtin rules.

## TODOs

- [ ] Compilation database 
- [ ] Dry run, see the output without actually executing it.
- [ ] Examples
- [ ] Tests
- [ ] Small wrapper around git clone
- [ ] Small wrapper around requests

## Note

It is not production ready and probably will never be. I am using Python 3.13, in the future I will try to test 
things with older versions.
