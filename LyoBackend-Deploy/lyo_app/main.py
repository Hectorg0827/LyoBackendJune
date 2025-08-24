"""DEPRECATED bootstrap retained for backward compatibility.

Imports and re-exports the application from enhanced_main. Prefer importing
`lyo_app.enhanced_main:app` moving forward. This file will be removed after
clients update their entrypoints.
"""

from lyo_app.enhanced_main import app  # re-export for backward compatibility

# (Optional) lightweight root note to warn about deprecation
@app.get("/legacy-info", include_in_schema=False)
async def legacy_info():  # pragma: no cover - minimal endpoint
    return {"detail": "Use lyo_app.enhanced_main:app; lyo_app.main is deprecated."}
