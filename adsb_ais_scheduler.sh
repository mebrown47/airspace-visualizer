#!/bin/bash
#
# Single RTL-SDR Time-Slicing Scheduler
# Alternates between ADS-B and AIS capture on one device
#
DEVICE_ID=0
ADSB_DURATION=10  # seconds for ADS-B capture
AIS_DURATION=50  # seconds for AIS capture
TRANSITION_DELAY=2  # seconds to allow clean shutdown/startup
# File paths
AIRCRAFT_FILE="/tmp/aircraft.json"
AIS_FILE="/tmp/vesselsjson"
# Process tracking
ADSB_PID=""
AIS_PID=""
# Cleanup function
cleanup() {
  echo "Shutting down processes..."
  if [ ! -z "$ADSB_PID" ]; then
    kill $ADSB_PID 2>/dev/null
    wait $ADSB_PID 2>/dev/null
  fi
  if [ ! -z "$AIS_PID" ]; then
    kill $AIS_PID 2>/dev/null
    wait $AIS_PID 2>/dev/null
  fi
  echo "Cleanup complete"
  exit 0
}
# Set up signal handlers
trap cleanup SIGINT SIGTERM
# Function to start ADS-B capture
start_adsb() {
  echo "Starting ADS-B capture for ${ADSB_DURATION} seconds..."
  ./readsb --device-type rtlsdr --device $DEVICE_ID --write-json /tmp --write-json-every 1 &
  ADSB_PID=$!
  echo "ADS-B process started (PID: $ADSB_PID)"
}
# Function to start AIS capture
start_ais() {
  echo "Starting AIS capture for ${AIS_DURATION} seconds..."
  AIS-catcher -w -c json -o /tmp/vessels.json -d $DEVICE_ID &
  AIS_PID=$!
  echo "AIS process started (PID: $AIS_PID)"
}
# Function to stop current process
stop_current() {
  if [ ! -z "$ADSB_PID" ]; then
    echo "Stopping ADS-B process..."
    kill $ADSB_PID 2>/dev/null
    wait $ADSB_PID 2>/dev/null
    ADSB_PID=""
  fi
  if [ ! -z "$AIS_PID" ]; then
    echo "Stopping AIS process..."
    kill $AIS_PID 2>/dev/null
    wait $AIS_PID 2>/dev/null
    AIS_PID=""
  fi
  echo "Waiting ${TRANSITION_DELAY} seconds for clean transition..."
  sleep $TRANSITION_DELAY
}
# Main scheduling loop
echo "Single RTL-SDR Time-Slicing Scheduler Started"
echo "Device: $DEVICE_ID"
echo "ADS-B Duration: ${ADSB_DURATION}s, AIS Duration: ${AIS_DURATION}s"
echo "Transition Delay: ${TRANSITION_DELAY}s"
echo "Press Ctrl+C to stop"
echo "============================================"
while true; do
  # ADS-B Phase
  start_adsb
  sleep $ADSB_DURATION
  stop_current

  # AIS Phase
  start_ais
  sleep $AIS_DURATION
  stop_current

  echo "Cycle complete. Starting next cycle..."
done

