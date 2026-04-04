# spotifyRoutines

An AWS Lambda API that builds and plays a Spotify podcast queue based on your configured shows and time windows. Deploy it to AWS and trigger it from any HTTP client (e.g. MacroDroid, Samsung Routines, cron).

## Endpoint

### `POST /api/v1/play_music?play=true`

Clears the queue playlist and refills it with new/unplayed podcast episodes based on the configured shows and time windows.

- `play=true` (default): also starts playback on the configured Spotify device.
- `play=false`: only prepares the playlist for manual playback.

## AWS Lambda deployment

### Download the code

```
git clone https://github.com/mpedreira/spotifyRoutines.git
```

### Create the Lambda layer

```
mkdir python
pip3 install --platform x86_64 --target python -r spotifyRoutines/requirements.txt --python-version 3.12 --only-binary :all:
zip -r9 spotifyRoutines-layer.zip python
```

### Create the app ZIP

```
cd spotifyRoutines
zip -r9 ../my_app.zip app
```

### Create config.ini

Copy the example and fill in your Spotify credentials:

```
cp config/config.example.ini config/config.ini
nano config/config.ini
zip -r9 ../my_app.zip app config
```

### Deploy

1. Create a Lambda layer from `spotifyRoutines-layer.zip`.
2. Create a new Lambda function (Python 3.12, x86_64).
3. Upload `my_app.zip` as the function code.
4. Attach the layer created above.
5. Set the handler to `app.main.handler`.
6. Expose the function through API Gateway.

## Configuration

All configuration lives in `config/config.ini` (JSON format). Copy `config/config.example.ini` as a starting point.

| Key | Description |
|-----|-------------|
| `spotify_client_id` | Spotify application client ID |
| `spotify_client_secret` | Spotify application client secret |
| `spotify_refresh_token` | OAuth refresh token for your Spotify account |
| `spotify_device_id` | Target Spotify device ID for playback |
| `spotify_queue_playlist_id` | Playlist ID used as the episode queue |
| `spotify_podcasts` | Array of objects with `id` and `window_hours` fields |

This project is tested with BrowserStack.
