"""The add-on hook: Fingerino Premium, when it is installed.

At start-up Fingerino imports ``fingerino_premium`` if it can. An add-on is a
module with:

    ADDON_API = 1                   # the version of this contract it was built for
    def addon(host: Host) -> object # returns something with a ``features``
                                    # attribute: an iterable of feature ids

The add-on is told what it is allowed to do through ``host.entitled(feature)``,
which Fingerino answers from the licence (licence.py); the add-on never
checks keys itself. Anything that goes wrong (not installed, built for another
contract, raises while loading) leaves Fingerino as the free version, which
must always work fully on its own. A plain import rather than a Python entry
point, because a PyInstaller build carries no package metadata to find entry
points by.
"""

from __future__ import annotations

import importlib
from collections.abc import Callable
from dataclasses import dataclass, field

API = 1
MODULE = "fingerino_premium"


@dataclass(frozen=True)
class Host:
    """What Fingerino offers an add-on."""
    version: str
    entitled: Callable[[str], bool]


@dataclass
class Addon:
    """The outcome of looking for the add-on."""
    installed: bool = False
    version: str = ""
    features: frozenset[str] = field(default_factory=frozenset)
    note: str = ""                  # shown in Settings when it couldn't be used
    impl: object = None             # whatever addon() returned

    @property
    def loaded(self) -> bool:
        return self.impl is not None


def load(host: Host, module: str = MODULE) -> Addon:
    try:
        mod = importlib.import_module(module)
    except ImportError as exc:
        # Missing is normal; a module that is there but fails to import isn't.
        if exc.name == module:
            return Addon()
        return Addon(True, note=f"Fingerino Premium couldn't start ({exc}).")
    except Exception as exc:
        return Addon(True, note=f"Fingerino Premium couldn't start ({exc}).")
    version = str(getattr(mod, "__version__", ""))
    wanted = getattr(mod, "ADDON_API", None)
    if wanted != API:
        newer = isinstance(wanted, int) and wanted > API
        return Addon(True, version, note=(
            "This Fingerino Premium needs a newer Fingerino. Update Fingerino."
            if newer else "This Fingerino Premium is too old for this Fingerino. "
            "Update Fingerino Premium."))
    try:
        impl = mod.addon(host)
        features = frozenset(str(f) for f in getattr(impl, "features", ()))
    except Exception as exc:
        return Addon(True, version, note=f"Fingerino Premium couldn't start ({exc}).")
    return Addon(True, version, features, impl=impl)
