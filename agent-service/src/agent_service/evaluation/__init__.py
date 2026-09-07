from agent_service.evaluation.agent import (
    AgentEvaluationCase,
    AgentEvaluationCaseResult,
    AgentEvaluationObservation,
    AgentEvaluationSummary,
    AnswerQualityExpectations,
    DeterministicExpectations,
    ExpectedCallCounts,
    KnowledgeRetrievalObservation,
    OrderLookupObservation,
    evaluate_agent_case,
    load_agent_evaluation_cases,
    summarize_agent_results,
)
from agent_service.evaluation.live import (
    JavaAgentLiveClient,
    LiveAgentCaseResult,
    LiveAgentObservation,
    LiveEvaluationProtocolError,
    evaluate_live_agent_case,
)
from agent_service.evaluation.live_report import (
    LiveAgentEvaluationReport,
    LiveAgentStabilityPolicy,
    build_live_agent_evaluation_report,
    evaluate_live_agent_stability,
    live_agent_evaluation_exit_code,
)
from agent_service.evaluation.live_suite import (
    LiveAgentRunEvidence,
    LiveAgentRunRecord,
    LiveAgentSuiteResult,
    run_live_agent_suite,
)
from agent_service.evaluation.report import (
    AgentEvaluationReport,
    agent_evaluation_exit_code,
    build_agent_evaluation_report,
)
from agent_service.evaluation.stability import (
    AgentCaseStabilityResult,
    AgentStabilityPolicy,
    AgentStabilitySummary,
    evaluate_agent_stability,
)

__all__ = [
    "AgentCaseStabilityResult",
    "AgentEvaluationCase",
    "AgentEvaluationCaseResult",
    "AgentEvaluationObservation",
    "AgentEvaluationReport",
    "AgentEvaluationSummary",
    "AgentStabilityPolicy",
    "AgentStabilitySummary",
    "AnswerQualityExpectations",
    "DeterministicExpectations",
    "ExpectedCallCounts",
    "ExpectedSource",
    "JavaAgentLiveClient",
    "KnowledgeRetrievalObservation",
    "LiveAgentCaseResult",
    "LiveAgentEvaluationReport",
    "LiveAgentObservation",
    "LiveAgentRunEvidence",
    "LiveAgentRunRecord",
    "LiveAgentStabilityPolicy",
    "LiveAgentSuiteResult",
    "LiveEvaluationProtocolError",
    "OrderLookupObservation",
    "RetrievalCaseResult",
    "RetrievalEvaluationCase",
    "RetrievalEvaluationSummary",
    "agent_evaluation_exit_code",
    "build_agent_evaluation_report",
    "build_live_agent_evaluation_report",
    "evaluate_agent_case",
    "evaluate_agent_stability",
    "evaluate_live_agent_case",
    "evaluate_live_agent_stability",
    "evaluate_retrieval_case",
    "live_agent_evaluation_exit_code",
    "load_agent_evaluation_cases",
    "load_retrieval_cases",
    "run_controlled_agent_case",
    "run_live_agent_suite",
    "summarize_agent_results",
    "summarize_retrieval_results",
]


def __getattr__(name: str):
    if name == "run_controlled_agent_case":
        from agent_service.evaluation.controlled_runner import (
            run_controlled_agent_case,
        )

        return run_controlled_agent_case
    retrieval_exports = {
        "ExpectedSource",
        "RetrievalCaseResult",
        "RetrievalEvaluationCase",
        "RetrievalEvaluationSummary",
        "evaluate_retrieval_case",
        "load_retrieval_cases",
        "summarize_retrieval_results",
    }
    if name in retrieval_exports:
        from agent_service.evaluation import retrieval

        return getattr(retrieval, name)
    raise AttributeError(name)
