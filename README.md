# phonotaxis
Modules for developing a sound localization task that uses video tracking.

## INSTALLATION
1. Clone the repo:
  * `git clone https://github.com/sjara/phonotaxis.git`
1. Go to the `phonotaxis` folder, and create a conda environment for this package:
  * `conda env create -f environment.yml`
1. Activate the environment:
  * `conda activate phonotaxis`
  * The prompt should now say `(phonotaxis)`, indicating you are in the environment.
1. Create a config file (based on the template):
  * Make a copy of config_template.py and call it config.py
  * Edit your config.py file if necessary
1. Test the installation:
  * `python test_gui_minimal.py`
  * You should see a window showing video from your camera.

