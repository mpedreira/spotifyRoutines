#!/usr/bin/env bash
set -euo pipefail

DEFAULT_CONFIG="config/config.ini"

# Supported invocation styles:
#   ./get_devices.sh Mireia
#   ./get_devices.sh config/config.ini Mireia
#   ./get_devices.sh Mireia config/config.ini
ARG1="${1:-}"
ARG2="${2:-}"

if [[ -z "$ARG1" && -z "$ARG2" ]]; then
	CONFIG_FILE="$DEFAULT_CONFIG"
	USER_NAME="YourUser"
elif [[ -n "$ARG1" && -z "$ARG2" ]]; then
	if [[ -f "$ARG1" ]]; then
		CONFIG_FILE="$ARG1"
		USER_NAME="YourUser"
	else
		CONFIG_FILE="$DEFAULT_CONFIG"
		USER_NAME="$ARG1"
	fi
else
	if [[ -f "$ARG1" ]]; then
		CONFIG_FILE="$ARG1"
		USER_NAME="$ARG2"
	elif [[ -f "$ARG2" ]]; then
		CONFIG_FILE="$ARG2"
		USER_NAME="$ARG1"
	else
		CONFIG_FILE="$DEFAULT_CONFIG"
		USER_NAME="$ARG1"
	fi
fi

if ! command -v curl >/dev/null 2>&1; then
	echo "ERROR: curl no está instalado"
	exit 1
fi

if ! command -v jq >/dev/null 2>&1; then
	echo "ERROR: jq no está instalado"
	echo "Instala jq en WSL: sudo apt-get update && sudo apt-get install -y jq"
	exit 1
fi

if [[ ! -f "$CONFIG_FILE" ]]; then
	echo "ERROR: no existe el fichero de config: $CONFIG_FILE"
	exit 1
fi

CLIENT_ID="$(jq -r --arg u "$USER_NAME" '.users[] | select(.user == $u) | .spotify_client_id // empty' "$CONFIG_FILE")"
CLIENT_SECRET="$(jq -r --arg u "$USER_NAME" '.users[] | select(.user == $u) | .spotify_client_secret // empty' "$CONFIG_FILE")"
REFRESH_TOKEN="$(jq -r --arg u "$USER_NAME" '.users[] | select(.user == $u) | .spotify_refresh_token // empty' "$CONFIG_FILE")"
CURRENT_DEVICE_ID="$(jq -r --arg u "$USER_NAME" '.users[] | select(.user == $u) | .spotify_device_id // empty' "$CONFIG_FILE")"
CURRENT_DEVICE_NAME="$(jq -r --arg u "$USER_NAME" '.users[] | select(.user == $u) | .spotify_device_name // empty' "$CONFIG_FILE")"

if [[ -z "$CLIENT_ID" || -z "$CLIENT_SECRET" || -z "$REFRESH_TOKEN" ]]; then
	echo "ERROR: faltan credenciales para el usuario '$USER_NAME' en $CONFIG_FILE"
	exit 1
fi

echo "Usuario: $USER_NAME"
echo "Device guardado en config: ${CURRENT_DEVICE_ID:-<vacío>}"
echo "Device name guardado en config: ${CURRENT_DEVICE_NAME:-<vacío>}"
echo

TOKEN_RESPONSE="$(curl -sS -X POST "https://accounts.spotify.com/api/token" \
	-H "Content-Type: application/x-www-form-urlencoded" \
	--data-urlencode "grant_type=refresh_token" \
	--data-urlencode "refresh_token=$REFRESH_TOKEN" \
	--data-urlencode "client_id=$CLIENT_ID" \
	--data-urlencode "client_secret=$CLIENT_SECRET")"

ACCESS_TOKEN="$(echo "$TOKEN_RESPONSE" | jq -r '.access_token // empty')"

if [[ -z "$ACCESS_TOKEN" ]]; then
	echo "ERROR obteniendo access_token:"
	echo "$TOKEN_RESPONSE" | jq .
	exit 1
fi

DEVICES_JSON="$(curl -sS -X GET "https://api.spotify.com/v1/me/player/devices" \
	-H "Authorization: Bearer $ACCESS_TOKEN")"

echo "Dispositivos disponibles ahora en Spotify Connect:"
TABLE_OUTPUT="$(echo "$DEVICES_JSON" | jq -r --arg current_id "$CURRENT_DEVICE_ID" --arg current_name "$CURRENT_DEVICE_NAME" '
	.devices // [] |
	if length == 0 then
		"  (ninguno visible ahora; abre Spotify/Alexa y vuelve a probar)"
	else
		(["selected","name","id","type","is_active","is_restricted","supports_volume"] | @tsv),
		(.[] | [
			(if (.id == $current_id) or (.name == $current_name and ($current_name|length)>0) then "*" else "" end),
			.name,
			.id,
			.type,
			(.is_active|tostring),
			(.is_restricted|tostring),
			(.supports_volume|tostring)
		] | @tsv)
	end
')"

if command -v column >/dev/null 2>&1; then
	echo "$TABLE_OUTPUT" | column -t -s $'\t'
else
	echo "$TABLE_OUTPUT"
fi

echo
echo "Tip: el grupo de 'toda la casa' debe estar activo para aparecer aquí."
