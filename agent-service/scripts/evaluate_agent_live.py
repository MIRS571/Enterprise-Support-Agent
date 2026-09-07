import argparse
import asyncio
from pathlib import Path

import httpx

from agent_service.core.config import get_settings
from agent_service.evaluation import (
    JavaAgentLiveClient,
    build_live_agent_evaluation_report,
    live_agent_evaluation_exit_code,
    load_agent_evaluation_cases,
    run_live_agent_suite,
)

DEFAULT_CASES_PATH = Path("data/evaluation/agent_cases.json")
DEFAULT_REPORT_PATH = Path("reports/agent-live-evaluation.json")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the authorized 21-request live Agent baseline through Java.",
    )
    parser.add_argument(
        "--java-base-url",
        default="http://127.0.0.1:8080",
    )
    parser.add_argument(
        "--cases",
        type=Path,
        default=DEFAULT_CASES_PATH,
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=DEFAULT_REPORT_PATH,
    )
    parser.add_argument(
        "--model-provider",
        default="deepseek",
    )
    parser.add_argument("--model-name")
    parser.add_argument(
        "--confirm-external-evaluation",
        action="store_true",
        help="Confirm that the approved fictional dataset may be sent externally.",
    )
    args = parser.parse_args()
    if not args.confirm_external_evaluation:
        parser.error("--confirm-external-evaluation is required")
    return args


async def run(args: argparse.Namespace) -> int:
    settings = get_settings()
    model_name = args.model_name or settings.llm_model
    if not model_name:
        raise ValueError("model name is required for the live evaluation report")

    cases = load_agent_evaluation_cases(args.cases)
    timeout = httpx.Timeout(
        connect=5.0,
        read=180.0,
        write=10.0,
        pool=5.0,
    )
    async with httpx.AsyncClient(
        base_url=args.java_base_url,
        timeout=timeout,
        trust_env=False,
    ) as http_client:
        suite = await run_live_agent_suite(
            cases=cases,
            runner=JavaAgentLiveClient(http_client),
        )

    report = build_live_agent_evaluation_report(
        cases=cases,
        suite=suite,
        model_provider=args.model_provider,
        model_name=model_name,
    )
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        report.model_dump_json(indent=2),
        encoding="utf-8",
    )
    print(f"status={report.status}")
    print(f"runs={report.completed_runs}/{report.planned_runs}")
    if report.abort_code:
        print(f"abort_code={report.abort_code}")
    if report.stability is not None:
        print(f"public_contract_rate={report.stability.public_contract_pass_rate:.2%}")
        print(f"required_facts_rate={report.stability.required_facts_pass_rate:.2%}")
    print(f"report={args.report}")
    return live_agent_evaluation_exit_code(report)


def main() -> int:
    return asyncio.run(run(parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
