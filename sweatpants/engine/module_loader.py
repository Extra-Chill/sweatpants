"""Module loader for installing and managing automation modules."""

import importlib.util
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, Field

from sweatpants.config import get_settings
from sweatpants.engine.state import StateManager


class ModuleInput(BaseModel):
    """Definition of a module input parameter."""

    id: str
    type: str = "text"
    required: bool = False
    default: Optional[Any] = None
    description: Optional[str] = None


class ModuleSetting(BaseModel):
    """Definition of a module setting."""

    id: str
    type: str = "text"
    default: Optional[Any] = None
    description: Optional[str] = None


class ModuleManifest(BaseModel):
    """Module manifest loaded from module.json."""

    id: str
    name: str
    version: str
    description: str = ""
    entrypoint: str = "main.py"
    inputs: list[ModuleInput] = Field(default_factory=list)
    settings: list[ModuleSetting] = Field(default_factory=list)
    capabilities: list[str] = Field(default_factory=list)


class ModuleLoader:
    """Loads and manages automation modules."""

    def __init__(self) -> None:
        self.settings = get_settings()
        self.state = StateManager()
        self._loaded_modules: dict[str, Any] = {}

    def _get_module_path(self, module_id: str) -> Path:
        """Get the installation path for a module."""
        return self.settings.modules_dir / module_id

    async def install(self, source_path: str) -> ModuleManifest:
        """Install a module from a source directory."""
        source = Path(source_path)
        if not source.exists():
            raise FileNotFoundError(f"Source path does not exist: {source}")

        manifest_path = source / "module.json"
        if not manifest_path.exists():
            raise FileNotFoundError(f"No module.json found in {source}")

        with open(manifest_path) as f:
            manifest_data = json.load(f)

        manifest = ModuleManifest(**manifest_data)

        dest = self._get_module_path(manifest.id)
        # Skip copy if source is already at destination (e.g., module already in modules_dir)
        if source.resolve() == dest.resolve():
            requirements = dest / "requirements.txt"
            if requirements.exists():
                subprocess.run(
                    [
                        sys.executable,
                        "-m",
                        "pip",
                        "install",
                        "-r",
                        str(requirements),
                        "-q",
                    ],
                    check=True,
                    capture_output=True,
                )
            await self.state.save_module(
                module_id=manifest.id,
                name=manifest.name,
                version=manifest.version,
                description=manifest.description,
                entrypoint=manifest.entrypoint,
                inputs=[i.model_dump() for i in manifest.inputs],
                settings=[s.model_dump() for s in manifest.settings],
                capabilities=manifest.capabilities,
                path=str(dest),
            )
            return manifest
        if dest.exists():
            shutil.rmtree(dest)

        shutil.copytree(source, dest)

        requirements = dest / "requirements.txt"
        if requirements.exists():
            subprocess.run(
                [sys.executable, "-m", "pip", "install", "-r", str(requirements), "-q"],
                check=True,
                capture_output=True,
            )

        await self.state.save_module(
            module_id=manifest.id,
            name=manifest.name,
            version=manifest.version,
            description=manifest.description,
            entrypoint=manifest.entrypoint,
            inputs=[i.model_dump() for i in manifest.inputs],
            settings=[s.model_dump() for s in manifest.settings],
            capabilities=manifest.capabilities,
            path=str(dest),
        )

        return manifest

    async def install_from_git(
        self, repo_url: str, module_name: Optional[str] = None
    ) -> ModuleManifest:
        """Install a module from a git repository.

        Args:
            repo_url: Git repository URL to clone.
            module_name: Optional subdirectory within the repo containing the module.
                        If not provided, uses the repo root.

        Returns:
            The installed module manifest.

        Raises:
            ValueError: If the repo URL is invalid or git operations fail.
            FileNotFoundError: If module.json is not found.
        """
        # Validate URL format (basic check for git-compatible URLs)
        if not re.match(r"^(https?://|git@|ssh://)", repo_url):
            raise ValueError(f"Invalid git repository URL: {repo_url}")

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            clone_path = temp_path / "repo"

            # Clone the repository
            try:
                result = subprocess.run(
                    ["git", "clone", "--depth", "1", repo_url, str(clone_path)],
                    capture_output=True,
                    text=True,
                    check=True,
                    timeout=120,
                )
            except subprocess.CalledProcessError as e:
                raise ValueError(f"Failed to clone repository: {e.stderr.strip()}")
            except subprocess.TimeoutExpired:
                raise ValueError("Git clone timed out after 120 seconds")
            except FileNotFoundError:
                raise ValueError("Git is not installed or not in PATH")

            # Determine the module source path
            if module_name:
                source_path = clone_path / module_name
                if not source_path.exists():
                    raise FileNotFoundError(
                        f"Module subdirectory not found: {module_name}"
                    )
            else:
                source_path = clone_path

            # Verify module.json exists
            manifest_path = source_path / "module.json"
            if not manifest_path.exists():
                if module_name:
                    raise FileNotFoundError(
                        f"No module.json found in {module_name}. "
                        "Ensure the subdirectory contains a valid module."
                    )
                else:
                    raise FileNotFoundError(
                        "No module.json found in repository root. "
                        "If the module is in a subdirectory, specify the module_name."
                    )

            # Use existing install method to complete the installation
            return await self.install(str(source_path))

    async def uninstall(self, module_id: str) -> bool:
        """Uninstall a module."""
        module = await self.state.get_module(module_id)
        if not module:
            return False

        module_path = self._get_module_path(module_id)
        if module_path.exists():
            shutil.rmtree(module_path)

        if module_id in self._loaded_modules:
            del self._loaded_modules[module_id]

        await self.state.delete_module(module_id)
        return True

    async def get(self, module_id: str) -> Optional[dict]:
        """Get module information."""
        return await self.state.get_module(module_id)

    async def list(self) -> list[dict]:
        """List all installed modules."""
        return await self.state.list_modules()

    async def load_class(self, module_id: str) -> Any:
        """Load and return the module class."""
        if module_id in self._loaded_modules:
            return self._loaded_modules[module_id]

        module_info = await self.state.get_module(module_id)
        if not module_info:
            raise ValueError(f"Module not found: {module_id}")

        module_path = Path(module_info["path"])
        entrypoint = module_path / module_info["entrypoint"]

        if not entrypoint.exists():
            raise FileNotFoundError(f"Entrypoint not found: {entrypoint}")

        spec = importlib.util.spec_from_file_location(module_id, entrypoint)
        if spec is None or spec.loader is None:
            raise ImportError(f"Cannot load module: {module_id}")

        loaded_module = importlib.util.module_from_spec(spec)
        sys.modules[module_id] = loaded_module
        spec.loader.exec_module(loaded_module)

        from sweatpants.sdk.module import Module

        module_class = None
        for attr_name in dir(loaded_module):
            attr = getattr(loaded_module, attr_name)
            if (
                isinstance(attr, type)
                and issubclass(attr, Module)
                and attr is not Module
            ):
                module_class = attr
                break

        if module_class is None:
            raise ImportError(f"No Module subclass found in {module_id}")

        self._loaded_modules[module_id] = module_class
        return module_class

    async def reload_all(self) -> dict:
        """Reload all modules from disk.

        Clears the in-memory module cache and Python's sys.modules cache
        for all loaded module entrypoints, then re-discovers modules from
        the modules directory.

        Returns summary of reloaded modules.
        """
        # Clear Python's import cache for loaded modules
        modules_to_remove = [
            key for key in sys.modules
            if key.startswith("sweatpants_module_") or str(self.settings.modules_dir) in str(getattr(sys.modules[key], '__file__', '') or '')
        ]
        for key in modules_to_remove:
            del sys.modules[key]

        # Clear instance cache
        self._loaded_modules.clear()

        # Re-discover all modules
        modules = await self.list()

        return {
            "status": "reloaded",
            "cleared_cache_entries": len(modules_to_remove),
            "modules_found": len(modules),
            "modules": modules,
        }

    async def discover_modules(self) -> int:
        """Discover and auto-install modules from the modules directory.

        Scans SWEATPANTS_MODULES_DIR for subdirectories containing module.json
        that aren't already registered in the database.

        Returns:
            Number of newly discovered and installed modules.
        """
        modules_dir = self.settings.modules_dir
        if not modules_dir.exists():
            return 0

        discovered = 0
        for subdir in modules_dir.iterdir():
            if not subdir.is_dir():
                continue

            manifest_path = subdir / "module.json"
            if not manifest_path.exists():
                continue

            try:
                with open(manifest_path) as f:
                    manifest_data = json.load(f)

                module_id = manifest_data.get("id")
                if not module_id:
                    print(f"Warning: module.json in {subdir.name} has no id, skipping")
                    continue

                existing = await self.state.get_module(module_id)
                if existing:
                    continue

                print(f"Discovered unregistered module: {module_id}")
                await self.install(str(subdir))
                print(f"Auto-installed module: {module_id}")
                discovered += 1

            except Exception as e:
                print(f"Error discovering module in {subdir.name}: {e}")
                continue

        return discovered

    def validate_inputs(self, manifest: ModuleManifest, inputs: dict[str, Any]) -> dict[str, Any]:
        """Validate and normalize inputs against manifest."""
        validated = {}

        for input_def in manifest.inputs:
            value = inputs.get(input_def.id)

            if value is None and input_def.default is not None:
                value = input_def.default

            if value is None and input_def.required:
                raise ValueError(f"Required input missing: {input_def.id}")

            if value is not None:
                if input_def.type == "number":
                    value = float(value)
                elif input_def.type == "integer":
                    value = int(value)
                elif input_def.type == "boolean":
                    value = str(value).lower() in ("true", "1", "yes")

            validated[input_def.id] = value

        return validated

    async def sync_modules(self) -> dict[str, Any]:
        """Sync modules from configured module sources.

        Reads module_sources from modules.yaml config, clones/pulls each repo,
        and installs the specified modules. Handles errors gracefully by skipping
        failed repos and continuing with others.

        Returns:
            Summary dict with installed, failed, and skipped modules.
        """
        modules_config = self.settings.load_modules_config()

        if not modules_config or not modules_config.module_sources:
            raise ValueError("No module_sources configured in modules.yaml")

        installed = []
        failed = []
        skipped = []

        for source in modules_config.module_sources:
            repo_url = source.repo
            modules_to_install = source.modules

            # If no specific modules listed, try to install from repo root
            if not modules_to_install:
                modules_to_install = [None]

            for module_name in modules_to_install:
                module_display = module_name if module_name else "(root)"

                try:
                    manifest = await self.install_from_git(
                        repo_url=repo_url,
                        module_name=module_name,
                    )
                    installed.append({
                        "id": manifest.id,
                        "name": manifest.name,
                        "version": manifest.version,
                        "source": repo_url,
                        "module_path": module_name,
                    })
                    print(f"Installed: {manifest.id} from {repo_url}/{module_display}")

                except FileNotFoundError as e:
                    failed.append({
                        "module": module_display,
                        "source": repo_url,
                        "error": str(e),
                    })
                    print(f"Failed: {module_display} from {repo_url} - {e}")

                except ValueError as e:
                    failed.append({
                        "module": module_display,
                        "source": repo_url,
                        "error": str(e),
                    })
                    print(f"Failed: {module_display} from {repo_url} - {e}")

                except Exception as e:
                    failed.append({
                        "module": module_display,
                        "source": repo_url,
                        "error": str(e),
                    })
                    print(f"Failed: {module_display} from {repo_url} - {e}")

        return {
            "installed": installed,
            "failed": failed,
            "skipped": skipped,
        }
