# Real Module Examples

## Image Generator (API-based)

```json
// module.json
{
  "id": "image-generator",
  "name": "Image Generator",
  "version": "1.0.0",
  "description": "Generate images using Replicate Flux Schnell",
  "inputs": {
    "prompt": {
      "type": "string",
      "description": "Image generation prompt (optional if topic provided)"
    },
    "topic": {
      "type": "string", 
      "description": "Topic for auto-generated prompt"
    },
    "aspect_ratio": {
      "type": "string",
      "description": "Aspect ratio (1:1, 2:3, 3:2, 16:9, etc)",
      "default": "2:3"
    },
    "num_images": {
      "type": "integer",
      "description": "Number of images to generate",
      "default": 1
    }
  },
  "settings": {
    "replicate_key": {
      "type": "string",
      "env": "REPLICATE_API_TOKEN"
    }
  },
  "capabilities": {
    "browser": false,
    "proxy": false
  }
}
```

```python
# main.py (key parts)
class ImageGenerator(Module):
    async def run(self, inputs: dict, settings: dict) -> AsyncIterator[dict]:
        prompt = inputs.get("prompt") or self._generate_prompt(inputs["topic"])
        num_images = int(inputs.get("num_images", 1))

        for i in range(num_images):
            await self.log(f"Generating image {i+1}/{num_images}")
            image_url = await self._call_replicate_api(prompt)
            
            yield {
                "index": i + 1,
                "success": True,
                "url": image_url,
                "prompt": prompt,
            }
            
            if i < num_images - 1:
                await asyncio.sleep(2)  # Rate limit
```

## Pinterest Pinner (API with validation)

```json
// module.json
{
  "id": "pinterest-pinner",
  "name": "Pinterest Pinner",
  "version": "2.0.0",
  "description": "Pin images to Pinterest with SEO metadata",
  "inputs": {
    "image_url": {
      "type": "string",
      "description": "URL of image to pin",
      "required": true
    },
    "link_url": {
      "type": "string",
      "description": "Destination URL when pin is clicked",
      "required": true
    },
    "board_name": {
      "type": "string",
      "description": "Pinterest board name",
      "required": true
    },
    "title": {
      "type": "string",
      "description": "Pin title (SEO)"
    },
    "description": {
      "type": "string",
      "description": "Pin description (SEO)"
    }
  },
  "capabilities": {
    "browser": false,
    "proxy": false
  }
}
```

```python
# main.py pattern: validate before acting
class PinterestPinner(Module):
    async def run(self, inputs: dict, settings: dict):
        # 1. Load credentials
        token = self._load_pinterest_token()
        if not token:
            yield {"error": "Missing Pinterest token"}
            return

        # 2. Validate inputs exist
        await self.log("Validating destination URL...")
        if not await self._validate_url(inputs["link_url"]):
            yield {"error": f"URL not reachable: {inputs['link_url']}"}
            return

        # 3. Find resources
        board_id = await self._find_board(token, inputs["board_name"])
        if not board_id:
            yield {"error": f"Board not found", "available_boards": await self._list_boards(token)}
            return

        # 4. Execute
        result = await self._create_pin(token, board_id, ...)
        yield result
```

## OpenClaw Trigger (Webhook integration)

```json
// module.json
{
  "id": "openclaw-trigger",
  "name": "OpenClaw Trigger",
  "version": "1.1.0",
  "description": "Trigger OpenClaw agent via gateway wake event",
  "inputs": {
    "message": {
      "type": "string",
      "description": "Message to send to the agent",
      "required": true
    },
    "gateway_url": {
      "type": "string",
      "description": "OpenClaw gateway WebSocket URL",
      "default": "ws://127.0.0.1:18789"
    }
  },
  "capabilities": {
    "browser": false,
    "proxy": false
  }
}
```

```python
# Pattern: WebSocket communication
import websockets

class OpenClawTrigger(Module):
    async def run(self, inputs: dict, settings: dict):
        gateway_url = inputs.get("gateway_url", "ws://127.0.0.1:18789")
        token = self._load_token()

        await self.log(f"Connecting to {gateway_url}")
        
        async with websockets.connect(f"{gateway_url}?token={token}") as ws:
            await ws.send(json.dumps({
                "type": "wake",
                "text": inputs["message"],
                "mode": "now"
            }))
            
            response = await ws.recv()
            await self.log(f"Response: {response}")
            yield json.loads(response)
```

## Chart Generator (File output)

```python
# Pattern: Generate files and return paths
class ChartGenerator(Module):
    async def run(self, inputs: dict, settings: dict):
        import matplotlib.pyplot as plt
        
        # Generate chart
        fig, ax = plt.subplots()
        ax.bar(inputs["labels"], inputs["values"])
        ax.set_title(inputs["title"])
        
        # Save to file
        output_path = f"/tmp/chart_{int(time.time())}.png"
        fig.savefig(output_path, dpi=150)
        plt.close()
        
        # Compress with pngquant
        subprocess.run(["pngquant", "--force", "--output", output_path, output_path])
        
        await self.log(f"Chart saved: {output_path}")
        yield {"path": output_path, "title": inputs["title"]}
```

## Common Patterns

### Loading secrets from files
```python
def _load_secret(self, filename: str) -> str | None:
    path = f"/root/.openclaw/secrets/{filename}"
    if os.path.exists(path):
        with open(path) as f:
            return f.read().strip()
    return None
```

### HTTP with retries
```python
async def _fetch_with_retry(self, url: str, max_retries: int = 3):
    for attempt in range(max_retries):
        try:
            response = await proxied_request("GET", url)
            if response.status_code == 200:
                return response.json()
        except Exception as e:
            await self.log(f"Attempt {attempt+1} failed: {e}")
            await asyncio.sleep(2 ** attempt)
    return None
```

### Progress tracking with checkpoints
```python
async def run(self, inputs: dict, settings: dict):
    items = inputs["items"]
    
    # Resume from checkpoint
    checkpoint = await self.load_checkpoint()
    start_index = checkpoint.get("index", 0) if checkpoint else 0
    
    for i, item in enumerate(items[start_index:], start=start_index):
        result = await self._process(item)
        yield {"index": i, "result": result}
        
        # Save checkpoint every 10 items
        if i % 10 == 0:
            await self.save_checkpoint(index=i)
```
