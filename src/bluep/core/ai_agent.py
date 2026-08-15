"""AI Agent for BlueP.

The AI agent can interact with the BlueP IDE exactly like a human user:
- Create, modify, and delete classes
- Compile and execute code
- Instantiate objects on the bench
- Inspect objects and call methods
- Set breakpoints and debug
- Read and analyze the project structure
- Write tests and documentation

Controlled via .env: BLUEP_AI_ENABLED=true/false
The AI gets access to the same APIs the GUI uses, plus additional
context about the project state.
"""

from __future__ import annotations

import json
import sys
import threading
import traceback
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable

from bluep.core.class_info import ClassAnalyzer, ClassInfo, ClassKind
from bluep.core.executor import CodeExecutor, ExecutionResult, BenchObject
from bluep.core.project import Project
from bluep.config import AIConfig


@dataclass
class AIMessage:
    """A message in the AI conversation."""
    role: str  # "system", "user", "assistant"
    content: str
    tool_calls: list[dict] = field(default_factory=list)
    tool_call_id: str | None = None


@dataclass
class AIResponse:
    """Response from the AI model."""
    content: str = ""
    tool_calls: list[dict] = field(default_factory=list)
    error: str = ""

    @property
    def has_error(self) -> bool:
        return bool(self.error)


class AIProjectAPI:
    """The API the AI agent uses to interact with BlueP.

    This gives the AI the same capabilities as a human user:
    read/write files, compile code, instantiate objects, inspect, debug.

    Every action a human can do through the GUI, the AI can do through
    this API.
    """

    def __init__(self, project: Project, executor: CodeExecutor) -> None:
        self.project = project
        self.executor = executor

    def get_project_state(self) -> dict[str, Any]:
        """Get full project state - all classes, relationships, bench objects."""
        return {
            "project_name": self.project.name,
            "project_path": str(self.project.path),
            "classes": {
                name: {
                    "kind": ci.kind.value,
                    "bases": ci.bases,
                    "fields": [
                        {"name": f.name, "type": f.display_type, "is_class_var": f.is_class_var}
                        for f in ci.fields
                    ],
                    "methods": [
                        {"name": m.name, "signature": m.display_signature, "is_abstract": m.is_abstract}
                        for m in ci.methods
                    ],
                    "source_file": str(ci.source_file) if ci.source_file else None,
                    "is_compiled": ci.is_compiled,
                }
                for name, ci in self.project.model.classes.items()
            },
            "relationships": [
                {"source": r.source, "target": r.target, "kind": r.kind.value}
                for r in self.project.model.relationships
            ],
            "bench_objects": {
                name: {
                    "class_name": obj.class_name,
                    "fields": obj.get_fields(),
                }
                for name, obj in self.executor.bench.items()
            },
        }

    def get_class_source(self, class_name: str) -> str:
        """Get the source code of a class."""
        return self.project.get_class_source(class_name)

    def update_class_source(self, class_name: str, source: str) -> dict[str, Any]:
        """Update the source code of a class."""
        self.project.update_class_source(class_name, source)
        return {"success": True, "message": f"Updated {class_name}"}

    def create_class(self, class_name: str, kind: str = "concrete", source: str | None = None) -> dict[str, Any]:
        """Create a new class in the project."""
        kind_enum = ClassKind(kind) if kind in [k.value for k in ClassKind] else ClassKind.CONCRETE
        self.project.add_class_file(class_name, kind_enum, source)
        return {"success": True, "message": f"Created class {class_name}"}

    def delete_class(self, class_name: str) -> dict[str, Any]:
        """Delete a class from the project."""
        self.project.remove_class(class_name)
        return {"success": True, "message": f"Deleted {class_name}"}

    def compile_all(self) -> dict[str, Any]:
        """Compile (load) all classes into the executor namespace."""
        results = {}
        for py_file in self.project.get_source_files():
            result = self.executor.load_module(py_file)
            results[py_file.stem] = {
                "success": result.success,
                "error": result.error if result.has_error else None,
            }
        return {"results": results}

    def compile_class(self, class_name: str) -> dict[str, Any]:
        """Compile a single class."""
        cls_info = self.project.model.get_class(class_name)
        if cls_info is None or cls_info.source_file is None:
            return {"success": False, "error": f"Class {class_name} not found"}
        result = self.executor.load_module(cls_info.source_file)
        return {
            "success": result.success,
            "error": result.error if result.has_error else None,
        }

    def instantiate(self, class_name: str, *args: Any, **kwargs: Any) -> dict[str, Any]:
        """Create an instance of a class and place it on the bench."""
        try:
            obj = self.executor.instantiate(class_name, *args, **kwargs)
            return {
                "success": True,
                "object_name": obj.name,
                "class_name": obj.class_name,
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def call_method(self, bench_name: str, method_name: str, *args: Any, **kwargs: Any) -> dict[str, Any]:
        """Call a method on a bench object."""
        result = self.executor.call_bench_method(bench_name, method_name, *args, **kwargs)
        return {
            "success": result.success,
            "output": result.output,
            "value": repr(result.value) if result.value is not None else None,
            "error": result.error if result.has_error else None,
        }

    def inspect_object(self, bench_name: str) -> dict[str, Any]:
        """Inspect a bench object (like BlueJ's object inspector)."""
        obj = self.executor.bench.get(bench_name)
        if obj is None:
            return {"success": False, "error": f"Object {bench_name} not found"}
        return {"success": True, "data": obj.inspect()}

    def evaluate_expression(self, expression: str) -> dict[str, Any]:
        """Evaluate a Python expression (like BlueJ's Code Pad)."""
        result = self.executor.evaluate_expression(expression)
        return {
            "success": result.success,
            "value": repr(result.value) if result.value is not None else None,
            "output": result.output,
            "error": result.error if result.has_error else None,
        }

    def execute_code(self, code: str) -> dict[str, Any]:
        """Execute arbitrary Python code."""
        result = self.executor.execute_code(code)
        return {
            "success": result.success,
            "output": result.output,
            "error": result.error if result.has_error else None,
        }

    def remove_bench_object(self, name: str) -> dict[str, Any]:
        """Remove an object from the bench."""
        self.executor.remove_bench_object(name)
        return {"success": True}

    def clear_bench(self) -> dict[str, Any]:
        """Clear all objects from the bench."""
        self.executor.clear_bench()
        return {"success": True}

    def get_all_methods_info(self) -> dict[str, Any]:
        """Get detailed info about all available methods (tool list for AI)."""
        methods = []
        for name, method in AIProjectAPI.__dict__.items():
            if not name.startswith("_") and callable(method):
                import inspect as insp
                sig = insp.signature(method)
                methods.append({
                    "name": name,
                    "params": [(p, str(sig.parameters[p].annotation) if sig.parameters[p].annotation != insp.Parameter.empty else "Any") for p in sig.parameters],
                    "return": "dict",
                })
        return {"methods": methods}


class AIAgent:
    """AI agent that can interact with BlueP like a human.

    Uses an LLM (OpenAI-compatible API) to:
    1. Understand the project state
    2. Decide what actions to take
    3. Execute those actions via AIProjectAPI
    4. Report results to the user

    The agent operates in a tool-use loop:
    - Reads project state
    - Decides what to do
    - Calls API methods
    - Evaluates results
    - Repeats until task is done
    """

    def __init__(self, config: AIConfig, project: Project, executor: CodeExecutor) -> None:
        self.config = config
        self.api = AIProjectAPI(project, executor)
        self.conversation: list[AIMessage] = []
        self._message_callback: Callable[[str], None] | None = None
        self._is_running = False
        self._thread: threading.Thread | None = None

        # Initialize system prompt
        self._system_prompt = self._build_system_prompt()

    @property
    def is_enabled(self) -> bool:
        return self.config.enabled

    def set_message_callback(self, callback: Callable[[str], None]) -> None:
        """Set callback for AI messages (to display in UI)."""
        self._message_callback = callback

    def _build_system_prompt(self) -> str:
        """Build the system prompt with project context."""
        state = self.api.get_project_state()
        return f"""You are BlueP AI, an intelligent assistant integrated into the BlueP IDE
(a BlueJ clone for Python). You have full access to the IDE's capabilities,
just like a human user.

Current Project State:
- Name: {state['project_name']}
- Path: {state['project_path']}
- Classes: {json.dumps(list(state['classes'].keys()))}

Available Actions (you can call these via tool_calls):
- get_project_state(): Get full project state including all classes, fields, methods, relationships, and bench objects
- get_class_source(class_name): Get source code of a class
- update_class_source(class_name, source): Update source code of a class
- create_class(class_name, kind="concrete", source=None): Create a new class
- delete_class(class_name): Delete a class
- compile_all(): Compile all classes
- compile_class(class_name): Compile a single class
- instantiate(class_name, *args, **kwargs): Create an instance on the bench
- call_method(bench_name, method_name, *args, **kwargs): Call a method on a bench object
- inspect_object(bench_name): Inspect a bench object's fields and methods
- evaluate_expression(expression): Evaluate a Python expression
- execute_code(code): Execute arbitrary Python code
- remove_bench_object(name): Remove an object from the bench
- clear_bench(): Clear all objects from the bench

You can do ANYTHING a human can do in the IDE:
- Read, write, and modify class source code
- Create and delete classes
- Compile code and fix errors
- Create objects and call their methods
- Inspect object state
- Evaluate expressions
- Run tests
- Debug code
- Write documentation

When asked to do something:
1. First, understand the current state by calling get_project_state()
2. Plan your approach
3. Execute step by step, calling the appropriate tools
4. Report results clearly to the user

Always write clean, well-documented Python code following PEP 8.
Use type annotations. Include docstrings."""

    def chat(self, user_message: str) -> str:
        """Send a message to the AI and get a response.

        This is the main entry point for AI interaction.
        """
        if not self.config.enabled:
            return "AI agent is disabled. Set BLUEP_AI_ENABLED=true in .env to enable."

        # Add user message
        self.conversation.append(AIMessage(role="user", content=user_message))

        # Build messages for API
        messages = [{"role": "system", "content": self._system_prompt}]
        for msg in self.conversation:
            messages.append({"role": msg.role, "content": msg.content})

        # Call LLM with tool use loop
        response = self._call_llm_with_tools(messages, max_iterations=10)

        # Add assistant response to conversation
        self.conversation.append(AIMessage(role="assistant", content=response))

        if self._message_callback:
            self._message_callback(response)

        return response

    def chat_async(self, user_message: str) -> None:
        """Start an async chat (non-blocking)."""
        if self._thread and self._thread.is_alive():
            return

        def run():
            try:
                self.chat(user_message)
            except Exception as e:
                if self._message_callback:
                    self._message_callback(f"AI Error: {e}")

        self._thread = threading.Thread(target=run, daemon=True)
        self._is_running = True
        self._thread.start()

    def _call_llm_with_tools(self, messages: list[dict], max_iterations: int = 10) -> str:
        """Call the LLM with tool-use loop."""
        tool_definitions = [
            {
                "type": "function",
                "function": {
                    "name": name,
                    "description": (getattr(getattr(self.api, name), "__doc__", "") or "").strip(),
                    "parameters": self._get_tool_schema(name),
                }
            }
            for name in self._get_api_method_names()
        ]

        for iteration in range(max_iterations):
            try:
                response = self._call_llm_api(messages, tools=tool_definitions)
            except Exception as e:
                return f"Error calling AI: {e}"

            if response.has_error:
                return f"AI Error: {response.error}"

            # Check if there are tool calls
            if response.tool_calls:
                messages.append({
                    "role": "assistant",
                    "content": response.content,
                    "tool_calls": response.tool_calls,
                })

                for tool_call in response.tool_calls:
                    func_name = tool_call["function"]["name"]
                    func_args = json.loads(tool_call["function"]["arguments"])

                    # Execute the tool
                    result = self._execute_tool(func_name, func_args)

                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call["id"],
                        "content": json.dumps(result),
                    })

                    if self._message_callback:
                        self._message_callback(f"[AI executing: {func_name}({func_args})]")
            else:
                # No tool calls - we have the final answer
                return response.content

        return "Max iterations reached without final answer."

    def _get_api_method_names(self) -> list[str]:
        """Get all public API method names."""
        return [
            name for name in dir(self.api)
            if not name.startswith("_") and callable(getattr(self.api, name))
        ]

    def _get_tool_schema(self, method_name: str) -> dict:
        """Get JSON schema for an API method."""
        # Simplified schemas
        schemas: dict[str, dict] = {
            "get_project_state": {"type": "object", "properties": {}},
            "get_class_source": {
                "type": "object",
                "properties": {"class_name": {"type": "string"}},
                "required": ["class_name"],
            },
            "update_class_source": {
                "type": "object",
                "properties": {
                    "class_name": {"type": "string"},
                    "source": {"type": "string"},
                },
                "required": ["class_name", "source"],
            },
            "create_class": {
                "type": "object",
                "properties": {
                    "class_name": {"type": "string"},
                    "kind": {"type": "string"},
                    "source": {"type": "string"},
                },
                "required": ["class_name"],
            },
            "delete_class": {
                "type": "object",
                "properties": {"class_name": {"type": "string"}},
                "required": ["class_name"],
            },
            "compile_all": {"type": "object", "properties": {}},
            "compile_class": {
                "type": "object",
                "properties": {"class_name": {"type": "string"}},
                "required": ["class_name"],
            },
            "instantiate": {
                "type": "object",
                "properties": {
                    "class_name": {"type": "string"},
                    "args": {"type": "array", "items": {}},
                    "kwargs": {"type": "object"},
                },
                "required": ["class_name"],
            },
            "call_method": {
                "type": "object",
                "properties": {
                    "bench_name": {"type": "string"},
                    "method_name": {"type": "string"},
                    "args": {"type": "array", "items": {}},
                    "kwargs": {"type": "object"},
                },
                "required": ["bench_name", "method_name"],
            },
            "inspect_object": {
                "type": "object",
                "properties": {"bench_name": {"type": "string"}},
                "required": ["bench_name"],
            },
            "evaluate_expression": {
                "type": "object",
                "properties": {"expression": {"type": "string"}},
                "required": ["expression"],
            },
            "execute_code": {
                "type": "object",
                "properties": {"code": {"type": "string"}},
                "required": ["code"],
            },
            "remove_bench_object": {
                "type": "object",
                "properties": {"name": {"type": "string"}},
                "required": ["name"],
            },
            "clear_bench": {"type": "object", "properties": {}},
        }
        return schemas.get(method_name, {"type": "object", "properties": {}})

    def _execute_tool(self, name: str, args: dict) -> dict:
        """Execute an API tool by name."""
        method = getattr(self.api, name, None)
        if method is None:
            return {"error": f"Unknown method: {name}"}
        try:
            return method(**args) if isinstance(args, dict) else method(*args)
        except Exception as e:
            return {"error": f"Error executing {name}: {e}\n{traceback.format_exc()}"}

    def _call_llm_api(self, messages: list[dict], tools: list[dict] | None = None) -> AIResponse:
        """Call the LLM API (OpenAI-compatible)."""
        if not self.config.api_key:
            return AIResponse(error="No API key configured. Set BLUEP_AI_API_KEY in .env.")

        url = f"{self.config.base_url.rstrip('/')}/chat/completions"

        payload: dict[str, Any] = {
            "model": self.config.model,
            "messages": messages,
            "max_tokens": self.config.max_tokens,
            "temperature": self.config.temperature,
        }
        if tools:
            payload["tools"] = tools

        body = json.dumps(payload).encode("utf-8")

        request = urllib.request.Request(
            url,
            data=body,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.config.api_key}",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                data = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            error_body = e.read().decode("utf-8") if e.fp else str(e)
            return AIResponse(error=f"HTTP {e.code}: {error_body}")
        except urllib.error.URLError as e:
            return AIResponse(error=f"Network error: {e.reason}")
        except Exception as e:
            return AIResponse(error=f"API error: {e}")

        choice = data.get("choices", [{}])[0]
        message = choice.get("message", {})

        content = message.get("content", "")
        tool_calls = message.get("tool_calls", [])

        # Convert tool_calls to our format
        formatted_tool_calls = []
        for tc in tool_calls:
            formatted_tool_calls.append({
                "id": tc.get("id", ""),
                "function": {
                    "name": tc["function"]["name"],
                    "arguments": tc["function"]["arguments"],
                },
            })

        return AIResponse(content=content, tool_calls=formatted_tool_calls)

    def reset_conversation(self) -> None:
        """Clear conversation history."""
        self.conversation.clear()
        # Refresh system prompt with current state
        self._system_prompt = self._build_system_prompt()

    def is_running(self) -> bool:
        """Check if the agent is currently processing."""
        return self._is_running and self._thread is not None and self._thread.is_alive()

    def stop(self) -> None:
        """Signal the agent to stop."""
        self._is_running = False
