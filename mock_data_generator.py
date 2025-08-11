#!/usr/bin/env python3
"""
Mock Data Generator for UDP Bridge Testing
Generates realistic ADS-B and VDL2/ACARS data for testing the UDP bridge
"""

import json
import time
import random
import math
import threading
import os

# Gulf Coast area coordinates for realistic aircraft positions
GULF_COAST_CENTER = {"lat": 30.5, "lon": -87.5}
RANGE_DEGREES = 2.0  # Approximately 120 nautical miles

# Common aircraft types and their typical cruise speeds/altitudes
AIRCRAFT_TYPES = [
    {"type": "A320", "speed_range": (400, 480), "alt_range": (30000, 39000)},
    {"type": "B737", "speed_range": (420, 500), "alt_range": (31000, 39000)},
    {"type": "E175", "speed_range": (380, 450), "alt_range": (30000, 37000)},
    {"type": "CRJ9", "speed_range": (380, 430), "alt_range": (28000, 35000)},
    {"type": "A321", "speed_range": (430, 510), "alt_range": (32000, 39000)},
    {"type": "B738", "speed_range": (420, 500), "alt_range": (31000, 39000)},
]

# Airlines and their typical flight number patterns
AIRLINES = [
    {"name": "DAL", "prefix": "DAL", "range": (1, 9999)},
    {"name": "AAL", "prefix": "AAL", "range": (1, 9999)},
    {"name": "UAL", "prefix": "UAL", "range": (1, 9999)},
    {"name": "SWA", "prefix": "SWA", "range": (1, 9999)},
    {"name": "JBU", "prefix": "JBU", "range": (1, 999)},
]

# Sample ACARS message texts
ACARS_MESSAGES = [
    "ENGINE DATA OK",
    "FUEL STATUS: 12500 LBS",
    "WEATHER REQUEST: KATL",
    "POSITION REPORT: 30.5N 087.5W",
    "ETA REVISED: 1430Z",
    "GATE INFO REQUEST",
    "MAINTENANCE: OIL PRESS OK",
    "DISPATCH: ON TIME",
    "CREW REPORT: NORMAL OPS",
    "TURBULENCE REPORT: LIGHT CHOP",
]

class MockAircraft:
    def __init__(self):
        self.hex = format(random.randint(0x100000, 0xFFFFFF), '06X')
        self.flight = self.generate_flight_number()
        self.aircraft_type = random.choice(AIRCRAFT_TYPES)
        
        # Start position in Gulf Coast area
        self.lat = GULF_COAST_CENTER["lat"] + random.uniform(-RANGE_DEGREES, RANGE_DEGREES)
        self.lon = GULF_COAST_CENTER["lon"] + random.uniform(-RANGE_DEGREES, RANGE_DEGREES)
        
        # Random heading and speed
        self.track = random.uniform(0, 359)
        self.speed = random.uniform(*self.aircraft_type["speed_range"])
        self.altitude = random.randint(*self.aircraft_type["alt_range"])
        
        # Vertical rate (mostly level flight with occasional climbs/descents)
        if random.random() < 0.8:
            self.vert_rate = 0
        else:
            self.vert_rate = random.randint(-2000, 2000)
        
        self.squawk = format(random.randint(1000, 7777), '04d')
        self.seen = 0
        self.rssi = random.uniform(-30, -10)
        
    def generate_flight_number(self):
        airline = random.choice(AIRLINES)
        number = random.randint(*airline["range"])
        return f"{airline['prefix']}{number}"
    
    def update_position(self):
        """Update aircraft position based on speed and heading"""
        # Convert speed from knots to degrees per second (very approximate)
        speed_deg_per_sec = (self.speed * 0.000154323) / 3600
        
        # Update position
        lat_change = speed_deg_per_sec * math.cos(math.radians(self.track))
        lon_change = speed_deg_per_sec * math.sin(math.radians(self.track)) / math.cos(math.radians(self.lat))
        
        self.lat += lat_change
        self.lon += lon_change
        
        # Update altitude if climbing/descending
        if self.vert_rate != 0:
            self.altitude += self.vert_rate / 60  # per second
            
            # Level off randomly
            if random.random() < 0.1:
                self.vert_rate = 0
        
        # Randomly change heading occasionally
        if random.random() < 0.05:
            self.track += random.uniform(-30, 30)
            self.track = self.track % 360
        
        # Update seen counter and RSSI
        self.seen = random.uniform(0, 2)
        self.rssi += random.uniform(-2, 2)
        self.rssi = max(-50, min(-5, self.rssi))
    
    def to_dict(self):
        """Convert to ADS-B JSON format"""
        return {
            "hex": self.hex,
            "flight": self.flight,
            "alt_baro": int(self.altitude),
            "alt_geom": int(self.altitude + random.randint(-100, 100)),
            "gs": int(self.speed),
            "track": round(self.track, 1),
            "baro_rate": int(self.vert_rate),
            "squawk": self.squawk,
            "emergency": "none",
            "category": "A3",
            "nav_qnh": 1013.25,
            "nav_altitude_mcp": int(self.altitude),
            "lat": round(self.lat, 6),
            "lon": round(self.lon, 6),
            "nic": 8,
            "rc": 186,
            "seen_pos": self.seen,
            "version": 2,
            "nic_baro": 1,
            "nac_p": 9,
            "nac_v": 2,
            "sil": 3,
            "sil_type": "perhour",
            "gva": 2,
            "sda": 2,
            "alert": False,
            "spi": False,
            "mlat": [],
            "tisb": [],
            "messages": random.randint(100, 10000),
            "seen": round(self.seen, 1),
            "rssi": round(self.rssi, 1)
        }

def generate_vdl2_message(aircraft_hex, flight_num):
    """Generate a VDL2/ACARS message"""
    return {
        "vdl2": {
            "app": {
                "name": "mock_dumpvdl2",
                "ver": "2.3.0"
            },
            "t": {
                "sec": int(time.time()),
                "usec": random.randint(100000, 999999)
            },
            "freq": random.choice([136925000, 136975000, 131525000, 131725000]),
            "burst_len_octets": random.randint(20, 200),
            "hdr_bits_fixed": 0,
            "octets_corrected_by_fec": 0,
            "idx": 0,
            "sig_level": round(random.uniform(-25.0, -10.0), 6),
            "noise_level": round(random.uniform(-55.0, -40.0), 6),
            "freq_skew": round(random.uniform(-3.0, 3.0), 6),
            "avlc": {
                "src": {
                    "addr": aircraft_hex,
                    "type": "Aircraft",
                    "status": "Airborne"
                },
                "dst": {
                    "addr": "234C97",
                    "type": "Ground station"
                },
                "cr": "Command",
                "frame_type": "I",
                "cmd": "Data",
                "pf": True,
                "rseq": random.randint(0, 7)
            },
            "acars": {
                "msg_text": random.choice(ACARS_MESSAGES),
                "flight": flight_num,
                "tail": f"N{random.randint(100, 999)}{random.choice(['AA', 'AB', 'AC', 'AD'])}",
                "msg_type": "DATA"
            }
        }
    }

def generate_adsb_data(aircraft_list):
    """Generate ADS-B aircraft.json format data"""
    # Update all aircraft positions
    for aircraft in aircraft_list:
        aircraft.update_position()
    
    return {
        "now": time.time(),
        "messages": random.randint(100000, 999999),
        "aircraft": [aircraft.to_dict() for aircraft in aircraft_list]
    }

def write_adsb_data(aircraft_list):
    """Write ADS-B data to /tmp/aircraft.json"""
    try:
        adsb_data = generate_adsb_data(aircraft_list)
        with open('/tmp/aircraft.json', 'w') as f:
            json.dump(adsb_data, f, indent=2)
        print(f"📡 Generated ADS-B data: {len(aircraft_list)} aircraft")
    except Exception as e:
        print(f"❌ Error writing ADS-B data: {e}")

def write_vdl2_data(aircraft_list):
    """Write VDL2/ACARS data to /tmp/vdl2.json"""
    try:
        # Pick a random aircraft to send an ACARS message
        if aircraft_list and random.random() < 0.3:  # 30% chance per update
            aircraft = random.choice(aircraft_list)
            vdl2_msg = generate_vdl2_message(aircraft.hex, aircraft.flight)
            
            # dumpvdl2 format is one JSON object per line
            with open('/tmp/vdl2.json', 'w') as f:
                json.dump(vdl2_msg, f)
            
            msg_text = vdl2_msg["vdl2"]["acars"]["msg_text"]
            freq_mhz = vdl2_msg["vdl2"]["freq"] / 1000000.0
            print(f"📻 Generated VDL2 message: {aircraft.flight} on {freq_mhz:.3f}MHz - {msg_text}")
    except Exception as e:
        print(f"❌ Error writing VDL2 data: {e}")

def main():
    print("🚀 Starting Mock Data Generator for UDP Bridge")
    print("=" * 60)
    
    # Create /tmp directory if it doesn't exist
    os.makedirs('/tmp', exist_ok=True)
    
    # Generate initial aircraft
    num_aircraft = random.randint(5, 15)
    aircraft_list = [MockAircraft() for _ in range(num_aircraft)]
    
    print(f"✈️  Generated {num_aircraft} mock aircraft")
    print("📁 Writing data to:")
    print("   /tmp/aircraft.json (ADS-B data)")
    print("   /tmp/vdl2.json (VDL2/ACARS data)")
    print("=" * 60)
    print("🔄 Updating data every 3 seconds...")
    print("Press Ctrl+C to stop")
    print("=" * 60)
    
    try:
        while True:
            # Write ADS-B data
            write_adsb_data(aircraft_list)
            
            # Write VDL2/ACARS data (less frequently)
            write_vdl2_data(aircraft_list)
            
            # Occasionally add or remove aircraft
            if random.random() < 0.1:  # 10% chance
                if len(aircraft_list) > 3 and random.random() < 0.5:
                    # Remove an aircraft
                    removed = aircraft_list.pop()
                    print(f"🛬 Aircraft departed: {removed.flight}")
                elif len(aircraft_list) < 20:
                    # Add an aircraft
                    new_aircraft = MockAircraft()
                    aircraft_list.append(new_aircraft)
                    print(f"🛫 New aircraft: {new_aircraft.flight}")
            
            time.sleep(3)  # Update every 3 seconds
            
    except KeyboardInterrupt:
        print("\n🛑 Mock data generator stopped")
        print("🧹 Cleaning up temporary files...")
        try:
            os.remove('/tmp/aircraft.json')
            os.remove('/tmp/vdl2.json')
            print("✅ Temporary files removed")
        except:
            pass

if __name__ == "__main__":
    main()
