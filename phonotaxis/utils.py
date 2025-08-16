"""
Utility functions for phonotaxis tasks.
"""

import h5py
from typing import Dict, Any, Optional

def append_dict_to_hdf5(
    h5_file_group: h5py.Group, 
    dict_name: str, 
    dict_data: Dict[str, Any], 
    compression: Optional[str] = None
) -> h5py.Group:
    """
    Append a Python dictionary to a location/group in an HDF5 file.

    Creates one scalar dataset for each key in the dictionary.
    Only works for scalar values (not arrays or nested structures).

    Args:
        h5_file_group: Open HDF5 group object where the dictionary will be stored.
        dict_name: Name for the new group that will contain the dictionary.
        dict_data: Dictionary to store (values must be scalars).
        compression: Optional compression method for datasets.

    Returns:
        The created HDF5 group containing the dictionary.

    Raises:
        TypeError: If dict_data is not a dictionary.
        ValueError: If dictionary values are not scalar types.

    Note:
        An alternative approach would be to use the special dtype 'enum'.
        See: http://www.h5py.org/docs/topics/special.html
    """
    if not isinstance(dict_data, dict):
        raise TypeError(f"dict_data must be a dictionary, got {type(dict_data)}")
    
    dict_group = h5_file_group.create_group(dict_name)
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

    def append_to_file(self, h5_file: h5py.File, current_trial: int) -> h5py.Dataset:
        """
        Append data in container to an open HDF5 file.
        
        Args:
            h5_file: Open HDF5 file object.
            current_trial: Current trial number (must be >= 1).
            
        Raises:
            UserWarning: If current_trial < 1.
        """
        if current_trial < 1:
            raise UserWarning('WARNING: No trials have been completed or ' +
                              'current_trial not updated.')
        results_data_group = h5_file.require_group('resultsData')
        results_labels_group = h5_file.require_group('resultsLabels')
        for key, item in self.items():
            dset = results_data_group.create_dataset(key, data=item[:current_trial])
        for key, item in self.labels.items():
            if not isinstance(item, dict):
                raise TypeError(f"Label item '{key}' must be a dictionary, got {type(item)}")
            dset = append_dict_to_hdf5(results_labels_group, key, item)
        return dset
 