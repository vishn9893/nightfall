# Nightfall CLI

A minimal coding agent harness in Python, built to show how the pieces of a coding agent fit together.

This is the Nightfall CLI repository, a small coding-agent harness built from scratch.

## Getting started

Install the project with [uv](https://docs.astral.sh/uv/):

```bash
uv sync
```

Configure an OpenAI-compatible endpoint and key in `~/.agents/env`:

```text
BASE_URL=https://your-endpoint/v1
API_KEY=your-api-key
MODEL=your-model-name
```

Start the agent from the repository root:

```bash
uv run nightfall
```

Use `uv run nightfall --resume` to resume the latest saved session or
`uv run nightfall --debug` to display raw model responses. The sandbox backend
is selected automatically for the host operating system.


## Features

- Interactive terminal chat 
- Tools for running shell commands, reading and writing files, and making targeted edits.
- Configurable model and OpenAI-compatible API endpoint.
- Tool permissions and shell sandboxing on macOS, Linux, and Windows
- Skills loaded from project and user `.agents/skills` directories.
- Prompt autocomplete: `/` completes commands, `/skill:` completes skills, and `@` completes paths.
- Subagents for exploring a codebase in a separate context window.
- Todo tracking for tasks with multiple steps.
- Saved chat sessions, with `/sessions` to reopen them and `/rewind` to go back in the conversation.
- Automatic context compaction, plus `/compact` to trigger it manually.
- Git branch context and reminders when files change between turns.
- Optional OpenTelemetry traces and metrics (see below).

## Telemetry

Tracing is off unless an exporter is configured, so the default install does
not pay for it. Install the extra and point it at a collector:

```bash
uv sync --extra otel
export OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318   # base URL, no /v1/traces
uv run nightfall
```

A session then reports a span per turn, one per model call and one per tool
call, plus counters for turns, tool calls, errors and tokens (input, output,
reasoning and cached). `NIGHTFALL_TELEMETRY=console` prints the spans to the
terminal instead of shipping them, which is the quickest way to see what is
being recorded.

Only names, counts and sizes are ever recorded - never prompts, replies, tool
arguments, tool output or file contents. Prompts, file contents and tool
output stay in the transcript; telemetry reports how long the session was and
what it touched.

The standard `OTEL_*` variables work as they do everywhere else
(`OTEL_SERVICE_NAME`, `OTEL_EXPORTER_OTLP_HEADERS`, and the rest). The
exporter is given five seconds to hand over a batch before the CLI exits, so
an unreachable collector costs a warning rather than a hang.
