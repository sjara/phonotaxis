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
  * `python tests/test_gui_minimal.py`
  * You should see a window with minimal text on it.

## ADDITIONAL TESTS:
1. Test video and object tracking:
  * `python tests/test_video_tracking.py`
  * You should see a window with b/w video from your camera and red dot tracking a black object.
2. Test adding the session controller and parameters:
  * `python tests/test_gui_parameters.py`
  * This will show a window with a green "Start" button and some text boxes for parameters.

## CONTENTS
* `phonotaxis`: core modules.
* `tests`: test scripts for each capability (video, arduino, etc).
* `examples`: example scripts for creating full tasks (which we call paradigms).
