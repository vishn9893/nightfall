# Nightfall CLI

A minimal coding agent harness in Python, built to show how the pieces of a coding agent fit together.

This is the Nightfall CLI repository, a small coding-agent harness built from scratch.

https://github.com/user-attachments/assets/e4aaa9e4-69ec-40e3-8f5a-e4ec8c5b7208

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
- Subagents for exploring a codebase in a separate context window.
- Todo tracking for tasks with multiple steps.
- Saved chat sessions, with `/sessions` to reopen them and `/rewind` to go back in the conversation.
- Automatic context compaction, plus `/compact` to trigger it manually.
- Git branch context and reminders when files change between turns.
