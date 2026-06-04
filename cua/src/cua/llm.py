"""llm.py — live LLM client [code]: the reusable Anthropic seam every role body plugs into.

Implements: contracts.md §1.8 (RoleConfig → API params: Opus 4.x `effort`, no temperature;
            Sonnet/Haiku `temperature`), §1.10 (one TraceEvent per role call);
            decisions/2026-06-02-live-bodies-wave-decisions.md (#1 forced tool-use + local pydantic
            validation; #2 CUA_LIVE toggle, surrogates default, lazy `anthropic` import).
Generic role: maps a RoleConfig + (system, user, schema) to ONE Anthropic call that is forced to return
              JSON conforming to `schema`, validated locally; emits one TraceEvent. OFF by default.
NIH binding: none — the per-role live bodies (LIVE-1..6) live under cua.roles/cua.nih and call
             `complete()`; this module names no domain nouns.
Owner: LIVE-0 (builder 1).

Leak rule (CONVENTIONS rule 1): this file names no domain nouns — it is generic engine infra. It knows
only RoleConfig, a caller-supplied pydantic `schema`, prompt strings, and the TraceRecorder.

Offline + deterministic: importing this module performs NO network call and does NOT import
`anthropic` — the SDK is imported LAZILY inside the single network seam (`_call_model`), reached only
when `is_live()`. With `CUA_LIVE` unset, `is_live()` is False and `complete()` raises `LiveUnavailable`
so the caller falls back to its deterministic surrogate — the offline path and its determinism are
untouched. `ANTHROPIC_API_KEY` is read from the environment by the SDK; it is never logged or committed.
"""

from __future__ import annotations

import os
import sys
import time

from pydantic import BaseModel, ValidationError

from .config import RoleConfig
from .trace import TraceRecorder

# Opus 4.x reasoning effort coexists with tool-use; non-Opus uses temperature. Large default so an Opus
# writer fragment fits; callers may override per role. (Single call here — best-of-N is the driver's job.)
DEFAULT_MAX_TOKENS = 16384

# Retry-with-error-feedback cap: a frontier model returns slightly-off structured output many ways
# (flattened, missing, mistyped); rather than hard-fail after a paid call, re-prompt with the error and
# re-call. 3 total attempts = 1 + 2 retries (decisions/2026-06-02-live-structured-output-robustness.md).
MAX_LIVE_ATTEMPTS = 3


class LiveUnavailable(RuntimeError):
    """Raised by `complete()` when not `is_live()` (CUA_LIVE unset or no key). The caller catches this
    and falls back to its deterministic surrogate — surrogates stay the default (wave decision #2)."""


class LiveProtocolError(RuntimeError):
    """The model returned a response that does not carry the forced tool-call (no `tool_use` block for
    the declared tool). Malformed *fields* surface as pydantic ValidationError instead — never silent."""


class LiveStructuredOutputError(RuntimeError):
    """Raised by `complete()` when the model cannot produce schema-valid structured output within
    `MAX_LIVE_ATTEMPTS` (the retry is exhausted). Carries diagnostics so a hard-fail is legible at a
    glance — `stop_reason` (a `max_tokens` value means TRUNCATION → raise the budget; anything else with
    missing fields means OMISSION), the missing/invalid field list, and a raw tool-input snippet. The
    original ValidationError/LiveProtocolError is chained as `__cause__`."""


def is_live() -> bool:
    """True IFF `CUA_LIVE` is set (non-empty) AND `ANTHROPIC_API_KEY` is present. Default False → the
    deterministic surrogates run and the offline tests stay green (wave decision #2)."""
    return bool(os.environ.get("CUA_LIVE")) and bool(os.environ.get("ANTHROPIC_API_KEY"))


def _verbose() -> bool:
    """Per-call live progress (to STDERR) is ON by default; set `CUA_VERBOSE` to a falsy value
    (`0`/`false`/`no`/`off`/empty) to silence it. This NEVER affects stdout (the offline byte oracle) and
    NEVER fires offline — it is read only inside `complete()`, which is live-only (returns `LiveUnavailable`
    before any progress line when not `is_live()`)."""
    val = os.environ.get("CUA_VERBOSE")
    if val is None:
        return True
    return val.strip().lower() not in ("", "0", "false", "no", "off")


def _progress(message: str) -> None:
    """Emit one live-progress line to STDERR, flushed (so the operator sees a long live run advancing in
    real time, not buffered). STDERR-only + live-only → the offline oracle's stdout is untouched."""
    print(message, file=sys.stderr, flush=True)


def _is_opus(model_id: str) -> bool:
    """Opus 4.x rejects temperature/top_p/top_k (400) and uses `effort` instead (§1.8/§2.4). Detect by
    family so it holds across 4.7/4.8; Sonnet/Haiku take the temperature branch."""
    return "opus" in model_id.lower()


def _tool_name(schema: type[BaseModel]) -> str:
    """A stable, API-valid tool name (`^[A-Za-z0-9_-]{1,64}$`) derived from the schema. Pydantic model
    names are valid identifiers, so the class name satisfies the pattern."""
    name = getattr(schema, "__name__", "") or ""
    return name if name.replace("_", "").replace("-", "").isalnum() and name else "structured_output"


def _build_request(
    config: RoleConfig,
    *,
    system: str,
    user: str,
    schema: type[BaseModel],
    tool_name: str,
    max_tokens: int,
) -> dict:
    """PURE: assemble the `messages.create(**kwargs)` request dict. No network, no `anthropic` import —
    unit-testable by inspection. Structured output = ONE forced tool whose `input_schema` is `schema`'s
    JSON Schema (wave decision #1). Sampling maps per §1.8: Opus → `output_config.effort` (NO
    temperature); Sonnet/Haiku → `temperature` (NO effort)."""
    tool = {
        "name": tool_name,
        "description": f"Return the result strictly as a {getattr(schema, '__name__', 'structured')} object.",
        "input_schema": schema.model_json_schema(),
    }
    request: dict = {
        "model": config.model_id,
        "max_tokens": max_tokens,
        "system": system,
        "messages": [{"role": "user", "content": user}],
        "tools": [tool],
        "tool_choice": {"type": "tool", "name": tool_name},  # force the tool → structured output
    }
    if _is_opus(config.model_id):
        if config.effort is not None:
            request["output_config"] = {"effort": config.effort}  # Opus reasoning depth (SDK OutputConfig)
    else:
        if config.temperature is not None:
            request["temperature"] = config.temperature
    return request


def _call_model(request: dict):
    """The ONLY network seam (imports `anthropic` LAZILY; tests monkeypatch this). The SDK reads
    `ANTHROPIC_API_KEY` from the environment — the key is never passed through code or logged."""
    import anthropic  # lazy: importing cua.llm must not import anthropic or touch the network

    client = anthropic.Anthropic()  # api_key sourced from env by the SDK
    return client.messages.create(**request)


def _extract_tool_args(response, tool_name: str) -> dict:
    """PURE: pull the forced tool-call's input dict out of the response content blocks. Raises
    LiveProtocolError if the model didn't emit the `tool_name` tool_use block (no silent pass)."""
    for block in getattr(response, "content", None) or []:
        if getattr(block, "type", None) == "tool_use" and getattr(block, "name", None) == tool_name:
            args = getattr(block, "input", None)
            if isinstance(args, dict):
                return args
    raise LiveProtocolError(f"response carried no tool_use block named {tool_name!r}")


def _usage_tokens(response) -> int | None:
    """Real total token count from the response usage, for the TraceEvent (None if absent)."""
    usage = getattr(response, "usage", None)
    if usage is None:
        return None
    return (getattr(usage, "input_tokens", 0) or 0) + (getattr(usage, "output_tokens", 0) or 0)


def _find_tool_use(response, tool_name: str):
    """The (id, name, input) of the forced tool_use block, or None if the model emitted none."""
    for block in getattr(response, "content", None) or []:
        if getattr(block, "type", None) == "tool_use" and getattr(block, "name", None) == tool_name:
            return getattr(block, "id", None) or "toolu_retry", tool_name, getattr(block, "input", {})
    return None


def _assistant_text(response) -> str:
    """The text the model returned (to echo its turn when it emitted no tool call)."""
    parts = [
        getattr(b, "text", "")
        for b in (getattr(response, "content", None) or [])
        if getattr(b, "type", None) == "text"
    ]
    return " ".join(p for p in parts if p)


def _validation_fields(exc: Exception) -> str:
    """For a pydantic `ValidationError`, a concise 'loc (type)' list (e.g. 'central_hypothesis (missing),
    innovation (missing)') so the re-prompt names EXACTLY which fields to fix; '' for any other error."""
    errors = getattr(exc, "errors", None)
    if not callable(errors):
        return ""
    try:
        parts = [
            f"{'.'.join(str(x) for x in e.get('loc', ())) or '?'} ({e.get('type', 'invalid')})"
            for e in exc.errors()
        ]
    except Exception:
        return ""
    return ", ".join(parts)


def _feedback_turns(response, tool_name: str, exc: Exception) -> list[dict]:
    """The retry turns: echo the model's invalid turn, then a user turn carrying the error so it corrects
    its structured output. Canonical Anthropic `tool_result(is_error=True)` when a tool_use block exists;
    else a plain-text correction (there is no tool_use_id to reference). On a `ValidationError` the
    missing/invalid fields are named EXPLICITLY (a persistent omission needs more than the raw dump). No
    key/URL is ever included."""
    err = str(exc)
    if len(err) > 800:
        err = err[:800] + " …"
    fields = _validation_fields(exc)
    named = f"Missing or invalid required fields: {fields}. " if fields else ""
    found = _find_tool_use(response, tool_name)
    if found is not None:
        tool_use_id, name, args = found
        return [
            {"role": "assistant", "content": [{"type": "tool_use", "id": tool_use_id, "name": name, "input": args}]},
            {"role": "user", "content": [{
                "type": "tool_result",
                "tool_use_id": tool_use_id,
                "is_error": True,
                "content": (
                    f"Invalid `{tool_name}` arguments. {named}You MUST include EVERY field of the "
                    f"`{tool_name}` schema, each with a non-empty value. Details: {err}. Re-call "
                    f"`{tool_name}` now with all fields present and matching its schema exactly."
                ),
            }]},
        ]
    return [
        {"role": "assistant", "content": _assistant_text(response) or "(no tool call)"},
        {"role": "user", "content": f"You did not call the required tool `{tool_name}`: {err}. You MUST call `{tool_name}` with EVERY field of its schema present."},
    ]


def _failure_diagnostics(exc: Exception, stop_reason, response, tool_name: str) -> str:
    """A legible one-line diagnostic for a persistent structured-output failure: the attempt cap, the
    `stop_reason` (with a TRUNCATION hint when `max_tokens`), the missing/invalid fields, the original
    error (truncated), and a snippet of the raw tool input — so a future hard-fail tells truncation from
    omission at a glance. No key/URL is ever included."""
    err = str(exc)
    if len(err) > 400:
        err = err[:400] + " …"
    found = _find_tool_use(response, tool_name)
    if found is not None:
        snippet = str(found[2])
        raw = "tool_use input: " + (snippet[:300] + " …" if len(snippet) > 300 else snippet)
    else:
        raw = "no tool_use block in the final response"
    hint = " (TRUNCATION — raise max_tokens)" if stop_reason == "max_tokens" else ""
    parts = [f"structured output failed after {MAX_LIVE_ATTEMPTS} attempts", f"stop_reason={stop_reason}{hint}"]
    fields = _validation_fields(exc)
    if fields:
        parts.append(f"missing/invalid: {fields}")
    parts.append(f"{type(exc).__name__}: {err}")
    parts.append(raw)
    return " | ".join(parts)


def complete(
    config: RoleConfig,
    *,
    system: str,
    user: str,
    schema: type[BaseModel],
    trace_role: str,
    recorder: TraceRecorder,
    round: int = 0,
    input_refs: tuple[str, ...] = ("system", "user"),
    output_ref: str | None = None,
    max_tokens: int = DEFAULT_MAX_TOKENS,
) -> BaseModel:
    """One Anthropic role call, forced to return JSON conforming to `schema`, validated locally; returns
    the validated instance. Records exactly ONE TraceEvent (§1.10) for the call — role=`trace_role`,
    model/sampling echoed from `config`, real token usage (summed across retries).

    Retry-with-error-feedback: on a `LiveProtocolError` (no tool block) or pydantic `ValidationError`,
    re-prompt the model with the error (its invalid turn + a `tool_result(is_error=True)` that NAMES the
    missing/invalid fields; the canonical Anthropic tool-error pattern) and re-call — up to
    `MAX_LIVE_ATTEMPTS` total, then raise `LiveStructuredOutputError` (diagnostics — stop_reason, fields,
    a raw-input snippet — chaining the last error). This generalizes over every shape miss (flattened,
    missing, mistyped); the schema-level str→object coercion stays as a fast-path that avoids a retry.

    ONE event per call holds (the §1.10 / trace-guard invariant): record once at the end (success OR final
    failure), tokens summed across attempts, `decision` noting the attempt count. Raises `LiveUnavailable`
    when not `is_live()` (the caller falls back to its surrogate). `anthropic` is imported lazily in
    `_call_model`; no key/URL is logged."""
    if not is_live():
        raise LiveUnavailable("CUA_LIVE unset or ANTHROPIC_API_KEY missing — use the surrogate")

    tool_name = _tool_name(schema)
    request = _build_request(
        config, system=system, user=user, schema=schema, tool_name=tool_name, max_tokens=max_tokens
    )

    # Live progress (STDERR, live-only): one line when the (long) call starts so a multi-minute live run is
    # visibly advancing rather than apparently hung — observability only, no behavior/trace change.
    verbose = _verbose()
    started = time.monotonic()
    if verbose:
        _progress(f"[live] {trace_role} {config.model_id} round={round} start …")

    total_tokens = 0
    attempt = 0
    last_stop = None
    instance: BaseModel | None = None
    error: Exception | None = None
    while attempt < MAX_LIVE_ATTEMPTS:
        attempt += 1
        response = _call_model(request)
        last_stop = getattr(response, "stop_reason", None)
        used = _usage_tokens(response)
        if used:
            total_tokens += used  # sum the cost of every attempt, including the failed ones
        try:
            instance = schema.model_validate(_extract_tool_args(response, tool_name))
            error = None
            break
        except (LiveProtocolError, ValidationError) as exc:
            error = exc
            if attempt < MAX_LIVE_ATTEMPTS:
                # re-prompt with the error and re-call (the loop re-enters with the grown conversation)
                request = {**request, "messages": [*request["messages"], *_feedback_turns(response, tool_name, exc)]}

    # Live progress (STDERR, live-only): one line when the call finishes — tokens, attempts, elapsed — so
    # the operator sees each role complete (and the cost) as the run advances.
    if verbose:
        status = "done" if error is None else f"FAILED:{type(error).__name__}"
        _progress(
            f"[live] {trace_role} {config.model_id} {status} "
            f"{total_tokens or 0} tok, {attempt} attempt(s), {time.monotonic() - started:.1f}s"
        )

    decision = f"live tool_use={tool_name} stop={last_stop} attempts={attempt}"
    if error is not None:
        decision += f" FAILED:{type(error).__name__}"
    recorder.record(  # ONCE — success or final failure — so the trace-guard sees exactly one event/call
        round=round,
        role=trace_role,
        model=config.model_id,
        sampling=config.sampling_descriptor(),
        input_refs=input_refs,
        output_ref=output_ref or f"{trace_role}:live",
        tokens=total_tokens or None,
        decision=decision,
    )
    if error is not None:
        # Raise a diagnostic-bearing error (stop_reason → truncation-vs-omission, named fields, raw
        # snippet) so a hard-fail is legible; the original ValidationError/LiveProtocolError is the cause.
        raise LiveStructuredOutputError(_failure_diagnostics(error, last_stop, response, tool_name)) from error
    return instance
