"""Deterministic DESIGN.md renderer with explicit transfer policy."""

from __future__ import annotations

import html
import re
import copy

from .contracts import check, number
from .dna import DIMENSIONS, FEATURES, feature_groups, group_status, validate_dna

RENDER_POLICY_VERSION = "0.1"
TEMPLATES = {
    "color.accent_usage": {"actions": "Prefer accent color for primary actions.", "decorative": "Allow accent color in decorative surfaces.", "mixed": "Balance action and decorative accent usage."},
    "component.card_usage": {"low": "Use cards selectively for distinct objects.", "medium": "Use cards where they clarify grouping.", "high": "Use a consistent card grammar for repeated objects."},
    "component.grouping": {"spacing": "Prefer whitespace to separate groups.", "borders": "Prefer thin borders to separate groups.", "cards": "Prefer cards for distinct groups.", "mixed": "Combine grouping treatments according to component role."},
    "layout.alignment": {"left": "Maintain a dominant left alignment.", "center": "Maintain a dominant centered alignment.", "right": "Maintain a dominant right alignment.", "mixed": "Use multiple alignment axes deliberately."},
    "layout.hero_pattern": {"centered": "Compose the hero around a central axis.", "split": "Use a split hero composition.", "asymmetric": "Preserve asymmetric visual balance in the hero.", "stacked": "Stack the major hero elements."},
    "responsive.transformation": {"stack": "Stack the relevant elements at the specified viewport.", "drawer": "Adapt the relevant navigation to a drawer.", "carousel": "Adapt the relevant repeated elements to a carousel.", "full-screen": "Adapt the relevant panel to a full-screen presentation.", "unchanged": "Preserve the observed structure at the specified viewport."},
}


def _escape(value: str) -> str:
    # Keep supplied prose on a single Markdown line; it is still untrusted
    # design data, never a reason for the host agent to execute instructions.
    value = " ".join(value.split())
    return re.sub(r"([\\`*\[\]#])", r"\\\1", html.escape(value, quote=False))


def _scope(scope: dict) -> str:
    return ", ".join(f"{k}={_escape(v)}" for k, v in scope.items())


def render_design(dna: dict, *, mode: str = "compact", min_confidence: float = 0.6,
                  generation_safe: bool = False) -> str:
    validate_dna(dna)
    check(mode in {"compact", "full"}, "mode must be compact or full")
    number(min_confidence, 0, 1)
    if generation_safe:
        dna = copy.deepcopy(dna)
        # Free-form scope labels can themselves contain source URLs or branding.
        # Alias subjects and constrain viewport/state strings in the export.
        subjects = {s: f"role-{i}" for i, s in enumerate(sorted({f["scope"]["subject"] for f in dna["features"]}), 1)}
        for feature in dna["features"]:
            scope = feature["scope"]
            if not re.fullmatch(r"(?:page|visible-sample:tag=[a-z][a-z0-9]*)", scope["subject"]):
                scope["subject"] = subjects[scope["subject"]]
            if not re.fullmatch(r"[0-9]{1,4}x[0-9]{1,4}", scope["viewport"]):
                scope["viewport"] = "unspecified"
            if scope["state"] not in {"default", "hover", "focus", "active", "disabled"}:
                scope["state"] = "supplied-state"
    lines = ["# Design guidance", "", f"Rendering policy: {RENDER_POLICY_VERSION}.", "",
             "Apply these design principles to the new product brief. Preserve its own content, branding, assets, and information architecture.", "",
             "SHOULD expresses transfer guidance, not proof of a universal source rule. Scope and uncertainty qualify every recommendation.", ""]
    groups = feature_groups(dna)
    gaps = []
    for dimension in DIMENSIONS:
        rules = []
        for key in sorted(groups):
            group = groups[key]
            feature = group[0]
            if FEATURES[feature["name"]][0] != dimension:
                continue
            status = group_status(group, min_confidence)
            if status != "known":
                gaps.append(f"{feature['name']} ({_scope(feature['scope'])}): {status}")
                continue
            name, value = feature["name"], feature["value"]
            if generation_safe and FEATURES[name][1] == "text":
                gaps.append(f"{name}: free-text value omitted from generation export")
                continue
            if name in TEMPLATES:
                wording = TEMPLATES[name][value]
            elif isinstance(value, (int, float)):
                unit = feature["unit"] or ""
                if name in {"surface.shadow_usage", "surface.border_usage"}:
                    wording = f"Use the observed {name} fraction ({value:.3g}) as a scoped tendency; it does not prohibit other treatments."
                else:
                    wording = f"Use {name} around {value:.4g}{unit} as a starting point for the corresponding role."
            else:
                wording = f"Preserve the {name} tendency: {_escape(str(value))}."
            origin = "inferred" if any(f["origin"] == "inferred" for f in group) else feature["origin"]
            levels = [f["confidence"] for f in group if f["confidence"] is not None]
            qualifier = f"{origin}" + (f", confidence={min(levels):.2f}" if levels else "")
            rules.append(f"- SHOULD: {wording} [{qualifier}; {_scope(feature['scope'])}]")
            if not generation_safe and "uncertainty" in feature:
                rules.append(f"  Uncertainty: {_escape(feature['uncertainty'])}")
            if mode == "full" and not generation_safe:
                rules.append(f"  Evidence: {_escape(', '.join(sorted({e for f in group for e in f['evidence_ids']})))}. Method: {_escape(feature['method'])}.")
        if rules:
            lines.extend(["## " + dimension.replace("_", " ").title(), "", *rules, ""])
    if not generation_safe:
        principles = []
        for principle in dna["principles"]:
            if principle["confidence"] is None or principle["confidence"] < min_confidence:
                gaps.append(f"Principle {principle['id']}: " + ("unknown_confidence" if principle["confidence"] is None else "low_confidence"))
                continue
            principles.append(f"- {principle['strength']}: {_escape(principle['statement'])} [basis={principle['basis']}; confidence={principle['confidence']:.2f}; {_scope(principle['scope'])}]")
            if mode == "full":
                principles.append(f"  Evidence: {_escape(', '.join(principle['evidence_ids']))}.")
        if principles:
            lines.extend(["## Supplied principles", "", *principles, ""])
        gaps.extend(dna["gaps"])
    else:
        lines.extend(["Free-text principles, evidence IDs, provenance, and raw source locators are omitted from this generation export.", ""])
    present = {FEATURES[g[0]["name"]][0] for g in groups.values() if group_status(g, min_confidence) == "known"}
    gaps.extend(f"{d}: no comparable supported features" for d in DIMENSIONS if d not in present)
    if gaps:
        lines.extend(["## Known gaps", "", *["- " + _escape(g) for g in sorted(set(gaps))], ""])
    return "\n".join(lines)
