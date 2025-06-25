#!/usr/bin/env python
"""Start the FastAPI backend server."""

import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "src.dr_exp.api.main:app",
        host="0.0.0.0",  # noqa: S104
        port=8000,
        reload=True,
        log_level="info",
    )
