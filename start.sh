#!/bin/bash
cd "$(dirname "$0")"
mkdir -p uploads
python3 backend/server.py
