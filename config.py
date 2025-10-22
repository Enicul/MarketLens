from langchain_google_genai import ChatGoogleGenerativeAI, chat_models
from google.ai.generativelanguage_v1beta.types import FunctionResponse
import os
from dotenv import load_dotenv

# 加载 .env 文件
load_dotenv()

google_api_key = os.getenv("GOOGLE_API_KEY")
if not google_api_key:
    raise RuntimeError("GOOGLE_API_KEY is not set. Please configure your Google AI Studio API key before启动代理。")

# ------------------------------------------------------------------ #
# Gemini tool-response compatibility patch
# ------------------------------------------------------------------ #

def _apply_function_response_fallback(part, message):
    function_response = getattr(part, "function_response", None)
    if isinstance(function_response, FunctionResponse) and not function_response.name:
        fallback = (
            message.name
            or (message.additional_kwargs or {}).get("name")
            or (message.additional_kwargs or {}).get("tool_name")
            or "tool_response"
        )
        function_response.name = fallback
    return part


if hasattr(chat_models, "_convert_tool_message_to_parts"):
    _original_convert_tool_message = chat_models._convert_tool_message_to_parts

    def _patch_convert_tool_message(message, name=None):
        parts = _original_convert_tool_message(message, name=name)
        return [_apply_function_response_fallback(part, message) for part in parts]

    chat_models._convert_tool_message_to_parts = _patch_convert_tool_message
elif hasattr(chat_models, "_convert_tool_message_to_part"):
    _original_convert_tool_message = chat_models._convert_tool_message_to_part

    def _patch_convert_tool_message(message):
        part = _original_convert_tool_message(message)
        return _apply_function_response_fallback(part, message)

    chat_models._convert_tool_message_to_part = _patch_convert_tool_message
else:
    raise AttributeError(
        "Unsupported langchain_google_genai version: missing tool message converters"
    )

# ------------------------------------------------------------------ #
LLM_GOOGLE = ChatGoogleGenerativeAI(
    model="gemini-2.5-pro",
    temperature=0.3,
    google_api_key=google_api_key,
    convert_system_message_to_human=False,
    verbose=True,
    streaming=True,
)
