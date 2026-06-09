from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path

from hackathon_agents.config import RunMode, load_config
from hackathon_agents.demos.discovery_demo import run_demo
from hackathon_agents.llm.benchmark import benchmark_models
from hackathon_agents.llm.router import ModelRouter
from hackathon_agents.logging_config import configure_logging
from hackathon_agents.mechanism.graph import run_mechanism_loop, run_mechanism_once
from hackathon_agents.tools.paper_review import review_paper
from hackathon_agents.tools.snellius_vllm import generate_snellius_vllm_job

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
    ) -> None:
        """Run one mechanism analysis pass on existing kinetic data."""

        configure_logging()
        state = run_mechanism_once(
            objective=objective,
            data_path=data,
            mode=mode,  # type: ignore[arg-type]
            run_root=run_root,
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

        review_parser = subparsers.add_parser("review-paper")
        review_parser.add_argument("path")
        review_parser.add_argument("--output", "-o", default=None)
        review_parser.add_argument("--domain", default="chem_bio")
        review_parser.add_argument("--focus-question", "-q", action="append", default=[])
        review_parser.add_argument("--review-depth", default="standard")

        mechanism_loop_parser = subparsers.add_parser("mechanism-loop")
        mechanism_loop_parser.add_argument("--objective", required=True)
        mechanism_loop_parser.add_argument("--rounds", type=int, default=3)
        mechanism_loop_parser.add_argument("--mode", default="mock")
        mechanism_loop_parser.add_argument("--run-root", default="runs")
        mechanism_loop_parser.add_argument("--allow-real-robot", action="store_true")
        mechanism_loop_parser.add_argument("--allow-hpc-submit", action="store_true")
        mechanism_loop_parser.add_argument("--robot-base-url", default=None)
        mechanism_loop_parser.add_argument("--robot-api-key", default=None)

        mechanism_once_parser = subparsers.add_parser("mechanism-once")
        mechanism_once_parser.add_argument("--data", required=True)
        mechanism_once_parser.add_argument("--objective", required=True)
        mechanism_once_parser.add_argument("--mode", default="mock")
        mechanism_once_parser.add_argument("--run-root", default="runs")

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
            )
            print(f"Run directory: {state.run_dir}")
            if state.rankings:
                print(f"Top hypothesis: {state.rankings[0].title} ({state.rankings[0].score:.3f})")
            if state.report_docx_path:
                print(f"Report: {state.report_docx_path}")


if __name__ == "__main__":
    main()
