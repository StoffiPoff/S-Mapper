#!/usr/bin/env python3
"""Convenience runner for S-Mapper during development.

This script executes the package entrypoint module so you can run the
application with a single command from the repository root:

    python run_app.py

It forwards execution to `s_mapper.app` (same behaviour as
`python -m s_mapper.app`) and avoids duplicating startup logic.
"""
import runpy

if __name__ == "__main__":
    # Run the package entrypoint as if executed with -m so the module-level
    # __main__ block in s_mapper.app runs.
    runpy.run_module('s_mapper.app', run_name='__main__')
