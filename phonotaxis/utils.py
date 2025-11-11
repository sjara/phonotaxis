"""
Utility functions for phonotaxis tasks.
"""

import h5py
import datetime
from typing import Dict, Any, Optional
from bidict import bidict


def date_time_string(timestamp):
    """
    Return a string with the date and time the session started.
    
    Returns:
        String in format YYYYMMDDhhmmss (e.g., '20250821143025')
    """
    dt = datetime.datetime.fromtimestamp(timestamp)
    return dt.strftime("%Y%m%d%H%M%S")


def append_dict_to_hdf5(h5_file_group: h5py.Group,
                        dict_name: str,
                        dict_data: dict,  # Accept both dict and bidict
                        compression: Optional[str] = None
                        ) -> h5py.Group:
    """
    Append a Python dictionary or bidict to a location/group in an HDF5 file.

    Creates one scalar dataset for each key in the dictionary.
    Only works for scalar values (not arrays or nested structures).

    Args:
        h5_file_group: Open HDF5 group object where the dictionary will be stored.
        dict_name: Name for the new group that will contain the dictionary.
        dict_data: Dictionary or bidict to store (values must be scalars).
        compression: Optional compression method for datasets.

    Returns:
        The created HDF5 group containing the dictionary.

    Raises:
        TypeError: If dict_data is not a dictionary or bidict.
        ValueError: If dictionary values are not scalar types.
    """
    if not isinstance(dict_data, (dict, bidict)):
        raise TypeError(f"dict_data must be a dictionary or bidict, got {type(dict_data)}")
    
    dict_group = h5_file_group.create_group(dict_name)
    ### For bidict, only store the forward mapping (not the inverse)
    ###items = dict_data.items() if not isinstance(dict_data, bidict) else dict_data.items()
    for key, val in dict_data.items():
        try:
            dtype = type(val)
            dset = dict_group.create_dataset(key, data=val, dtype=dtype,
                                             compression=compression)
        except (TypeError, ValueError) as e:
            raise ValueError(f"Cannot store value for key '{key}': {e}")
    return dict_group


def dict_from_hdf5(dict_group: h5py.Group) -> Dict[str, Any]:
    """
    Convert an HDF5 group back to a Python dictionary.
    
    Args:
        dict_group: HDF5 group object containing the dictionary data.
        
    Returns:
        Reconstructed dictionary with key-value pairs.
    """
    new_dict = {}
    for key, val in dict_group.items():
        new_dict[key] = val[()]
        new_dict[val[()]] = key
    return new_dict


class EnumContainer(dict):
    """
    Container for enumerated variables.

    Useful for non-graphical variables like choice and outcome which take
    a finite set of values, where each value is associated with a label.
    
    Attributes:
        labels: Dictionary containing label mappings for enumerated values.
    """
    def __init__(self):
        super().__init__()
        self.labels = dict()

    def append_to_file(self, h5_file: h5py.File) -> h5py.Dataset:
        """
        Append data in container to an open HDF5 file.
        
        Saves all data that has been added to the container. Only add data
        for completed trials to ensure incomplete trials are not saved.
        
        Args:
            h5_file: Open HDF5 file object.
            
        Raises:
            UserWarning: If container is empty (no data to save).
        """
        if len(self) == 0:
            raise UserWarning('WARNING: Container is empty. No data to save.')
        
        # Check if any items have data
        has_data = False
        for key, item in self.items():
            if len(item) > 0:
                has_data = True
                break
        
        if not has_data:
            raise UserWarning('WARNING: No trials have been completed or container not updated.')
            
        results_data_group = h5_file.require_group('resultsData')
        results_labels_group = h5_file.require_group('resultsLabels')
        for key, item in self.items():
            # Save all data in the container (only complete trials should be added)
            dset = results_data_group.create_dataset(key, data=item)
        for key, item in self.labels.items():
            if not isinstance(item, (dict, bidict)):
                raise TypeError(f"Label item '{key}' must be a dictionary, got {type(item)}")
            dset = append_dict_to_hdf5(results_labels_group, key, item)
        return dset
 

class SessionData:
    """
    Load and access session data from HDF5 files saved by phonotaxis.savedata.
    
    This class provides a clean interface to load all data containers saved
    by the savedata module, including trial parameters, labels, events, 
    state matrix definitions, and video tracking data.
    
    Attributes:
        filename (str): Full path to the HDF5 data file.
        trialdata (dict): Trial-by-trial data from '/resultsData' group.
        labels (dict): Label mappings for enumerated parameters from '/resultsLabels'.
        state_matrix (dict): State matrix definitions from '/stateMatrix'.
        events (dict): Event data (timestamps, codes, states, trials) from '/events'.
        video_tracking (dict): Video tracking data (timestamps, centroids) from '/videoTracking'.
    
    Example:
        >>> sdata = SessionData('subject_paradigm_20251102a.h5')
        >>> print(sdata.trialdata['choice'])  # Access trial choices
        >>> print(sdata.events['timestamp'])  # Access event timestamps
        >>> print(sdata.labels['choice'])     # Access choice label mappings
    """
    
    def __init__(self, filename: str):
        """
        Load session data from an HDF5 file.
        
        Args:
            filename (str): Full path to the HDF5 data file.
            
        Raises:
            FileNotFoundError: If the file does not exist.
            IOError: If the file cannot be opened or read.
        """
        self.filename = filename
        self.trialdata = {}
        self.labels = {}
        self.state_matrix = {}
        self.events = {}
        self.video_tracking = {}
        
        try:
            with h5py.File(self.filename, 'r') as h5file:
                self._load_all(h5file)
        except FileNotFoundError:
            raise FileNotFoundError(f'File does not exist: {self.filename}')
        except IOError as e:
            raise IOError(f'Error opening or reading file {self.filename}: {e}')
    
    def _load_all(self, h5file: h5py.File) -> None:
        """
        Load all available data from the HDF5 file.
        
        Args:
            h5file: Open HDF5 file object.
        """
        # Load trial-by-trial data
        if 'resultsData' in h5file:
            for varname, varvalue in h5file['resultsData'].items():
                self.trialdata[varname] = varvalue[...]
        
        # Load labels for enumerated parameters
        if 'resultsLabels' in h5file:
            for varname, varvalue in h5file['resultsLabels'].items():
                self.labels[varname] = self._load_dict_from_hdf5(varvalue)
        
        # Load state matrix definitions
        if 'stateMatrix' in h5file:
            for varname, varvalue in h5file['stateMatrix'].items():
                self.state_matrix[varname] = self._load_dict_from_hdf5(varvalue)
        
        # Load events data
        if 'events' in h5file:
            for varname, varvalue in h5file['events'].items():
                self.events[varname] = varvalue[...]
        
        # Load video tracking data
        if 'videoTracking' in h5file:
            for varname, varvalue in h5file['videoTracking'].items():
                self.video_tracking[varname] = varvalue[...]
    
    def _load_dict_from_hdf5(self, dict_group: h5py.Group) -> bidict:
        """
        Load a dictionary from an HDF5 group and return as bidict.
        
        Args:
            dict_group: HDF5 group containing key-value pairs.
            
        Returns:
            bidict with the loaded key-value mappings (numpy types converted to Python types).
        """
        data_dict = {}
        for key, val in dict_group.items():
            value = val[()]
            # Convert numpy types to native Python types
            if hasattr(value, 'item'):
                value = value.item()
            data_dict[key] = value
        return bidict(data_dict)
    
    def __getitem__(self, key: str):
        """
        Access trial data using dictionary-like syntax.
        
        Args:
            key: Name of the trial data variable.
            
        Returns:
            The trial data array for the specified variable.
            
        Raises:
            KeyError: If the key is not found in trial data.
            
        Example:
            >>> sdata = SessionData('file.h5')
            >>> choices = sdata['choice']  # Same as sdata.trialdata['choice']
        """
        return self.trialdata[key]
    
    def __setitem__(self, key: str, value):
        """
        Set trial data using dictionary-like syntax.
        
        Args:
            key: Name of the trial data variable.
            value: Data to store.
            
        Example:
            >>> sdata = SessionData('file.h5')
            >>> sdata['new_variable'] = [1, 2, 3]
        """
        self.trialdata[key] = value
    
    def __contains__(self, key: str) -> bool:
        """
        Check if a key exists in trial data.
        
        Args:
            key: Name of the trial data variable to check.
            
        Returns:
            True if key exists in trial data, False otherwise.
            
        Example:
            >>> sdata = SessionData('file.h5')
            >>> 'choice' in sdata  # Same as 'choice' in sdata.trialdata
        """
        return key in self.trialdata
    
    def __repr__(self) -> str:
        """Return a string representation of the SessionData object."""
        info_lines = [f"SessionData('{self.filename}')"]
        
        if self.trialdata:
            n_trials = len(next(iter(self.trialdata.values())))
            info_lines.append(f"  Trial data: {len(self.trialdata)} variables, {n_trials} trials")
        
        if self.labels:
            info_lines.append(f"  Labels: {len(self.labels)} variables")
        
        if self.state_matrix:
            info_lines.append(f"  State matrix: {len(self.state_matrix)} components")
        
        if self.events:
            n_events = len(self.events.get('timestamp', []))
            info_lines.append(f"  Events: {len(self.events)} types, {n_events} total events")
        
        if self.video_tracking:
            n_frames = len(self.video_tracking.get('timestamps', []))
            info_lines.append(f"  Video tracking: {n_frames} frames")
        
        return '\n'.join(info_lines)
    
    def __str__(self) -> str:
        """Return a detailed string representation showing all loaded data."""
        return self.__repr__()
