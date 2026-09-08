# Analyzer configuration

All LLM-backed analysis commands accept the same options:
`--agent`, `--model`, `--executable`, `--timeout-seconds`, and `--config`.

| Command | Evidence | Default timeout |
| --- | --- | --- |
| `analyze` | One image | 120 seconds |
| `analyze-design` | Reference and optional target screenshots | 300 seconds |
| `design-extract` | Evidence in normalized Design DNA | 300 seconds |
| `ux-analyze` | Recorded interactions | 300 seconds |

```sh
visparse analyze screenshot.png --agent codex --model gpt-6-astra
visparse analyze-design reference.png --target target.png --model gpt-6-astra
visparse design-extract dna.json --model gpt-6-astra
visparse ux-analyze sequence.json --model gpt-6-astra
```

The model above was used in the Kirka UX experiment. Its availability depends on
the installed agent and account; it is not Visparse's default. With no settings,
each command continues to run Codex with no model override and its original timeout.
The same options work with both `preserve` and `adapt` design intents and with
the detailed geometry, appearance and media options.

## Configuration file

Pass an explicit JSON file with `--config`; no files are discovered automatically.
Use the same file for any of the four commands. All option fields are optional
except that the resolved `command` agent requires an explicit executable.

```json
{
  "analyzer": {
    "agent": "codex",
    "model": "gpt-6-astra"
  },
  "commands": {
    "analyze": {"timeout_seconds": 120},
    "analyze-design": {"timeout_seconds": 450},
    "design-extract": {"timeout_seconds": 300},
    "ux-analyze": {"timeout_seconds": 600}
  }
}
```

```sh
visparse analyze-design reference.png --config examples/analyzer-config.json
visparse ux-analyze sequence.json --config my-config.json --model another-model
```

Each `commands` entry can override `agent`, `executable`, `model` and
`timeout_seconds`. Priority, by field, is CLI > matching command settings >
legacy `ux_analyzer` settings (UX only) > shared `analyzer` settings > defaults.
The legacy UX-only file remains accepted for `ux-analyze`; using it for an image
analysis command is an error rather than silently treating it as shared settings.
Unknown fields/commands, duplicate JSON keys and malformed values are errors.
File settings are validated even when CLI values would override them.

Timeouts must be finite numbers from 1 to 900. A model is a nonempty identifier
without whitespace; absent/null means the agent's default. The explicit model
is forwarded unchanged, not checked against a model catalog. An executable is
one path or executable name, not a shell command string; relative paths resolve
from the invocation directory. Neither Visparse's settings file nor its model
selection changes the agent's authentication configuration.

`design-extract --predictions` and `ux-analyze --predictions` skip reading the
configuration and do not invoke any agent. Validation, normalization, collection,
comparison, evaluation and rendering commands are deterministic and have no LLM
selection options. Website generation is an external workflow, not one of these
analysis commands.

## Other agents

`codex` is the built-in agent. Choose `command` for an explicitly supplied
executable wrapper implementing the following protocol:

```sh
visparse analyze-design reference.png --agent command \
  --executable /absolute/path/to/analysis-wrapper --model your-model
```

Visparse launches only that executable once, without arguments or shell
interpretation. It does not launch Codex for the `command` backend. Stdin contains
one JSON object:

```json
{
  "schema_version": "analysis-agent-request/0.1",
  "command": "analyze-design",
  "model": "your-model",
  "prompt": "The complete task-specific analysis instructions and evidence...",
  "image_paths": ["/temporary/reference.image", "/temporary/target.image"]
}
```

The wrapper must pass the prompt and all listed images to its agent, honor the
requested model or exit nonzero, and return exactly one JSON object on stdout.
Diagnostics belong on stderr. The expected result schema is specified in the
prompt: a Visparse record, Design Profile, semantic prediction, or interaction
prediction, according to `command`. The usual input identity, evidence grounding,
requested detail coverage and output validators remain active for every backend.

Image paths are private temporary files available for the duration of the call;
their extension does not identify the media type. `analyze` supplies one image.
`analyze-design` supplies references first, then targets, in input order. The
prompt identifies those roles. Consume the images before returning; Visparse
removes the files on success and failure. Semantic and standard UX calls have no
image attachments; artifact references in their evidence are not automatically
resolved into files. External wrappers must not claim those images were inspected.

This is a protocol adapter, not native support for every third-party agent.
Wrappers own authentication, agent flags, permissions, child-process cleanup and
model-selection enforcement. Visparse does not sandbox a user-supplied wrapper.
Use a wrapper you intend to execute. Neither Visparse nor the wrapper should retry,
reset usage allowance, buy capacity or switch agents/models on a usage limit.
Visparse stops on timeouts, process errors and invalid results, without fallback.

## Python API and verification

All four built-in classes accept `model`, `executable` and `timeout_seconds`:
`CodexAnalyzer`, `CodexDesignAnalyzer`, `CodexSemanticExtractor`, and
`CodexInteractionAnalyzer`. For shared config and either backend:

```python
from visparse.agent_config import AnalyzerConfig
from visparse.design import CodexDesignAnalyzer

config = AnalyzerConfig.resolve(document, command="analyze-design", model="override")
analyzer = CodexDesignAnalyzer(**config.adapter_options("analyze-design"))
```

The task adapter retains its historical class name even when the selected runner
uses an external command. The earlier UX-only Python imports remain available
from `visparse.interaction_config`; its compatibility factory retains the older
three-field `interaction-analysis-request/0.1` wrapper protocol.

Offline tests exercise CLI precedence and both transports across all four commands,
image order and temporary-file cleanup, model/timeout forwarding, invalid configs,
stored-prediction bypass, and failure without retries or provider fallback. They do
not establish live availability of a model or compatibility of a third-party wrapper.
