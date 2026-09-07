import argparse
import asyncio
from pathlib import Path

from agent_service.evaluation import (
    agent_evaluation_exit_code,
    build_agent_evaluation_report,
    load_agent_evaluation_cases,
    run_controlled_agent_case,
)

DEFAULT_CASES_PATH = Path("data/evaluation/agent_cases.json")


async def run_controlled_evaluation(
    *,
    cases_path: Path,
) -> tuple[str, int]:
    cases = load_agent_evaluation_cases(cases_path)
    observations = [await run_controlled_agent_case(case) for case in cases]
    report = build_agent_evaluation_report(
        cases=cases,
        observations=observations,
        mode="controlled",
        model_provider="controlled",
        model_name="deterministic-dependencies-v1",
    )
    return (
        report.model_dump_json(indent=2),
        agent_evaluation_exit_code(report),
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run controlled LangGraph Agent evaluation.",
    )
    parser.add_argument(
        "--cases",
        type=Path,
        default=DEFAULT_CASES_PATH,
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional JSON report path. The report contains no raw prompts.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    report_json, exit_code = asyncio.run(
        run_controlled_evaluation(cases_path=args.cases)
    )
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            f"{report_json}\n",
            encoding="utf-8",
        )
    print(report_json)
    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
