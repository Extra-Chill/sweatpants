# Module Loader

Handles module installation, loading, and management.

## ModuleManifest

Pydantic model for module.json validation.

```python
class ModuleManifest(BaseModel):
    id: str
    name: str
    version: str
    description: str = ""
    entrypoint: str = "main.py"
    inputs: list[ModuleInput] = []
    settings: list[ModuleSetting] = []
    capabilities: list[str] = []
```

## ModuleLoader

### Methods

#### install

```python
async def install(self, source_path: str) -> ModuleManifest
```

Install a module from a local directory.

1. Validates `module.json` exists
2. Copies directory to modules dir
3. Installs `requirements.txt` if present
4. Registers module in database

**Returns:** Parsed module manifest

#### install_from_git

```python
async def install_from_git(
    self,
    repo_url: str,
    module_name: Optional[str] = None,
) -> ModuleManifest
```

Install a module from a git repository.

**Parameters:**
- `repo_url` — Git repository URL (HTTPS, SSH, or git@ format)
- `module_name` — Subdirectory containing the module (for monorepos)

**Process:**
1. Clone repository to temp directory (depth 1)
2. Locate module.json in root or specified subdirectory
3. Call `install()` with the module path

**Raises:**
- `ValueError` — Invalid URL or git operation failed
- `FileNotFoundError` — module.json not found

#### uninstall

```python
async def uninstall(self, module_id: str) -> bool
```

Uninstall a module. Removes files and database entry.

#### get

```python
async def get(self, module_id: str) -> Optional[dict]
```

Get module information from database.

#### list

```python
async def list(self) -> list[dict]
```

List all installed modules.

#### load_class

```python
async def load_class(self, module_id: str) -> Any
```

Dynamically load and return the Module subclass from a module's entrypoint.

**Process:**
1. Check cache for already-loaded modules
2. Load module info from database
3. Import entrypoint file using `importlib`
4. Find first class that subclasses `Module`
5. Cache and return the class

#### discover_modules

```python
async def discover_modules(self) -> int
```

Scan modules directory for unregistered modules and auto-install them.

Useful for manually-placed modules or post-restore scenarios.

**Returns:** Number of newly discovered modules.

#### validate_inputs

```python
def validate_inputs(
    self,
    manifest: ModuleManifest,
    inputs: dict[str, Any],
) -> dict[str, Any]
```

Validate and normalize inputs against manifest.

- Applies default values
- Converts types (number, integer, boolean)
- Raises `ValueError` for missing required inputs

#### sync_modules

```python
async def sync_modules(self) -> dict[str, Any]
```

Sync modules from configured sources in `modules.yaml`.

**Process:**
1. Load `module_sources` from config
2. For each source, clone repo and install specified modules
3. Continue on errors, collect results

**Returns:**
```python
{
    "installed": [...],  # Successfully installed
    "failed": [...],     # Failed with errors
    "skipped": [...]     # Skipped (already up to date)
}
```

## Module Discovery Flow

On daemon startup:

1. `ModuleLoader.discover_modules()` scans modules directory
2. Finds subdirectories with `module.json`
3. Auto-installs any not registered in database
4. Logs discovered modules
