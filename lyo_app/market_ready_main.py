from .app_factory import create_app

# ASGI app used by uvicorn/gunicorn
app = create_app()
