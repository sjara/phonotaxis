"""
Session information widget for phonotaxis applications.
"""

import socket
import time
from PyQt6.QtWidgets import QWidget, QVBoxLayout
from phonotaxis import gui


class SessionInfo(QWidget):
    """
    Widget for session information parameters.
    
    Contains standard session parameters: hostname, subject, trainer, maxSessionDuration, 
    and maxTrials. Provides a consistent interface for displaying and saving session info 
    across tasks.
    
    Usage:
        session_info = SessionInfo()
        layout.addWidget(session_info)
        
        # Later, save to HDF5 file
        session_info.append_to_file(h5file)
    """
    
    def __init__(self, parent=None):
        """
        Initialize SessionInfo widget with default parameters.
        
        Args:
            parent: Parent widget (optional)
        """
        super().__init__(parent)
        
        # Create parameter container
        self.params = gui.Container()
        
        # Define session parameters (without history)
        self.params['subject'] = gui.StringParam('Subject', value='', history=False,
                                                 group='Session info')
        self.params['trainer'] = gui.StringParam('Trainer', value='', history=False,
                                                 group='Session info')
        self.params['hostname'] = gui.StringParam('Hostname', value=socket.gethostname(), 
                                                  enabled=False, history=False,
                                                  group='Session info')
        self.params['maxSessionDuration'] = gui.NumericParam('Max duration (s)', value=float('inf'), 
                                                          units='s', history=False,
                                                          group='Session info')
        self.params['maxTrials'] = gui.NumericParam('Max trials', value=float('inf'), 
                                                     units='trials', decimals=0, history=False,
                                                     group='Session info')
        
        # Create layout with the group
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self.groupBox = self.params.layout_group('Session info')
        self._layout.addWidget(self.groupBox)
    
    def get_value(self, param_name):
        """
        Get the value of a specific parameter.
        
        Args:
            param_name: Name of the parameter ('hostname', 'subject', 'trainer', 
                       'maxSessionDuration', or 'maxTrials')
        
        Returns:
            The current value of the parameter
        """
        if param_name not in self.params:
            raise KeyError(f"Parameter '{param_name}' not found in SessionInfo")
        return self.params[param_name].get_value()
    
    def set_value(self, param_name, value):
        """
        Set the value of a specific parameter.
        
        Args:
            param_name: Name of the parameter
            value: New value for the parameter
        """
        if param_name not in self.params:
            raise KeyError(f"Parameter '{param_name}' not found in SessionInfo")
        self.params[param_name].set_value(value)
    
    def set_values(self, values_dict):
        """
        Set multiple parameter values at once.
        
        Args:
            values_dict: Dictionary with parameter names as keys and their values
        """
        self.params.set_values(values_dict)
    
    def append_to_file(self, h5file):
        """
        Append session info to an HDF5 file.
        
        Saves all session parameters to the 'sessionData' group in the HDF5 file.
        Unlike Container.append_to_file(), this method does not save history,
        as session parameters should remain constant throughout a session.
        
        Args:
            h5file: Open HDF5 file object (h5py.File)
        """
        sessionDataGroup = h5file.require_group('sessionData')
        
        # Append date/time
        dateAndTime = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())
        dset = sessionDataGroup.create_dataset('date', data=dateAndTime)
        
        # Append all session parameters (including hostname)
        for key, item in self.params.items():
            if item.get_type() == 'string':
                dset = sessionDataGroup.create_dataset(key, data=item.get_value())
            else:
                dset = sessionDataGroup.create_dataset(key, data=item.get_value())
            dset.attrs['Description'] = item.get_label()
            if item.get_type() == 'numeric':
                dset.attrs['Units'] = item.get_units()
