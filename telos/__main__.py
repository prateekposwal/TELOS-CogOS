"""
Module entry point: ``python -m telos``.

Delegates to telos.cli.main so the package is runnable without installation.
"""

from telos.cli import main

if __name__ == "__main__":
    main()
