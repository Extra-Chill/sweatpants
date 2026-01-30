"""Module loader for installing and managing automation modules."""

import importlib.util
import json
import shutil
import subprocess
import sys
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
