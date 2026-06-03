from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path

from hackathon_agents.config import RunMode, load_config
from hackathon_agents.demos.discovery_demo import run_demo
from hackathon_agents.llm.benchmark import benchmark_models
from hackathon_agents.llm.router import ModelRouter
from hackathon_agents.logging_config import configure_logging
from hackathon_agents.tools.paper_review import review_paper

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

        review_parser = subparsers.add_parser("review-paper")
        review_parser.add_argument("path")
        review_parser.add_argument("--output", "-o", default=None)
        review_parser.add_argument("--domain", default="chem_bio")
        review_parser.add_argument("--focus-question", "-q", action="append", default=[])
        review_parser.add_argument("--review-depth", default="standard")

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


if __name__ == "__main__":
    main()
