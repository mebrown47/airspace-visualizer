#!/bin/bash
#
# Single RTL-SDR Time-Slicing Scheduler
# Alternates between ADS-B and VDL2 capture on one device
#

DEVICE_ID=0
ADSB_DURATION=10    # seconds for ADS-B capture
VDL2_DURATION=50    # seconds for VDL2 capture
TRANSITION_DELAY=2  # seconds to allow clean shutdown/startup

# File paths
AIRCRAFT_FILE="/tmp/aircraft.json"
VDL2_FILE="/tmp/vdl2.json"

# Process tracking
ADSB_PID=""
VDL2_PID=""

# Cleanup function
cleanup() {
    echo "Shutting down processes..."
    if [ ! -z "$ADSB_PID" ]; then
        kill $ADSB_PID 2>/dev/null
        wait $ADSB_PID 2>/dev/null
    fi
    if [ ! -z "$VDL2_PID" ]; then
        kill $VDL2_PID 2>/dev/null
        wait $VDL2_PID 2>/dev/null
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

# Function to start VDL2 capture
start_vdl2() {
    echo "Starting VDL2 capture for ${VDL2_DURATION} seconds..."
    dumpvdl2 --rtlsdr $DEVICE_ID 136650000 136725000 136775000 136800000 136825000 136875000 136900000 136975000 --output decoded:json:file:path="$VDL2_FILE" &
    VDL2_PID=$!
    echo "VDL2 process started (PID: $VDL2_PID)"
}

# Function to stop current process
stop_current() {
    if [ ! -z "$ADSB_PID" ]; then
        echo "Stopping ADS-B process..."
        kill $ADSB_PID 2>/dev/null
        wait $ADSB_PID 2>/dev/null
        ADSB_PID=""
    fi
    if [ ! -z "$VDL2_PID" ]; then
        echo "Stopping VDL2 process..."
        kill $VDL2_PID 2>/dev/null
        wait $VDL2_PID 2>/dev/null
        VDL2_PID=""
    fi
    echo "Waiting ${TRANSITION_DELAY} seconds for clean transition..."
    sleep $TRANSITION_DELAY
}

# Main scheduling loop
echo "Single RTL-SDR Time-Slicing Scheduler Started"
echo "Device: $DEVICE_ID"
echo "ADS-B Duration: ${ADSB_DURATION}s, VDL2 Duration: ${VDL2_DURATION}s"
echo "Transition Delay: ${TRANSITION_DELAY}s"
echo "Press Ctrl+C to stop"
echo "============================================"

while true; do
    # ADS-B Phase
    start_adsb
    sleep $ADSB_DURATION
    stop_current
    
    # VDL2 Phase  
    start_vdl2
    sleep $VDL2_DURATION
    stop_current
    
    echo "Cycle complete. Starting next cycle..."
done
