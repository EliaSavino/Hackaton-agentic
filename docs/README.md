# Documentation

This documentation is written for hackathon use: fast onboarding, clear extension points, and enough structure to keep multi-agent experiments debuggable.

## Start Here

- [Quickstart](quickstart.md): install, configure, run demos, run tests.
- [Architecture](architecture.md): how state, agents, tools, graph, and models fit together.
- [Configuration](configuration.md): `configs/*.yaml`, `.env`, and run modes.
- [Model Routing](models.md): LiteLLM aliases, Ollama servers, capabilities, and benchmarking.
- [Agents](agents.md): how to write agents and system prompts.
- [Graph And Iteration](graph-iteration.md): LangGraph topology, bounded loops, and context sharing.
- [Tools](tools.md): tool contracts and the current tool inventory.
- [Function Guide](function-guide.md): how to call the public functions, classes, and CLI commands.
- [Paper Review](paper-review.md): deterministic paper reviewing workflow.
- [Testing](testing.md): unit tests, smoke tests, and dependency-sensitive tests.
- [HPC And Remote Terminal](hpc.md): Slurm workflows, vLLM serving, and SSH tunnels.
- [Hackathon Playbook](hackathon-playbook.md): practical workflow for uncertain challenge prompts.

## Core Design Rule

Keep agents thin and tools boring.

Agents should read state, call a model only when needed, and update typed state. Tools should do deterministic work and always return `ToolResult`. The graph decides the workflow and enforces hard loop limits.
