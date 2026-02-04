import sys
from pathlib import Path

PROJECT_ROOT = (
    Path(sys._MEIPASS)
    if hasattr(sys, "_MEIPASS")
    else Path(__file__).resolve().parent
)

DATA_DIR = PROJECT_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
EXPORT_DIR = DATA_DIR / "exports"
BENCHMARK_DIR = DATA_DIR / "benchmarks"
CITIES_FILE = DATA_DIR / "cities_europe.txt"

PIXEL_SIZE_KM = 2.0

for p in (DATA_DIR, RAW_DIR, EXPORT_DIR, BENCHMARK_DIR):
    p.mkdir(parents=True, exist_ok=True)

#from pathlib import Path
#
## Base paths
#PROJECT_ROOT = Path(__file__).resolve().parent
#DATA_DIR = PROJECT_ROOT / "data"
#RAW_DIR = DATA_DIR / "raw"
#EXPORT_DIR = DATA_DIR / "exports"
#BENCHMARK_DIR = DATA_DIR / "benchmarks"
#CITIES_FILE = DATA_DIR / "cities_europe.txt"
#
## EURADCLIM pixel size (km)
#PIXEL_SIZE_KM = 2.0
#
## Ensure folders exist
#for p in (DATA_DIR, RAW_DIR, EXPORT_DIR, BENCHMARK_DIR):
#    p.mkdir(parents=True, exist_ok=True)

