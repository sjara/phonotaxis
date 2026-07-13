import os
import sys
import pathlib
import importlib.util

# -- Load phonotaxis/config.py file --
_packageDir = os.path.dirname(os.path.abspath(__file__))
_configDir = os.path.split(_packageDir)[0] # One directory above
_configBasename = 'config.py'
configPath = os.path.join(_configDir,_configBasename)
_spec = importlib.util.spec_from_file_location('phonotaxis.config', configPath)
config = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(config)

import warnings as _warnings
try:
    from . import sharedbuffer, resultbus, videoworkers
    _CYTHON_AVAILABLE = True
except ImportError:
    try:
        from . import sharedbuffer_pure as sharedbuffer
        from . import resultbus_pure as resultbus
        from . import videoworkers_pure as videoworkers
        sys.modules['phonotaxis.sharedbuffer'] = sharedbuffer
        sys.modules['phonotaxis.resultbus'] = resultbus
        sys.modules['phonotaxis.videoworkers'] = videoworkers
        _warnings.warn(
            "Cython extensions not found. Using pure-Python fallback. "
            "Run 'pip install -e .' to compile Cython extensions.",
            RuntimeWarning
        )
        _CYTHON_AVAILABLE = False
    except ImportError as e:
        raise ImportError(f"Could not load phonotaxis package (neither Cython nor pure fallback): {e}")

