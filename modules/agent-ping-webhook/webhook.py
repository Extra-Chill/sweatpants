#!/usr/bin/env python3
"""Fleet Agent Ping Webhook Bridge

Receives Data Machine Agent Ping webhooks and routes them to the correct
fleet agent via Kimaki CLI. Each agent is identified by its Discord channel ID.

Architecture:
    DM Flow (scheduled) → Agent Ping step → POST to this webhook
    → kimaki send --channel <channel> --prompt <message> → agent wakes up

Designed for Fleet Command — routes to ANY fleet member, not a single agent.
"""

import json
import os
import subprocess
import sys
import threading
import urllib.request
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime

def log(msg: str):
    """Log with timestamp and flush."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {msg}", flush=True)


# ---------------------------------------------------------------------------
# Configuration (environment variables with sensible defaults)
# ---------------------------------------------------------------------------

LISTEN_PORT = int(os.environ.get("WEBHOOK_PORT", "8421"))

# Default channel to route pings to when no reply_to is specified.
# Override per-deployment via env var.
DEFAULT_CHANNEL_ID = os.environ.get("DEFAULT_CHANNEL_ID", "")

# Optional Discord webhook for visibility notifications (separate from agent delivery)
DISCORD_NOTIFICATION_WEBHOOK = os.environ.get("DISCORD_NOTIFICATION_WEBHOOK", "")

# Auth token for external requests. Loaded from file or env var.
# Local requests (127.0.0.1) bypass auth.
AUTH_TOKEN = os.environ.get("AGENT_PING_TOKEN", "")

# Path to kimaki CLI
KIMAKI_PATH = os.environ.get("KIMAKI_PATH", "kimaki")

# Optional: user to add to the spawned thread
DEFAULT_USER = os.environ.get("DEFAULT_USER", "")


def load_token_from_file():
    """Try to load auth token from a file if env var isn't set."""
    global AUTH_TOKEN
    if AUTH_TOKEN:
        return
    token_paths = [
        os.path.expanduser("~/.config/fleet/agent-ping-token.txt"),
        "/etc/fleet/agent-ping-token.txt",
    ]
    for path in token_paths:
        try:
            with open(path) as f:
                AUTH_TOKEN = f.read().strip()
                log(f"Loaded auth token from {path}")
                return
        except FileNotFoundError:
            continue

load_token_from_file()


# ---------------------------------------------------------------------------
# Agent routing table
# ---------------------------------------------------------------------------
# Maps agent names/aliases to Discord channel IDs.
# This lets DM flows specify agent="chubes-bot" instead of raw channel IDs.
# Loaded from AGENT_ROUTES env var (JSON) or a config file.

AGENT_ROUTES = {}

def load_agent_routes():
    """Load agent routing table from env var or config file."""
    global AGENT_ROUTES

    # Try env var first (JSON string)
    routes_json = os.environ.get("AGENT_ROUTES", "")
    if routes_json:
        try:
            AGENT_ROUTES = json.loads(routes_json)
            log(f"Loaded {len(AGENT_ROUTES)} agent routes from env")
            return
        except json.JSONDecodeError:
            log("WARNING: AGENT_ROUTES env var is not valid JSON, ignoring")

    # Try config file
    config_paths = [
        os.path.expanduser("~/.config/fleet/agent-routes.json"),
        "/etc/fleet/agent-routes.json",
    ]
    for path in config_paths:
        try:
            with open(path) as f:
                AGENT_ROUTES = json.load(f)
                log(f"Loaded {len(AGENT_ROUTES)} agent routes from {path}")
                return
        except (FileNotFoundError, json.JSONDecodeError):
            continue

load_agent_routes()


def resolve_channel(reply_to: str, agent_name: str = "") -> str:
    """Resolve a channel ID from reply_to or agent name.

    Priority:
    1. reply_to if it looks like a channel ID (numeric)
    2. Agent name lookup in routing table
    3. DEFAULT_CHANNEL_ID fallback
    """
    # Direct channel ID
    if reply_to and reply_to.isdigit():
        return reply_to

    # Agent name lookup
    if agent_name and agent_name in AGENT_ROUTES:
        return AGENT_ROUTES[agent_name]

    if reply_to and reply_to in AGENT_ROUTES:
        return AGENT_ROUTES[reply_to]

    return DEFAULT_CHANNEL_ID


# ---------------------------------------------------------------------------
# Notifications
# ---------------------------------------------------------------------------

def notify_discord(message: str, from_queue: bool = False):
    """Send notification to Discord webhook for visibility."""
    if not DISCORD_NOTIFICATION_WEBHOOK:
        return

    source = "\U0001f4cb" if from_queue else "\U0001f916"  # 📋 or 🤖
    content = f"{source} **Agent Ping Received**\n{message[:500]}"

    try:
        data = json.dumps({"content": content}).encode("utf-8")
        req = urllib.request.Request(
            DISCORD_NOTIFICATION_WEBHOOK,
            data=data,
            headers={
                "Content-Type": "application/json",
                "User-Agent": "FleetAgentPingWebhook/1.0",
            },
            method="POST",
        )
        urllib.request.urlopen(req, timeout=10)
        log("Notified Discord webhook")
    except Exception as e:
        log(f"WARNING: Discord notification failed: {e}")


# ---------------------------------------------------------------------------
# Kimaki session spawning
# ---------------------------------------------------------------------------

def spawn_kimaki_session(channel_id: str, prompt: str, user: str = "") -> dict:
    """Spawn a Kimaki session via CLI.

    Returns dict with success status and session info.
    """
    cmd = [
        KIMAKI_PATH, "send",
        "--channel", channel_id,
        "--prompt", prompt,
    ]

    if user:
        cmd.extend(["--user", user])

    try:
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )

        log(f"Spawned kimaki send (pid {process.pid}) -> channel:{channel_id}: {prompt[:80]}...")

        return {
            "success": True,
            "pid": process.pid,
            "channel_id": channel_id,
        }

    except FileNotFoundError:
        log(f"ERROR: Kimaki CLI not found at: {KIMAKI_PATH}")
        return {"success": False, "error": f"Kimaki CLI not found: {KIMAKI_PATH}"}
    except Exception as e:
        log(f"ERROR: Failed to spawn kimaki: {e}")
        return {"success": False, "error": str(e)}


# ---------------------------------------------------------------------------
# Webhook handler
# ---------------------------------------------------------------------------

class WebhookHandler(BaseHTTPRequestHandler):
    """Handle incoming Agent Ping webhooks."""

    def do_POST(self):
        """Process POST requests from Data Machine Agent Ping."""
        # Auth check: local requests bypass, external need token
        real_ip = self.headers.get("X-Real-IP", "127.0.0.1")
        is_local = real_ip in ("127.0.0.1", "::1", "localhost")

        if AUTH_TOKEN and not is_local:
            token = self.headers.get("X-Agent-Token") or self.headers.get("Authorization", "").removeprefix("Bearer ").strip()
            if not token:
                log(f"Rejected {real_ip}: missing auth")
                self.send_error(401, "Missing authentication token")
                return
            if token != AUTH_TOKEN:
                log(f"Rejected {real_ip}: invalid token")
                self.send_error(401, "Invalid token")
                return

        # Parse body
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length)

        try:
            payload = json.loads(body) if body else {}
        except json.JSONDecodeError:
            self.send_error(400, "Invalid JSON")
            return

        # Extract prompt from Agent Ping payload
        prompt = payload.get("prompt", "")

        # Fallback: check data_packets for published content context
        if not prompt:
            context = payload.get("context", {})
            data_packets = context.get("data_packets", [])
            if data_packets:
                first_packet = data_packets[0]
                content = first_packet.get("content", {})
                metadata = first_packet.get("metadata", {})
                title = content.get("title", "")
                url = metadata.get("url", "")
                if title:
                    prompt = f"New post published: {title}"
                    if url:
                        prompt += f"\nURL: {url}"
                else:
                    prompt = "Pipeline completed — review results"

        if not prompt:
            self.send_error(400, "No prompt in payload")
            return

        # Resolve routing
        context = payload.get("context", {})
        from_queue = context.get("from_queue", False)
        reply_to = payload.get("reply_to", "")
        agent_name = payload.get("agent_name", "")
        user = payload.get("user", DEFAULT_USER)

        channel_id = resolve_channel(reply_to, agent_name)

        if not channel_id:
            log("ERROR: No channel resolved — set DEFAULT_CHANNEL_ID or provide reply_to")
            self.send_error(400, "No channel ID resolved. Set reply_to or configure DEFAULT_CHANNEL_ID.")
            return

        # Enrich prompt with context if available
        enriched_prompt = prompt
        if from_queue:
            flow_id = context.get("flow_id", "")
            site_url = context.get("site_url", "")
            if flow_id:
                enriched_prompt += f"\n\n> Queued task from flow {flow_id}"
            if site_url:
                enriched_prompt += f" on {site_url}"

        # Notify Discord for visibility
        notify_discord(prompt, from_queue)

        # Spawn kimaki session
        result = spawn_kimaki_session(channel_id, enriched_prompt, user)

        if result["success"]:
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({
                "success": True,
                "pid": result["pid"],
                "channel_id": result["channel_id"],
                "message_preview": prompt[:100],
            }).encode())
        else:
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({
                "success": False,
                "error": result["error"],
            }).encode())

    def do_GET(self):
        """Health check endpoint."""
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({
            "status": "ok",
            "service": "fleet-agent-ping-webhook",
            "routes": len(AGENT_ROUTES),
            "default_channel": bool(DEFAULT_CHANNEL_ID),
        }).encode())

    def log_message(self, fmt, *args):
        log(f"[http] {args[0]}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    if not DEFAULT_CHANNEL_ID and not AGENT_ROUTES:
        log("WARNING: No DEFAULT_CHANNEL_ID or AGENT_ROUTES configured.")
        log("Pings without reply_to will fail.")

    server = HTTPServer(("127.0.0.1", LISTEN_PORT), WebhookHandler)
    log(f"Fleet Agent Ping Webhook listening on http://127.0.0.1:{LISTEN_PORT}")
    log(f"Default channel: {DEFAULT_CHANNEL_ID or '(none)'}")
    log(f"Agent routes: {list(AGENT_ROUTES.keys()) or '(none)'}")
    log(f"Kimaki CLI: {KIMAKI_PATH}")
    server.serve_forever()


if __name__ == "__main__":
    main()
