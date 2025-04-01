import os
import multiprocessing

# Bind to 0.0.0.0:8000
bind = "0.0.0.0:8000"

# Number of workers: 2-4 × number of cores
workers = multiprocessing.cpu_count() * 2 + 1
worker_class = "sync"

# Logging
accesslog = "-"
errorlog = "-"
loglevel = "info"

# Timeout
timeout = 120

# Maximum requests per worker before restart
max_requests = 1000
max_requests_jitter = 50

# Process naming
proc_name = "youtuber_bidding_api"