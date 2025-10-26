# phonotaxis
Modules for developing sound localization tasks that use video tracking.

## INSTALLATION
1. Clone the repo:
    * `git clone https://github.com/sjara/phonotaxis.git`
2. Go to the `phonotaxis` folder, and create a conda environment for this package:
    * `conda env create -f environment.yml`
3. Activate the environment:
    * `conda activate phonotaxis`
    * The prompt should now say `(phonotaxis)`, indicating you are in the environment.
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
