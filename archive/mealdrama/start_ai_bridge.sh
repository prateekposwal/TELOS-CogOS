#!/bin/bash
# Start MealDrama AI Bridge (Python)
echo "🥗 Starting MealDrama AI Bridge on port 5002..."
cd /Users/prateekposwal/Desktop/Vrooom-computation
export PYTHONPATH=.
nohup python3 telos/server_bridge.py > /tmp/server_bridge.log 2>&1 &
echo "PID: $!"
echo "Logs: /tmp/server_bridge.log"
echo "Test: curl http://localhost:5002/health"
