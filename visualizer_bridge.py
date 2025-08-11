#!/usr/bin/env python3
"""
Complete UDP Bridge for ADS-B and ACARS Data
Receives UDP ADS-B on port 30005 and serves HTTP endpoints for the radar app
Receives UDP ACARS on port 5555 and transforms to VDL2 format
Serves ADS-B data on port 8080 (dump1090 compatible)
Serves ACARS data on port 8081 (dumpvdl2 compatible)
"""

import socket
import json
import threading
import time
import sys
import random
import os
import math
from flask import Flask, jsonify, make_response, request
from collections import deque

def add_cors_headers(response):
    """Add CORS headers to response"""
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
    return response

# Create two Flask apps for different ports
adsb_app = Flask(__name__)
acars_app = Flask(__name__)

@adsb_app.after_request
def adsb_after_request(response):
    return add_cors_headers(response)

@acars_app.after_request
def acars_after_request(response):
    return add_cors_headers(response)

# Global data stores
latest_aircraft_data = {"now": time.time(), "aircraft": []}
recent_acars_messages = deque(maxlen=100)
latest_vdl2_message = None

def generate_coastline_data(center_lat, center_lon, range_nm):
    """Generate simplified coastline data for the Gulf Coast region"""
    
    # Convert nautical miles to degrees (approximate)
    range_deg = range_nm / 60.0
    
    # Gulf Coast approximate coastline data (simplified)
    gulf_coast_points = [
        # Florida Panhandle to Alabama
        {"lat": 30.1588, "lon": -87.6947, "type": "coast"},  # Pensacola
        {"lat": 30.2672, "lon": -87.5664, "type": "coast"},  # Gulf Shores area
        {"lat": 30.2267, "lon": -87.7311, "type": "coast"},  # Orange Beach
        {"lat": 30.3904, "lon": -87.8169, "type": "coast"},  # Mobile Bay entrance
        {"lat": 30.6954, "lon": -88.0399, "type": "coast"},  # Mobile Bay
        {"lat": 30.8324, "lon": -87.9073, "type": "coast"},  # Mobile River
        {"lat": 31.1801, "lon": -87.8558, "type": "coast"},  # Inland Mobile
        
        # Mississippi Sound
        {"lat": 30.3588, "lon": -88.5561, "type": "coast"},  # Biloxi area
        {"lat": 30.3960, "lon": -89.0927, "type": "coast"},  # Mississippi coast
        
        # Louisiana coast
        {"lat": 29.9547, "lon": -90.0751, "type": "coast"},  # New Orleans area
        {"lat": 29.7003, "lon": -93.2174, "type": "coast"},  # Louisiana coast
        
        # Major rivers and inlets
        {"lat": 31.0076, "lon": -87.8847, "type": "river"},  # Mobile River
        {"lat": 30.6890, "lon": -87.9073, "type": "river"},  # Tensaw River
    ]
    
    # Filter points within radar range
    visible_features = []
    for point in gulf_coast_points:
        distance = haversine_distance(center_lat, center_lon, point["lat"], point["lon"])
        if distance <= range_nm:
            visible_features.append({
                "lat": point["lat"],
                "lon": point["lon"],
                "type": point["type"],
                "distance_nm": distance
            })
    
    # Add some artificial islands and features for demonstration
    if range_nm > 50:  # Only show at longer ranges
        artificial_features = [
            {"lat": center_lat + 0.5, "lon": center_lon - 0.3, "type": "island"},
            {"lat": center_lat - 0.3, "lon": center_lon + 0.4, "type": "island"},
        ]
        for feature in artificial_features:
            distance = haversine_distance(center_lat, center_lon, feature["lat"], feature["lon"])
            if distance <= range_nm:
                visible_features.append({
                    "lat": feature["lat"],
                    "lon": feature["lon"],
                    "type": feature["type"],
                    "distance_nm": distance
                })
    
    return {
        "center": {"lat": center_lat, "lon": center_lon},
        "range_nm": range_nm,
        "features": visible_features,
        "feature_count": len(visible_features)
    }

def haversine_distance(lat1, lon1, lat2, lon2):
    """Calculate distance between two points in nautical miles"""
    R = 3440.065  # Earth's radius in nautical miles
    
    lat1_rad = math.radians(lat1)
    lon1_rad = math.radians(lon1)
    lat2_rad = math.radians(lat2)
    lon2_rad = math.radians(lon2)
    
    dlat = lat2_rad - lat1_rad
    dlon = lon2_rad - lon1_rad
    
    a = math.sin(dlat/2)**2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon/2)**2
    c = 2 * math.asin(math.sqrt(a))
    
    return R * c

def file_listener():
    """Read ADS-B data from aircraft.json file"""
    global latest_aircraft_data
    
    aircraft_file = "/tmp/aircraft.json"
    last_mtime = 0
    
    print(f"✅ File listener started for {aircraft_file}")
    
    while True:
        try:
            if os.path.exists(aircraft_file):
                # Check if file has been modified
                current_mtime = os.path.getmtime(aircraft_file)
                
                if current_mtime != last_mtime:
                    with open(aircraft_file, 'r') as f:
                        aircraft_json = json.load(f)
                        latest_aircraft_data = aircraft_json
                        
                    aircraft_count = len(aircraft_json.get('aircraft', []))
                    if aircraft_count > 0:
                        print(f"📡 FILE: Read {aircraft_count} aircraft from {aircraft_file}")
                    
                    last_mtime = current_mtime
            else:
                if last_mtime != 0:  # Only warn once
                    print(f"⚠️ Aircraft file not found: {aircraft_file}")
                    last_mtime = 0
                    
        except json.JSONDecodeError as e:
            print(f"❌ Aircraft JSON decode error: {e}")
        except Exception as e:
            print(f"❌ Aircraft file read error: {e}")
            
        time.sleep(1)  # Check file every second

def transform_acars_to_vdl2(acars_data):
    """Transform ACARS message to VDL2 format expected by radar app"""
    global latest_vdl2_message
    
    msg = acars_data.get('msg', {})
    flight = msg.get('flight', 'UNKNOWN')
    icao = msg.get('icao', flight)
    msg_text = msg.get('msg_text', '')
    
    # Convert flight to ICAO hex format if needed
    if len(icao) <= 3:
        # Generate a pseudo-hex from flight number for consistency
        icao_hex = format(abs(hash(flight)) % 0xFFFFFF, '06X')
    else:
        icao_hex = icao.upper()
    
    # Create VDL2-compatible message structure
    vdl2_message = {
        "vdl2": {
            "app": {
                "name": "simulated_dumpvdl2",
                "ver": "2.3.0"
            },
            "t": {
                "sec": int(time.time()),
                "usec": random.randint(100000, 999999)
            },
            "freq": random.choice([136925000, 136975000, 131525000, 131725000]),  # Common VDL2 frequencies
            "burst_len_octets": len(msg_text) + 10,
            "hdr_bits_fixed": 0,
            "octets_corrected_by_fec": 0,
            "idx": 0,
            "sig_level": round(random.uniform(-20.0, -10.0), 6),
            "noise_level": round(random.uniform(-50.0, -40.0), 6),
            "freq_skew": round(random.uniform(-2.0, 2.0), 6),
            "avlc": {
                "src": {
                    "addr": icao_hex,
                    "type": "Aircraft",
                    "status": "Airborne"
                },
                "dst": {
                    "addr": "234C97",  # Ground station
                    "type": "Ground station"
                },
                "cr": "Command",
                "frame_type": "I" if msg_text else "S",
                "cmd": "Data" if msg_text else "Receive Ready",
                "pf": True,
                "rseq": random.randint(0, 7)
            }
        }
    }
    
    # Add message text if present
    if msg_text:
        vdl2_message["vdl2"]["acars"] = {
            "msg_text": msg_text,
            "flight": flight,
            "tail": msg.get('tail', ''),
            "msg_type": msg.get('msg_type', 'DATA')
        }
    
    latest_vdl2_message = vdl2_message
    return vdl2_message

def vdl2_file_listener():
    """Read VDL2/ACARS data from vdl2.json file"""
    global recent_acars_messages, latest_vdl2_message
    
    vdl2_file = "/tmp/vdl2.json"
    last_mtime = 0
    processed_messages = set()  # Track processed messages to avoid duplicates
    
    print(f"✅ VDL2 file listener started for {vdl2_file}")
    
    while True:
        try:
            if os.path.exists(vdl2_file):
                # Check if file has been modified
                current_mtime = os.path.getmtime(vdl2_file)
                
                if current_mtime != last_mtime:
                    with open(vdl2_file, 'r') as f:
                        # dumpvdl2 writes one JSON object per line
                        for line in f:
                            line = line.strip()
                            if not line:
                                continue
                                
                            try:
                                vdl2_data = json.loads(line)
                                
                                # Check if this is a VDL2 message
                                if 'vdl2' in vdl2_data:
                                    # Create unique message ID to avoid duplicates
                                    msg_id = f"{vdl2_data['vdl2'].get('t', {}).get('sec', 0)}_{vdl2_data['vdl2'].get('avlc', {}).get('src', {}).get('addr', 'unknown')}"
                                    
                                    if msg_id not in processed_messages:
                                        recent_acars_messages.append(vdl2_data)
                                        latest_vdl2_message = vdl2_data
                                        processed_messages.add(msg_id)
                                        
                                        # Keep processed_messages set manageable
                                        if len(processed_messages) > 1000:
                                            processed_messages.clear()
                                        
                                        # Extract info for logging
                                        vdl2_info = vdl2_data['vdl2']
                                        src_addr = vdl2_info.get('avlc', {}).get('src', {}).get('addr', 'Unknown')
                                        freq = vdl2_info.get('freq', 0)
                                        freq_mhz = freq / 1000000.0 if freq else 0
                                        
                                        acars_content = vdl2_info.get('acars', {})
                                        if acars_content:
                                            msg_text = acars_content.get('msg_text', '')
                                            flight = acars_content.get('flight', src_addr)
                                            print(f"📻 VDL2 FILE: {flight} ({src_addr}) on {freq_mhz:.3f}MHz - {msg_text}")
                                        else:
                                            frame_type = vdl2_info.get('avlc', {}).get('frame_type', 'Unknown')
                                            print(f"📻 VDL2 FILE: {src_addr} on {freq_mhz:.3f}MHz - Frame: {frame_type}")
                                            
                            except json.JSONDecodeError:
                                continue  # Skip malformed lines
                    
                    last_mtime = current_mtime
            else:
                if last_mtime != 0:  # Only warn once
                    print(f"⚠️ VDL2 file not found: {vdl2_file}")
                    last_mtime = 0
                    
        except Exception as e:
            print(f"❌ VDL2 file read error: {e}")
            
        time.sleep(1)  # Check file every second

# ADS-B HTTP Endpoints (Port 8080 - dump1090 compatible)
@adsb_app.route('/tmp/aircraft.json')
def get_aircraft():
    """Serve ADS-B aircraft data (dump1090 compatible)"""
    return jsonify(latest_aircraft_data)

@adsb_app.route('/api/coastline')
def get_coastline():
    """Serve coastline data for radar display"""
    try:
        # Get parameters from query string
        center_lat = float(request.args.get('lat', 31.3228))  # Default to Elba, AL
        center_lon = float(request.args.get('lon', -86.0792))
        range_nm = float(request.args.get('range', 100))
        
        coastline_data = generate_coastline_data(center_lat, center_lon, range_nm)
        
        return jsonify({
            "status": "success",
            "data": coastline_data,
            "timestamp": time.time()
        })
        
    except Exception as e:
        return jsonify({
            "status": "error",
            "error": str(e),
            "timestamp": time.time()
        }), 400

@adsb_app.route('/status')
def get_adsb_status():
    """ADS-B status endpoint"""
    return jsonify({
        "service": "ADS-B Bridge (dump1090 compatible)",
        "aircraft_count": len(latest_aircraft_data.get('aircraft', [])),
        "last_update": latest_aircraft_data.get('now', 0),
        "port": 8080
    })

# ACARS/VDL2 HTTP Endpoints (Port 8081 - dumpvdl2 compatible)
@acars_app.route('/tmp/vdl2.json')
def get_vdl2():
    """Serve latest VDL2 message (dumpvdl2 compatible)"""
    try:
        # Try to read from file first (if using file-based simulator)
        vdl2_file_path = '/tmp/vdl2.json'
        if os.path.exists(vdl2_file_path):
            with open(vdl2_file_path, 'r') as f:
                file_data = json.load(f)
                if file_data and 'vdl2' in file_data:
                    print(f"📻 Serving VDL2 from file: {vdl2_file_path}")
                    return jsonify(file_data)
        
        # Fall back to in-memory message
        if latest_vdl2_message:
            return jsonify(latest_vdl2_message)
        else:
            # Return empty VDL2 structure if no messages
            return jsonify({
                "vdl2": {
                    "app": {"name": "simulated_dumpvdl2", "ver": "2.3.0"},
                    "status": "no_messages"
                }
            })
    except Exception as e:
        print(f"❌ Error serving VDL2 data: {e}")
        return jsonify({
            "vdl2": {
                "app": {"name": "simulated_dumpvdl2", "ver": "2.3.0"},
                "error": str(e)
            }
        })

@acars_app.route('/tmp/acars.json')
def get_acars():
    """Serve all recent ACARS messages"""
    return jsonify({"messages": list(recent_acars_messages)})

@acars_app.route('/status')
def get_acars_status():
    """ACARS/VDL2 status endpoint"""
    vdl2_file_exists = os.path.exists('/tmp/vdl2.json')
    file_mtime = None
    if vdl2_file_exists:
        try:
            file_mtime = os.path.getmtime('/tmp/vdl2.json')
        except:
            file_mtime = None
    
    return jsonify({
        "service": "ACARS/VDL2 Bridge (dumpvdl2 compatible)",
        "vdl2_messages": len(recent_acars_messages),
        "latest_message_time": latest_vdl2_message['vdl2']['t']['sec'] if latest_vdl2_message else None,
        "vdl2_file_exists": vdl2_file_exists,
        "vdl2_file_modified": file_mtime,
        "port": 8081,
        "udp_port": 5555
    })

def run_adsb_server():
    """Run ADS-B server on port 8080"""
    try:
        adsb_app.run(host='127.0.0.1', port=8080, debug=False, use_reloader=False)
    except Exception as e:
        print(f"❌ ADS-B server error: {e}")

def run_acars_server():
    """Run ACARS/VDL2 server on port 8081"""
    try:
        acars_app.run(host='127.0.0.1', port=8081, debug=False, use_reloader=False)
    except Exception as e:
        print(f"❌ ACARS server error: {e}")

def main():
    print("🚀 Starting Complete UDP Bridge for ADS-B and ACARS")
    print("=" * 60)
    
    # Start background threads
    print("📡 Starting file listener for ADS-B data...")
    adsb_thread = threading.Thread(target=file_listener, daemon=True)
    adsb_thread.start()
    
    print("📻 Starting file listener for VDL2/ACARS data...")
    vdl2_thread = threading.Thread(target=vdl2_file_listener, daemon=True)
    vdl2_thread.start()
    
    print("🌐 Starting HTTP servers...")
    
    # Start ADS-B server in background thread
    adsb_server_thread = threading.Thread(target=run_adsb_server, daemon=True)
    adsb_server_thread.start()
    
    # Give ADS-B server time to start
    time.sleep(1)
    
    print("✅ ADS-B Server (dump1090 compatible): http://localhost:8080")
    print("   📊 Aircraft data: http://localhost:8080/data/aircraft.json")
    print("   📈 Status: http://localhost:8080/status")
    print("   📡 UDP Input: port 30005")
    print()
    print("✅ ACARS/VDL2 Server (dumpvdl2 compatible): http://localhost:8081")
    print("   📻 VDL2 data: http://localhost:8081/data/vdl2.json")
    print("   📋 All ACARS: http://localhost:8081/data/acars.json")
    print("   📈 Status: http://localhost:8081/status")
    print("   📡 UDP Input: port 5555")
    print("=" * 60)
    print("🎯 Configure radar app:")
    print("   dump1090 URL: http://localhost:8080")
    print("   dumpvdl2 URL: http://localhost:8081")
    print("=" * 60)
    print("📡 Send VDL2 or ACARS data to UDP port 5555 (JSON or text format)")
    print("=" * 60)
    
    try:
        # Run ACARS server in main thread
        run_acars_server()
    except KeyboardInterrupt:
        print("\n🛑 Bridge stopped")

if __name__ == "__main__":
    main()
