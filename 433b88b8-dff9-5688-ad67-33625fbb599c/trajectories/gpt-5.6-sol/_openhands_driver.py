#!/usr/bin/env python3
# Copyright (c) 2026 ByteDance Ltd. and/or its affiliates
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""In-container entrypoint for the OpenHands agent.

The other two agents are CLIs: sforge installs a binary and runs a command.
The OpenHands agent is a *library*, so this file is the command — it is shipped
into the work container by :mod:`sforge.harness.agent.openhands` and invoked as
``python openhands_driver.py <prompt_file>``.

It does three jobs, and only these three:

1. Build an ``LLM`` pointed at whichever OAuth bridge the host chose, wrap it in
   an ``Agent`` with the terminal + file-editor tools, and run it in ``cwd``.
2. Emit the transcript **as Claude-Code stream-json on stdout**.  sforge pipes
   the agent's stdout into ``agent_output.txt``, which is the file that
   ``refine/distill.py`` and the visualizer both read.  Matching the existing
   format is deliberate: it means the participation/void logic in
   ``refine/runner.py`` keeps working with no new parser and no new format
   detector.  We control the writer, so we write what the readers already know.
3. Install a Stop hook that refuses to let the agent stop.  The SDK consults
   Stop hooks when the agent reports FINISHED and, on a ``deny``, injects the
   reason as a user message and keeps looping — the same mechanism the Claude
   Code and Codex agents rely on to spend their whole time budget.

Everything is configured through ``OH_*`` environment variables so the sforge
agent class stays a thin, declarative mapping (see ``openhands.py``).
"""

from __future__ import annotations

import json
import os
import signal
import sys
import time
import uuid

# The SDK prints a multi-line ASCII banner on import.  It would land in
# agent_output.txt ahead of the first JSON line, and the format detectors in
# distill.py / scanner.py sniff the *head* of that file.  Suppress it before
# the import, not after.
os.environ.setdefault("OPENHANDS_SUPPRESS_BANNER", "1")

from pydantic import SecretStr  # noqa: E402

from openhands.sdk import LLM, Agent, Conversation, get_logger  # noqa: E402
from openhands.sdk.context.condenser import (  # noqa: E402
    LLMSummarizingCondenser,
)
from openhands.sdk.event import Event  # noqa: E402
from openhands.sdk.event.condenser import Condensation  # noqa: E402
from openhands.sdk.event.llm_convertible import (  # noqa: E402
    ActionEvent,
    AgentErrorEvent,
    MessageEvent,
    ObservationEvent,
)
from openhands.sdk.hooks import (  # noqa: E402
    HookConfig,
    HookDefinition,
    HookMatcher,
    HookType,
)
from openhands.tools.preset.default import get_default_tools  # noqa: E402

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# stream-json emitters
# ---------------------------------------------------------------------------
#
# Only the fields the downstream readers actually consume are emitted.  See
# refine/distill.py::_transcript and visualizer/parsers/agent_output.py::parse
# for the contract; the shapes below are the subset both agree on.


def _emit(obj: dict) -> None:
    """One event, one line, flushed — the transcript is read while it grows."""
    sys.stdout.write(json.dumps(obj, default=str) + "\n")
    sys.stdout.flush()


def _emit_assistant(blocks: list[dict], usage: dict | None = None) -> None:
    message: dict = {"role": "assistant", "content": blocks}
    if usage:
        message["usage"] = usage
    _emit({"type": "assistant", "message": message, "uuid": str(uuid.uuid4())})


# ---------------------------------------------------------------------------
# token accounting
# ---------------------------------------------------------------------------
#
# Usage has to ride on the assistant events, not just on a final `result`.
# sforge ends a run by sending SIGTERM to the agent process when the timeout
# expires, and the default disposition for SIGTERM tears the interpreter down
# without unwinding `finally` — so a run that ends the way EVERY run in this
# harness ends would report a `result` event that was never written, and a
# token ledger of zero.  The other two agents avoid this by reporting usage
# per turn as they go; so do we.
#
# The SDK exposes only a *cumulative* counter, while the readers accumulate
# what they are given (`refine/distill.py::_add_usage` does `+=`).  Emitting
# the cumulative figure each turn would therefore record the sum of prefix
# sums.  Every emission below is a delta against what has already been sent,
# which also matches Claude Code's semantics, where a message's `usage` counts
# that message alone.

# How full the conversation gets before the older middle is summarised away.
#
# The SDK's own default is 80 events, which measured out at a ~100k-token prompt
# ceiling — only a tenth of this model's 1M window, and it showed: with 80 the
# run held context fine but flattened in its second half and finished at 0.266,
# where the same task WITHOUT any condenser reached 0.312 while running at
# ~263k tokens.  200 puts the ceiling near 250k, which is roughly the working
# memory that better run actually had, while still bounding growth.  That is the
# whole reason for the number: match the context the stronger run operated at,
# and keep the ceiling.
#
# Measured rate was ~1,251 tokens per event, so the projection is
# `max_size * 1251` — retune from that, not from guesswork, and remember the
# run-to-run spread on these tasks is wide enough (0.21-0.38 observed) that one
# pair of runs cannot settle a 0.05 difference.
CONDENSER_MAX_SIZE = 200
# The task prompt lives in the first few events and must survive every
# condensation, or the agent forgets what it was asked to do.
CONDENSER_KEEP_FIRST = 4

_conversation_box: dict = {}
_usage_sent = {
    "prompt_tokens": 0,
    "completion_tokens": 0,
    "cache_read_tokens": 0,
    "cache_write_tokens": 0,
}


def _cumulative_usage() -> dict | None:
    conversation = _conversation_box.get("conversation")
    if conversation is None:
        return None
    try:
        metrics = conversation.conversation_stats.get_combined_metrics()
        usage = getattr(metrics, "accumulated_token_usage", None)
        if usage is None:
            return None
        return {k: int(getattr(usage, k, 0) or 0) for k in _usage_sent}
    except Exception as exc:
        logger.debug("token usage unavailable: %s", exc)
        return None


def _usage_delta() -> dict | None:
    """Tokens spent since the last emission, in stream-json field names."""
    current = _cumulative_usage()
    if current is None:
        return None
    delta = {k: current[k] - _usage_sent.get(k, 0) for k in current}
    if not any(v for v in delta.values()):
        return None
    _usage_sent.update(current)
    # The SDK's `prompt_tokens` is the TOTAL prompt, cached portion included
    # (telemetry.py takes it raw and reads `cache_read` out of
    # prompt_tokens_details.cached_tokens, a subset of it).  Claude Code's
    # stream-json — the format this file claims to emit — keeps the two
    # disjoint, so `input_tokens` there EXCLUDES cache reads.  Emitting the
    # inclusive figure under the exclusive field name made the transcript and
    # the bridge log disagree by exactly the cached amount on the same run
    # (472,281 vs 386,532 on a verified muse run: a 17% gap that is pure
    # convention, not measurement).  Subtract, so the two agree.
    uncached = delta["prompt_tokens"] - delta["cache_read_tokens"]
    return {
        # Clamped: these are deltas of two independently reported counters, and
        # a provider that revises one out of step with the other must not be
        # able to push a negative into the readers' running totals.
        "input_tokens": max(uncached, 0),
        "output_tokens": delta["completion_tokens"],
        "cache_read_input_tokens": delta["cache_read_tokens"],
        "cache_creation_input_tokens": delta["cache_write_tokens"],
    }


def _emit_user(blocks: list[dict]) -> None:
    _emit(
        {
            "type": "user",
            "message": {"role": "user", "content": blocks},
            "uuid": str(uuid.uuid4()),
        }
    )


def _text_blocks(seq) -> list[dict]:
    """TextContent[] -> stream-json text blocks, dropping empties."""
    out = []
    for item in seq or []:
        text = getattr(item, "text", None)
        if text is None and isinstance(item, str):
            text = item
        if text and text.strip():
            out.append({"type": "text", "text": text})
    return out


def _reasoning_blocks(event) -> list[dict]:
    """Every field the SDK can put the model's thinking in, as text blocks.

    Reading only ``thought`` — which this driver did originally — is correct for
    a model that narrates alongside its tool calls, and silently lossy for a
    reasoning model, which puts its thinking somewhere else entirely.  A
    verified muse-spark run produced 21 tool calls and ZERO prose: a transcript
    of what the agent did with no record of why, which is exactly what the
    trajectories are supposed to capture.

    The four sources, and who fills each:

    * ``thought`` — models that emit prose beside a tool call.
    * ``reasoning_content`` — chat-completions reasoning models.  LiteLLM maps
      the provider's non-standard ``message.reasoning`` onto this field in
      ``_extract_reasoning_content``, which is how Meta/OpenRouter's summary
      arrives; the SDK then carries it to ActionEvent.reasoning_content.
    * ``thinking_blocks`` — Anthropic extended thinking.  ``RedactedThinkingBlock``
      is deliberately skipped: its ``data`` is an opaque ciphertext, not prose.
    * ``responses_reasoning_item`` — the OpenAI Responses shape, which is the
      path the codex bridge takes.  ``encrypted_content`` is skipped for the
      same reason as redacted blocks.

    Collected rather than chosen between: a model may populate more than one,
    and dropping the extras is the bug this function exists to fix.
    """
    out = _text_blocks(getattr(event, "thought", None))

    content = getattr(event, "reasoning_content", None)
    if isinstance(content, str) and content.strip():
        out.append({"type": "text", "text": content})

    for block in getattr(event, "thinking_blocks", None) or []:
        text = getattr(block, "thinking", None)
        if isinstance(text, str) and text.strip():
            out.append({"type": "text", "text": text})

    item = getattr(event, "responses_reasoning_item", None)
    if item is not None:
        for part in list(getattr(item, "summary", None) or []) + list(
            getattr(item, "content", None) or []
        ):
            if isinstance(part, str) and part.strip():
                out.append({"type": "text", "text": part})

    return out


def _tool_input(action) -> dict:
    """Best-effort dict of the tool call's arguments.

    Only used for display and for distill.py's `_tool_call()` summary, which
    looks for command/file_path/path/pattern/query/description.  A tool whose
    schema uses none of those still renders as a bare name, which is the same
    thing distill does for the other agents.
    """
    if action is None:
        return {}
    for attr in ("model_dump",):
        dump = getattr(action, attr, None)
        if callable(dump):
            try:
                return dump(exclude_none=True)
            except Exception:
                pass
    return {}


def _observation_text(event: ObservationEvent) -> str:
    obs = getattr(event, "observation", None)
    for attr in ("to_llm_content", "agent_observation", "text", "content"):
        val = getattr(obs, attr, None)
        if callable(val):
            try:
                val = val()
            except Exception:
                continue
        if isinstance(val, str) and val.strip():
            return val
        if isinstance(val, (list, tuple)):
            joined = "\n".join(
                getattr(b, "text", "") for b in val if getattr(b, "text", "")
            )
            if joined.strip():
                return joined
    return str(obs)


def _make_callback():
    """Translate SDK events into stream-json as they happen.

    The mapping is intentionally lossy in the same places the Claude Code
    transcript is lossy: thinking is folded into text, and tool results are
    truncated by the readers rather than here.
    """

    def on_event(event: Event) -> None:
        try:
            if isinstance(event, ActionEvent):
                blocks = _reasoning_blocks(event)
                blocks.append(
                    {
                        "type": "tool_use",
                        "id": event.tool_call_id or str(uuid.uuid4()),
                        "name": event.tool_name,
                        "input": _tool_input(getattr(event, "action", None)),
                    }
                )
                _emit_assistant(blocks, _usage_delta())

            elif isinstance(event, ObservationEvent):
                _emit_user(
                    [
                        {
                            "type": "tool_result",
                            "tool_use_id": event.tool_call_id,
                            "content": _observation_text(event),
                        }
                    ]
                )

            elif isinstance(event, MessageEvent):
                # Same reason as the ActionEvent branch: a reasoning model's
                # thinking rides on the message, not in its content blocks.
                blocks = _reasoning_blocks(
                    getattr(event, "llm_message", None)
                ) + _text_blocks(getattr(event.llm_message, "content", None))
                if not blocks:
                    return
                # source == "agent" is the model talking; "user"/"environment"
                # is the harness talking back (including the Stop-hook feedback
                # that keeps the loop alive), and both belong in the record.
                if event.source == "agent":
                    _emit_assistant(blocks, _usage_delta())
                else:
                    _emit_user(blocks)

            elif isinstance(event, Condensation):
                # Context compaction is otherwise invisible: it changes what the
                # model can see, costs a summarisation call, and leaves no trace
                # in the transcript.  A one-line note makes it auditable after
                # the fact — which run compacted, how often, and how much it
                # dropped each time.
                dropped = len(getattr(event, "forgotten_event_ids", ()) or ())
                _emit_user(
                    [
                        {
                            "type": "text",
                            "text": f"[context condensed] summarised and dropped "
                                    f"{dropped} earlier events",
                        }
                    ]
                )

            elif isinstance(event, AgentErrorEvent):
                _emit_user(
                    [
                        {
                            "type": "text",
                            "text": f"[agent error] {getattr(event, 'error', event)}",
                        }
                    ]
                )
        except Exception as exc:  # never let the transcript kill the run
            logger.warning("transcript callback failed: %s", exc)

    return on_event


# ---------------------------------------------------------------------------
# stop hook
# ---------------------------------------------------------------------------


STOP_HOOK_MARKER = "/tmp/sforge-openhands-stophook.json"


def _stop_hook_config() -> HookConfig | None:
    """Refuse the agent's request to stop, the way the other two agents do.

    The SDK runs the hook as a shell command and reads a JSON verdict from its
    stdout; ``decision: deny`` sets ``should_continue = False``, which
    LocalConversation.run() turns into "flip back to RUNNING and keep going".
    Exit status is irrelevant on this path — only the verdict is read — so the
    command is a single echo with no script file to ship.

    Presence of the marker file is what enables the hook.  sforge signals
    ``--disable-stop-hook`` by *not calling* ``install_stop_hook``, so there is
    no env var to read: the agent class writes this file only when the hook is
    wanted, and its absence is the disable.
    """
    marker = os.environ.get("OH_STOP_HOOK_FILE", STOP_HOOK_MARKER)
    try:
        with open(marker, encoding="utf-8") as fh:
            reason = (json.load(fh) or {}).get("reason") or ""
    except (OSError, ValueError):
        return None
    if not reason:
        return None

    verdict = json.dumps({"decision": "deny", "reason": reason})
    return HookConfig(
        stop=[
            HookMatcher(
                matcher="*",
                hooks=[
                    HookDefinition(
                        type=HookType.COMMAND,
                        command=f"echo {json.dumps(verdict)}",
                        timeout=30,
                    )
                ],
            )
        ]
    )


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ[name])
    except (KeyError, ValueError):
        return default


_result_emitted = False


def _emit_result(started: float, *, is_error: bool) -> None:
    """Close the transcript with a `result` event, at most once.

    Carries only the tokens not already reported on an assistant event, so the
    readers' running total lands on the true figure rather than double-counting
    what the turns already accounted for.
    """
    global _result_emitted
    if _result_emitted:
        return
    _result_emitted = True
    _emit(
        {
            "type": "result",
            "subtype": "error" if is_error else "success",
            "is_error": is_error,
            "duration_ms": int((time.time() - started) * 1000),
            "usage": _usage_delta() or {},
        }
    )


def _install_sigterm_handler(started: float) -> None:
    """Best-effort closing event if this process is signalled directly.

    NOT the reason token accounting survives a timeout — that is the per-turn
    usage above, and it has to be, because on the Docker backend this handler
    never runs.  sforge execs the agent as ``bash -c <cmd>`` and its timeout
    sends SIGTERM to *bash*, which does not forward it to the Python child, so
    the signal never arrives here.  A verified timed-out run ends with a
    ``tool_result`` and no ``result`` event, which is fine: nothing reads
    ``result_events`` (see refine/distill.py), and Claude Code's own transcripts
    do not always carry one either.

    Kept because it costs nothing and does fire wherever the process is
    signalled directly rather than through a shell.  It does the minimum and
    exits — no conversation teardown, which can block on a running tool.
    """

    def _on_term(signum, frame):  # noqa: ANN001
        _emit_result(started, is_error=False)
        os._exit(128 + signum)

    try:
        signal.signal(signal.SIGTERM, _on_term)
    except (ValueError, OSError) as exc:
        logger.warning("could not install SIGTERM handler: %s", exc)


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: openhands_driver.py <prompt_file>", file=sys.stderr)
        return 2

    prompt = open(argv[1], encoding="utf-8").read()

    model = os.environ.get("OH_MODEL") or ""
    if not model:
        print("OH_MODEL is not set", file=sys.stderr)
        return 2

    workspace = os.environ.get("OH_WORKSPACE") or os.getcwd()
    max_iterations = _env_int("OH_MAX_ITERATIONS", 100000)

    llm_kwargs: dict = {
        "model": model,
        "usage_id": "sforge-agent",
        # The bridge terminates a run's credential on a cap; retrying inside the
        # SDK would race sforge's own resume/rotate path, which is the one that
        # can actually swap accounts.  Keep the SDK's retries short.
        "num_retries": _env_int("OH_NUM_RETRIES", 3),
        # The SDK defaults this to 300s, which sits BELOW the bridge's ceiling
        # for a single upstream attempt -- so a healthy long turn blew the
        # client deadline while the bridge was still legitimately waiting, and
        # the SDK tore the conversation down (2026-09-03, arc_compiler_runtime,
        # twice).  Keep it above the bridge's non-stream caps (read 600 /
        # request 900) so a genuine stall comes back as a bridge 502 we can
        # read, not as an opaque client timeout.
        "timeout": _env_int("OH_REQUEST_TIMEOUT", 1800),
    }
    if os.environ.get("OH_BASE_URL"):
        llm_kwargs["base_url"] = os.environ["OH_BASE_URL"]
    if os.environ.get("OH_API_KEY"):
        llm_kwargs["api_key"] = SecretStr(os.environ["OH_API_KEY"])
    # "auto" resolves the endpoint from model metadata, which does not know our
    # bridge aliases.  The agent class sets this explicitly per provider.
    api_mode = os.environ.get("OH_API_MODE")
    if api_mode:
        llm_kwargs["api_mode"] = api_mode

    # The SDK already defaults this to "high" for every model, so leaving it
    # unset is NOT the same as leaving it off — it is a choice, just an implicit
    # one.  Stating it lets a provider that supports a higher tier ask for it
    # (Muse Spark tops out at "xhigh") and, more usefully, puts the thinking
    # budget in the transcript below, where a cross-model comparison can see it
    # instead of assuming the lanes matched.
    reasoning_effort = os.environ.get("OH_REASONING_EFFORT")
    if reasoning_effort:
        llm_kwargs["reasoning_effort"] = reasoning_effort

    # Nothing special is needed for the codex bridge here, and that is on
    # purpose.  The ChatGPT-subscription endpoint behind it refuses non-streamed
    # requests and rejects several standard Responses parameters, but both are
    # handled bridge-side (see codex_oauth/bridge.py: strip_unsupported_params
    # and _proxy_collapsed).  Asking for streaming from this end does not work:
    # the SDK only drains an SSE Responses reply in `is_subscription` mode, which
    # also makes it run its own OpenAI login and ignore the bridge entirely —
    # without that mode it raises "Expected ResponsesAPIResponse, got
    # ...StreamingIterator".  So the client stays a plain buffered caller.
    if os.environ.get("OH_MODEL_CANONICAL"):
        llm_kwargs["model_canonical_name"] = os.environ["OH_MODEL_CANONICAL"]

    llm = LLM(**llm_kwargs)

    # Browser tools pull a headless browser that no EdgeBench task needs and
    # that network isolation would block anyway.
    tools = get_default_tools(enable_browser=False)

    # Without a condenser the conversation is replayed in full on every turn, so
    # the prompt grows for as long as the run does.  Measured on a 90-minute run:
    # ~1,400 tokens added per turn, 16k at the first turn and 263k at the last,
    # with no ceiling in sight — a full-length run would exhaust the context
    # window partway through.  The condenser summarises the older middle of the
    # conversation once it grows past `max_size` events, keeping the first couple
    # (the task prompt) verbatim, which turns that climb into a plateau.
    #
    # `Agent(...)` defaults this to None; the SDK's own `get_default_agent()`
    # wires it exactly as below.  The separate `usage_id` keeps the summarising
    # calls legible in the metrics without hiding them: they are real spend
    # through the same bridge, and `get_combined_metrics()` sums every usage_id,
    # so they still reach the token ledger.
    agent = Agent(
        llm=llm,
        tools=tools,
        condenser=LLMSummarizingCondenser(
            llm=llm.model_copy(update={"usage_id": "condenser"}),
            max_size=_env_int("OH_CONDENSER_MAX_SIZE", CONDENSER_MAX_SIZE),
            keep_first=CONDENSER_KEEP_FIRST,
        ),
    )

    _emit(
        {
            "type": "system",
            "subtype": "init",
            "model": model,
            # Recorded so a trajectory says what budget it ran on.  Falls back
            # to the SDK's own default rather than reporting None, so an older
            # run and a newer one are read the same way.
            "reasoning_effort": llm_kwargs.get("reasoning_effort", "high"),
            "session_id": str(uuid.uuid4()),
            "tools": [getattr(t, "name", str(t)) for t in tools],
            "cwd": workspace,
        }
    )

    started = time.time()
    _install_sigterm_handler(started)
    conversation = None
    is_error = False
    try:
        conversation = Conversation(
            agent=agent,
            workspace=workspace,
            callbacks=[_make_callback()],
            hook_config=_stop_hook_config(),
            max_iteration_per_run=max_iterations,
            # Stuck-detection short-circuits the run loop *before* the Stop hook
            # is consulted, so with it on the agent can exit early no matter what
            # the hook says.  sforge decides when a run is over, by timeout.
            stuck_detection=False,
            # The workspace is the task checkout; deleting it on close would
            # destroy the submission.
            delete_on_close=False,
            visualizer=None,
        )
        # The callback reads cumulative usage off the conversation, which does
        # not exist until now; publish it before the first event can fire.
        _conversation_box["conversation"] = conversation
        conversation.send_message(prompt)
        conversation.run()
    except KeyboardInterrupt:
        is_error = True
    except Exception as exc:
        is_error = True
        logger.exception("openhands run failed")
        _emit_user([{"type": "text", "text": f"[driver error] {exc}"}])
    finally:
        _emit_result(started, is_error=is_error)
        try:
            if conversation is not None:
                conversation.close()
        except Exception:
            pass

    return 1 if is_error else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
