#!/usr/bin/env python3
"""Check if Mireia's device_id changed after opening Spotify."""
import json
import requests
from app.classes.adapters.config_aws import ConfigAWS

# Get configured device ID
config = ConfigAWS(user='Mireia')
configured_id = config.spotify['device_id']

print("="*70)
print("Mireia Device ID Check")
print("="*70)
print(f"\n📋 Configured device ID:  {configured_id}")

# Get current devices from Spotify
resp = requests.post(
    'https://accounts.spotify.com/api/token',
    data={
        'grant_type': 'refresh_token',
        'refresh_token': config.spotify['refresh_token'],
        'client_id': config.spotify['client_id'],
        'client_secret': config.spotify['client_secret'],
    },
    verify=False, timeout=5
)
access_token = resp.json()['access_token']

devices_resp = requests.get(
    'https://api.spotify.com/v1/me/player/devices',
    headers={'Authorization': f'Bearer {access_token}'},
    verify=False, timeout=5
)
devices = devices_resp.json()['devices']

print(f"\n📱 Devices found in Spotify API ({len(devices)} total):\n")

mireia_devices = [d for d in devices if 'Mireia' in d['name'] or d['type'] == 'Smartphone']

for device in mireia_devices:
    name = device['name']
    dtype = device['type']
    device_id = device['id']
    active = "🟢" if device['is_active'] else "⚪"
    match = "✅ MATCHES CONFIG" if device_id == configured_id else "❌ DIFFERENT"
    print(f"  {active} {name:30} ({dtype:10}) {match}")
    print(f"     ID: {device_id}\n")

if any(d['id'] == configured_id for d in mireia_devices):
    print(f"✅ Configured device ID is available in Spotify")
else:
    print(f"❌ Configured device ID NOT found!")
    print(f"\n💡 Suggestion: The device_id may have changed. Update it with:")
    print(f"   - Open Spotify on Mireia's phone and start playing any song")
    print(f"   - Then run: python update_device_ids.py")
