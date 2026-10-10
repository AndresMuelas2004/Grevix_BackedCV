from langgraph.graph import END, START, StateGraph
from langgraph.types import RetryPolicy

from backedcv.graph.nodes import make_nodes
from backedcv.graph.state import AnalysisState
from backedcv.llm.structured import StructuredLLM

LLM_RETRY = RetryPolicy(max_attempts=2)
MAX_CONCURRENCY = 4


def build_graph(llm: StructuredLLM, checkpointer=None):
    nodes = make_nodes(llm)
    graph = StateGraph(AnalysisState)

    graph.add_node("prepare_cv", nodes["prepare_cv"])
    graph.add_node("prepare_job", nodes["prepare_job"], retry_policy=LLM_RETRY)
    graph.add_node("plan_matching", nodes["plan_matching"])
    graph.add_node("match_chunk", nodes["match_chunk"])
    graph.add_node("score_and_verdict", nodes["score_and_verdict"])
    graph.add_node("await_optimize", nodes["await_optimize"])

    # Both branches take one step each, then join.
    graph.add_edge(START, "prepare_cv")
    graph.add_edge(START, "prepare_job")
    graph.add_edge(["prepare_cv", "prepare_job"], "plan_matching")
    graph.add_conditional_edges(
        "plan_matching", nodes["route_matching"], ["match_chunk", "score_and_verdict"]
    )
    graph.add_edge("match_chunk", "score_and_verdict")
    graph.add_edge("score_and_verdict", "await_optimize")
    graph.add_edge("await_optimize", END)

    return graph.compile(checkpointer=checkpointer)


def run_config(analysis_id: str) -> dict:
    return {
        "configurable": {"thread_id": analysis_id},
        "max_concurrency": MAX_CONCURRENCY,
        "run_name": "analysis",
        "metadata": {"analysis_id": analysis_id},
    }
