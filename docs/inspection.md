# Supplied experience inspection

Visparse accepts evidence already collected from a web page or interactive experience and validates it for use by an external agent. It does not open URLs, execute JavaScript, drive a browser, click controls, or claim that a capture happened. The collector—browser extension, test harness, devtools script, human, or agent tool—remains responsible for capture fidelity and authorization.

## Feasibility decision

The stable integration boundary is a supplied evidence bundle, not a second browser automation stack inside Visparse. Existing host-agent tools can collect the source data with more authority and less duplication:

- The [Chrome DevTools Protocol DOM domain](https://chromedevtools.github.io/devtools-protocol/tot/DOM/) exposes document structure and box models; its [CSS domain](https://chromedevtools.github.io/devtools-protocol/tot/CSS/) exposes computed and matched styles. The Accessibility, Runtime, DOMSnapshot, Animation, Network, Performance, and Tracing domains provide complementary exact or runtime evidence.
- [Playwright tracing](https://playwright.dev/docs/api/class-tracing) records browser operations, network activity, screenshots, and snapshots, while [Playwright video](https://playwright.dev/docs/videos) records interaction sequences. A host agent that already controls Playwright can select and authorize interactions without Visparse embedding an autonomous browser.
- Generic canvas and WebGL state can be reported through bounded runtime instrumentation, but reconstructing application semantics from draw calls is intentionally outside this layer.
- The official [three.js DevTools project](https://github.com/threejs/three-devtools) is experimental and relies on an application or injected integration explicitly registering a scene or renderer. Consequently, Three.js inspection is progressive and cooperative: Visparse accepts high-level scene evidence when a collector can supply it, but never claims that arbitrary WebGL can be reverse-engineered into a scene graph.

This split keeps browser-version negotiation, credentials, navigation, consent, and page interaction in the authorized host collector. Visparse supplies the model-independent validation and provenance boundary that an MCP server, browser agent, extension, or test harness can call.

## Bundle format

Use the public `inspect_snapshot` function or the CLI:

```sh
PYTHONPATH=src python -m visparse inspect capture-bundle.json
PYTHONPATH=src python -m visparse inspect-summary capture-bundle.json
PYTHONPATH=src python -m visparse inspect-capabilities
```

`inspect` validates and emits canonical JSON. `inspect-summary` reports only counts and evidence availability. `inspect-capabilities` is a machine-readable description suitable for exposing through a later MCP resource or tool.

A minimal bundle is:

```json
{
  "schema_version": "0.1",
  "captures": [
    {
      "id": "dom-1",
      "kind": "dom",
      "locator": "document",
      "payload": {"node_count": 42}
    }
  ],
  "measurements": [],
  "runtime_observations": [
    {
      "id": "runtime-1",
      "source_ids": ["dom-1"],
      "statement": "The supplied DOM snapshot reports 42 nodes."
    }
  ],
  "visual_observations": [],
  "interpretations": [],
  "confidence": [],
  "provenance": {
    "created_by": "collector-name",
    "inputs": ["dom-1"]
  }
}
```

Capture payloads are bounded, opaque JSON. Visparse accepts these generic capture kinds:

- `dom`: serialized DOM or a purpose-built DOM inventory
- `css`: computed styles, matched rules, variables, or stylesheet inventories
- `accessibility`: an accessibility tree or audit output
- `runtime`: console, performance, network, state, or other observed runtime facts
- `screenshot`: image identity and metadata; image bytes remain an external artifact
- `video`: video identity, timing, and metadata for motion or interaction evidence; bytes remain external
- `canvas`: dimensions, context metadata, or instrumented canvas state
- `webgl`: context, renderer, extension, draw-call, or resource metadata
- `threejs`: an explicitly collected high-level scene, camera, light, material, or object inventory

Locators need only be stable within the collector's domain. Examples include `document`, `computed:#hero`, `accessibility-tree`, `canvas#scene:webgl2`, and a content-addressed capture URI.

## Evidence layers

The four claim layers are structurally separate.

- `measurements` are finite numeric values read mechanically. Each names one capture, a method, and an optional unit. Model estimates and qualitative values do not belong here.
- `runtime_observations` directly report supplied DOM, CSS, accessibility, runtime, canvas, WebGL, or Three.js evidence.
- `visual_observations` directly report supplied screenshot, canvas, or WebGL appearance evidence.
- `interpretations` cite measurement or observation IDs, never raw captures, and require a separate confidence record with uncertainty and basis.

This contract prevents confidence from turning an interpretation into a measurement. Validation checks global ID uniqueness, exact object shapes, compatible source kinds for observation layers, complete provenance, bounded JSON, finite numbers, and all cross-references. It does not decide whether a statement is true; callers must keep original capture artifacts available for review.

## Progressive Three.js evidence

Generic WebGL and canvas evidence works without Three.js. When a `threejs` capture is supplied, the summary reports `high_level` evidence. When a runtime or WebGL payload explicitly identifies Three.js through conventional instrumentation metadata—such as `technology`, `libraries`, `renderer.library`, or a `globals.THREE` entry—the summary reports `detected`. Detection only says that a high-level Three.js capture may be useful; it does not invent a scene graph.

If neither form is present, the status is `not_available`, not “Three.js absent.” An agent can begin with generic DOM/runtime/canvas/WebGL evidence and request an authorized high-level scene capture only when the collector can provide one.

## Python and tool wrapping

```python
from visparse import inspect_snapshot, inspection_capabilities, summarize_inspection

validated = inspect_snapshot(raw_json)
summary = summarize_inspection(validated)
capabilities = inspection_capabilities()
```

All three functions are deterministic and provider-neutral. A future MCP wrapper can expose the capability descriptor and pass a JSON argument to `inspect_snapshot` without embedding a host-agent reasoning model in Visparse. Browser-side collectors and model adapters remain replaceable boundaries.
