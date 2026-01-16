1. Open a terminal in your project folder

Your folder should contain:

app.py
config.py
patches.py
io_rainfall.py
schemas.py
benchmarks.py
cities.py
cities_list.py
data/raw/   ← put .h5 rainfall files here

✅ 2. (Optional but recommended) Activate your environment

macOS / Linux:

1. Create the environment

If not already created:

python3 -m venv env

✅ 2. Activate it (macOS)
source env/bin/activate


You should now see:

(env) yourname@mac ...

pip install -r requirements.txt


✅ 3. Start the server

Run:

uvicorn app:app --reload


If port 8000 is busy use:

uvicorn app:app --reload --port 8001


The server is running when you see:

Uvicorn running on http://127.0.0.1:8000

✅ 4. Open the API interface

In your browser go to:

http://127.0.0.1:8000/docs


(Or :8001/docs if you used port 8001.)

This page lets you test everything easily.

✅ 5. Run patch detection

In the /docs page:

Scroll to POST /detect_patches

Click Try it out

Use parameters like:

{
  "threshold_mm": 3,
  "avg_window_y": 10,
  "avg_window_x": 10,
  "min_width_km": 50,
  "min_height_km": 50,
  "max_width_km": 250,
  "max_height_km": 250,
  "max_files": 3
}


Click Execute.

If everything is correct, you get a JSON list of patches:

[
  {
    "id": "...",
    "source_file": "...",
    "nearest_city": "...",
    ...
  }
]

✅ 6. View patch images

Copy one patch id from the above output.

Then in /docs:

Go to GET /patch_image/{patch_id}

Click Try it out

Paste the patch id

Execute → You get a PNG heatmap with x/y ticks.

✅ 7. Get map info for the patch (for your UI panel)

In /docs:

Go to GET /patch_geo/{patch_id}

Try it out → paste the same patch id

Execute

You’ll see:

Patch bounding box

Map bounding box (3× larger)

Coordinates to center your OSM map

🔄 Summary (very short)

To run the program:

uvicorn app:app --reload


Use it through:

http://127.0.0.1:8000/docs


Run /detect_patches, then /patch_image/{id}, /patch_geo/{id}.

If you want, I can create a Makefile with one command:

make run


or a script like:

./run.sh


Just say what you prefer.

You said:
port 8000 and 8100 used. how to assignr different port number
ChatGPT said:

Super simple: just add --port <number> to your uvicorn command.

For example, if 8000 and 8100 are busy, run:

uvicorn app:app --reload --port 8200
