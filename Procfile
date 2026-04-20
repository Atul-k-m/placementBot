web: gunicorn main:app -w 2 -k uvicorn.workers.UvicornWorker --timeout 120
worker: python worker.py
