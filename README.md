# spotifyRoutines

AWS Lambda that builds and plays a Spotify podcast queue based on configured shows and time windows. Trigger it from any HTTP client (MacroDroid, Samsung Routines, cron, etc.).

## Endpoint

### `POST /api/v1/play_music?play=true`

Clears the queue playlist and refills it with new/unplayed podcast episodes.

| Parameter | Default | Description |
|-----------|---------|-------------|
| `play` | `true` | Start playback immediately on the configured device |

## Configuration

All config lives in `config/config.ini` (JSON format). Copy `config/config.example.ini` as a starting point:

```bash
cp config/config.example.ini config/config.ini
```

| Key | Description |
|-----|-------------|
| `spotify_client_id` | Spotify application client ID |
| `spotify_client_secret` | Spotify application client secret |
| `spotify_refresh_token` | OAuth refresh token (permanent, only changes on revoke) |
| `spotify_device_id` | Target Spotify device ID for playback |
| `spotify_queue_playlist_id` | Playlist ID used as the episode queue |
| `spotify_podcasts` | Array of podcast objects (see below) |
| `spotify_queue_uris` | Auto-managed — persisted to SSM Parameter Store in Lambda |

### Podcast object

```json
{
  "name": "My Podcast",
  "id": "<spotify_show_id>",
  "window_hours": 24,
  "days": [0, 1, 2, 3, 4]
}
```

- `window_hours`: only include episodes released within this many hours (`null` = no limit).
- `days`: days of the week to include this podcast (`null` = every day, `0` = Monday, `6` = Sunday).

## AWS Lambda deployment

### 1. Build

```bash
git clone https://github.com/mpedreira/spotifyRoutines.git
cd spotifyRoutines
cp config/config.example.ini config/config.ini  # fill in your credentials
./build.sh
```

Produces `layer.zip` (dependencies) and `app.zip` (application code + config).

### 2. Deploy

1. **Lambda Layer**: create or update a layer from `layer.zip` (Python 3.x, x86_64).
2. **Lambda Function**: create a function (Python 3.12, x86_64), upload `app.zip`, set handler to `app.main.handler`.
3. **Attach the layer** to the function.
4. **API Gateway**: expose the function via HTTP API or REST API.

### 3. SSM Parameter Store

`spotify_queue_uris` is the only value updated at runtime. Create it once:

```bash
aws ssm put-parameter --name spotify_queue_uris --value '[]' --type String --region us-east-1
```

Add this IAM policy to the Lambda execution role:

```json
{
  "Effect": "Allow",
  "Action": ["ssm:GetParameter", "ssm:GetParameters", "ssm:PutParameter"],
  "Resource": "arn:aws:ssm:us-east-1:<account-id>:parameter/spotify_*"
}
```

> All other config values are read from the bundled `config/config.ini`. Update them by editing the file and redeploying.

## Local development

```bash
pip install -r requirements.txt
pytest tests/
```

SSM is not used locally — all reads/writes go directly to `config/config.ini`.
