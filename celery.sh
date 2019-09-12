#!/bin/bash

# Init the celery work queue
./venv/bin/celery -A tasks worker --loglevel=info