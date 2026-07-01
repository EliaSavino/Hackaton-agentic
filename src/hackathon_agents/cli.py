from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path

from hackathon_agents.benchmarks.system import benchmark_system
from hackathon_agents.config import RunMode, load_config
from hackathon_agents.demos.discovery_demo import run_demo
from hackathon_agents.llm.benchmark import benchmark_models
from hackathon_agents.llm.client import CompletionRequest, LLMClient
from hackathon_agents.llm.prompt_terminal import build_prompt_messages, terminal_metadata, trim_history
from hackathon_agents.llm.router import ModelRouter
from hackathon_agents.logging_config import configure_logging
from hackathon_agents.mechanism.graph import run_mechanism_loop, run_mechanism_once
from hackathon_agents.rag import DEFAULT_RAG_DB_PATH, RAGStore
from hackathon_agents.tools.rag_tools import build_rag_context, ingest_rag_documents, search_rag
from hackathon_agents.tools.linker_design import design_adc_linkers
from hackathon_agents.tools.paper_review import review_paper
from hackathon_agents.tools.snellius_vllm import (
    generate_snellius_gateway_job,
    generate_snellius_vllm_job,
    render_snellius_client_env,
)


def _run_prompt_terminal(
    *,
    config_dir: Path,
    run_mode: RunMode | str,
    model_alias: str | None,
    db_path: Path,
    use_rag: bool,
    rag_limit: int,
    max_context_chars: int,
    system_prompt: str,
    temperature: float,
    max_tokens: int,
) -> None:
    configure_logging()
    config = load_config(config_dir=config_dir, run_mode=run_mode)
    client = LLMClient(config)
    store = RAGStore(db_path)
    history: list[dict[str, str]] = []

    print("Prompt terminal. Commands: /exit, /clear, /rag <query>.")
    while True:
        try:
            prompt = input("you> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not prompt:
            continue
        if prompt in {"/exit", "/quit"}:
            break
        if prompt == "/clear":
            history.clear()
            print("history cleared")
            continue
        if prompt.startswith("/rag "):
            query = prompt.removeprefix("/rag ").strip()
            context = store.build_context(query, limit=rag_limit, max_chars=max_context_chars)
            print(context["context"] or "no matching RAG context")
            continue

        rag_context = ""
        rag_result_count = 0
        if use_rag:
            context = store.build_context(prompt, limit=rag_limit, max_chars=max_context_chars)
            rag_context = context["context"]
            rag_result_count = int(context["result_count"])

        messages = build_prompt_messages(
            prompt,
            system_prompt=system_prompt,
            history=trim_history(history),
            rag_context=rag_context,
        )
        result = client.complete(
            CompletionRequest(
                model_alias=model_alias,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                retries=1,
                metadata=terminal_metadata(model_alias, use_rag, rag_result_count),
            )
        )
        if not result.ok:
            print(f"model error: {result.error}")
            continue
        print(f"\nassistant> {result.content}\n")
        history.extend([{"role": "user", "content": prompt}, {"role": "assistant", "content": result.content}])


try:
    import typer

    app = typer.Typer(help="Scientific-discovery multi-agent workbench.")

    @app.command()
    def demo(
        request: str,
        run_mode: RunMode = typer.Option(RunMode.CHEAP, "--run-mode", "-m"),
        config_dir: Path = typer.Option(Path("configs"), "--config-dir"),
        run_root: Path = typer.Option(Path("runs"), "--run-root"),
        max_iterations: int = typer.Option(3, "--max-iterations", min=1, max=20),
        min_valid_candidates: int = typer.Option(10, "--min-valid-candidates", min=1),
        score_threshold: float = typer.Option(0.75, "--score-threshold", min=0.0, max=1.0),
    ) -> None:
        """Run the deterministic discovery demo."""

        state = run_demo(
            request,
            run_mode=run_mode,
            config_dir=config_dir,
            run_root=run_root,
            max_iterations=max_iterations,
            min_valid_candidates=min_valid_candidates,
            score_threshold=score_threshold,
        )
        typer.echo(f"Run directory: {state.run_dir}")
        if state.final_report_path:
            typer.echo(f"Report: {state.final_report_path}")
        if state.metadata.get("latex_report_path"):
            typer.echo(f"LaTeX: {state.metadata['latex_report_path']}")
        if state.metadata.get("memory_markdown_path"):
            typer.echo(f"Memory: {state.metadata['memory_markdown_path']}")
        typer.echo(f"Iterations: {state.iteration}")
        if state.stop_reason:
            typer.echo(f"Stop reason: {state.stop_reason}")
        typer.echo(f"Errors: {len(state.errors)}")

    @app.command("benchmark-models")
    def benchmark_models_command(
        config_dir: Path = typer.Option(Path("configs"), "--config-dir"),
        run_mode: RunMode = typer.Option(RunMode.CHEAP, "--run-mode", "-m"),
        run_root: Path = typer.Option(Path("runs"), "--run-root"),
    ) -> None:
        """Benchmark all configured models and save JSON results."""

        configure_logging()
        config = load_config(config_dir=config_dir, run_mode=run_mode)
        output_path = benchmark_models(config, run_root=run_root)
        typer.echo(f"Benchmark written to {output_path}")

    @app.command("benchmark-system")
    def benchmark_system_command(
        run_root: Path = typer.Option(Path("runs"), "--run-root"),
    ) -> None:
        """Run deterministic end-to-end system benchmarks and save JSON results."""

        configure_logging()
        output_path = benchmark_system(run_root=run_root)
        typer.echo(f"System benchmark written to {output_path}")

    @app.command("design-linkers")
    def design_linkers_command(
        objective: str = typer.Option(
            "Design a next-generation ADC linker with improved stability, tunable release, and broad payload compatibility.",
            "--objective",
            "-o",
        ),
        output_dir: Path | None = typer.Option(None, "--output-dir"),
        payload_class: list[str] = typer.Option(
            ["cytotoxin", "oligonucleotide", "immunomodulator"],
            "--payload-class",
            "-p",
        ),
        trigger: list[str] = typer.Option(
            ["lysosomal protease", "acidic pH", "reducing environment", "tumor enzyme"],
            "--trigger",
            "-t",
        ),
        conjugation_handle: list[str] = typer.Option(
            ["maleimide", "strain-promoted azide"],
            "--conjugation-handle",
            "-c",
        ),
        max_candidates: int = typer.Option(8, "--max-candidates", min=1, max=50),
        reference_corpus: Path | None = typer.Option(None, "--reference-corpus"),
        include_reference_controls: bool = typer.Option(True, "--reference-controls/--no-reference-controls"),
    ) -> None:
        """Design and rank ADC linker concepts with deterministic in-silico proof points."""

        configure_logging()
        result = design_adc_linkers(
            {
                "objective": objective,
                "output_dir": str(output_dir) if output_dir else None,
                "payload_classes": payload_class,
                "desired_triggers": trigger,
                "conjugation_handles": conjugation_handle,
                "max_candidates": max_candidates,
                "reference_corpus_path": str(reference_corpus) if reference_corpus else None,
                "include_reference_controls": include_reference_controls,
            }
        )
        if not result.ok:
            typer.echo(f"Linker design failed: {result.error}")
            raise typer.Exit(code=1)
        top = result.data.get("top_candidate") or {}
        score = ((top.get("scorecard") or {}).get("overall")) if isinstance(top, dict) else None
        typer.echo(f"Run directory: {result.data['output_dir']}")
        typer.echo(f"Candidates: {result.data['candidate_count']}")
        if top:
            typer.echo(f"Top linker: {top.get('name')} ({score:.3f})")
        for artifact in result.artifacts:
            typer.echo(f"Artifact: {artifact}")

    @app.command("review-paper")
    def review_paper_command(
        path: Path = typer.Argument(..., help="Path to a .txt, .md, .pdf, or .docx paper."),
        output: Path | None = typer.Option(None, "--output", "-o"),
        domain: str = typer.Option("chem_bio", "--domain"),
        focus_question: list[str] = typer.Option([], "--focus-question", "-q"),
        review_depth: str = typer.Option("standard", "--review-depth"),
    ) -> None:
        """Create a deterministic structured paper review JSON artifact."""

        configure_logging()
        output_path = output or Path("runs") / f"paper_review_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        result = review_paper(
            {
                "path": str(path),
                "domain": domain,
                "focus_questions": focus_question,
                "review_depth": review_depth,
                "output_path": str(output_path),
            }
        )
        if not result.ok:
            typer.echo(f"Paper review failed: {result.error}")
            raise typer.Exit(code=1)
        review = result.data["review"]
        typer.echo(f"Review: {output_path}")
        typer.echo(f"Recommendation: {review['recommendation']}")
        typer.echo(review["summary"])

    @app.command("rag-ingest")
    def rag_ingest_command(
        path: Path = typer.Argument(..., help="File or directory to index."),
        db_path: Path = typer.Option(DEFAULT_RAG_DB_PATH, "--db-path"),
        extension: list[str] = typer.Option([".txt", ".md", ".markdown", ".pdf", ".docx"], "--extension", "-e"),
        chunk_size: int = typer.Option(700, "--chunk-size", min=50, max=4000),
        chunk_overlap: int = typer.Option(100, "--chunk-overlap", min=0, max=1000),
        max_chars: int = typer.Option(2_000_000, "--max-chars", min=1),
        replace: bool = typer.Option(True, "--replace/--skip-unchanged"),
    ) -> None:
        """Index local documents into the SQLite RAG database."""

        result = ingest_rag_documents(
            {
                "path": str(path),
                "db_path": str(db_path),
                "extensions": extension,
                "chunk_size": chunk_size,
                "chunk_overlap": chunk_overlap,
                "max_chars": max_chars,
                "replace": replace,
            }
        )
        if not result.ok:
            typer.echo(f"RAG ingest failed: {result.error}")
            raise typer.Exit(code=1)
        typer.echo(f"Database: {result.data['db_path']}")
        typer.echo(f"Indexed documents: {result.data['document_count']}")
        typer.echo(f"Indexed chunks: {result.data['chunk_count']}")
        if result.data["skipped"]:
            typer.echo(f"Skipped: {len(result.data['skipped'])}")

    @app.command("rag-search")
    def rag_search_command(
        query: str = typer.Argument(..., help="Search query."),
        db_path: Path = typer.Option(DEFAULT_RAG_DB_PATH, "--db-path"),
        limit: int = typer.Option(5, "--limit", "-n", min=1, max=50),
        context: bool = typer.Option(False, "--context"),
        max_context_chars: int = typer.Option(4_000, "--max-context-chars", min=200),
    ) -> None:
        """Search the local RAG database."""

        if context:
            result = build_rag_context(
                {
                    "query": query,
                    "db_path": str(db_path),
                    "limit": limit,
                    "max_chars": max_context_chars,
                }
            )
            if not result.ok:
                typer.echo(f"RAG search failed: {result.error}")
                raise typer.Exit(code=1)
            typer.echo(result.data["context"] or "No matching RAG context.")
            return

        result = search_rag({"query": query, "db_path": str(db_path), "limit": limit})
        if not result.ok:
            typer.echo(f"RAG search failed: {result.error}")
            raise typer.Exit(code=1)
        for index, record in enumerate(result.data["records"], start=1):
            source = record.get("source_path") or record["title"]
            typer.echo(f"{index}. {record['title']} [{record['score']:.3f}] {source}")
            typer.echo(record["snippet"])

    @app.command("prompt-terminal")
    def prompt_terminal_command(
        config_dir: Path = typer.Option(Path("configs"), "--config-dir"),
        run_mode: RunMode = typer.Option(RunMode.CHEAP, "--run-mode", "-m"),
        model_alias: str | None = typer.Option(None, "--model-alias", "-M"),
        db_path: Path = typer.Option(DEFAULT_RAG_DB_PATH, "--db-path"),
        rag: bool = typer.Option(True, "--rag/--no-rag"),
        rag_limit: int = typer.Option(4, "--rag-limit", min=1, max=20),
        max_context_chars: int = typer.Option(4_000, "--max-context-chars", min=200),
        system_prompt: str = typer.Option(
            "You are a concise scientific discovery assistant. Use retrieved context only when relevant.",
            "--system",
        ),
        temperature: float = typer.Option(0.1, "--temperature", min=0.0, max=2.0),
        max_tokens: int = typer.Option(1200, "--max-tokens", min=1),
    ) -> None:
        """Open an interactive model prompting terminal with optional RAG context."""

        _run_prompt_terminal(
            config_dir=config_dir,
            run_mode=run_mode,
            model_alias=model_alias,
            db_path=db_path,
            use_rag=rag,
            rag_limit=rag_limit,
            max_context_chars=max_context_chars,
            system_prompt=system_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    @app.command("mechanism-loop")
    def mechanism_loop_command(
        objective: str = typer.Option(..., "--objective"),
        rounds: int = typer.Option(3, "--rounds", min=1, max=20),
        mode: str = typer.Option("mock", "--mode"),
        run_root: Path = typer.Option(Path("runs"), "--run-root"),
        allow_real_robot: bool = typer.Option(False, "--allow-real-robot"),
        allow_hpc_submit: bool = typer.Option(False, "--allow-hpc-submit"),
        robot_base_url: str | None = typer.Option(None, "--robot-base-url"),
        robot_api_key: str | None = typer.Option(None, "--robot-api-key"),
        literature_corpus_dir: Path | None = typer.Option(None, "--literature-corpus-dir"),
        dft_structure_file: Path | None = typer.Option(None, "--dft-structure-file"),
    ) -> None:
        """Run the bounded mechanism discovery loop."""

        configure_logging()
        state = run_mechanism_loop(
            objective=objective,
            rounds=rounds,
            mode=mode,  # type: ignore[arg-type]
            run_root=run_root,
            allow_real_robot=allow_real_robot,
            allow_hpc_submit=allow_hpc_submit,
            robot_base_url=robot_base_url,
            robot_api_key=robot_api_key,
            literature_corpus_dir=literature_corpus_dir,
            dft_structure_file=dft_structure_file,
        )
        typer.echo(f"Run directory: {state.run_dir}")
        typer.echo(f"Rounds: {state.round_index}/{state.max_rounds}")
        typer.echo(f"Hypotheses: {len(state.hypotheses)}")
        typer.echo(f"Datasets: {len(state.datasets)}")
        if state.report_docx_path:
            typer.echo(f"Report: {state.report_docx_path}")

    @app.command("mechanism-once")
    def mechanism_once_command(
        data: Path = typer.Option(..., "--data"),
        objective: str = typer.Option(..., "--objective"),
        mode: str = typer.Option("mock", "--mode"),
        run_root: Path = typer.Option(Path("runs"), "--run-root"),
        literature_corpus_dir: Path | None = typer.Option(None, "--literature-corpus-dir"),
        dft_structure_file: Path | None = typer.Option(None, "--dft-structure-file"),
    ) -> None:
        """Run one mechanism analysis pass on existing kinetic data."""

        configure_logging()
        state = run_mechanism_once(
            objective=objective,
            data_path=data,
            mode=mode,  # type: ignore[arg-type]
            run_root=run_root,
            literature_corpus_dir=literature_corpus_dir,
            dft_structure_file=dft_structure_file,
        )
        typer.echo(f"Run directory: {state.run_dir}")
        if state.rankings:
            typer.echo(f"Top hypothesis: {state.rankings[0].title} ({state.rankings[0].score:.3f})")
        if state.report_docx_path:
            typer.echo(f"Report: {state.report_docx_path}")

    @app.command("check-models")
    def check_models(
        config_dir: Path = typer.Option(Path("configs"), "--config-dir"),
        run_mode: RunMode = typer.Option(RunMode.CHEAP, "--run-mode", "-m"),
    ) -> None:
        """Check local and hosted model availability from config."""

        configure_logging()
        config = load_config(config_dir=config_dir, run_mode=run_mode)
        router = ModelRouter(config)
        for alias, availability in router.check_model_availability().items():
            status = "available" if availability.available else "unavailable"
            typer.echo(f"{alias}: {status} ({availability.reason})")

    @app.command("snellius-vllm-script")
    def snellius_vllm_script_command(
        model_checkpoint: str = typer.Option(..., "--model-checkpoint"),
        output_dir: Path = typer.Option(Path("runs/snellius_vllm"), "--output-dir"),
        container_path: str = typer.Option("/projects/2/managed_datasets/containers/vllm/vllm.sif", "--container-path"),
        partition: str = typer.Option("gpu_a100", "--partition"),
        gpus_per_node: int = typer.Option(1, "--gpus-per-node", min=1, max=4),
        time_limit: str = typer.Option("02:00:00", "--time-limit"),
        port: int = typer.Option(8000, "--port", min=1024, max=65535),
        project_space: str = typer.Option("", "--project-space"),
    ) -> None:
        """Generate a Snellius SLURM job for serving vLLM."""

        result = generate_snellius_vllm_job(
            {
                "output_dir": str(output_dir),
                "model_checkpoint": model_checkpoint,
                "container_path": container_path,
                "partition": partition,
                "gpus_per_node": gpus_per_node,
                "time_limit": time_limit,
                "port": port,
                "project_space": project_space,
            }
        )
        typer.echo(f"Script: {result.data['script_path']}")
        typer.echo(f"Base URL after tunneling: {result.data['base_url']}")

    @app.command("snellius-gateway-script")
    def snellius_gateway_script_command(
        model_checkpoint: str = typer.Option(..., "--model-checkpoint"),
        output_dir: Path = typer.Option(Path("runs/snellius_gateway"), "--output-dir"),
        served_model_name: str = typer.Option("claude-snellius-local", "--served-model-name"),
        local_model_alias: str = typer.Option("claude-snellius-local", "--local-model-alias"),
        hosted_model_alias: str = typer.Option("claude-snellius-hosted", "--hosted-model-alias"),
        hosted_litellm_model: str = typer.Option(
            "anthropic/claude-sonnet-4-20250514",
            "--hosted-litellm-model",
        ),
        container_path: str = typer.Option("/projects/2/managed_datasets/containers/vllm/vllm.sif", "--container-path"),
        partition: str = typer.Option("gpu_a100", "--partition"),
        gpus_per_node: int = typer.Option(1, "--gpus-per-node", min=1, max=4),
        time_limit: str = typer.Option("02:00:00", "--time-limit"),
        vllm_port: int = typer.Option(8000, "--vllm-port", min=1024, max=65535),
        gateway_port: int = typer.Option(4000, "--gateway-port", min=1024, max=65535),
        project_space: str = typer.Option("", "--project-space"),
        tool_call_parser: str = typer.Option("openai", "--tool-call-parser"),
        litellm_command: str = typer.Option("litellm", "--litellm-command"),
        env_file: str = typer.Option(".env", "--env-file"),
    ) -> None:
        """Generate a Snellius SLURM job for a Claude Code LiteLLM gateway."""

        result = generate_snellius_gateway_job(
            {
                "output_dir": str(output_dir),
                "model_checkpoint": model_checkpoint,
                "served_model_name": served_model_name,
                "local_model_alias": local_model_alias,
                "hosted_model_alias": hosted_model_alias,
                "hosted_litellm_model": hosted_litellm_model,
                "container_path": container_path,
                "partition": partition,
                "gpus_per_node": gpus_per_node,
                "time_limit": time_limit,
                "vllm_port": vllm_port,
                "gateway_port": gateway_port,
                "local_client_port": gateway_port,
                "project_space": project_space,
                "tool_call_parser": tool_call_parser,
                "litellm_command": litellm_command,
                "env_file": env_file,
            }
        )
        typer.echo(f"Script: {result.data['script_path']}")
        typer.echo(f"LiteLLM config: {result.data['litellm_config_path']}")
        typer.echo(f"Local-only config: {result.data['local_only_litellm_config_path']}")
        typer.echo(f"Gateway after tunneling: {result.data['gateway_url']}")

    @app.command("snellius-client-env")
    def snellius_client_env_command(
        snellius_user: str = typer.Option(..., "--snellius-user", "-u"),
        compute_node: str = typer.Option(..., "--compute-node", "-n"),
        local_port: int = typer.Option(4000, "--local-port", min=1024, max=65535),
        gateway_port: int = typer.Option(4000, "--gateway-port", min=1024, max=65535),
        model_alias: str = typer.Option("claude-snellius-local", "--model-alias", "-M"),
        gateway_token_env: str = typer.Option("SNELLIUS_GATEWAY_TOKEN", "--gateway-token-env"),
        login_host: str = typer.Option("snellius.surf.nl", "--login-host"),
    ) -> None:
        """Print local SSH tunnel and Claude Code environment commands."""

        typer.echo(
            render_snellius_client_env(
                {
                    "snellius_user": snellius_user,
                    "compute_node": compute_node,
                    "local_port": local_port,
                    "gateway_port": gateway_port,
                    "model_alias": model_alias,
                    "gateway_token_env": gateway_token_env,
                    "login_host": login_host,
                }
            ),
            nl=False,
        )

    def main() -> None:
        app()

except Exception:
    app = None

    def main() -> None:
        parser = argparse.ArgumentParser(description="Scientific-discovery multi-agent workbench.")
        subparsers = parser.add_subparsers(dest="command", required=True)

        demo_parser = subparsers.add_parser("demo")
        demo_parser.add_argument("request")
        demo_parser.add_argument("--run-mode", default=RunMode.CHEAP.value)
        demo_parser.add_argument("--config-dir", default="configs")
        demo_parser.add_argument("--run-root", default="runs")
        demo_parser.add_argument("--max-iterations", type=int, default=3)
        demo_parser.add_argument("--min-valid-candidates", type=int, default=10)
        demo_parser.add_argument("--score-threshold", type=float, default=0.75)

        bench_parser = subparsers.add_parser("benchmark-models")
        bench_parser.add_argument("--run-mode", default=RunMode.CHEAP.value)
        bench_parser.add_argument("--config-dir", default="configs")
        bench_parser.add_argument("--run-root", default="runs")

        system_bench_parser = subparsers.add_parser("benchmark-system")
        system_bench_parser.add_argument("--run-root", default="runs")

        linker_parser = subparsers.add_parser("design-linkers")
        linker_parser.add_argument(
            "--objective",
            "-o",
            default="Design a next-generation ADC linker with improved stability, tunable release, and broad payload compatibility.",
        )
        linker_parser.add_argument("--output-dir", default=None)
        linker_parser.add_argument("--payload-class", "-p", action="append", default=None)
        linker_parser.add_argument("--trigger", "-t", action="append", default=None)
        linker_parser.add_argument("--conjugation-handle", "-c", action="append", default=None)
        linker_parser.add_argument("--max-candidates", type=int, default=8)
        linker_parser.add_argument("--reference-corpus", default=None)
        linker_parser.add_argument("--no-reference-controls", action="store_true")

        check_parser = subparsers.add_parser("check-models")
        check_parser.add_argument("--run-mode", default=RunMode.CHEAP.value)
        check_parser.add_argument("--config-dir", default="configs")

        snellius_parser = subparsers.add_parser("snellius-vllm-script")
        snellius_parser.add_argument("--model-checkpoint", required=True)
        snellius_parser.add_argument("--output-dir", default="runs/snellius_vllm")
        snellius_parser.add_argument("--container-path", default="/projects/2/managed_datasets/containers/vllm/vllm.sif")
        snellius_parser.add_argument("--partition", default="gpu_a100")
        snellius_parser.add_argument("--gpus-per-node", type=int, default=1)
        snellius_parser.add_argument("--time-limit", default="02:00:00")
        snellius_parser.add_argument("--port", type=int, default=8000)
        snellius_parser.add_argument("--project-space", default="")

        snellius_gateway_parser = subparsers.add_parser("snellius-gateway-script")
        snellius_gateway_parser.add_argument("--model-checkpoint", required=True)
        snellius_gateway_parser.add_argument("--output-dir", default="runs/snellius_gateway")
        snellius_gateway_parser.add_argument("--served-model-name", default="claude-snellius-local")
        snellius_gateway_parser.add_argument("--local-model-alias", default="claude-snellius-local")
        snellius_gateway_parser.add_argument("--hosted-model-alias", default="claude-snellius-hosted")
        snellius_gateway_parser.add_argument("--hosted-litellm-model", default="anthropic/claude-sonnet-4-20250514")
        snellius_gateway_parser.add_argument("--container-path", default="/projects/2/managed_datasets/containers/vllm/vllm.sif")
        snellius_gateway_parser.add_argument("--partition", default="gpu_a100")
        snellius_gateway_parser.add_argument("--gpus-per-node", type=int, default=1)
        snellius_gateway_parser.add_argument("--time-limit", default="02:00:00")
        snellius_gateway_parser.add_argument("--vllm-port", type=int, default=8000)
        snellius_gateway_parser.add_argument("--gateway-port", type=int, default=4000)
        snellius_gateway_parser.add_argument("--project-space", default="")
        snellius_gateway_parser.add_argument("--tool-call-parser", default="openai")
        snellius_gateway_parser.add_argument("--litellm-command", default="litellm")
        snellius_gateway_parser.add_argument("--env-file", default=".env")

        snellius_client_parser = subparsers.add_parser("snellius-client-env")
        snellius_client_parser.add_argument("--snellius-user", "-u", required=True)
        snellius_client_parser.add_argument("--compute-node", "-n", required=True)
        snellius_client_parser.add_argument("--local-port", type=int, default=4000)
        snellius_client_parser.add_argument("--gateway-port", type=int, default=4000)
        snellius_client_parser.add_argument("--model-alias", "-M", default="claude-snellius-local")
        snellius_client_parser.add_argument("--gateway-token-env", default="SNELLIUS_GATEWAY_TOKEN")
        snellius_client_parser.add_argument("--login-host", default="snellius.surf.nl")

        review_parser = subparsers.add_parser("review-paper")
        review_parser.add_argument("path")
        review_parser.add_argument("--output", "-o", default=None)
        review_parser.add_argument("--domain", default="chem_bio")
        review_parser.add_argument("--focus-question", "-q", action="append", default=[])
        review_parser.add_argument("--review-depth", default="standard")

        rag_ingest_parser = subparsers.add_parser("rag-ingest")
        rag_ingest_parser.add_argument("path")
        rag_ingest_parser.add_argument("--db-path", default=str(DEFAULT_RAG_DB_PATH))
        rag_ingest_parser.add_argument("--extension", "-e", action="append", default=None)
        rag_ingest_parser.add_argument("--chunk-size", type=int, default=700)
        rag_ingest_parser.add_argument("--chunk-overlap", type=int, default=100)
        rag_ingest_parser.add_argument("--max-chars", type=int, default=2_000_000)
        rag_ingest_parser.add_argument("--skip-unchanged", action="store_true")

        rag_search_parser = subparsers.add_parser("rag-search")
        rag_search_parser.add_argument("query")
        rag_search_parser.add_argument("--db-path", default=str(DEFAULT_RAG_DB_PATH))
        rag_search_parser.add_argument("--limit", "-n", type=int, default=5)
        rag_search_parser.add_argument("--context", action="store_true")
        rag_search_parser.add_argument("--max-context-chars", type=int, default=4_000)

        prompt_parser = subparsers.add_parser("prompt-terminal")
        prompt_parser.add_argument("--config-dir", default="configs")
        prompt_parser.add_argument("--run-mode", default=RunMode.CHEAP.value)
        prompt_parser.add_argument("--model-alias", "-M", default=None)
        prompt_parser.add_argument("--db-path", default=str(DEFAULT_RAG_DB_PATH))
        prompt_parser.add_argument("--no-rag", action="store_true")
        prompt_parser.add_argument("--rag-limit", type=int, default=4)
        prompt_parser.add_argument("--max-context-chars", type=int, default=4_000)
        prompt_parser.add_argument(
            "--system",
            default="You are a concise scientific discovery assistant. Use retrieved context only when relevant.",
        )
        prompt_parser.add_argument("--temperature", type=float, default=0.1)
        prompt_parser.add_argument("--max-tokens", type=int, default=1200)

        mechanism_loop_parser = subparsers.add_parser("mechanism-loop")
        mechanism_loop_parser.add_argument("--objective", required=True)
        mechanism_loop_parser.add_argument("--rounds", type=int, default=3)
        mechanism_loop_parser.add_argument("--mode", default="mock")
        mechanism_loop_parser.add_argument("--run-root", default="runs")
        mechanism_loop_parser.add_argument("--allow-real-robot", action="store_true")
        mechanism_loop_parser.add_argument("--allow-hpc-submit", action="store_true")
        mechanism_loop_parser.add_argument("--robot-base-url", default=None)
        mechanism_loop_parser.add_argument("--robot-api-key", default=None)
        mechanism_loop_parser.add_argument("--literature-corpus-dir", default=None)
        mechanism_loop_parser.add_argument("--dft-structure-file", default=None)

        mechanism_once_parser = subparsers.add_parser("mechanism-once")
        mechanism_once_parser.add_argument("--data", required=True)
        mechanism_once_parser.add_argument("--objective", required=True)
        mechanism_once_parser.add_argument("--mode", default="mock")
        mechanism_once_parser.add_argument("--run-root", default="runs")
        mechanism_once_parser.add_argument("--literature-corpus-dir", default=None)
        mechanism_once_parser.add_argument("--dft-structure-file", default=None)

        args = parser.parse_args()
        configure_logging()
        if args.command == "demo":
            state = run_demo(
                args.request,
                run_mode=args.run_mode,
                config_dir=args.config_dir,
                run_root=args.run_root,
                max_iterations=args.max_iterations,
                min_valid_candidates=args.min_valid_candidates,
                score_threshold=args.score_threshold,
            )
            print(f"Run directory: {state.run_dir}")
            if state.final_report_path:
                print(f"Report: {state.final_report_path}")
            print(f"Iterations: {state.iteration}")
            if state.stop_reason:
                print(f"Stop reason: {state.stop_reason}")
            print(f"Errors: {len(state.errors)}")
        elif args.command == "benchmark-models":
            config = load_config(config_dir=args.config_dir, run_mode=args.run_mode)
            output_path = benchmark_models(config, run_root=args.run_root)
            print(f"Benchmark written to {output_path}")
        elif args.command == "benchmark-system":
            output_path = benchmark_system(run_root=args.run_root)
            print(f"System benchmark written to {output_path}")
        elif args.command == "design-linkers":
            result = design_adc_linkers(
                {
                    "objective": args.objective,
                    "output_dir": args.output_dir,
                    "payload_classes": args.payload_class
                    or ["cytotoxin", "oligonucleotide", "immunomodulator"],
                    "desired_triggers": args.trigger
                    or ["lysosomal protease", "acidic pH", "reducing environment", "tumor enzyme"],
                    "conjugation_handles": args.conjugation_handle
                    or ["maleimide", "strain-promoted azide"],
                    "max_candidates": args.max_candidates,
                    "reference_corpus_path": args.reference_corpus,
                    "include_reference_controls": not args.no_reference_controls,
                }
            )
            if not result.ok:
                print(f"Linker design failed: {result.error}")
                raise SystemExit(1)
            top = result.data.get("top_candidate") or {}
            score = ((top.get("scorecard") or {}).get("overall")) if isinstance(top, dict) else None
            print(f"Run directory: {result.data['output_dir']}")
            print(f"Candidates: {result.data['candidate_count']}")
            if top:
                print(f"Top linker: {top.get('name')} ({score:.3f})")
            for artifact in result.artifacts:
                print(f"Artifact: {artifact}")
        elif args.command == "check-models":
            config = load_config(config_dir=args.config_dir, run_mode=args.run_mode)
            router = ModelRouter(config)
            for alias, availability in router.check_model_availability().items():
                status = "available" if availability.available else "unavailable"
                print(f"{alias}: {status} ({availability.reason})")
        elif args.command == "snellius-vllm-script":
            result = generate_snellius_vllm_job(
                {
                    "output_dir": args.output_dir,
                    "model_checkpoint": args.model_checkpoint,
                    "container_path": args.container_path,
                    "partition": args.partition,
                    "gpus_per_node": args.gpus_per_node,
                    "time_limit": args.time_limit,
                    "port": args.port,
                    "project_space": args.project_space,
                }
            )
            print(f"Script: {result.data['script_path']}")
            print(f"Base URL after tunneling: {result.data['base_url']}")
        elif args.command == "snellius-gateway-script":
            result = generate_snellius_gateway_job(
                {
                    "output_dir": args.output_dir,
                    "model_checkpoint": args.model_checkpoint,
                    "served_model_name": args.served_model_name,
                    "local_model_alias": args.local_model_alias,
                    "hosted_model_alias": args.hosted_model_alias,
                    "hosted_litellm_model": args.hosted_litellm_model,
                    "container_path": args.container_path,
                    "partition": args.partition,
                    "gpus_per_node": args.gpus_per_node,
                    "time_limit": args.time_limit,
                    "vllm_port": args.vllm_port,
                    "gateway_port": args.gateway_port,
                    "local_client_port": args.gateway_port,
                    "project_space": args.project_space,
                    "tool_call_parser": args.tool_call_parser,
                    "litellm_command": args.litellm_command,
                    "env_file": args.env_file,
                }
            )
            print(f"Script: {result.data['script_path']}")
            print(f"LiteLLM config: {result.data['litellm_config_path']}")
            print(f"Local-only config: {result.data['local_only_litellm_config_path']}")
            print(f"Gateway after tunneling: {result.data['gateway_url']}")
        elif args.command == "snellius-client-env":
            print(
                render_snellius_client_env(
                    {
                        "snellius_user": args.snellius_user,
                        "compute_node": args.compute_node,
                        "local_port": args.local_port,
                        "gateway_port": args.gateway_port,
                        "model_alias": args.model_alias,
                        "gateway_token_env": args.gateway_token_env,
                        "login_host": args.login_host,
                    }
                ),
                end="",
            )
        elif args.command == "review-paper":
            output_path = args.output or str(Path("runs") / f"paper_review_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
            result = review_paper(
                {
                    "path": args.path,
                    "domain": args.domain,
                    "focus_questions": args.focus_question,
                    "review_depth": args.review_depth,
                    "output_path": output_path,
                }
            )
            if not result.ok:
                print(f"Paper review failed: {result.error}")
                raise SystemExit(1)
            review = result.data["review"]
            print(f"Review: {output_path}")
            print(f"Recommendation: {review['recommendation']}")
            print(review["summary"])
        elif args.command == "rag-ingest":
            result = ingest_rag_documents(
                {
                    "path": args.path,
                    "db_path": args.db_path,
                    "extensions": args.extension or [".txt", ".md", ".markdown", ".pdf", ".docx"],
                    "chunk_size": args.chunk_size,
                    "chunk_overlap": args.chunk_overlap,
                    "max_chars": args.max_chars,
                    "replace": not args.skip_unchanged,
                }
            )
            if not result.ok:
                print(f"RAG ingest failed: {result.error}")
                raise SystemExit(1)
            print(f"Database: {result.data['db_path']}")
            print(f"Indexed documents: {result.data['document_count']}")
            print(f"Indexed chunks: {result.data['chunk_count']}")
        elif args.command == "rag-search":
            if args.context:
                result = build_rag_context(
                    {
                        "query": args.query,
                        "db_path": args.db_path,
                        "limit": args.limit,
                        "max_chars": args.max_context_chars,
                    }
                )
                if not result.ok:
                    print(f"RAG search failed: {result.error}")
                    raise SystemExit(1)
                print(result.data["context"] or "No matching RAG context.")
            else:
                result = search_rag({"query": args.query, "db_path": args.db_path, "limit": args.limit})
                if not result.ok:
                    print(f"RAG search failed: {result.error}")
                    raise SystemExit(1)
                for index, record in enumerate(result.data["records"], start=1):
                    source = record.get("source_path") or record["title"]
                    print(f"{index}. {record['title']} [{record['score']:.3f}] {source}")
                    print(record["snippet"])
        elif args.command == "prompt-terminal":
            _run_prompt_terminal(
                config_dir=Path(args.config_dir),
                run_mode=args.run_mode,
                model_alias=args.model_alias,
                db_path=Path(args.db_path),
                use_rag=not args.no_rag,
                rag_limit=args.rag_limit,
                max_context_chars=args.max_context_chars,
                system_prompt=args.system,
                temperature=args.temperature,
                max_tokens=args.max_tokens,
            )
        elif args.command == "mechanism-loop":
            state = run_mechanism_loop(
                objective=args.objective,
                rounds=args.rounds,
                mode=args.mode,
                run_root=args.run_root,
                allow_real_robot=args.allow_real_robot,
                allow_hpc_submit=args.allow_hpc_submit,
                robot_base_url=args.robot_base_url,
                robot_api_key=args.robot_api_key,
                literature_corpus_dir=args.literature_corpus_dir,
                dft_structure_file=args.dft_structure_file,
            )
            print(f"Run directory: {state.run_dir}")
            print(f"Rounds: {state.round_index}/{state.max_rounds}")
            print(f"Hypotheses: {len(state.hypotheses)}")
            print(f"Datasets: {len(state.datasets)}")
            if state.report_docx_path:
                print(f"Report: {state.report_docx_path}")
        elif args.command == "mechanism-once":
            state = run_mechanism_once(
                objective=args.objective,
                data_path=args.data,
                mode=args.mode,
                run_root=args.run_root,
                literature_corpus_dir=args.literature_corpus_dir,
                dft_structure_file=args.dft_structure_file,
            )
            print(f"Run directory: {state.run_dir}")
            if state.rankings:
                print(f"Top hypothesis: {state.rankings[0].title} ({state.rankings[0].score:.3f})")
            if state.report_docx_path:
                print(f"Report: {state.report_docx_path}")


if __name__ == "__main__":
    main()
