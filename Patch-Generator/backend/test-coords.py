import h5py

path = "data/raw/RAD_OPERA_HOURLY_RAINFALL_ACCUMULATION_202301010700.h5"  # adjust if needed

with h5py.File(path, "r") as f:
    print("Groups and datasets:")
    f.visititems(lambda name, obj: print(name, type(obj)))

    print("\nAttributes in root:")
    print(dict(f.attrs))

    if "where" in f:
        print("\nAttributes in /where:")
        print(dict(f["where"].attrs))

