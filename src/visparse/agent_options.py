"""Validate explicit agent options without invoking a provider."""
from .contracts import check, number, text


def validate_agent_options(executable, model, timeout_seconds):
    text(executable)
    check(not executable.startswith("-") and not any(c in executable for c in "\x00\r\n"), "invalid agent executable")
    if model is not None:
        text(model)
        check(len(model) <= 256 and not model.startswith("-") and not any(c.isspace() or ord(c) < 32 for c in model), "invalid model identifier")
    number(timeout_seconds, 1, 900)

