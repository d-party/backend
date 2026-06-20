import multiprocessing
import os

DEBUG = os.getenv("DEBUG") == "1"

wsgi_app = "d_party.asgi:application"

bind = "0.0.0.0:8000"

workers = multiprocessing.cpu_count() * 1 + 1
threads = 2

# The in-tree uvicorn.workers.UvicornWorker is deprecated; use the maintained
# standalone uvicorn-worker package.
worker_class = "uvicorn_worker.UvicornWorker"

if DEBUG:
    reload = True
