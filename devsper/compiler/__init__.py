from .ir import GraphSpec, NodeSpec, EdgeSpec, RawWorkflowDoc

try:
    from .parser import parse
except ImportError:
    pass

try:
    from .compressor import compress
except ImportError:
    pass

try:
    from .objectives import score_f1_token_cost, score_f2_task_fidelity, score_f3_predicted_performance
except ImportError:
    pass

try:
    from .gepa import optimize, GEPAConfig
except ImportError:
    pass

try:
    from .codegen import compile_graph
except ImportError:
    pass

__all__ = [
    "GraphSpec", "NodeSpec", "EdgeSpec", "RawWorkflowDoc",
    "parse", "compress",
    "score_f1_token_cost", "score_f2_task_fidelity", "score_f3_predicted_performance",
    "optimize", "GEPAConfig",
    "compile_graph",
]
