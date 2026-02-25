# Fleet Agent Ping Webhook

Receives Data Machine Agent Ping webhooks and routes them to fleet agents via Kimaki.

## Architecture

```
DM Flow (Action Scheduler)
  → Agent Ping step (POST to localhost:8421)
    → webhook.py (this service)
      → kimaki send --channel <channel> --prompt <message>
        → Agent wakes up in Discord thread
```

## Components

| File | Purpose |
|------|---------|
| `webhook.py` | HTTP server that receives Agent Ping POSTs and spawns Kimaki sessions |
| `main.py` | Sweatpants module for triggering Kimaki from scheduled jobs |
| `module.json` | Sweatpants module manifest |

## Setup

### 1. Agent Routes

Create `~/.config/fleet/agent-routes.json`:

```json
{
  "chubes-bot": "1471183792227090704",
  "sarai-chinwag": "1471174119650365490",
  "fleet-command": "1470265088496767099"
}
```

### 2. Auth Token

Create `~/.config/fleet/agent-ping-token.txt` with a secret token, or set `AGENT_PING_TOKEN` env var.

This must match the `auth_token` configured on the DM Agent Ping step.

### 3. Run the Webhook

```bash
# Direct
python3 webhook.py

# With env vars
DEFAULT_CHANNEL_ID=1471183792227090704 \
DEFAULT_USER=chubes \
WEBHOOK_PORT=8421 \
python3 webhook.py
```

### 4. Systemd Service

```bash
sudo cp fleet-agent-ping.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now fleet-agent-ping
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `WEBHOOK_PORT` | `8421` | Port to listen on |
| `DEFAULT_CHANNEL_ID` | _(none)_ | Fallback Discord channel for pings without `reply_to` |
| `DEFAULT_USER` | _(none)_ | Default Discord user to add to spawned threads |
| `AGENT_PING_TOKEN` | _(none)_ | Auth token for external requests |
| `DISCORD_NOTIFICATION_WEBHOOK` | _(none)_ | Optional Discord webhook for visibility notifications |
| `KIMAKI_PATH` | `kimaki` | Path to kimaki CLI |
| `AGENT_ROUTES` | _(none)_ | JSON string mapping agent names to channel IDs |

## DM Agent Ping Configuration

On the Data Machine flow step, configure:

```
webhook_url: http://127.0.0.1:8421
prompt: "Run weekly site health check..."
auth_header_name: X-Agent-Token
auth_token: <same token as agent-ping-token.txt>
reply_to: <discord-channel-id or agent name>
```

## Payload Format

The webhook accepts the standard DM Agent Ping payload:

```json
{
  "prompt": "Task instructions for the agent",
  "context": {
    "flow_id": 7,
    "pipeline_id": 3,
    "job_id": 1234,
    "from_queue": false,
    "site_url": "https://chubes.net",
    "data_packets": []
  },
  "reply_to": "1471183792227090704",
  "agent_name": "chubes-bot",
  "user": "chubes"
}
```

Routing priority:
1. `reply_to` if numeric (direct channel ID)
2. `agent_name` lookup in agent routes
3. `reply_to` lookup in agent routes (allows `reply_to: "chubes-bot"`)
4. `DEFAULT_CHANNEL_ID` fallback

## Health Check

```bash
curl http://127.0.0.1:8421
```

Returns service status, route count, and default channel.
