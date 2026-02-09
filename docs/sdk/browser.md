# Browser Pool

Playwright browser pool with automatic proxy integration and lifecycle management.

## Import

```python
from sweatpants import get_browser
```

## get_browser

```python
@asynccontextmanager
async def get_browser(
    geo: Optional[str] = None,
    use_proxy: bool = True,
) -> AsyncIterator[BrowserContext]
```

Get a browser context from the pool.

**Parameters:**
- `geo` — Geo-target location (city/country/state). Uses default pool if `None`.
- `use_proxy` — Whether to route through proxy. Defaults to `True`. Set to `False` for sites that block known proxy IPs (e.g., Google).

**Returns:** Playwright `BrowserContext` as async context manager

## Usage Examples

### Basic Browser Automation

```python
from sweatpants import get_browser

async with get_browser() as browser:
    page = await browser.new_page()
    await page.goto("https://example.com")
    
    title = await page.title()
    content = await page.content()
```

### Geo-Targeted Browsing

```python
async with get_browser(geo="newyork") as browser:
    page = await browser.new_page()
    await page.goto("https://example.com")
    # Request originates from NYC IP
```

### Direct Connection (No Proxy)

For sites that block proxy IPs:

```python
async with get_browser(use_proxy=False) as browser:
    page = await browser.new_page()
    await page.goto("https://google.com")
```

### Full Module Example

```python
from sweatpants import Module, get_browser

class ScraperModule(Module):
    async def run(self, inputs, settings):
        url = inputs["url"]
        
        async with get_browser() as browser:
            page = await browser.new_page()
            await page.goto(url)
            
            # Wait for content
            await page.wait_for_selector(".content")
            
            # Extract data
            items = await page.query_selector_all(".item")
            for item in items:
                text = await item.text_content()
                yield {"text": text}
```

## Pool Configuration

Environment variables:

- `SWEATPANTS_BROWSER_POOL_SIZE` — Number of browser instances (default: `3`)
- `SWEATPANTS_BROWSER_RESTART_HOURS` — Browser restart interval to prevent memory leaks (default: `4`)

## Browser Context

Each acquired context has:
- Viewport: 1920x1080
- User-Agent: Chrome 120 on Windows 10
- Proxy configuration (if enabled)

Contexts are automatically closed when exiting the context manager.

## Pool Lifecycle

The pool:
1. Initializes lazily on first `get_browser()` call
2. Maintains configured number of browser instances
3. Automatically restarts browsers after configured hours
4. Routes all browser traffic through proxy (unless disabled)
5. Uses unique session IDs per browser for sticky IPs

## shutdown_pool

```python
async def shutdown_pool() -> None
```

Shut down all browser pools. Called automatically on daemon shutdown.
