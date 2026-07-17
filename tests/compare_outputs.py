import pandas as pd
import numpy as np

def compare():
    df_cython = pd.read_csv("real_timing_cython.csv")
    df_pure = pd.read_csv("real_timing_pure.csv")
    
    print(f"Cython rows: {len(df_cython)}")
    print(f"Pure Python rows: {len(df_pure)}")
    
    # We parse the tuples
    def parse_tuple(val):
        if pd.isna(val) or not isinstance(val, str):
            return np.nan, np.nan
        val = val.strip("()")
        parts = val.split(",")
        def to_float(x):
            x = x.strip()
            if x == "None" or x == "":
                return np.nan
            return float(x)
        return to_float(parts[0]), to_float(parts[1])
        
    for df_name, df in [("Cython", df_cython), ("Pure Python", df_pure)]:
        print(f"\n--- {df_name} Timing Statistics ---")
        
        # Contour Tracker
        ct_recv, ct_emit = zip(*df['contour_tracker_recv_emit'].map(parse_tuple))
        ct_duration = np.array(ct_emit) - np.array(ct_recv)
        print(f"Contour Tracker Duration:")
        print(f"  Mean: {np.nanmean(ct_duration)*1000:.4f} ms")
        print(f"  Max:  {np.nanmax(ct_duration)*1000:.4f} ms")
        
        # Locomotion
        loc_recv, loc_emit = zip(*df['locomotion_recv_emit'].map(parse_tuple))
        loc_duration = np.array(loc_emit) - np.array(loc_recv)
        print(f"Locomotion Duration:")
        print(f"  Mean: {np.nanmean(loc_duration)*1000:.4f} ms")
        print(f"  Max:  {np.nanmax(loc_duration)*1000:.4f} ms")

if __name__ == "__main__":
    compare()
