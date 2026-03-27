#!/bin/bash

cd /root/heist-v3/heist/apis/newd2r
source venv/bin/activate

uvicorn d2r:app --host 0.0.0.0 --port 7690