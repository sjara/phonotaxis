# phonotaxis
Modules for developing a sound localization task that uses video tracking.

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
  * `python tests/test_gui_minimal.py`
  * You should see a window showing video from your camera.

