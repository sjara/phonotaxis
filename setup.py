from setuptools import setup, Extension
from Cython.Build import cythonize
import numpy as np

# Define Cython extensions
extensions = [
    Extension(
        name="phonotaxis.sharedbuffer",
        sources=["phonotaxis/sharedbuffer.pyx"],
        include_dirs=[np.get_include()]
    ),
    Extension(
        name="phonotaxis.resultbus",
        sources=["phonotaxis/resultbus.pyx"]
    ),
    Extension(
        name="phonotaxis.videoworkers",
        sources=["phonotaxis/videoworkers.pyx"],
        include_dirs=[np.get_include()]
    ),
]

setup(
    ext_modules=cythonize(extensions, language_level="3")
)
