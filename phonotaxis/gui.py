"""
Graphical interface utilities. 
"""

import sys
import importlib.util
import socket
import time
import numpy as np
from PyQt6.QtWidgets import QApplication, QMainWindow, QLabel, QVBoxLayout, QHBoxLayout
from PyQt6.QtWidgets import QWidget, QGridLayout, QSlider, QPushButton, QLineEdit, QGroupBox, QComboBox
from PyQt6.QtGui import QImage, QPixmap, QIcon, QPainter, QPen, QColor
from PyQt6.QtCore import QThread, pyqtSignal, Qt, QTimer, QObject
from phonotaxis import utils

BUTTON_COLORS = {'start': 'limegreen', 'stop': 'red'}
LABEL_WIDTH = 120

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Phonotaxis task")
        self.setGeometry(100, 100, 800, 600)
        self.setWindowIcon(self.create_icon())
        self.current_threshold = 10
        self.init_ui()
        
    def create_icon(self):
        """Creates a simple icon using a Font Awesome-like character."""
        pixmap = QPixmap(64, 64)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        font = painter.font()
        font.setPointSize(40)
        painter.setFont(font)
        painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, "🔊")
        painter.end()
        return QIcon(pixmap)

    def init_ui(self):
        """Initializes the user interface elements."""
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.layout = QVBoxLayout(self.central_widget)
        self.video_widget = VideoWidget()
        self.layout.addWidget(self.video_widget)

    def closeEvent(self, event):
        event.accept()

def create_icon():
    """Creates a simple icon using a Font Awesome-like character."""
    pixmap = QPixmap(64, 64)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    font = painter.font()
    font.setPointSize(40)
    painter.setFont(font)
    painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, "🔊")
    painter.end()
    return QIcon(pixmap)

class StatusWidget(QLabel):
    def __init__(self):
        super().__init__("Monitoring video feed...")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.reset()
    def reset(self, label="Monitoring video feed..."):
        self.setText(label)
        self.setStyleSheet("font-size: 20px; font-weight: bold;" +
                           "padding: 10px; border-radius: 6px;" +
                           "background-color: #333; color: #eee;")

class Container(dict):
    def __init__(self):
        super(Container, self).__init__()
        self._groups = {}
        self._paramsToKeepHistory = []
        self.history = {}

    def __setitem__(self, paramName, paramInstance):
        # -- Check if there is already a parameter with that name --
        if paramName in self:
            print('There is already a parameter named {}'.format(paramName))
            raise ValueError
        # -- Check if paramInstance is of valid type and has a group --
        try:
            groupName = paramInstance.get_group()
            historyEnabled = paramInstance.history_enabled()
        except AttributeError:
            print('Container cannot hold items of type {}'.format(type(paramInstance)))
            raise
        # -- Append name of parameter to group list --
        try:
            self._groups[groupName].append(paramName)
        except KeyError:  # If group does not exist yet
            self._groups[groupName] = [paramName]
        # -- Append name of parameter to list of params to keep history --
        if historyEnabled:
            try:
                self._paramsToKeepHistory.append(paramName)
            except KeyError:  # If group does not exist yet
                self._paramsToKeepHistory = [paramName]

        # -- Add paramInstance to Container --
        dict.__setitem__(self, paramName, paramInstance)

    def print_items(self):
        for key, item in self.items():
            print('[{0}] {1}} : {2}}'.format(type(item), key, str(item.get_value())))

    def layout_group(self, groupName):
        """Create box and layout with all parameters of a given group"""
        groupBox = QGroupBox(groupName)
        self.layoutForm = ParamGroupLayout()
        for paramkey in self._groups[groupName]:
            self.layoutForm.add_row(self[paramkey].labelWidget, self[paramkey].editWidget)

        groupBox.setLayout(self.layoutForm)
        return groupBox

    def update_history(self, lastTrial=None):
        """Append the value of each parameter (to track) for this trial."""
        for key in self._paramsToKeepHistory:
            try:
                self.history[key].append(self[key].get_value())
            except KeyError:  # If the key does not exist yet (e.g. first trial)
                self.history[key] = [self[key].get_value()]
            if lastTrial is not None:
                msg = 'The length of the history does not match the number of trials.'
                assert len(self.history[key])==lastTrial+1, msg

    def set_values(self, valuesdict):
        """Set the value of many parameters at once.
        valuesDict is a dictionary of parameters and their values.
        for example: {param1:val1, param2:val2}
        """
        for key, val in valuesdict.items():
            if key in self:
                if isinstance(self[key], MenuParam):
                    self[key].set_string(val)
                else:
                    self[key].set_value(val)
            else:
                print('Warning! {0} is not a valid parameter.'.format(key))

    def from_file(self, filename, dictname='default'):
        """
        Set values from a dictionary stored in a file.
        filename: (string) file with parameters (full path)
        dictname: (string) name of dictionary in filename containing parameters
                  If none is given, it will attempt to load 'default'
        """
        if filename is not None:
            spec = importlib.util.spec_from_file_location('params_module', filename)
            paramsmodule = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(paramsmodule)
            # Old way to load a module from a file
            #paramsmodule = imp.load_source('module.name', filename)
            try:
                self.set_values(getattr(paramsmodule, dictname))
            except AttributeError:
                print("There is no '{0}' in {1}".format(dictname, filename))
                raise

    def append_to_file(self, h5file, currentTrial):
        """
        Append parameters' history to an HDF5 file.
        It truncates data to the trial before currentTrial, because currentTrial has not ended.
        """
        dataParent = 'resultsData'      # Parameters from each trial
        itemsParent = 'resultsLabels'   # Items in menu parameters
        sessionParent = 'sessionData'   # Parameters for the whole session
        # descriptionAttr = 'Description'
        # FIXME: the contents of description should not be the label, but the
        #        description of the parameter (including its units)
        trialDataGroup = h5file.require_group(dataParent)
        menuItemsGroup = h5file.require_group(itemsParent)
        sessionDataGroup = h5file.require_group(sessionParent)

        # -- Append date/time and hostname --
        dset = sessionDataGroup.create_dataset('hostname', data=socket.gethostname())
        dateAndTime = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())
        dset = sessionDataGroup.create_dataset('date', data=dateAndTime)

        # -- Append all other parameters --
        for key, item in self.items():
            # -- Store parameters with history --
            if item.history_enabled():
                if key not in self.history:
                    raise ValueError('No history was recorded for "{0}". '.format(key) +
                                     'Did you use paramgui.Container.update_history() correctly?')
                dset = trialDataGroup.create_dataset(key, data=self.history[key][:currentTrial])
                dset.attrs['Description'] = item.get_label()
                if item.get_type() == 'numeric':
                    dset.attrs['Units'] = item.get_units()
                # FIXME: not very ObjectOriented to use getType
                #        the object should be able to save itself
                if item.get_type() == 'menu':
                    menuList = item.get_items()
                    menuDict = dict(zip(menuList, range(len(menuList))))
                    utils.append_dict_to_hdf5(menuItemsGroup, key, menuDict)
                    dset.attrs['Description'] = '{} menu items'.format(item.get_label())
            else:  # -- Store parameters without history (Session parameters) --
                if item.get_type() == 'string':
                    # dset = sessionDataGroup.create_dataset(key, data=np.str_(item.get_value()))
                    dset = sessionDataGroup.create_dataset(key, data=item.get_value())
                else:
                    dset = trialDataGroup.create_dataset(key, data=item.get_value())
                dset.attrs['Description'] = item.get_label()


class ParamGroupLayout(QGridLayout):
    """Layout for group of parameters."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setVerticalSpacing(0)

    def add_row(self, labelWidget, editWidget):
        currentRow = self.rowCount()
        self.addWidget(labelWidget, currentRow, 0, Qt.AlignmentFlag.AlignRight)
        self.addWidget(editWidget, currentRow, 1, Qt.AlignmentFlag.AlignLeft)

class GenericParam(QWidget):
    """Generic class to use as parent for parameter classes."""
    def __init__(self, labelText='', value=0, group=None,
                 history=True, labelWidth=LABEL_WIDTH, parent=None):
        super().__init__(parent)
        self._group = group
        self._historyEnabled = history
        self._type = None
        self._value = value
        self.labelWidget = QLabel(labelText)
        self.labelWidget.setObjectName('ParamLabel')
        self.labelWidget.setFixedWidth(labelWidth)
        self.editWidget = None

        # Layout for label and edit widget
        self.layout = QVBoxLayout(self)
        self.layout.addWidget(self.labelWidget)

    def get_type(self):
        return self._type

    def get_label(self):
        return str(self.labelWidget.text())

    def get_group(self):
        return self._group

    def in_group(self, groupName):
        return self._group == groupName

    def history_enabled(self):
        return self._historyEnabled

    def set_enabled(self, enabledStatus):
        """Enable/disable the widget"""
        if self.editWidget is not None:
            self.editWidget.setEnabled(enabledStatus)
        #self.labelWidget.setEnabled(enabledStatus)

    def set_value(self, value):
        """Set the parameter value."""
        self._value = value

    def get_value(self):
        """Get the parameter value."""
        return self._value


class StringParam(GenericParam):
    def __init__(self, labelText='', value='', group=None,
                 labelWidth=LABEL_WIDTH, enabled=True, parent=None):
        super().__init__(labelText, value, group,
                         history=False, labelWidth=labelWidth,  parent=parent)
        self._type = 'string'
        if self._historyEnabled:
            raise ValueError('Keeping a history for string parameters is not supported.\n' +
                             'When creating the instance use: history=False')

        # -- Define graphical interface --
        self.editWidget = QLineEdit()
        self.editWidget.setObjectName('ParamEdit')
        self.set_enabled(enabled)

        # -- Define value --
        self.set_value(value)

    def set_value(self, value):
        self._value = value
        self.editWidget.setText(str(value))

    def get_value(self):
        return str(self.editWidget.text())


class NumericParam(GenericParam):
    def __init__(self, labelText='', value=0, units='', group=None, decimals=None,
                 history=True, labelWidth=LABEL_WIDTH, enabled=True, parent=None):
        super(NumericParam, self).__init__(labelText, value, group,
                                           history, labelWidth,  parent)
        self._type = 'numeric'
        self.decimals = decimals

        # -- Define graphical interface --
        self.editWidget = QLineEdit()
        self.editWidget.setToolTip('{0}'.format(units))
        self.editWidget.setObjectName('ParamEdit')
        self.set_enabled(enabled)

        # -- Define value --
        self.set_value(value)
        self._units = units

    def set_value(self, value):
        self._value = value
        if self.decimals is not None:
            strFormat = '{{0:0.{0}f}}'.format(self.decimals)
            self.editWidget.setText(strFormat.format(value))
        else:
            self.editWidget.setText(str(value))

    def get_value(self):
        try:
            return int(self.editWidget.text())
        except ValueError:
            return float(self.editWidget.text())

    def get_units(self):
        return self._units

    def add(self, value):
        self.set_value(self.get_value()+value)

class MenuParam(GenericParam):
    def __init__(self, labelText='', menuItems=(), value=0, group=None,
                 history=True, labelWidth=LABEL_WIDTH, enabled=True, parent=None):
        super(MenuParam, self).__init__(labelText, value, group,
                                        history, labelWidth, parent)
        self._type = 'menu'

        # -- Check if spaces in items --
        if ' ' in ''.join(menuItems):
            raise ValueError('MenuParam items cannot contain spaces')

        # -- Define graphical interface --
        self.editWidget = QComboBox()
        self.editWidget.addItems(menuItems)
        self.editWidget.setObjectName('ParamMenu')

        # -- Define value --
        self._items = menuItems
        self.set_value(value)
        self.set_enabled(enabled)

    def set_value(self, value):
        self._value = value
        self.editWidget.setCurrentIndex(value)

    def set_string(self, newstring):
        # FIXME: graceful warning if wrong string (ValueError exception)
        try:
            value = self._items.index(newstring)
        except ValueError:
            print("'{0}' is not a valid menu item".format(newstring))
            raise
        self._value = value
        self.editWidget.setCurrentIndex(value)

    def get_value(self):
        return self.editWidget.currentIndex()

    def get_string(self):
        return str(self.editWidget.currentText())

    def get_items(self):
        return self._items
    
# class SessionWidger(QWidget):
#     """
#     A widget that contains """

class SessionControlWidget(QWidget):
    resume = pyqtSignal()
    pause = pyqtSignal()
    
    def __init__(self):
        super().__init__()
        # -- Creat a button --
        self.button_start_stop = QPushButton('Text')
        self.button_start_stop.setCheckable(False)
        self.button_start_stop.setMinimumHeight(100)
        # Get current font size
        self.stylestr = ("QPushButton { font-weight: normal; padding: 10px; border-radius: 6px; "
                        "color: black; border: none; }")
        self.button_start_stop.setStyleSheet(self.stylestr.replace("}", "background-color: gray; }"))
        button_font = self.button_start_stop.font()
        button_font.setPointSize(button_font.pointSize()+10)
        self.button_start_stop.setFont(button_font)
        self.layout = QVBoxLayout(self)
        self.layout.addWidget(self.button_start_stop)
        
        # -- Connect signals --
        self.running_state = False
        self.button_start_stop.clicked.connect(self.startOrStop)
        self.stop()
        
    def startOrStop(self):
        """Toggle (start or stop) session running state."""
        if(self.running_state):
            self.stop()
        else:
            self.start()

    def start(self):
        """Resume session."""
        # -- Change button appearance --
        #stylestr = 'QWidget {{ background-color: {} }}'.format(BUTTON_COLORS['stop'])
        #stylestr = self.stylestr + 'background-color: {}'.format(BUTTON_COLORS['stop'])
        stylestr = self.stylestr.replace("}", "background-color: {}".format(BUTTON_COLORS['stop']) + " }")
        self.button_start_stop.setStyleSheet(stylestr)
        self.button_start_stop.setText('Stop')

        self.resume.emit()
        self.running_state = True

    def stop(self):
        """Pause session."""
        # -- Change button appearance --
        #stylestr = 'QWidget {{ background-color: {} }}'.format(BUTTON_COLORS['start'])
        #stylestr = self.stylestr + ' background-color: {}'.format(BUTTON_COLORS['start'])
        stylestr = self.stylestr.replace("}", "background-color: {}".format(BUTTON_COLORS['start']) + " }")
        self.button_start_stop.setStyleSheet(stylestr)
        self.button_start_stop.setText('Start')
        self.pause.emit()
        self.running_state = False
    
        
class VideoWidget(QWidget):
    def __init__(self):
        super().__init__()
        #self.setGeometry(100, 100, 800, 600)
        self.layout = QVBoxLayout(self)
        self.video_label = QLabel("Waiting for camera feed...")
        self.video_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.video_label.setStyleSheet("background-color: #222; color: #fff;" +
                                       "border-radius: 6px;")
        # Set minimum size to match the expected video display size (640x480)
        self.video_label.setMinimumSize(640, 480)
        self.layout.addWidget(self.video_label)
        
        # Store first point trail (list of (x, y) tuples)
        self.first_point_trail = []
        self.max_trail_length = 20

    def display_frame(self, frame, points=(), initzone=(), mask=(), show_trail=True):
        """
        Converts a grayscale frame to a QPixmap and displays it in the video label.
        Args:
            frame (np.ndarray): The grayscale frame to display.
            points (tuple): Tuple of tuples containing the centroid coordinates (x, y).
            initzone (tuple): Tuple containing (x, y, radius) of initiation zone
            mask (tuple): Tuple containing (x, y, radius) of mask
            show_trail (bool): If True, shows the trail of recent centroids. If False, shows only the latest point.
        """
        h, w = frame.shape  # Grayscale frames have only height and width
        bytes_per_line = w
        img_format = QImage.Format.Format_Grayscale8
        convert_to_qt_format = QImage(frame.data, w, h, bytes_per_line, img_format)
        p = convert_to_qt_format.scaled(640, 480, Qt.AspectRatioMode.KeepAspectRatio)
        pixmap = QPixmap.fromImage(p)
        #print(roi[2]); print('------------------------')
        #print(points); print('------------------------')
        if len(initzone):
            self.add_circular_roi(pixmap, initzone[:2], initzone[2], color=(0,0,255))
        if len(mask):
            self.add_circular_roi(pixmap, mask[:2], mask[2], color=(240,240,240))
            #self.add_rectangular_roi(pixmap, mask)
        # Update first point trail with new first point
        if points and points[0][0] > 0:
            self.update_first_point_trail(points[0])
        
        # Draw centroids based on show_trail parameter
        if show_trail:
            # Draw the first point trail
            self.add_first_point_trail(pixmap)
        else:
            # Draw only the latest point(s)
            for point in points:
                if point[0] > 0:
                    self.add_point(pixmap, point)
        
        self.video_label.setPixmap(pixmap)

    def add_point(self, pixmap, point):
        """
        Displays the centroid as a red dot on the video label.
        Args:
            pixmap (QPixmap): The pixmap to draw on.
            point (tuple): The coordinates of the centroid (x, y).
        """
        painter = QPainter(pixmap)
        painter.setPen(Qt.PenStyle.NoPen)  # No border
        painter.setBrush(Qt.GlobalColor.red)
        painter.drawEllipse(point[0] - 5, point[1] - 5, 10, 10)
        painter.end()

    def update_first_point_trail(self, point):
        """
        Updates the first point trail with a new point.
        Args:
            point (tuple): The coordinates of the first point (x, y).
        """
        self.first_point_trail.append(point)
        # Keep only the last max_trail_length points
        if len(self.first_point_trail) > self.max_trail_length:
            self.first_point_trail.pop(0)

    def add_first_point_trail(self, pixmap):
        """
        Draws the first point trail with decreasing transparency.
        Args:
            pixmap (QPixmap): The pixmap to draw on.
        """
        if not self.first_point_trail:
            return
            
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Draw trail points with decreasing alpha (oldest to newest)
        for ind, point in enumerate(self.first_point_trail):
            # Calculate alpha based on position in trail (0 = oldest, -1 = newest)
            alpha = int(255 * (ind + 1) / len(self.first_point_trail))
            
            # Create color with alpha
            color = QColor(255, 0, 0, alpha)  # Red with varying alpha
            painter.setPen(Qt.PenStyle.NoPen)  # No border
            painter.setBrush(color)
            
            # Draw smaller circles for older points, larger for newer ones
            radius = 3 + (ind * 2) // len(self.first_point_trail)
            painter.drawEllipse(point[0] - radius, point[1] - radius, 
                              2 * radius, 2 * radius)
        
        painter.end()

    def clear_first_point_trail(self):
        """
        Clears the first point trail.
        """
        self.first_point_trail.clear()

    def set_trail_length(self, length):
        """
        Sets the maximum length of the first point trail.
        Args:
            length (int): Maximum number of points to keep in the trail.
        """
        self.max_trail_length = max(1, length)
        # Trim existing trail if necessary
        while len(self.first_point_trail) > self.max_trail_length:
            self.first_point_trail.pop(0)

    def add_circular_roi(self, pixmap: QPixmap, center: tuple, radius: int,
                color: tuple = (0,0,255)) -> QPixmap:
        """
        Draw a circular region of interest on a QPixmap.
        """
        #new_pixmap = pixmap.copy()
        painter = QPainter(pixmap)
        pen = QPen(QColor(*color), 3, Qt.PenStyle.SolidLine)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(pen)
        #painter.setPen(Qt.GlobalColor.blue)

        rect_x = center[0] - radius
        rect_y = center[1] - radius
        diameter = 2 * radius

        painter.drawEllipse(rect_x, rect_y, diameter, diameter)
        painter.end()
        #return new_pixmap

    def add_rectangular_roi(self, pixmap: QPixmap, roi: tuple,
                           color: tuple = (255,0,0)) -> QPixmap:
        """
        Draw a rectangular region of interest on a QPixmap.
        
        Args:
            pixmap (QPixmap): The pixmap to draw on
            roi (tuple): (x1, y1, x2, y2) coordinates of the rectangle
            color (tuple): RGB color for the rectangle border (default: red)
        """
        x1, y1, x2, y2 = roi
        painter = QPainter(pixmap)
        pen = QPen(QColor(*color), 2, Qt.PenStyle.SolidLine)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(pen)

        # Draw rectangle from top-left to bottom-right
        width = x2 - x1
        height = y2 - y1
        painter.drawRect(x1, y1, width, height)
        painter.end()


class CustomSlider(QSlider):
    """Custom QSlider that ignores arrow key events."""
    def keyPressEvent(self, event):
        """Override to ignore arrow keys."""
        if event.key() in [Qt.Key.Key_Left, Qt.Key.Key_Right, Qt.Key.Key_Up, Qt.Key.Key_Down]:
            # Ignore arrow keys - let parent handle them
            event.ignore()
        else:
            # For other keys, use default slider behavior
            super().keyPressEvent(event)

OLD_SLIDER_STYLESHEET = """
    QSlider::groove:horizontal {
        border: 1px solid #999;
        height: 8px;
        background: #ddd;
        margin: 2px 0;
        border-radius: 4px;
    }
    QSlider::handle:horizontal {
        background: #555;
        border: 1px solid #555;
        width: 18px;
        margin: -2px 0;
        border-radius: 9px;
    }
    QSlider::add-page:horizontal {
        background: #bbb;
    }
    QSlider::sub-page:horizontal {
        background: #888;
    }
"""

SLIDER_STYLESHEET = """
    QSlider::handle:horizontal {
        background: #555;
    }
    QSlider::add-page:horizontal {
        background: #bbb;
    }
    QSlider::sub-page:horizontal {
        background: #888;
    }
"""

class SliderWidget(QWidget):
    """
    A widget that contains a slider for adjusting a video parameter.
    """
    value_changed = pyqtSignal(int)
    
    def __init__(self, parent=None, maxvalue=128, label="Value", value=None):
        super().__init__(parent)
        self.maxvalue = maxvalue
        self.value = value if value is not None else maxvalue // 2
        self.label = label
        
        self.layout = QHBoxLayout(self)
        # Label to display the current slider value
        self.value_label = QLabel(f"{self.label}: {self.value}")
        self.value_label.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self.value_label.setStyleSheet("font-size: 12px; padding: 4px;")
        self.value_label.setFixedWidth(100)  # Set a fixed width for consistent layout
        self.layout.addWidget(self.value_label)
        # Slider to adjust the value
        self.slider = CustomSlider(Qt.Orientation.Horizontal)
        self.slider.setMinimum(0)
        self.slider.setMaximum(self.maxvalue)
        self.slider.setValue(self.value)
        self.slider.setSingleStep(self.maxvalue//128)
        self.slider.setStyleSheet(SLIDER_STYLESHEET)
        self.slider.valueChanged.connect(self.update_value)
        self.layout.addWidget(self.slider)
        
    def update_value(self, value):
        """
        Updates the current value and the display label.
        This method is connected to the QSlider's valueChanged signal.
        """
        self.value = value
        self.value_label.setText(f"{self.label}: {self.value}")
        self.value_changed.emit(self.value)
        

class Message(object):
    """
    Base container for a message.

    It contains the timestamp, the message, and the sender.
    """
    def __init__(self, text):
        self.text = text
        self.timestamp = time.localtime()

    def __str__(self):
        '''String representation of the message'''
        timeString = time.strftime('[%H:%M:%S] ', self.timestamp)
        return f'{timeString}{self.text}'


class Messenger(QObject):
    """
    Class for keeping a log of messages.

    You use it within a QMainWindow by connecting it's signals and slots as follows:
        self.messagebar = messenger.Messenger()
        self.messagebar.timedMessage.connect(self.show_message)
        self.messagebar.collect('Created window')
    where show_message() does something like:
        self.statusBar().showMessage(str(msg))
    """
    timed_message = pyqtSignal(str)
    messages = []

    def __init__(self):
        super().__init__()

    # @QtCore.Slot(str)
    def collect(self, text):
        new_message = Message(text)
        Messenger.messages.append(new_message)
        self.timed_message.emit(str(new_message))

    def get_list(self):
        return [str(x) for x in Messenger.messages]

    def __str__(self):
        return '\n'.join(self.get_list())



def create_app(task_class):

    app = QApplication(sys.argv)

    # Create a dummy QPainter for icon creation if not running in a full GUI environment
    # This is a workaround for the QPainter issue if run in a headless environment or certain IDEs
    try:
        from PyQt6.QtGui import QPainter
    except ImportError:
        print("QPainter not available. Icon might not render correctly.")
        # Define a dummy QPainter if not available (e.g., in some test environments)
        class QPainter:
            def __init__(self, *args): pass
            def setRenderHint(self, *args): pass
            def setFont(self, *args): pass
            def drawText(self, *args): pass
            def end(self): pass

    # Create and show the main window
    window = task_class()
    window.show()

    # Start the application event loop
    sys.exit(app.exec())

