import sys
import json
from pathlib import Path
from typing import Optional
import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from .config import ShieldConfig
from .guards.circuit_breaker import AgentAction, DriftCircuitBreaker
from .guards.context_budget import ContextBudgetGate
from .prober.contract_generator import ContractGenerator
from .prober.system_prober import SystemProber
from .tools.schema_linter import ToolSchemaLinter

app = typer.Typer(
    name="tbs",
    help="Token Bleed Shield: Preventive workflow to stop bleeding AI API costs before generation starts.",
    add_completion=False,
)
console = Console(legacy_windows=False)


@app.command()
def probe(
    output: Optional[Path] = typer.Option(
        None, "--output", "-o", help="Target path for generated .agent-env.md contract"
    ),
    json_output: Optional[Path] = typer.Option(
        None, "--json", help="Optional path to output raw JSON snapshot"
    ),
):
    """Probe the local host environment once and generate an immutable agent contract."""
    console.print(Panel.fit("[bold cyan]🛡️ Token Bleed Shield — Pre-flight Prober[/bold cyan]"))
    
    prober = SystemProber()
    with console.status("[bold green]Probing local toolchains and runtimes..."):
        snapshot = prober.capture()

    table = Table(title="Host Environment Snapshot", show_header=True, header_style="bold magenta")
    table.add_column("Component", style="dim", width=22)
    table.add_column("Detected Runtime / Policy")

    table.add_row("Operating System", f"{snapshot.os_name} {snapshot.os_release} ({snapshot.architecture})")
    table.add_row("Primary Shell", snapshot.primary_shell)
    table.add_row("Workspace Root", snapshot.workspace_root)

    if snapshot.python_toolchain:
        tc = snapshot.python_toolchain
        status = f"[green]{tc.name}[/green]"
        if tc.version:
            status += f" ({tc.version})"
        if tc.command_prefix:
            status += f" -> Run via `{tc.command_prefix}`"
        table.add_row("Python Toolchain", status)

    if snapshot.node_toolchain:
        tc = snapshot.node_toolchain
        status = f"[green]{tc.name}[/green]"
        if tc.version:
            status += f" ({tc.version})"
        table.add_row("Node Toolchain", status)

    if snapshot.rust_toolchain:
        table.add_row("Rust Toolchain", f"[green]{snapshot.rust_toolchain.name}[/green]")

    if snapshot.detected_project_files:
        table.add_row("Project Files", ", ".join(snapshot.detected_project_files))

    console.print(table)

    contract_path = ContractGenerator.write_contract(snapshot, output)
    console.print(f"\n[bold green]✔ Successfully locked runtime contract to:[/bold green] [underline]{contract_path}[/underline]")
    console.print("[dim]Inject this contract into your agent's system prompt to stop exploratory tool loops.[/dim]\n")

    if json_output:
        json_output.write_text(snapshot.model_dump_json(indent=2), encoding="utf-8")
        console.print(f"[green]✔ Saved JSON snapshot to:[/green] {json_output}")


@app.command("lint-tools")
def lint_tools(
    input_file: Path = typer.Option(..., "--input", "-i", help="JSON file containing tool definitions"),
    output_file: Optional[Path] = typer.Option(
        None, "--output", "-o", help="Optional path to write minified schema"
    ),
    strip_titles: bool = typer.Option(True, "--strip-titles/--keep-titles", help="Strip JSON schema 'title' fields"),
    max_desc_length: int = typer.Option(140, "--max-desc", help="Max character length for parameter descriptions"),
):
    """Minify tool and MCP schemas to cut 40-70% of static prompt token bloat."""
    console.print(Panel.fit("[bold cyan]🛠️ Tool Schema Minifier & Linter[/bold cyan]"))

    if not input_file.exists():
        console.print(f"[bold red]Error:[/bold red] Input file {input_file} not found.")
        raise typer.Exit(code=1)

    try:
        raw_data = json.loads(input_file.read_text(encoding="utf-8"))
        tools = raw_data if isinstance(raw_data, list) else raw_data.get("tools", [raw_data])
    except Exception as e:
        console.print(f"[bold red]Failed to parse JSON:[/bold red] {e}")
        raise typer.Exit(code=1)

    linter = ToolSchemaLinter()
    linter.config.strip_titles = strip_titles
    linter.config.max_description_length = max_desc_length
    report = linter.lint_tools(tools)

    table = Table(title="Tool Optimization Breakdown", show_header=True, header_style="bold magenta")
    table.add_column("Tool Name", style="bold")
    table.add_column("Original Tokens", justify="right")
    table.add_column("Minified Tokens", justify="right")
    table.add_column("Saved %", justify="right", style="green")

    for t in report.tools:
        table.add_row(t.name, str(t.original_tokens), str(t.minified_tokens), f"{t.savings_percent}%")

    console.print(table)

    summary_panel = (
        f"[bold]Total Tools:[/bold] {report.total_tools}\n"
        f"[bold]Original Weight:[/bold] {report.original_tokens} tokens\n"
        f"[bold]Minified Weight:[/bold] {report.minified_tokens} tokens\n"
        f"[bold green]Saved per API call:[/bold green] {report.saved_tokens_per_call} tokens ({report.savings_percent}% reduction)\n"
        f"[bold cyan]Projected 10-turn savings:[/bold cyan] ~{report.saved_tokens_projected_10_turns:,} tokens saved!"
    )
    console.print(Panel(summary_panel, title="Token Savings Summary", border_style="green"))

    if output_file:
        output_file.write_text(json.dumps(report.minified_schema, indent=2), encoding="utf-8")
        console.print(f"[green]✔ Minified schemas saved to:[/green] {output_file}")


@app.command("gate")
def gate(
    file: Optional[Path] = typer.Option(None, "--file", "-f", help="File to evaluate (prompt or context dump)"),
    max_tokens: int = typer.Option(32000, "--max-tokens", help="Maximum allowable context tokens"),
    warn_threshold: int = typer.Option(24000, "--warn", help="Warning threshold in tokens"),
):
    """Pre-flight check context payload before sending to LLM API."""
    console.print(Panel.fit("[bold cyan]🚪 Context Budget Gate[/bold cyan]"))

    if file and file.exists():
        content = file.read_text(encoding="utf-8")
    else:
        console.print("[dim]No file specified. Reading test content or stdin...[/dim]")
        content = "Example context payload."

    gate_checker = ContextBudgetGate()
    gate_checker.config.max_context_tokens = max_tokens
    gate_checker.config.warn_threshold_tokens = warn_threshold

    assessment = gate_checker.evaluate(content)

    status_color = "green" if assessment.is_safe else "yellow"
    if assessment.should_reject:
        status_color = "red"

    console.print(
        f"Estimated Tokens: [{status_color}]{assessment.estimated_tokens:,}[/{status_color}] / "
        f"{assessment.max_tokens_allowed:,} ({assessment.utilization_percent}%)\n"
    )

    if assessment.warnings:
        for w in assessment.warnings:
            console.print(
                Panel(
                    f"[bold yellow]{w.description}[/bold yellow]\n\n"
                    f"[dim]Impact:[/dim] ~{w.estimated_tokens:,} tokens\n"
                    f"[bold green]Action:[/bold green] {w.recommendation}",
                    title=f"⚠️ {w.category}",
                    border_style="yellow",
                )
            )
    else:
        console.print("[bold green]✔ Context payload is clean and within budget limits.[/bold green]")


@app.command("breaker")
def breaker(
    history_file: Path = typer.Option(..., "--history", "-h", help="JSON or JSONL file with agent action logs"),
):
    """Analyze agent tool history to detect infinite loops and model drift."""
    console.print(Panel.fit("[bold cyan]⚡ Drift & Loop Circuit Breaker[/bold cyan]"))

    if not history_file.exists():
        console.print(f"[bold red]Error:[/bold red] History file {history_file} not found.")
        raise typer.Exit(code=1)

    breaker_engine = DriftCircuitBreaker()
    actions = []

    try:
        content = history_file.read_text(encoding="utf-8").strip()
        if history_file.suffix == ".jsonl":
            for line in content.splitlines():
                if line.strip():
                    actions.append(AgentAction(**json.loads(line)))
        else:
            raw = json.loads(content)
            actions = [AgentAction(**item) for item in (raw if isinstance(raw, list) else [raw])]
    except Exception as e:
        console.print(f"[bold red]Failed to load actions:[/bold red] {e}")
        raise typer.Exit(code=1)

    console.print(f"Loaded {len(actions)} historical agent actions.\n")

    tripped = False
    for idx, act in enumerate(actions, start=1):
        verdict = breaker_engine.record_and_evaluate(act)
        if verdict.tripped:
            tripped = True
            console.print(
                Panel(
                    f"[bold red]🚨 CIRCUIT BREAKER TRIPPED AT STEP {idx}![/bold red]\n\n"
                    f"[bold]Reason:[/bold] {verdict.reason}\n"
                    f"[bold green]Suggested Action:[/bold green] {verdict.suggested_action}",
                    title="Circuit Tripped",
                    border_style="red",
                )
            )
            break

    if not tripped:
        console.print("[bold green]✔ No drift or infinite repetition detected in action history.[/bold green]")


@app.command("init")
def init():
    """Initialize Token Bleed Shield in the current repository."""
    console.print(Panel.fit("[bold cyan]🛡️ Initializing Token Bleed Shield[/bold cyan]"))

    config = ShieldConfig()
    config.save(Path(".tokenbleedshield.yaml"))
    console.print("[green]✔ Created configuration file:[/green] `.tokenbleedshield.yaml`")

    # Run prober
    prober = SystemProber()
    snapshot = prober.capture()
    contract_path = ContractGenerator.write_contract(snapshot)
    console.print(f"[green]✔ Generated pre-flight contract:[/green] `{contract_path}`")
    console.print("\n[bold]You are all set![/bold] Token Bleed Shield is active in this project.")


if __name__ == "__main__":
    app()
