# phonotaxis
A framework for developing behavioral tasks that use video tracking and sound playback.

## INSTALLATION
1. Clone the repo:
    * `git clone https://github.com/sjara/phonotaxis.git`
2. Create and activate an environment for this package:
    * **Windows:** using conda.
        * `conda env create -f environment.yml`
        * `conda activate phonotaxis`
        * The prompt should now say `(phonotaxis)`, indicating you are in the environment.
    * **Linux (Ubuntu):** using `virtualenvwrapper`.
        * Install system dependencies: `sudo apt install virtualenvwrapper libasound2-dev portaudio19-dev`
        * Add the following to your `~/.bashrc` (if not already there):
          ```bash
          export WORKON_HOME=$HOME/.virtualenvs
          source /usr/share/virtualenvwrapper/virtualenvwrapper.sh
          ```
        * Open a new terminal or run `source ~/.bashrc`.
        * Create the environment: `mkvirtualenv phonotaxis`
          * This also activates it; the prompt should now say `(phonotaxis)`.
        * From the `phonotaxis` folder, install the package and its dependencies:
          `pip install -e .`
        * Next time, just run `workon phonotaxis` to activate it again.
    * **Linux (Ubuntu), alternative:** using [uv](https://github.com/astral-sh/uv).
        * Install system dependencies: `sudo apt install pipx libasound2-dev portaudio19-dev`
        * Install uv (without running a shell script from the web):
          `pipx install uv`
        * From the `phonotaxis` folder: `uv venv` then `source .venv/bin/activate`.
        * Install the package and its dependencies: `uv pip install -e .`
4. Create a config file (based on the template):
    * Make a copy of `config_template.py` and call it `config.py`.
    * Edit your config.py file if necessary.
5. Test the installation:
    * `python examples/example_gui_minimal.py`
    * You should see a window with minimal text on it.
6. For additional examples, see `examples/README.md`.

## CONTENTS
* `phonotaxis`: core modules.
* `examples`: example scripts for demonstrating basic features and full tasks/paradigms.
* `tests`: unit tests for each module.
* `devel`: example use of external modules for lower level control of devices (Arduino, sounds, etc),
   useful for development of this package.

## TESTING
To run the unit tests, make sure you have activated the phonotaxis environment and then run:
```bash
pytest tests/
```

To run tests for a specific module:
```bash
pytest tests/test_statemachine.py
pytest tests/test_statematrix.py
```

For verbose output with detailed test information:
```bash
pytest tests/ -v
```
