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
