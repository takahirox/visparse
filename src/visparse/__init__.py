"""Public API for Visparse 0.1."""

from .analyzer import Analyzer, SourceEvidence, run_analyzer
from .evaluation import EvaluationResult, evaluate_fixture, load_fixture
from .design import (
    AVOID_COPYING,
    DESIGN_CATEGORIES,
    DESIGN_SCHEMA_VERSION,
    CodexDesignAnalyzer,
    DesignAnalyzer,
    load_design_profile,
    normalize_design_profile,
    run_design_analyzer,
    summarize_design_profile,
    validate_design_profile,
)
from .model import (
    MAX_INPUT_BYTES,
    SCHEMA_VERSION,
    ValidationError,
    load_record,
    normalize_record,
    summarize_record,
    validate_record,
)

__all__ = [
    "AVOID_COPYING", "Analyzer", "CodexDesignAnalyzer", "DESIGN_CATEGORIES",
    "DESIGN_SCHEMA_VERSION", "DesignAnalyzer", "EvaluationResult",
    "MAX_INPUT_BYTES", "SCHEMA_VERSION", "SourceEvidence", "ValidationError",
    "evaluate_fixture", "load_design_profile", "load_fixture", "load_record",
    "normalize_design_profile", "normalize_record", "run_analyzer",
    "run_design_analyzer", "summarize_design_profile", "summarize_record",
    "validate_design_profile", "validate_record",
]
