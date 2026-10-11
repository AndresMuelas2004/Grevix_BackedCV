from langgraph.graph import END, START, StateGraph
from langgraph.types import RetryPolicy

from backedcv.graph.build_nodes import make_build_nodes
from backedcv.graph.nodes import make_nodes
from backedcv.graph.optimize_nodes import make_optimize_nodes
from backedcv.graph.state import AnalysisState
from backedcv.llm.structured import StructuredLLM

LLM_RETRY = RetryPolicy(max_attempts=2)
MAX_CONCURRENCY = 4


def build_graph(llm: StructuredLLM, checkpointer=None, order_model=None):
    """`order_model` is the chat model of the ordering agent; None keeps the original order."""
    nodes = make_nodes(llm)
    optimize = make_optimize_nodes(llm)
    build = make_build_nodes(order_model)
    graph = StateGraph(AnalysisState)

    graph.add_node("prepare_cv", nodes["prepare_cv"])
    graph.add_node("prepare_job", nodes["prepare_job"], retry_policy=LLM_RETRY)
    graph.add_node("review_posting", nodes["review_posting"])
    graph.add_node("plan_matching", nodes["plan_matching"])
    graph.add_node("match_chunk", nodes["match_chunk"])
    graph.add_node("score_and_verdict", nodes["score_and_verdict"])
    graph.add_node("await_optimize", nodes["await_optimize"])
    graph.add_node("suggest", optimize["suggest"])
    graph.add_node("verify_batch", optimize["verify_batch"])
    graph.add_node("await_review", optimize["await_review"])
    graph.add_node("build_cv", build["build_cv"])
    graph.add_node("final_checks", build["final_checks"])

    # Both branches take one step each, then join. The posting review starts once the job
    # is extracted and runs alongside plan_matching.
    graph.add_edge(START, "prepare_cv")
    graph.add_edge(START, "prepare_job")
    graph.add_edge("prepare_job", "review_posting")
    graph.add_edge(["prepare_cv", "prepare_job"], "plan_matching")
    graph.add_conditional_edges(
        "plan_matching", nodes["route_matching"], ["match_chunk", "score_and_verdict"]
    )
    graph.add_edge("match_chunk", "score_and_verdict")
    graph.add_edge("score_and_verdict", "await_optimize")

    # After the first pause: suggest, verify per CV section in parallel, then the review pause.
    graph.add_edge("await_optimize", "suggest")
    graph.add_conditional_edges(
        "suggest", optimize["route_verification"], ["verify_batch", "await_review"]
    )
    graph.add_edge("verify_batch", "await_review")
    graph.add_edge("await_review", "build_cv")
    graph.add_edge("build_cv", "final_checks")
    graph.add_edge("final_checks", END)

    return graph.compile(checkpointer=checkpointer)


def run_config(analysis_id: str) -> dict:
    return {
        "configurable": {"thread_id": analysis_id},
        "max_concurrency": MAX_CONCURRENCY,
        "run_name": "analysis",
        "metadata": {"analysis_id": analysis_id},
    }
