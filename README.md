# spotifyRoutines

AWS Lambda that builds and plays a Spotify queue based on user-specific configuration. Sources can include podcasts and music playlists. Trigger it from any HTTP client (MacroDroid, Samsung Routines, cron, etc.).

## Endpoints

### `POST /api/v1/play_music?play=true`

Uses `default_user` from config.

### `POST /api/v1/play_music/{user}?play=true`

Uses the given user configuration.

| Parameter | Default | Description |
|-----------|---------|-------------|
| `play` | `true` | Start playback immediately on the configured device |

If `user` does not exist in config, API returns `404`.

## Configuration

All config lives in `config/config.ini` (JSON format). Copy `config/config.example.ini` as a starting point:

```bash
cp config/config.example.ini config/config.ini
```

### Root schema

```json
{
  "default_user": "manuel",
  "users": [
    {
      "user": "manuel",
      "spotify_client_id": "...",
      "spotify_client_secret": "...",
      "spotify_refresh_token": "...",
      "spotify_device_id": "...",
      "spotify_queue_playlist_id": "...",
      "sources": [],
      "spotify_queue_uris": []
    }
  ]
}
```

- `default_user`: mandatory, used by `POST /api/v1/play_music`.
- `users`: list of user objects. Each user needs a unique `user` value.

### Source object

`sources` supports mixed items:

#### Podcast source

```json
{
  "type": "podcast",
  "name": "My Podcast",
  "id": "<spotify_show_id>",
  "window_hours": 24,
  "days": [0, 1, 2, 3, 4],
  "active": true
}
```

- `window_hours`: only include episodes released within this many hours (`null` = no limit).
- `days`: include source on specific weekdays (`null` = every day, `0` = Monday, `6` = Sunday).

#### Playlist source

```json
{
  "type": "playlist",
  "name": "Top Hits",
  "id": "<spotify_playlist_id>",
  "tracks_limit": 20,
  "shuffle": true,
  "active": true
}
```

- `tracks_limit`: optional max tracks to enqueue from playlist.
- `shuffle`: optional shuffle before enqueue.

### Active flag

- `active` is optional.
- If omitted, it defaults to `true`.
- Set `active: false` to keep the source configured but temporarily disabled.

### Backward compatibility

Legacy flat config (`spotify_client_id`, `spotify_podcasts`, etc.) is still accepted and mapped internally to a `default` user.

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

`spotify_queue_uris` is updated at runtime inside each user object. If you use SSM for mutable runtime config, ensure `spotify_users_config` is writable.

For legacy deployments you can still create this parameter:

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

All other config values are read from bundled `config/config.ini` unless `spotify_users_config` exists in SSM.

## Local development

```bash
pip install -r requirements.txt
pytest tests/
```

SSM is not used locally — all reads/writes go directly to `config/config.ini`.
