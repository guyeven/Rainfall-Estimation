Option A — Run in a Python virtual environment (recommended)
1. Create a new virtual environment

In the folder containing your files (App.jsx, api.py, itu_r_p8383.py, main.py):

python3 -m venv venv

2. Activate the environment

macOS / Linux:

source venv/bin/activate


Windows (PowerShell):

venv\Scripts\Activate


Your prompt should now show (venv).

3. Install required Python packages

You need FastAPI + uvicorn:

pip install fastapi uvicorn


If you later add plotting or numeric libs, install them here too.

4. Run the backend

With the virtual environment active:

python main.py


You should see:

Uvicorn running on http://127.0.0.1:8000


Your API is now live.

Backend test URLs:

http://127.0.0.1:8000/itu/gamma?f_ghz=10&R_mm_per_h=10&pol=horizontal

http://127.0.0.1:8000/itu/gamma-freq?R_mm_per_h=10&pol=horizontal

http://127.0.0.1:8000/itu/gamma-rain?f_ghz=20&pol=vertical
