"""Convenience launcher for the FastAPI app.

Run from the project root:

    python run.py

Then open:
    http://127.0.0.1:8000/          dashboard
    http://127.0.0.1:8000/community  CRUD UI
    http://127.0.0.1:8000/docs      Swagger API docs
"""

from __future__ import annotations

import uvicorn


if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host="127.0.0.1",
        port=8000,
        reload=True,
    )
