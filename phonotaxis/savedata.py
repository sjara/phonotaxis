"""
Widget to save data.
"""

import os
import time
import h5py
import sys
from PyQt6.QtWidgets import QGroupBox, QPushButton, QCheckBox, QGridLayout, QFileDialog, QMessageBox
from PyQt6.QtGui import QFont
from PyQt6.QtCore import pyqtSignal
import subprocess

class SaveData(QGroupBox):
    """
    A widget to save data.
    """
    log_message = pyqtSignal(str)

    def __init__(self, datadir='', parent=None):
        """
        Args:
            datadir (str): data root directory.
        """
        super(SaveData, self).__init__(parent)

        self.datadir = datadir
        self.filepath = None

        # -- Create graphical objects --
        self.button = QPushButton("Save data")
        self.button.setMinimumHeight(50)
        buttonFont = QFont(self.button.font())
        buttonFont.setBold(True)
        self.button.setFont(buttonFont)
        self.checkInteractive = QCheckBox('Interactive')
        self.checkInteractive.setChecked(False)
        self.checkOverwrite = QCheckBox('Overwrite')
        self.checkOverwrite.setChecked(False)

        # -- Create layouts --
        layout = QGridLayout()
        layout.addWidget(self.button, 0, 0, 1, 2)
        layout.addWidget(self.checkInteractive, 1, 0)
        layout.addWidget(self.checkOverwrite, 1, 1)
        self.setLayout(layout)
        self.setTitle('Manage Data')

    def to_file(self, containers, currentTrial=None, subject='subject',
                paradigm='paradigm', date=None, suffix='a', filepath=None):
        """
        Saves the history of parameters, events and results to an HDF5 file.

        Args:
            containers: a list of objects that have a method 'append_to_file(h5file)'.
                Examples of these are: gui.Container, controller.SessionController,
                and statematrix.StateMatrix. Each container is responsible for deciding
                what data to save (e.g., all events vs only completed trials).
            currentTrial: (deprecated) Not used. Kept for backward compatibility during
                migration. Will be removed in future version.
            subject: string
            paradigm: string
            date: (optional) string. If none given, today's date will be used.
            suffix: (optional) string. If none give, it will use a lowercase letter.
            filepath: (optional) string with full path. If a filepath is given,
                all other string parameters will be ignored.

        The data is saved to:
        ``datadir/subject/subject_paradigm_YYMMDDa.h5``
        
        Note:
            All containers must implement append_to_file(h5file) with a single
            argument. Each container decides internally what data to save.
        """

        # Construct default filepath if none provided
        if filepath is None:
            if date is None:
                date = time.strftime('%Y%m%d', time.localtime())
            fileExt = 'h5'
            subjectDir = os.path.join(self.datadir, subject)
            if not os.path.exists(subjectDir):
                os.makedirs(subjectDir)
            filename = '{0}_{1}_{2}{3}.{4}'.format(subject, paradigm, date, suffix, fileExt)
            filepath = os.path.join(subjectDir, filename)

        self.log_message.emit('Saving data...')

        # Determine final file path to use
        final_filepath = None
        if self.checkInteractive.isChecked():
            # Open file dialog for user to select/confirm filepath
            final_filepath, ffilter = QFileDialog.getSaveFileName(self, 'Save to file',
                                                                   filepath, '*.*')
            if not final_filepath:
                self.log_message.emit('Saving cancelled.')
                return
        elif os.path.exists(filepath):
            if self.checkOverwrite.isChecked():
                final_filepath = filepath
                self.log_message.emit('File exists. I will overwrite {0}'.format(final_filepath))
            else:
                self.log_message.emit(f'File exists: {filepath}')
                msgBox = QMessageBox()
                msgBox.setIcon(QMessageBox.Icon.Warning)
                msgBox.setText(f'File exists: <br>{filepath} <br>' +
                               'Use <b>Interactive</b> or <b>Overwrite</b> modes.')
                msgBox.setWindowTitle('File exists')
                msgBox.setStandardButtons(QMessageBox.StandardButton.Ok)
                msgBox.exec()
                return
        else:
            final_filepath = filepath

        # -- Create data file --
        # FIXME: check that the file opened correctly
        h5file = h5py.File(final_filepath, 'w')

        success = True
        for container in containers:
            try:
                container.append_to_file(h5file)
            except UserWarning as uwarn:
                success = False
                self.log_message.emit(str(uwarn))
                print(uwarn)
            except:  # pylint: disable=bare-except
                success = False
                h5file.close()
                raise
        h5file.close()

        if success:
            self.filepath = final_filepath
            self.log_message.emit('Saved data to {0}'.format(final_filepath))

if __name__ == '__main__':
    """Example usage of the simplified Session Controller."""
    import sys
    from PyQt6.QtWidgets import QApplication, QVBoxLayout, QWidget
    
    app = QApplication(sys.argv)
    
    # Create main window
    main_window = QWidget()
    main_window.setWindowTitle('Save data example')
    # main_window.resize(300, 200)
    
    # Create widget
    # controller = SessionController(create_gui=True)
    save_data = SaveData(datadir='/tmp/')

    # def on_save(save_data):
    #     save_data.to_file([])
    save_data.button.clicked.connect(save_data.to_file)

    # Layout
    layout = QVBoxLayout()
    layout.addWidget(save_data)
    main_window.setLayout(layout)
    
    # Show window
    main_window.show()

    # Connect cleanup
    # app.aboutToQuit.connect(controller.cleanup)
    
    sys.exit(app.exec())