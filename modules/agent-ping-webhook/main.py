"""Kimaki Trigger Module

Trigger a Kimaki agent session via CLI.
Designed to be called by Sweatpants scheduler or external webhooks
(e.g., Data Machine Agent Ping → Sweatpants → this module).
"""

import asyncio
import os
import shutil
from typing import AsyncIterator

from sweatpants import Module


class KimakiTrigger(Module):
    """Trigger a Kimaki agent session with a prompt."""

    async def run(self, inputs: dict, settings: dict) -> AsyncIterator[dict]:
        """Execute kimaki send to spawn an agent session."""
        message = inputs["message"]
        channel = inputs.get("channel") or os.environ.get("DEFAULT_CHANNEL_ID", "")
        user = inputs.get("user", "")
        kimaki_path = inputs.get("kimaki_path", "kimaki")

        if not channel:
            await self.log("ERROR: No channel ID provided and DEFAULT_CHANNEL_ID not set")
            yield {"success": False, "error": "No channel ID"}
            return

        # Validate kimaki is available
        if not shutil.which(kimaki_path):
            await self.log(f"ERROR: Kimaki CLI not found at: {kimaki_path}")
            yield {"success": False, "error": f"Kimaki CLI not found: {kimaki_path}"}
            return

        await self.log(f"Triggering Kimaki session in channel {channel}")
        await self.log(f"Message length: {len(message)} chars")

        # Build command
        cmd = [
            kimaki_path, "send",
            "--channel", channel,
            "--prompt", message,
        ]

        if user:
            cmd.extend(["--user", user])
            await self.log(f"User: {user}")

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await process.communicate()

            if process.returncode == 0:
                output = stdout.decode().strip() if stdout else ""
                await self.log(f"Kimaki session spawned successfully")
                if output:
                    await self.log(f"Output: {output[:500]}")
                yield {
                    "success": True,
                    "return_code": 0,
                    "output": output,
                    "channel": channel,
                }
            else:
                error_msg = stderr.decode().strip() if stderr else "Unknown error"
                await self.log(f"ERROR: Kimaki send failed: {error_msg}")
                yield {
                    "success": False,
                    "return_code": process.returncode,
                    "error": error_msg,
                }

        except Exception as e:
            await self.log(f"ERROR: Failed to execute kimaki: {e}")
            yield {"success": False, "error": str(e)}
