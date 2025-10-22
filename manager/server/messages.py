import json
from typing import Any, Dict, List

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage

ToolDisplay = Dict[str, str]

TOOL_DISPLAY_NAMES: ToolDisplay = {
    "call_analyst": "Analyst 子代理",
    "call_researcher": "Researcher 子代理",
    "call_trader": "Trader 子代理",
    "call_risk_manager": "风险管理模块",
    "read_file": "文件读取工具",
    "write_file": "文件写入工具",
}


def _format_tool_section(label: str, payload: Any) -> str:
    """Return a formatted markdown snippet for tool inputs/outputs/logs."""
    if payload is None:
        return ""

    raw = payload
    if isinstance(raw, str):
        raw = raw.strip()
        if not raw:
            return ""

    parsed: Any = None
    if isinstance(payload, (dict, list)):
        parsed = payload
    elif isinstance(payload, str):
        try:
            parsed = json.loads(payload)
        except (json.JSONDecodeError, TypeError):
            parsed = None

    if isinstance(parsed, (dict, list)):
        pretty = json.dumps(parsed, ensure_ascii=False, indent=2)
        return f"**{label}**\n```json\n{pretty}\n```"

    text = str(payload).strip()
    if not text:
        return ""
    if len(text) > 1200:
        text = text[:1197] + "..."
    if "\n" in text or len(text) > 80:
        return f"**{label}**\n```\n{text}\n```"
    return f"**{label}**：{text}"


def render_tool_event(event: Dict[str, Any], tool_display_names: ToolDisplay | None = None) -> str:
    """Compose markdown for a recorded tool event."""
    tool_key = event.get("tool", "工具调用")
    tool_name = tool_display_names.get(tool_key, tool_key) if tool_display_names else tool_key
    parts: List[str] = [f"🔧 {tool_name}"]

    input_section = _format_tool_section("输入", event.get("input"))
    if input_section:
        parts.append(input_section)

    output_section = _format_tool_section("输出", event.get("output"))
    if output_section:
        parts.append(output_section)

    log_section = _format_tool_section("日志", event.get("log"))
    if log_section:
        parts.append(log_section)

    return "\n\n".join(parts)


def format_chat_history(messages: List[BaseMessage], tool_display_names: ToolDisplay | None = None) -> List[Dict[str, str]]:
    """Convert LangChain history into frontend-friendly dictionaries."""
    display_messages: List[Dict[str, str]] = []

    for msg in messages:
        if isinstance(msg, HumanMessage):
            display_messages.append({"role": "user", "content": msg.content})
        elif isinstance(msg, AIMessage):
            display_messages.append({"role": "assistant", "content": msg.content})
        elif isinstance(msg, SystemMessage):
            if "tool_event" in msg.additional_kwargs:
                # Skip rendering tool call cards in chat history; progress panel covers these details.
                continue
            if msg.content:
                display_messages.append({"role": "system", "content": msg.content})

    return display_messages
