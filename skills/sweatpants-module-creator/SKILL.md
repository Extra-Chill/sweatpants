---
name: sweatpants-module-creator
description: Create new Sweatpants automation modules. Use when building a new module for the Sweatpants engine, defining module.json manifests, implementing async run methods, or packaging modules for installation.
---

# Sweatpants Module Creator

Create automation modules for the Sweatpants engine.

## Module Structure

```
my-module/
├── module.json      # Manifest (required)
├── main.py          # Entry point (required)
└── requirements.txt # Dependencies (optional)
```

## Quick Start

### 1. Create module.json

```json
{
  "id": "my-module",
  "name": "My Module",
  "version": "1.0.0",
  "description": "What this module does",
  "inputs": {
    "url": {
      "type": "string",
      "description": "Target URL",
      "required": true
    },
    "count": {
      "type": "integer",
      "description": "Number of items",
      "default": 10
    }
  },
  "settings": {
    "api_key": {
      "type": "string",
      "description": "API key from environment",
      "env": "MY_API_KEY"
    }
  },
  "capabilities": {
    "browser": false,
    "proxy": true
  }
}
```

### 2. Create main.py

```python
from sweatpants import Module, proxied_request

class MyModule(Module):
    async def run(self, inputs: dict, settings: dict):
        url = inputs["url"]
        count = inputs.get("count", 10)
        
        await self.log(f"Processing {url}")
        
        # Make proxied HTTP request
        response = await proxied_request("GET", url)
        data = response.json()
        
        # Yield results incrementally
        for i, item in enumerate(data[:count]):
            yield {"index": i, "item": item}
            await self.log(f"Processed {i+1}/{count}")
        
        await self.log("Complete!")
```

### 3. Install and test

```bash
sweatpants module install /path/to/my-module
sweatpants run my-module -i url=https://api.example.com
```

## Module SDK

### Core imports

```python
from sweatpants import Module, proxied_request, get_browser
```

### Logging

```python
await self.log("Info message")
await self.log("Debug details", level="debug")
await self.log("Warning!", level="warning")
```

### HTTP requests (proxied)

```python
response = await proxied_request("GET", "https://example.com")
response = await proxied_request("POST", url, json={"key": "value"})
response = await proxied_request("GET", url, headers={"Auth": "token"})
```

### Browser automation

```python
async with get_browser() as browser:
    page = await browser.new_page()
    await page.goto("https://example.com")
    content = await page.content()
    await page.screenshot(path="screenshot.png")
```

### Checkpoints (resume after restart)

```python
# Save progress
await self.save_checkpoint(progress=50, last_id="abc123")

# Load on resume (in run method)
checkpoint = await self.load_checkpoint()
if checkpoint:
    start_from = checkpoint.get("last_id")
```

### Yielding results

```python
# Single result
yield {"data": "value"}

# Multiple results
for item in items:
    yield {"item": item}
```

## Input Types

| Type | JSON Schema | Python Type |
|------|-------------|-------------|
| `string` | `{"type": "string"}` | `str` |
| `integer` | `{"type": "integer"}` | `int` |
| `number` | `{"type": "number"}` | `float` |
| `boolean` | `{"type": "boolean"}` | `bool` |
| `array` | `{"type": "array", "items": {...}}` | `list` |
| `object` | `{"type": "object"}` | `dict` |

## Capabilities

```json
"capabilities": {
  "browser": true,    // Needs Playwright browser
  "proxy": true       // Routes through rotating proxy
}
```

## Best Practices

1. **Yield incrementally** - Don't accumulate all results, yield as you go
2. **Log progress** - Users watch logs for status
3. **Use checkpoints** - For long jobs that might restart
4. **Handle errors gracefully** - Catch and log, don't crash silently
5. **Validate inputs** - Check required fields early

## See Also

- [references/examples.md](references/examples.md) - Real module examples
