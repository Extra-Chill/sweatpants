# Proxy Client

HTTP client with rotating proxy support.

## Import

```python
from sweatpants import proxied_request
```

## proxied_request

```python
async def proxied_request(
    method: str,
    url: str,
    *,
    headers: Optional[dict[str, str]] = None,
    params: Optional[dict[str, Any]] = None,
    data: Optional[dict[str, Any]] = None,
    json: Optional[dict[str, Any]] = None,
    timeout: Optional[float] = None,
    browser_mode: bool = False,
    session_id: Optional[str] = None,
) -> httpx.Response
```

Make HTTP request through the rotating proxy.

**Parameters:**
- `method` — HTTP method (`GET`, `POST`, etc.)
- `url` — Target URL
- `headers` — Request headers
- `params` — Query parameters
- `data` — Form data
- `json` — JSON body
- `timeout` — Request timeout in seconds
- `browser_mode` — Add realistic browser headers (User-Agent, Accept, etc.)
- `session_id` — Sticky session ID for consistent IP across requests. `None` = new IP each request.

**Returns:** `httpx.Response`

## Usage Examples

### Basic Request

```python
from sweatpants import proxied_request

response = await proxied_request("GET", "https://api.example.com/data")
data = response.json()
```

### Browser Mode

Adds realistic browser headers to avoid detection:

```python
response = await proxied_request(
    "GET",
    "https://example.com",
    browser_mode=True,
)
```

### Sticky Sessions

Use the same IP for multiple requests:

```python
session = "my-session-123"

# These requests will use the same IP
response1 = await proxied_request("GET", url1, session_id=session)
response2 = await proxied_request("GET", url2, session_id=session)
```

### POST with JSON

```python
response = await proxied_request(
    "POST",
    "https://api.example.com/submit",
    json={"query": "test"},
    headers={"Authorization": "Bearer token"},
    timeout=30.0,
)
```

## Configuration

The proxy URL is configured via environment variables:

- `SWEATPANTS_PROXY_URL` — Full proxy URL: `http://user:pass@host:port`
- `SWEATPANTS_PROXY_ROTATION_URL` — URL pattern for sticky sessions with `{session}` placeholder

**Example:**
```bash
export SWEATPANTS_PROXY_URL="http://user:pass@proxy.example.com:8080"
export SWEATPANTS_PROXY_ROTATION_URL="http://user-session-{session}:pass@proxy.example.com:8080"
```

## Error Handling

Raises `RuntimeError` if proxy URL is not configured:

```python
try:
    response = await proxied_request("GET", url)
except RuntimeError as e:
    print(f"Proxy not configured: {e}")
```
