"""
Graphical interface utilities for phonotaxis experiments.

This module provides GUI components for creating parameter-driven experimental
interfaces using PyQt6. It includes:

- Container: A smart container that automatically handles parameters with or without trial history
- Parameter widgets: StringParam, NumericParam, MenuParam for user input
- Messenger: A message logging system with Qt signals
- Utility functions for creating Qt applications

Classes:
    Container: Smart container that automatically manages parameters with/without trial history
    ParamGroupLayout: Grid layout for organizing parameter widgets
    GenericParam: Base class for all parameter widgets
    StringParam: Parameter widget for string values (history not supported)
    NumericParam: Parameter widget for numeric values (int or float)
    MenuParam: Parameter widget for menu/dropdown selections
    Message: Container for a timestamped message
    Messenger: Message logging system with Qt signal support

Functions:
    create_icon: Creates a simple speaker icon for application windows
    create_app: Creates and runs a PyQt6 application

Note:
    Container automatically detects whether parameters have history enabled.
    Parameters with history=True are tracked across trials and saved to 'resultsData'.
    Parameters with history=False are saved once to 'sessionData'.
"""

import sys
import importlib.util
import time
import signal
from typing import Optional, Dict, List, Any, Union, Tuple
from PyQt6.QtWidgets import QApplication, QLabel, QVBoxLayout, QHBoxLayout
from PyQt6.QtWidgets import QWidget, QGridLayout, QLineEdit, QGroupBox, QComboBox
from PyQt6.QtGui import QPixmap, QIcon, QPainter
from PyQt6.QtCore import pyqtSignal, Qt, QObject
from phonotaxis import utils
import h5py


LABEL_WIDTH = 120


def create_icon() -> QIcon:
    """
    Create a simple speaker icon for application windows.
    
    Returns:
        QIcon: A 64x64 pixel icon with a speaker emoji.
    """
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


class Container:
    """
    Smart container for managing experimental parameters.
    
    This class automatically handles both trial-varying parameters (with history tracking)
    and session-constant parameters (without history). Parameters are organized into groups
    for display and saved appropriately to HDF5 files.
    
    Parameters with history=True are tracked across trials and saved to 'resultsData'.
    Parameters with history=False are saved once to 'sessionData'.
    
    Attributes:
        _params: Internal dictionary storing parameter objects
        _groups: Dictionary mapping group names to lists of parameter names
        _paramsToKeepHistory: List of parameter names with history tracking enabled
        history: Dictionary mapping parameter names to lists of values (one per trial)
    
    Example:
        >>> params = Container()
        >>> # Session-level parameter (no history)
        >>> params['subject'] = StringParam('Subject', value='mouse01', group='Session')
        >>> # Trial-varying parameters (with history)
        >>> params['frequency'] = NumericParam('Frequency', value=1000, units='Hz',
        ...                                    group='Sound', history=True)
        >>> params['amplitude'] = NumericParam('Amplitude', value=0.5, 
        ...                                    group='Sound', history=True)
        >>> params.update_history()        # Only tracks frequency and amplitude
        >>> params.append_to_file(h5file)  # Saves all appropriately
    """
    def __init__(self) -> None:
        self._params: Dict[str, 'GenericParam'] = {}
        self._groups: Dict[str, List[str]] = {}
        self._paramsToKeepHistory: List[str] = []
        self.history: Dict[str, List[Any]] = {}

    def __setitem__(self, paramName: str, paramInstance: 'GenericParam') -> None:
        """
        Add a parameter to the container.
        
        Automatically detects whether the parameter has history tracking enabled
        and manages it appropriately.
        
        Args:
            paramName: Unique name for the parameter
            paramInstance: Parameter object (must be a GenericParam subclass)
            
        Raises:
            ValueError: If a parameter with the same name already exists
            TypeError: If paramInstance is not a valid parameter type
        """
        # -- Check if there is already a parameter with that name --
        if paramName in self._params:
            raise ValueError(f'There is already a parameter named {paramName}')
        # -- Check if paramInstance is of valid type and has a group --
        try:
            groupName = paramInstance.get_group()
            historyEnabled = paramInstance.history_enabled()
        except AttributeError:
            raise TypeError(f'Container cannot hold items of type {type(paramInstance)}')
        
        # -- Append name of parameter to group list --
        try:
            self._groups[groupName].append(paramName)
        except KeyError:  # If group does not exist yet
            self._groups[groupName] = [paramName]
        
        # -- Add to history tracking list if enabled --
        if historyEnabled:
            self._paramsToKeepHistory.append(paramName)

        # -- Add paramInstance to Container --
        self._params[paramName] = paramInstance

    def __getitem__(self, paramName: str) -> 'GenericParam':
        """
        Get a parameter from the container.
        
        Args:
            paramName: Name of the parameter to retrieve
            
        Returns:
            The parameter object
            
        Raises:
            KeyError: If parameter name doesn't exist
        """
        return self._params[paramName]

    def __contains__(self, paramName: str) -> bool:
        """
        Check if a parameter exists in the container.
        
        Args:
            paramName: Name of the parameter to check
            
        Returns:
            True if parameter exists, False otherwise
        """
        return paramName in self._params

    def __len__(self) -> int:
        """Return the number of parameters in the container."""
        return len(self._params)

    def __iter__(self):
        """Iterate over parameter names."""
        return iter(self._params)

    def keys(self):
        """Return a view of parameter names."""
        return self._params.keys()

    def values(self):
        """Return a view of parameter objects."""
        return self._params.values()

    def items(self):
        """Return a view of (name, parameter) pairs."""
        return self._params.items()

    def print_items(self) -> None:
        """Print all parameters and their current values to console."""
        for key, item in self._params.items():
            print(f'[{type(item)}] {key} : {str(item.get_value())}')

    def layout_group(self, groupName: str) -> QGroupBox:
        """
        Create a QGroupBox with layout containing all parameters in a group.
        
        Args:
            groupName: Name of the parameter group to layout
            
        Returns:
            QGroupBox containing all parameters in the specified group
        """
        groupBox = QGroupBox(groupName)
        self.layoutForm = ParamGroupLayout()
        for paramkey in self._groups[groupName]:
            self.layoutForm.add_row(self[paramkey].labelWidget, self[paramkey].editWidget)

        groupBox.setLayout(self.layoutForm)
        return groupBox

    def update_history(self, lastTrial: Optional[int] = None) -> None:
        """
        Append current values of tracked parameters to history.
        
        Call this method once per trial to record parameter values. Only
        parameters with history=True will be tracked.
        
        Args:
            lastTrial: Expected trial number (0-indexed). If provided, validates
                      that history length matches expected trial count.
                      
        Raises:
            AssertionError: If lastTrial is provided and history length doesn't match
        """
        for key in self._paramsToKeepHistory:
            try:
                self.history[key].append(self[key].get_value())
            except KeyError:  # If the key does not exist yet (e.g. first trial)
                self.history[key] = [self[key].get_value()]
            if lastTrial is not None:
                msg = 'The length of the history does not match the number of trials.'
                assert len(self.history[key])==lastTrial+1, msg

    def set_values(self, valuesdict: Dict[str, Any]) -> None:
        """
        Set values for multiple parameters at once.
        
        Args:
            valuesdict: Dictionary mapping parameter names to their new values.
                       For MenuParam, values can be strings (menu item names) or
                       integers (menu indices).
                       
        Warns:
            UserWarning: If a key in valuesdict doesn't match any parameter
            
        Example:
            >>> params.set_values({'frequency': 2000, 'amplitude': 0.8})
        """
        for key, val in valuesdict.items():
            if key in self._params:
                if isinstance(self._params[key], MenuParam):
                    self._params[key].set_string(val)
                else:
                    self._params[key].set_value(val)
            else:
                import warnings
                warnings.warn(f'"{key}" is not a valid parameter', UserWarning)

    def from_file(self, filename: Optional[str], dictname: str = 'default') -> None:
        """
        Load parameter values from a Python file containing a dictionary.
        
        Args:
            filename: Full path to Python file containing parameter definitions
            dictname: Name of dictionary variable in the file to load
            
        Raises:
            AttributeError: If the specified dictionary name doesn't exist in file
            
        Example:
            >>> params.from_file('config.py', 'default')
        """
        if filename is not None:
            spec = importlib.util.spec_from_file_location('params_module', filename)
            paramsmodule = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(paramsmodule)
            try:
                self.set_values(getattr(paramsmodule, dictname))
            except AttributeError:
                raise AttributeError(f"There is no '{dictname}' in {filename}")

    def append_to_file(self, h5file: h5py.File) -> None:
        """
        Append parameters to an HDF5 file.
        
        Saves parameters appropriately based on their history tracking:
        - Parameters with history=True: saved to 'resultsData' as arrays (one value per trial)
        - Parameters with history=False: saved to 'sessionData' as scalars (single value)
        
        Only completed trials (those for which update_history() was called) are saved
        for history-tracked parameters.
        
        Args:
            h5file: Open HDF5 file object
            
        Raises:
            ValueError: If no history was recorded for a history-enabled parameter
        """
        # -- Save parameters with history to resultsData --
        if self._paramsToKeepHistory:
            trialDataGroup = h5file.require_group('resultsData')
            menuItemsGroup = h5file.require_group('resultsLabels')
            
            for key in self._paramsToKeepHistory:
                item = self._params[key]
                if key not in self.history:
                    raise ValueError(f'No history was recorded for "{key}". '
                                     'Did you use Container.update_history() correctly?')
                # Save all recorded history (only completed trials have been recorded)
                dset = trialDataGroup.create_dataset(key, data=self.history[key])
                dset.attrs['Description'] = item.get_label()
                if item.get_type() == 'numeric':
                    dset.attrs['Units'] = item.get_units()
                # Save menu item labels
                if item.get_type() == 'menu':
                    menuList = item.get_items()
                    menuDict = dict(zip(menuList, range(len(menuList))))
                    utils.append_dict_to_hdf5(menuItemsGroup, key, menuDict)
                    dset.attrs['Description'] = f'{item.get_label()} menu items'
        
        # -- Save parameters without history to sessionData --
        sessionParams = [k for k in self._params if k not in self._paramsToKeepHistory]
        if sessionParams:
            sessionDataGroup = h5file.require_group('sessionData')
            
            for key in sessionParams:
                item = self._params[key]
                dset = sessionDataGroup.create_dataset(key, data=item.get_value())
                dset.attrs['Description'] = item.get_label()
                if item.get_type() == 'numeric':
                    dset.attrs['Units'] = item.get_units()


class ParamGroupLayout(QGridLayout):
    """
    Grid layout optimized for displaying parameter label-widget pairs.
    
    This layout arranges parameters in rows with labels right-aligned on the left
    and edit widgets left-aligned on the right, with minimal vertical spacing.
    """
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setVerticalSpacing(0)

    def add_row(self, labelWidget: QLabel, editWidget: QWidget) -> None:
        """
        Add a parameter row to the layout.
        
        Args:
            labelWidget: QLabel displaying the parameter name
            editWidget: QWidget for editing the parameter value
        """
        currentRow = self.rowCount()
        self.addWidget(labelWidget, currentRow, 0, Qt.AlignmentFlag.AlignRight)
        self.addWidget(editWidget, currentRow, 1, Qt.AlignmentFlag.AlignLeft)


class GenericParam(QWidget):
    """
    Base class for all parameter widgets.
    
    This abstract-like base class provides common functionality for parameter
    widgets including labeling, grouping, and history tracking. Subclasses
    override set_value() and get_value() to provide type-specific behavior.
    
    Attributes:
        _group: Name of the parameter group (used for organizing UI)
        _historyEnabled: Whether to track this parameter's value across trials
        _type: String identifier for the parameter type (set by subclasses)
        _value: Current parameter value
        labelWidget: QLabel displaying the parameter name
        editWidget: QWidget for editing the value (set by subclasses)
        
    Args:
        labelText: Display name for the parameter
        value: Initial value
        group: Group name for organizing related parameters
        history: Whether to track value history across trials
        labelWidth: Fixed width for the label widget in pixels
        parent: Parent QWidget
    """
    def __init__(self, labelText: str = '', value: Any = 0, group: Optional[str] = None,
                 history: bool = True, labelWidth: int = LABEL_WIDTH, parent: Optional[QWidget] = None) -> None:
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

    def get_type(self) -> Optional[str]:
        """Return the parameter type string ('string', 'numeric', or 'menu')."""
        return self._type

    def get_label(self) -> str:
        """Return the parameter's display label text."""
        return str(self.labelWidget.text())

    def get_group(self) -> Optional[str]:
        """Return the name of the group this parameter belongs to."""
        return self._group

    def in_group(self, groupName: str) -> bool:
        """
        Check if this parameter belongs to a specific group.
        
        Args:
            groupName: Group name to check
            
        Returns:
            True if parameter belongs to the specified group
        """
        return self._group == groupName

    def history_enabled(self) -> bool:
        """Return whether history tracking is enabled for this parameter."""
        return self._historyEnabled

    def set_enabled(self, enabledStatus: bool) -> None:
        """
        Enable or disable the parameter's edit widget.
        
        Args:
            enabledStatus: True to enable editing, False to disable
        """
        """Enable/disable the widget"""
        if self.editWidget is not None:
            self.editWidget.setEnabled(enabledStatus)
        #self.labelWidget.setEnabled(enabledStatus)

    def set_value(self, value: Any) -> None:
        """Set the parameter value."""
        self._value = value

    def get_value(self) -> Any:
        """Get the parameter value."""
        return self._value


class StringParam(GenericParam):
    """
    Parameter widget for string values.
    
    Provides a text input field (QLineEdit) for entering string values.
    History tracking is not supported for string parameters.
    
    Args:
        labelText: Display name for the parameter
        value: Initial string value
        group: Group name for organizing related parameters
        labelWidth: Fixed width for the label widget in pixels
        enabled: Whether the widget is initially enabled
        parent: Parent QWidget
        
    Raises:
        ValueError: If history=True is passed (not supported for strings)
    """
    def __init__(self, labelText: str = '', value: str = '', group: Optional[str] = None,
                 history: bool = False, labelWidth: int = LABEL_WIDTH, enabled: bool = True, 
                 parent: Optional[QWidget] = None) -> None:
        super().__init__(labelText, value, group,
                         history=history, labelWidth=labelWidth,  parent=parent)
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

    def set_value(self, value: str) -> None:
        self._value = value
        self.editWidget.setText(str(value))

    def get_value(self) -> str:
        return str(self.editWidget.text())


class NumericParam(GenericParam):
    """
    Parameter widget for numeric values (integers or floats).
    
    Provides a text input field (QLineEdit) that parses numeric input.
    Automatically attempts to parse as int first, falling back to float.
    Optionally formats display with a fixed number of decimal places.
    
    Attributes:
        decimals: Number of decimal places for display (None for automatic)
        _units: Units string (displayed as tooltip)
    
    Args:
        labelText: Display name for the parameter
        value: Initial numeric value
        units: Units string (shown as tooltip on the widget)
        group: Group name for organizing related parameters
        decimals: Number of decimal places for display formatting (None for automatic)
        history: Whether to track value history across trials
        labelWidth: Fixed width for the label widget in pixels
        enabled: Whether the widget is initially enabled
        parent: Parent QWidget
    """
    def __init__(self, labelText: str = '', value: Union[int, float] = 0, units: str = '', 
                 group: Optional[str] = None, decimals: Optional[int] = None,
                 history: bool = True, labelWidth: int = LABEL_WIDTH, enabled: bool = True, 
                 parent: Optional[QWidget] = None) -> None:
        super(NumericParam, self).__init__(labelText, value, group,
                                           history, labelWidth,  parent)
        self._type = 'numeric'
        self.decimals = decimals

        # -- Define graphical interface --
        self.editWidget = QLineEdit()
        self.editWidget.setToolTip(f'{units}')
        self.editWidget.setObjectName('ParamEdit')
        self.set_enabled(enabled)

        # -- Define value --
        self.set_value(value)
        self._units = units

    def set_value(self, value: Union[int, float]) -> None:
        self._value = value
        if self.decimals is not None:
            strFormat = '{{0:0.{0}f}}'.format(self.decimals)
            self.editWidget.setText(strFormat.format(value))
        else:
            self.editWidget.setText(str(value))

    def get_value(self) -> Union[int, float]:
        try:
            return int(self.editWidget.text())
        except ValueError:
            return float(self.editWidget.text())

    def get_units(self) -> str:
        """Return the units string for this parameter."""
        return self._units

    def add(self, value: Union[int, float]) -> None:
        """
        Add a value to the current parameter value.
        
        Args:
            value: Amount to add (can be negative for subtraction)
        """
        self.set_value(self.get_value()+value)


class MenuParam(GenericParam):
    """
    Parameter widget for menu/dropdown selections.
    
    Provides a dropdown menu (QComboBox) for selecting from a fixed set of options.
    Values are stored as integer indices but can be accessed as strings.
    
    Attributes:
        _items: Tuple of menu item strings
    
    Args:
        labelText: Display name for the parameter
        menuItems: Tuple of string options for the menu
        value: Initial value as index (0-based)
        group: Group name for organizing related parameters
        history: Whether to track value history across trials
        labelWidth: Fixed width for the label widget in pixels
        enabled: Whether the widget is initially enabled
        parent: Parent QWidget
        
    Raises:
        ValueError: If menuItems is empty or contains spaces
        
    Example:
        >>> port_param = MenuParam('Port', menuItems=('left', 'right'), value=0)
        >>> port_param.get_value()  # Returns 0
        >>> port_param.get_string()  # Returns 'left'
    """
    def __init__(self, labelText: str = '', menuItems: Tuple[str, ...] = (), value: int = 0, 
                 group: Optional[str] = None, history: bool = True, labelWidth: int = LABEL_WIDTH, 
                 enabled: bool = True, parent: Optional[QWidget] = None) -> None:
        super(MenuParam, self).__init__(labelText, value, group,
                                        history, labelWidth, parent)
        self._type = 'menu'

        # -- Check if menuItems is empty --
        if not menuItems:
            raise ValueError('MenuParam requires at least one menu item')

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

    def set_value(self, value: int) -> None:
        self._value = value
        self.editWidget.setCurrentIndex(value)

    def set_string(self, newstring: str) -> None:
        """
        Set the parameter value by menu item string.
        
        Args:
            newstring: String that must match one of the menu items
            
        Raises:
            ValueError: If newstring is not in the menu items
        """
        try:
            value = self._items.index(newstring)
        except ValueError:
            raise ValueError(f"'{newstring}' is not a valid menu item")
        self._value = value
        self.editWidget.setCurrentIndex(value)

    def get_value(self) -> int:
        """Return the current menu selection as an index (0-based)."""
        return self.editWidget.currentIndex()

    def get_string(self) -> str:
        """Return the current menu selection as a string."""
        return str(self.editWidget.currentText())

    def get_items(self) -> Tuple[str, ...]:
        """Return the tuple of menu item strings."""
        return self._items
    

class Message(object):
    """
    Container for a timestamped message.
    
    Stores message text along with the timestamp when it was created.
    
    Attributes:
        text: The message content
        timestamp: time.struct_time when the message was created
        
    Args:
        text: Message content string
    """
    def __init__(self, text: str) -> None:
        self.text = text
        self.timestamp = time.localtime()

    def __str__(self) -> str:
        """Return formatted message string with timestamp in [HH:MM:SS] format."""
        '''String representation of the message'''
        timeString = time.strftime('[%H:%M:%S] ', self.timestamp)
        return f'{timeString}{self.text}'


class Messenger(QObject):
    """
    Message logging system with Qt signal support.
    
    Collects timestamped messages and emits them via Qt signals for display
    in the UI (e.g., status bar). Each Messenger instance maintains its own
    message list.
    
    Signals:
        timed_message: Emitted when a new message is collected (str)
        
    Attributes:
        messages: List of Message objects collected by this instance
    
    Example:
        >>> messenger = Messenger()
        >>> messenger.timed_message.connect(self.statusBar().showMessage)
        >>> messenger.collect('Experiment started')  # Emits signal and stores message
        >>> all_messages = messenger.get_list()  # Get all messages as strings
    """
    timed_message = pyqtSignal(str)

    def __init__(self) -> None:
        super().__init__()
        self.messages: List[Message] = []

    # @QtCore.Slot(str)
    def collect(self, text: str) -> None:
        """
        Add a new message to the log and emit signal.
        
        Args:
            text: Message content string
        """
        new_message = Message(text)
        self.messages.append(new_message)
        self.timed_message.emit(str(new_message))

    def get_list(self) -> List[str]:
        """
        Return all messages as a list of formatted strings.
        
        Returns:
            List of formatted message strings with timestamps
        """
        return [str(x) for x in self.messages]

    def __str__(self) -> str:
        """Return all messages as a single newline-separated string."""
        return '\n'.join(self.get_list())


def create_app(task_class: type) -> Tuple[QApplication, Any]:
    """
    Create and run a PyQt6 application.
    
    Sets up the Qt application, creates the main window, enables Ctrl-C handling,
    and starts the event loop.
    
    Args:
        task_class: Class to instantiate for the main window (must be QMainWindow subclass)
        
    Returns:
        Tuple of (QApplication instance, main window instance)
        
    Example:
        >>> class MyTask(QMainWindow):
        ...     pass
        >>> app, window = create_app(MyTask)
    """

    app = QApplication(sys.argv)

    # Create and show the main window
    window = task_class()
    window.show()

    # Start the application event loop
    signal.signal(signal.SIGINT, signal.SIG_DFL)  # Enable Ctrl-C to exit
    app.exec()
    return (app, window)

