"""Entry script for the packaged app.

``fingerino/__main__.py`` can't be used here: PyInstaller runs its entry script
as ``__main__`` with no parent package, so the relative ``from .main import``
inside it fails with "attempted relative import with no known parent package".
An absolute import from outside the package works in both worlds.
"""

import sys

from fingerino.main import main

if __name__ == "__main__":
    sys.exit(main())
