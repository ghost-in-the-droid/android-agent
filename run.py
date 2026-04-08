#!/usr/bin/env python3
"""Entry point — start the Ghost in the Droid server (FastAPI + Uvicorn)."""
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / '.env')

import uvicorn
from gitd.app import app

if __name__ == '__main__':
    uvicorn.run(app, host='0.0.0.0', port=5055)
