# Gunicorn production configuration for LyoBackendJune
import multiprocessing
import os
import shutil

# Create Prometheus metrics directory immediately
prometheus_dir = "/tmp/prometheus_multiproc_dir"
if os.path.exists(prometheus_dir):
    shutil.rmtree(prometheus_dir)
os.makedirs(prometheus_dir, exist_ok=True)

# Server socket
bind = "0.0.0.0:8000"
backlog = 2048

# Worker processes
workers = min(multiprocessing.cpu_count() * 2 + 1, 4)  # Reduced for Cloud Run
worker_class = "uvicorn.workers.UvicornWorker"
worker_connections = 1000
timeout = 120  # Increased for slow startup with AI model loading
graceful_timeout = 60
keepalive = 5

# Restart workers to prevent memory leaks
max_requests = 1000
max_requests_jitter = 100

# Logging
accesslog = "-"
errorlog = "-"
loglevel = "info"
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)s'

# Process naming
proc_name = "lyoapp-backend"

# Preload app for better memory usage (disabled for Cloud Run async startup)
preload_app = False

# Security
limit_request_line = 4096
limit_request_fields = 100
limit_request_field_size = 8190

# SSL (if terminating SSL at app level instead of Nginx)
# keyfile = "/app/ssl/server.key"
# certfile = "/app/ssl/server.crt"

# Environment variables
raw_env = [
    f"PROMETHEUS_MULTIPROC_DIR=/tmp/prometheus_multiproc_dir",
    f"INSTANCE_ID={os.getenv('INSTANCE_ID', 'unknown')}"
]

# Hooks for application lifecycle
def when_ready(server):
    """Called just after the server is started."""
    server.log.info("Server is ready. Spawning workers")
    
    # Create Prometheus metrics directory
    import os
    import shutil
    prometheus_dir = "/tmp/prometheus_multiproc_dir"
    if os.path.exists(prometheus_dir):
        shutil.rmtree(prometheus_dir)
    os.makedirs(prometheus_dir, exist_ok=True)

def worker_int(worker):
    """Called just after a worker exited on SIGINT or SIGQUIT."""
    worker.log.info("worker received INT or QUIT signal")

def pre_fork(server, worker):
    """Called just before a worker is forked."""
    server.log.info("Worker spawned (pid: %s)", worker.pid)

def post_fork(server, worker):
    """Called just after a worker has been forked."""
    server.log.info("Worker spawned (pid: %s)", worker.pid)
    
    # Initialize worker-specific resources
    from prometheus_client import multiprocess
    from prometheus_client import generate_latest
    from prometheus_client import CollectorRegistry
    
def worker_abort(worker):
    """Called when a worker received the SIGABRT signal."""
    worker.log.info("worker received SIGABRT signal")

def pre_exec(server):
    """Called just before a new master process is forked."""
    server.log.info("Forked child, re-executing.")

def on_exit(server):
    """Called just before exiting."""
    server.log.info("Server is shutting down")
    
    # Cleanup
    import os
    import shutil
    prometheus_dir = "/tmp/prometheus_multiproc_dir"
    if os.path.exists(prometheus_dir):
        shutil.rmtree(prometheus_dir)

def on_reload(server):
    """Called to recycle workers during a reload via SIGHUP."""
    server.log.info("Server is reloading")

# Custom application
def post_worker_init(worker):
    """Called just after a worker has initialized the application."""
    worker.log.info("Worker initialized application")
    
def worker_exit(server, worker):
    """Called just after a worker has been exited."""
    worker.log.info("Worker exited (pid: %s)", worker.pid)
