# Module Manifest

The `module.json` file defines a module's metadata, inputs, settings, and capabilities.

## Schema

```json
{
  "id": "string (required)",
  "name": "string (required)",
  "version": "string (required)",
  "description": "string",
  "entrypoint": "string (default: main.py)",
  "inputs": [],
  "settings": [],
  "capabilities": []
}
```

## Fields

### id

Unique identifier for the module. Used in CLI commands and API calls.

```json
"id": "image-generator"
```

### name

Human-readable display name.

```json
"name": "AI Image Generator"
```

### version

Semantic version string.

```json
"version": "1.2.0"
```

### description

Brief description of what the module does.

```json
"description": "Generate images using AI models"
```

### entrypoint

Python file containing the Module subclass. Default: `main.py`

```json
"entrypoint": "generator.py"
```

### inputs

Array of input parameter definitions. These are provided per-job.

```json
"inputs": [
  {
    "id": "prompt",
    "type": "text",
    "required": true,
    "description": "Image generation prompt"
  },
  {
    "id": "count",
    "type": "integer",
    "required": false,
    "default": 1,
    "description": "Number of images to generate"
  }
]
```

**Input fields:**
- `id` — Parameter identifier
- `type` — Data type: `text`, `number`, `integer`, `boolean`
- `required` — Whether the input must be provided
- `default` — Default value if not provided
- `description` — Help text

### settings

Array of module setting definitions. These are configured once per module installation.

```json
"settings": [
  {
    "id": "api_key",
    "type": "text",
    "description": "API key for the image service"
  }
]
```

**Setting fields:**
- `id` — Setting identifier
- `type` — Data type: `text`, `number`, `integer`, `boolean`
- `default` — Default value
- `description` — Help text

### capabilities

Array of capabilities the module requires.

```json
"capabilities": ["proxy", "browser"]
```

**Available capabilities:**
- `proxy` — HTTP requests through rotating proxy
- `browser` — Playwright browser automation

## Complete Example

```json
{
  "id": "web-scraper",
  "name": "Web Scraper",
  "version": "2.0.0",
  "description": "Scrape content from websites with JavaScript rendering",
  "entrypoint": "main.py",
  "inputs": [
    {
      "id": "url",
      "type": "text",
      "required": true,
      "description": "URL to scrape"
    },
    {
      "id": "selector",
      "type": "text",
      "required": false,
      "default": "body",
      "description": "CSS selector for content extraction"
    },
    {
      "id": "max_pages",
      "type": "integer",
      "required": false,
      "default": 10,
      "description": "Maximum pages to scrape"
    }
  ],
  "settings": [
    {
      "id": "user_agent",
      "type": "text",
      "default": "Mozilla/5.0...",
      "description": "Custom user agent string"
    }
  ],
  "capabilities": ["proxy", "browser"]
}
```

## File Structure

A complete module directory:

```
my-module/
├── module.json          # Manifest (required)
├── main.py              # Entrypoint with Module subclass (required)
├── requirements.txt     # Python dependencies (optional)
└── helpers/             # Additional Python modules (optional)
    └── utils.py
```
