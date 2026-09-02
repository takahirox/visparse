"""Public API for Visparse 0.1."""

from .analyzer import Analyzer, SourceEvidence, run_analyzer
from .evaluation import EvaluationResult, evaluate_fixture, load_fixture
from .design import (
    AVOID_COPYING,
    DESIGN_CATEGORIES,
    DESIGN_SCHEMA_VERSION,
    INTERPRETIVE_DESIGN_CATEGORIES,
    OBSERVATION_DESIGN_CATEGORIES,
    CodexDesignAnalyzer,
    DesignAnalyzer,
    load_design_profile,
    normalize_design_profile,
    run_design_analyzer,
    summarize_design_profile,
    validate_design_profile,
)
from .inspection import (
    CAPTURE_KINDS,
    INSPECTION_SCHEMA_VERSION,
    inspect_snapshot,
    inspection_capabilities,
    load_inspection,
    normalize_inspection,
    summarize_inspection,
    validate_inspection,
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
    "AVOID_COPYING", "Analyzer", "CAPTURE_KINDS", "CodexDesignAnalyzer", "DESIGN_CATEGORIES",
    "DESIGN_SCHEMA_VERSION", "DesignAnalyzer", "EvaluationResult",
    "INSPECTION_SCHEMA_VERSION", "INTERPRETIVE_DESIGN_CATEGORIES",
    "OBSERVATION_DESIGN_CATEGORIES",
    "MAX_INPUT_BYTES", "SCHEMA_VERSION", "SourceEvidence", "ValidationError",
    "evaluate_fixture", "inspect_snapshot", "inspection_capabilities",
    "load_design_profile", "load_fixture", "load_inspection", "load_record",
    "normalize_design_profile", "normalize_inspection", "normalize_record",
    "run_analyzer", "run_design_analyzer", "summarize_design_profile",
    "summarize_inspection", "summarize_record", "validate_design_profile",
    "validate_inspection", "validate_record",
]
