"""
Widget to save data.
"""

import os
import time
import h5py
import sys
from PyQt6 import QtWidgets
from PyQt6 import QtGui
from PyQt6 import QtCore
import subprocess

class SaveData(QtWidgets.QGroupBox):
    """
    A widget to save data.
    """
    log_message = QtCore.pyqtSignal(str)

    def __init__(self, datadir='', filename='data.h5', parent=None):
        """
        Args:
            datadir (str): data root directory.
        """
        super(SaveData, self).__init__(parent)

        self.datadir = datadir
        self.filename = filename

        # -- Create graphical objects --
        self.button = QtWidgets.QPushButton("Save data")
        self.button.setMinimumHeight(50)
        buttonFont = QtGui.QFont(self.button.font())
        buttonFont.setBold(True)
        self.button.setFont(buttonFont)
        self.checkInteractive = QtWidgets.QCheckBox('Interactive')
        self.checkInteractive.setChecked(False)
        self.checkOverwrite = QtWidgets.QCheckBox('Overwrite')
        self.checkOverwrite.setChecked(False)

        # -- Create layouts --
        layout = QtWidgets.QGridLayout()
        layout.addWidget(self.button, 0, 0, 1, 2)
        layout.addWidget(self.checkInteractive, 1, 0)
        layout.addWidget(self.checkOverwrite, 1, 1)
        self.setLayout(layout)
        self.setTitle('Manage Data')

    def to_file(self, containers, currentTrial=None, subject='subject',
                paradigm='paradigm', date=None, suffix='a', filename=None):
        """
        Saves the history of parameters, events and results to an HDF5 file.

        Args:
            containers: a list of objects that have a method 'append_to_file'.
                Examples of these are: paramgui.Container,
                dispatcher.Dispatcher, statematrix.StateMatrix
            currentTrial: limits how many elements are stored (up to currentTrial-1)
            subject: string
            paradigm: string
            date: (optional) string. If none given, today's date will be used.
            suffix: (optional) string. If none give, it will use a lowercase letter.
            filename: (optional) string with full path. If a filename is given,
                all other string parameters will be ignored.

        The data is saved to:
        ``datadir/subject/subject_paradigm_YYMMDDa.h5``
        """
        if filename is not None:
            defaultFileName = filename
        else:
            if date is None:
                date = time.strftime('%Y%m%d', time.localtime())
            dataRootDir = self.datadir
            fileExt = 'h5'
            fullDataDir = os.path.join(dataRootDir, subject)
            if not os.path.exists(fullDataDir):
                os.makedirs(fullDataDir)
            fileNameOnly = '{0}_{1}_{2}{3}.{4}'.format(subject, paradigm, date, suffix, fileExt)
            defaultFileName = os.path.join(fullDataDir, fileNameOnly)

        self.log_message.emit('Saving data...')

        if self.checkInteractive.isChecked():
            fname, ffilter = QtWidgets.QFileDialog.getSaveFileName(self, 'Save to file',
                                                                   defaultFileName, '*.*')
            if not fname:
                self.log_message.emit('Saving cancelled.')
                return
        elif os.path.exists(defaultFileName):
            if self.checkOverwrite.isChecked():
                fname = defaultFileName
                self.log_message.emit('File exists. I will overwrite {0}'.format(fname))
            else:
                msgBox = QtWidgets.QMessageBox()
                msgBox.setIcon(QtWidgets.QMessageBox.Warning)
                msgBox.setText(f'File exists: <br>{defaultFileName} <br>' +
                               'Use <b>Interactive</b> or <b>Overwrite</b> modes.')
                msgBox.exec_()
                return
        else:
            fname = defaultFileName

        # -- Create data file --
        # FIXME: check that the file opened correctly
        h5file = h5py.File(fname, 'w')

        success = True
        for container in containers:
            try:
                container.append_to_file(h5file, currentTrial)
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
            self.filename = fname
            self.log_message.emit('Saved data to {0}'.format(fname))

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