#!/bin/bash
cd "$(dirname "$0")"
source .venv/bin/activate
exec python -m marquee_flight_tracker -c config.yaml --display web
