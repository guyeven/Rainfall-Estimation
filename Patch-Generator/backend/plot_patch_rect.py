import matplotlib
matplotlib.use("Agg")  # non-GUI backend, safe on macOS

import matplotlib.pyplot as plt

# ----- values from your /patch_geo response -----
patch_id = "RAD_OPERA_HOURLY_RAINFALL_ACCUMULATION_202301010700_patch001"

center_lat = 40.962412099086805
center_lon = -25.489823369550788

patch_lat_min = 40.71015984683455
patch_lat_max = 41.21466435133906
patch_lon_min = -26.0982662711063
patch_lon_max = -24.881380467995275

map_lat_min = 40.20565534233005
map_lat_max = 41.71916885584356
map_lon_min = -27.315152074217323
map_lon_max = -23.664494664884252
# -----------------------------------------------

# Rectangle corners (closed polygon)
rect_lats = [
    patch_lat_min,
    patch_lat_min,
    patch_lat_max,
    patch_lat_max,
    patch_lat_min,
]
rect_lons = [
    patch_lon_min,
    patch_lon_max,
    patch_lon_max,
    patch_lon_min,
    patch_lon_min,
]

plt.figure(figsize=(6, 6))

# Plot patch rectangle
plt.plot(rect_lons, rect_lats)          # lon on x-axis, lat on y-axis

# Mark center point
plt.scatter(center_lon, center_lat, s=20)

# Set map extent to the larger map box
plt.xlim(map_lon_min, map_lon_max)
plt.ylim(map_lat_min, map_lat_max)

plt.xlabel("Longitude")
plt.ylabel("Latitude")
plt.title(f"Patch area: {patch_id}")
plt.grid(True)

plt.tight_layout()
plt.savefig("patch_geo_rect.png", dpi=150)
print("Saved patch_geo_rect.png")
