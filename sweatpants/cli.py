"""Command-line interface for Sweatpants."""

import asyncio
import json
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from sweatpants.config import get_settings

app = typer.Typer(
    name="sweatpants",
    help="Server-side automation engine for long-running tasks.",
    no_args_is_help=True,
)
module_app = typer.Typer(help="Module management commands.")
app.add_typer(module_app, name="module")

console = Console()


@app.command()
def config() -> None:
    """Show effective configuration values."""
    settings = get_settings()

    table = Table(title="Sweatpants Config")
    table.add_column("Key", style="cyan")
    table.add_column("Value")

    table.add_row("data_dir", str(settings.data_dir))
    table.add_row("modules_dir", str(settings.modules_dir))
    table.add_row("exports_dir", str(settings.exports_dir) if settings.exports_dir else "")
    table.add_row("db_path", str(settings.db_path))
    table.add_row("modules_config_path", str(settings.modules_config_path))
    table.add_row("api_host", settings.api_host)
    table.add_row("api_port", str(settings.api_port))
    table.add_row("api_auth_token", "(set)" if settings.api_auth_token else "(unset)")
    table.add_row("log_level", settings.log_level)

    console.print(table)


@app.command()
def serve(
    host: str = typer.Option(None, "--host", "-h", help="API host to bind to"),
    port: int = typer.Option(None, "--port", "-p", help="API port to bind to"),
) -> None:
    """Start the Sweatpants daemon."""
    import uvicorn

    from sweatpants.api.main import create_app
    from sweatpants.engine.state import init_database

    settings = get_settings()
    settings.ensure_directories()

    api_host = host or settings.api_host
    api_port = port or settings.api_port

    asyncio.run(init_database())

    console.print(f"[green]Starting Sweatpants on {api_host}:{api_port}[/green]")

    app_instance = create_app()
    uvicorn.run(app_instance, host=api_host, port=api_port, log_level=settings.log_level.lower())


@app.command()
def status() -> None:
    """Show engine status and running jobs."""
    import httpx

    settings = get_settings()
    url = f"http://{settings.api_host}:{settings.api_port}"

    try:
        response = httpx.get(f"{url}/status", timeout=5.0)
        response.raise_for_status()
        data = response.json()

        console.print(f"\n[bold]Sweatpants Engine[/bold]")
        console.print(f"Status: [green]{data['status']}[/green]")
        console.print(f"Uptime: {data['uptime']}")
        console.print(f"Modules: {data['module_count']}")

        if data["jobs"]:
            table = Table(title="Running Jobs")
            table.add_column("ID", style="cyan")
            table.add_column("Module")
            table.add_column("Status")
            table.add_column("Started")

            for job in data["jobs"]:
                table.add_row(
                    job["id"][:8],
                    job["module"],
                    job["status"],
                    job["started_at"],
                )
            console.print(table)
        else:
            console.print("\nNo running jobs.")

    except httpx.ConnectError:
        console.print("[red]Error: Cannot connect to Sweatpants daemon.[/red]")
        console.print("Is the daemon running? Start with: sweatpants serve")
        raise typer.Exit(1)


@app.command()
def run(
    module_id: str = typer.Argument(..., help="Module ID to run"),
    inputs: Optional[list[str]] = typer.Option(
        None, "--input", "-i", help="Input values as key=value pairs"
    ),
    duration: Optional[str] = typer.Option(
        None, "--duration", "-d", help="Auto-stop after duration (e.g., 30m, 2h, 24h, 7d)"
    ),
) -> None:
    """Start a job with the specified module."""
    import httpx

    settings = get_settings()
    url = f"http://{settings.api_host}:{settings.api_port}"

    input_data = {}
    if inputs:
        for item in inputs:
            if "=" in item:
                key, value = item.split("=", 1)
                input_data[key] = value

    request_body = {"module_id": module_id, "inputs": input_data}
    if duration:
        request_body["max_duration"] = duration

    try:
        response = httpx.post(
            f"{url}/jobs",
            json=request_body,
            timeout=10.0,
        )
        response.raise_for_status()
        data = response.json()

        console.print(f"[green]Job started:[/green] {data['id']}")
        console.print(f"Module: {module_id}")
        console.print(f"Status: {data['status']}")
        if duration:
            console.print(f"Duration limit: {duration}")
        console.print(f"\nView logs: sweatpants logs {data['id'][:8]}")

    except httpx.ConnectError:
        console.print("[red]Error: Cannot connect to Sweatpants daemon.[/red]")
        raise typer.Exit(1)
    except httpx.HTTPStatusError as e:
        console.print(f"[red]Error: {e.response.json().get('detail', str(e))}[/red]")
        raise typer.Exit(1)


@app.command()
def stop(job_id: str = typer.Argument(..., help="Job ID to stop")) -> None:
    """Stop a running job."""
    import httpx

    settings = get_settings()
    url = f"http://{settings.api_host}:{settings.api_port}"

    try:
        response = httpx.post(f"{url}/jobs/{job_id}/stop", timeout=10.0)
        response.raise_for_status()

        console.print(f"[green]Job {job_id[:8]} stopped.[/green]")

    except httpx.ConnectError:
        console.print("[red]Error: Cannot connect to Sweatpants daemon.[/red]")
        raise typer.Exit(1)
    except httpx.HTTPStatusError as e:
        console.print(f"[red]Error: {e.response.json().get('detail', str(e))}[/red]")
        raise typer.Exit(1)


@app.command()
def result(
    job_id: str = typer.Argument(..., help="Job ID to get results"),
    raw: bool = typer.Option(False, "--raw", "-r", help="Output raw JSON"),
) -> None:
    """Get results/output for a job."""
    import httpx

    settings = get_settings()
    url = f"http://{settings.api_host}:{settings.api_port}"

    try:
        response = httpx.get(f"{url}/jobs/{job_id}/results", timeout=10.0)
        response.raise_for_status()
        data = response.json()

        if raw:
            console.print(json.dumps(data, indent=2))
            return

        results = data.get("results", [])
        total = data.get("total", 0)

        if not results:
            console.print("[dim]No results for this job.[/dim]")
            return

        console.print(f"[bold]Results ({total} total):[/bold]\n")
        for i, result_item in enumerate(results, 1):
            console.print(f"[cyan]--- Result {i} ---[/cyan]")
            result_data = result_item.get("data", {})
            if isinstance(result_data, dict):
                console.print(json.dumps(result_data, indent=2))
            else:
                console.print(str(result_data))
            console.print()

    except httpx.ConnectError:
        console.print("[red]Error: Cannot connect to Sweatpants daemon.[/red]")
        raise typer.Exit(1)
    except httpx.HTTPStatusError as e:
        console.print(f"[red]Error: {e.response.json().get('detail', str(e))}[/red]")
        raise typer.Exit(1)


@app.command()
def logs(
    job_id: str = typer.Argument(..., help="Job ID to view logs"),
    follow: bool = typer.Option(False, "--follow", "-f", help="Follow log output"),
) -> None:
    """View logs for a job."""
    import httpx

    settings = get_settings()
    url = f"http://{settings.api_host}:{settings.api_port}"

    try:
        response = httpx.get(f"{url}/jobs/{job_id}/logs", timeout=10.0)
        response.raise_for_status()
        data = response.json()

        for entry in data["logs"]:
            timestamp = entry["timestamp"]
            level = entry["level"]
            message = entry["message"]

            color = {"INFO": "white", "WARNING": "yellow", "ERROR": "red"}.get(level, "white")
            console.print(f"[dim]{timestamp}[/dim] [{color}]{level}[/{color}] {message}")

        if follow:
            console.print("[dim]Following logs... (Ctrl+C to exit)[/dim]")
            import websockets.sync.client as ws_client

            ws_url = f"ws://{settings.api_host}:{settings.api_port}/jobs/{job_id}/logs/stream"
            with ws_client.connect(ws_url) as websocket:
                for message in websocket:
                    entry = json.loads(message)
                    timestamp = entry["timestamp"]
                    level = entry["level"]
                    msg = entry["message"]
                    color = {"INFO": "white", "WARNING": "yellow", "ERROR": "red"}.get(
                        level, "white"
                    )
                    console.print(f"[dim]{timestamp}[/dim] [{color}]{level}[/{color}] {msg}")

    except httpx.ConnectError:
        console.print("[red]Error: Cannot connect to Sweatpants daemon.[/red]")
        raise typer.Exit(1)


@module_app.command("list")
def module_list() -> None:
    """List installed modules."""
    import httpx

    settings = get_settings()
    url = f"http://{settings.api_host}:{settings.api_port}"

    try:
        response = httpx.get(f"{url}/modules", timeout=10.0)
        response.raise_for_status()
        data = response.json()

        if not data["modules"]:
            console.print("No modules installed.")
            console.print("Install a module with: sweatpants module install <path>")
            return

        table = Table(title="Installed Modules")
        table.add_column("ID", style="cyan")
        table.add_column("Name")
        table.add_column("Version")
        table.add_column("Capabilities")

        for module in data["modules"]:
            table.add_row(
                module["id"],
                module["name"],
                module["version"],
                ", ".join(module.get("capabilities", [])),
            )
        console.print(table)

    except httpx.ConnectError:
        console.print("[red]Error: Cannot connect to Sweatpants daemon.[/red]")
        raise typer.Exit(1)


@module_app.command("install")
def module_install(path: Path = typer.Argument(..., help="Path to module directory")) -> None:
    """Install a module from a directory."""
    import httpx

    if not path.exists():
        console.print(f"[red]Error: Path does not exist: {path}[/red]")
        raise typer.Exit(1)

    module_json = path / "module.json"
    if not module_json.exists():
        console.print(f"[red]Error: No module.json found in {path}[/red]")
        raise typer.Exit(1)

    with open(module_json) as f:
        module_data = json.load(f)

    settings = get_settings()
    url = f"http://{settings.api_host}:{settings.api_port}"

    try:
        response = httpx.post(
            f"{url}/modules/install",
            json={"source_path": str(path.resolve())},
            timeout=60.0,
        )
        response.raise_for_status()

        console.print(f"[green]Module installed:[/green] {module_data['id']}")
        console.print(f"Name: {module_data['name']}")
        console.print(f"Version: {module_data['version']}")

    except httpx.ConnectError:
        console.print("[red]Error: Cannot connect to Sweatpants daemon.[/red]")
        raise typer.Exit(1)
    except httpx.HTTPStatusError as e:
        console.print(f"[red]Error: {e.response.json().get('detail', str(e))}[/red]")
        raise typer.Exit(1)


@module_app.command("uninstall")
def module_uninstall(module_id: str = typer.Argument(..., help="Module ID to uninstall")) -> None:
    """Uninstall a module."""
    import httpx

    settings = get_settings()
    url = f"http://{settings.api_host}:{settings.api_port}"

    try:
        response = httpx.delete(f"{url}/modules/{module_id}", timeout=10.0)
        response.raise_for_status()

        console.print(f"[green]Module uninstalled:[/green] {module_id}")

    except httpx.ConnectError:
        console.print("[red]Error: Cannot connect to Sweatpants daemon.[/red]")
        raise typer.Exit(1)
    except httpx.HTTPStatusError as e:
        console.print(f"[red]Error: {e.response.json().get('detail', str(e))}[/red]")
        raise typer.Exit(1)


@module_app.command("install-git")
def module_install_git(
    repo_url: str = typer.Argument(..., help="Git repository URL to install from"),
    module_name: Optional[str] = typer.Argument(
        None, help="Module subdirectory within the repo (optional)"
    ),
) -> None:
    """Install a module from a git repository."""
    import httpx

    settings = get_settings()
    url = f"http://{settings.api_host}:{settings.api_port}"

    console.print(f"[dim]Cloning from {repo_url}...[/dim]")

    request_body = {"repo_url": repo_url}
    if module_name:
        request_body["module_name"] = module_name

    try:
        response = httpx.post(
            f"{url}/modules/install-git",
            json=request_body,
            timeout=180.0,  # Git clone can take a while
        )
        response.raise_for_status()
        data = response.json()

        console.print(f"[green]Module installed:[/green] {data['id']}")
        console.print(f"Name: {data['name']}")
        console.print(f"Version: {data['version']}")

    except httpx.ConnectError:
        console.print("[red]Error: Cannot connect to Sweatpants daemon.[/red]")
        raise typer.Exit(1)
    except httpx.HTTPStatusError as e:
        console.print(f"[red]Error: {e.response.json().get('detail', str(e))}[/red]")
        raise typer.Exit(1)


@module_app.command("sync")
def module_sync() -> None:
    """Sync modules from configured module sources.

    Reads module_sources from modules.yaml and installs/updates modules.
    Configure sources in SWEATPANTS_MODULES_CONFIG_PATH (default: /var/lib/sweatpants/modules.yaml).

    Example modules.yaml:
        module_sources:
          - repo: https://github.com/Sarai-Chinwag/sweatpants-modules
            modules: [diagram-generator, chart-generator]
    """
    import httpx

    settings = get_settings()
    url = f"http://{settings.api_host}:{settings.api_port}"

    console.print(f"[dim]Syncing modules from {settings.modules_config_path}...[/dim]")

    try:
        response = httpx.post(
            f"{url}/modules/sync",
            timeout=300.0,  # Multiple git clones can take a while
        )
        response.raise_for_status()
        data = response.json()

        installed = data.get("installed", [])
        failed = data.get("failed", [])

        if installed:
            table = Table(title="Installed Modules")
            table.add_column("ID", style="cyan")
            table.add_column("Name")
            table.add_column("Version")
            table.add_column("Source")

            for module in installed:
                table.add_row(
                    module["id"],
                    module["name"],
                    module["version"],
                    module["source"],
                )
            console.print(table)
        else:
            console.print("[dim]No modules were installed.[/dim]")

        if failed:
            console.print("\n[red]Failed:[/red]")
            for f in failed:
                console.print(f"  - {f['module']} from {f['source']}: {f['error']}")

        console.print(f"\n[green]Sync complete:[/green] {len(installed)} installed, {len(failed)} failed")

    except httpx.ConnectError:
        console.print("[red]Error: Cannot connect to Sweatpants daemon.[/red]")
        raise typer.Exit(1)
    except httpx.HTTPStatusError as e:
        console.print(f"[red]Error: {e.response.json().get('detail', str(e))}[/red]")
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
