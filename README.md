# Pircel

## Running
Currently little exists, standard virtualenv stuff applies except we're using python 3 so make your venv with

    virtualenv -p $(which python3) ...

then `pip install -r requirements.txt` in the venv

## Running tests
Inside the virtualenv from above, run:

    python -m unittest
