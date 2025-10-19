import os
import sys
import asyncio
import copy
import base64
import json
from pathlib import Path
from typing import List, Dict, Any

import streamlit as st
from langchain.callbacks.base import BaseCallbackHandler
from langchain_core.messages import HumanMessage, AIMessage

if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

# Ensure repository root is on path for sibling imports
CURRENT_DIR = os.path.dirname(__file__)
REPO_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, ".."))
if REPO_ROOT not in sys.path:
    sys.path.append(REPO_ROOT)

# Provide compatibility for environments without st.experimental_rerun
if not hasattr(st, "experimental_rerun") and hasattr(st, "rerun"):
    st.experimental_rerun = st.rerun  # type: ignore[attr-defined]

# Local imports (reuse existing agent configuration)
from manager.agent_stream_gradio import build_main_agent, enabled_analysis_types  # type: ignore
from manager.chat_history_manager import get_history_manager  # type: ignore

ToolNameMapping = Dict[str, str]

TOOL_DISPLAY_NAMES: ToolNameMapping = {
    "call_analyst": "Analyst 子代理",
    "call_researcher": "Researcher 子代理",
    "call_trader": "Trader 子代理",
    "call_risk_manager": "风险管理模块",
    "read_file": "文件读取工具",
    "write_file": "文件写入工具",
}

HISTORY_MANAGER = get_history_manager()
ICON_PATH = Path(CURRENT_DIR, "static", "image", "icon.png")
LOGIN_GIF_PATH = Path(CURRENT_DIR, "static", "image", "login.gif")
DEFAULT_CREDENTIALS = {"admin": "123456"}
INITIAL_ANALYSIS_CONFIG = copy.deepcopy(enabled_analysis_types)


@st.cache_data(show_spinner=False)
def _load_icon_base64(path_str: str, version: float) -> str:
    """Load icon file as base64 string for inline HTML usage.
    
    The version parameter ensures cache invalidation when the icon file changes.
    """
    try:
        return base64.b64encode(Path(path_str).read_bytes()).decode("utf-8")
    except FileNotFoundError:
        return ""
    except Exception:
        return ""


def _get_allowed_users() -> Dict[str, str]:
    """Derive allowed login credentials from environment variables or defaults."""
    users: Dict[str, str] = {}

    raw_mapping = os.getenv("MARKET_LENS_USERS")
    if raw_mapping:
        try:
            parsed = json.loads(raw_mapping)
            if isinstance(parsed, dict):
                for email, pwd in parsed.items():
                    if isinstance(email, str) and isinstance(pwd, str):
                        normalized = email.strip().lower()
                        if normalized:
                            users[normalized] = pwd
        except json.JSONDecodeError:
            pass

    env_email = os.getenv("MARKET_LENS_ADMIN_EMAIL")
    env_password = os.getenv("MARKET_LENS_ADMIN_PASSWORD")
    if env_email and env_password:
        users[env_email.strip().lower()] = env_password

    if not users:
        users = {email.lower(): password for email, password in DEFAULT_CREDENTIALS.items()}
    return users


def _validate_credentials(email: str, password: str) -> bool:
    """Return True if provided credentials match configured users."""
    if not email or not password:
        return False
    normalized_email = email.strip().lower()
    return _get_allowed_users().get(normalized_email) == password


def _ensure_auth_state() -> None:
    """Initialize authentication-related session state."""
    auth = st.session_state.setdefault("auth", {})
    auth.setdefault("is_authenticated", False)
    auth.setdefault("user_email", None)
    auth.setdefault("role", "guest")
    st.session_state.setdefault("logout_requested", False)


def _perform_logout() -> None:
    """Clear session data and reset to initial state."""
    keys_to_clear = [
        "messages",
        "analysis_config",
        "agent",
        "agent_config_snapshot",
        "session_id",
        "login_error",
    ]
    dynamic_prefixes = ("analysis_", "session_name_", "pending_session_name_")
    for key in list(st.session_state.keys()):
        if key in keys_to_clear or key.startswith(dynamic_prefixes):
            st.session_state.pop(key, None)

    enabled_analysis_types.update(INITIAL_ANALYSIS_CONFIG)
    st.session_state.auth = {
        "is_authenticated": False,
        "user_email": None,
        "role": "guest",
    }
    st.session_state.logout_requested = False


def render_app_header(show_title: bool = True, show_subtitle: bool = True) -> None:
    """Render the shared Market Lens header with optional title and subtitle."""
    if not show_title:
        return

    icon_mtime = ICON_PATH.stat().st_mtime if ICON_PATH.exists() else 0.0
    icon_base64 = _load_icon_base64(str(ICON_PATH), icon_mtime)
    if icon_base64:
        icon_html = (
            f"<img src='data:image/png;base64,{icon_base64}' alt='Market Lens AI Icon' "
            "style='height:48px;width:48px;object-fit:contain;margin-right:12px;' />"
        )
    else:
        icon_html = "<span style='font-size:2.5rem;margin-right:12px;'>🤖</span>"

    subtitle_html = ""
    if show_subtitle:
        subtitle_html = (
            "<p style='margin:0;color:#6b7280;'>全链路分析：Analyst &rarr; Researcher &rarr; Trader &rarr; Risk Management</p>"
        )

    st.markdown(
        "<div style='display:flex;flex-direction:column;align-items:center;gap:0.5rem;margin-bottom:1.5rem;'>"
        "<div style='display:flex;align-items:center;justify-content:center;'>"
        f"{icon_html}"
        "<span style='font-size:2rem;font-weight:600;'>Market Lens AI Financial Analysis Assistant</span>"
        "</div>"
        f"{subtitle_html}"
        "</div>",
        unsafe_allow_html=True,
    )


class StreamlitAgentCallback(BaseCallbackHandler):
    """Bridge LangChain callback events to Streamlit UI."""

    def __init__(self, status_placeholder: "st.delta_generator.DeltaGenerator", response_placeholder: "st.delta_generator.DeltaGenerator"):
        self.status_placeholder = status_placeholder
        self.response_placeholder = response_placeholder
        self._response_parts: List[str] = []
        self._active_tool: str | None = None

    def on_llm_start(self, *args, **kwargs) -> None:  # type: ignore[override]
        self._response_parts = []

    def on_llm_new_token(self, token: str, **kwargs) -> None:  # type: ignore[override]
        self._response_parts.append(token)
        self.response_placeholder.markdown("".join(self._response_parts) + "▌")

    def on_llm_end(self, *args, **kwargs) -> None:  # type: ignore[override]
        if self._response_parts:
            self.response_placeholder.markdown("".join(self._response_parts))

    def on_tool_start(self, serialized: Dict[str, Any], input_str: str, **kwargs) -> None:  # type: ignore[override]
        tool_name = serialized.get("name", "工具")
        display = TOOL_DISPLAY_NAMES.get(tool_name, tool_name)
        self._active_tool = display
        self.status_placeholder.info(f"{display} 正在处理…")

    def on_tool_end(self, output: Any, **kwargs) -> None:  # type: ignore[override]
        if self._active_tool:
            self.status_placeholder.success(f"{self._active_tool} 已完成")
            self._active_tool = None

    def on_tool_error(self, error: Exception, **kwargs) -> None:  # type: ignore[override]
        if self._active_tool:
            self.status_placeholder.error(f"{self._active_tool} 出现异常：{error}")
            self._active_tool = None

    def on_agent_finish(self, finish, **kwargs) -> None:  # type: ignore[override]
        # Clear status once agent completes
        self.status_placeholder.empty()
        if not self._response_parts:
            content = finish.return_values.get("output", "")
            if content:
                self._response_parts.append(content)
                self.response_placeholder.markdown(content)

    def get_response_text(self) -> str:
        return "".join(self._response_parts).strip()

    def emit_error(self, message: str) -> None:
        self._response_parts = [message]
        self.response_placeholder.markdown(message)
        self.status_placeholder.error("代理执行失败")


def _load_session_messages(session_id: str) -> List[Dict[str, str]]:
    """Load persisted history and convert to Streamlit-compatible format."""
    raw_history = HISTORY_MANAGER.get_raw_history(session_id)
    messages: List[Dict[str, str]] = []
    for record in raw_history:
        messages.append({"role": "user", "content": record.get("user", "")})
        messages.append({"role": "assistant", "content": record.get("assistant", "")})
    return messages


def _switch_session(session_id: str) -> None:
    """Switch active session and refresh in-memory messages."""
    st.session_state.session_id = session_id
    st.session_state.messages = _load_session_messages(session_id)


def _initialize_session_state() -> None:
    """Prepare Streamlit session state keys used across renders."""
    if "analysis_config" not in st.session_state:
        st.session_state.analysis_config = copy.deepcopy(enabled_analysis_types)

    sessions = HISTORY_MANAGER.list_sessions()
    if "session_id" not in st.session_state:
        if sessions:
            st.session_state.session_id = sessions[-1]
        else:
            st.session_state.session_id = HISTORY_MANAGER.create_session()
    elif st.session_state.session_id not in sessions:
        # Handle deleted session edge cases
        st.session_state.session_id = sessions[-1] if sessions else HISTORY_MANAGER.create_session()

    if "messages" not in st.session_state:
        st.session_state.messages = _load_session_messages(st.session_state.session_id)

    if "agent" not in st.session_state:
        st.session_state.agent = build_main_agent(st.session_state.analysis_config)
        st.session_state.agent_config_snapshot = copy.deepcopy(st.session_state.analysis_config)


def _build_langchain_history(messages: List[Dict[str, str]]) -> List[Any]:
    """Convert chat history into LangChain message objects."""
    formatted: List[Any] = []
    for item in messages:
        role = item.get("role")
        content = item.get("content", "")
        if role == "user":
            formatted.append(HumanMessage(content=content))
        elif role == "assistant":
            formatted.append(AIMessage(content=content))
    return formatted


def _maybe_refresh_agent() -> None:
    """Rebuild the AgentExecutor if analysis configuration changed."""
    current_config = st.session_state.analysis_config
    if st.session_state.get("agent_config_snapshot") != current_config:
        st.session_state.agent = build_main_agent(current_config)
        st.session_state.agent_config_snapshot = copy.deepcopy(current_config)


def _format_session_label(session_id: str) -> str:
    """Return the session's display name."""
    return HISTORY_MANAGER.get_session_name(session_id)


def render_login() -> None:
    """Render the login interface with email/password form and guest access."""
    render_app_header(show_title=False, show_subtitle=False)
    st.markdown("<div style='height: 2rem;'></div>", unsafe_allow_html=True)

    spacer_left, card_col, spacer_right = st.columns([1, 1.6, 1], gap="large")
    with card_col:
        st.markdown(
            "<h3 style='display:flex;align-items:center;justify-content:center;margin-bottom:24px;'>"
            "<span style='margin-right:10px;'>欢迎登录</span>"
            f"<img src='data:image/png;base64,{_load_icon_base64(str(ICON_PATH), ICON_PATH.stat().st_mtime if ICON_PATH.exists() else 0.0)}' "
            "alt='Market Lens Icon' style='height:40px;width:40px;object-fit:contain;margin-right:10px;' />"
            "<span>Market Lens</span>"
            "</h3>",
            unsafe_allow_html=True,
        )

        left_col, right_col = st.columns([1.15, 1], vertical_alignment="center")
        with left_col:
            if LOGIN_GIF_PATH.exists():
                st.image(str(LOGIN_GIF_PATH), width="stretch")
            else:
                st.info("登录动画缺失，请联系管理员补充 `static/image/login.gif`。")

        with right_col:
            st.markdown(
                "<div style='border-left: 3px solid #e2e8f0; padding-left: 24px;'>",
                unsafe_allow_html=True,
            )
            st.markdown("<div style='height: 12px;'></div>", unsafe_allow_html=True)

            if st.session_state.get("login_error"):
                st.error(st.session_state.login_error)

            with st.form("login_form", clear_on_submit=False):
                email = st.text_input("邮箱", placeholder="name@example.com", label_visibility="collapsed")
                password = st.text_input("密码", type="password", placeholder="请输入密码", label_visibility="collapsed")

                submit_col, guest_col = st.columns(2)
                with submit_col:
                    login_submit = st.form_submit_button("登录", width="stretch")
                with guest_col:
                    guest_submit = st.form_submit_button("游客登录", width="stretch")

                if login_submit:
                    with st.spinner("正在验证凭证..."):
                        if not email or not password:
                            st.session_state.login_error = "请完整填写邮箱和密码后再登录。"
                        elif _validate_credentials(email, password):
                            st.session_state.auth = {
                                "is_authenticated": True,
                                "user_email": email.strip(),
                                "role": "member",
                            }
                            st.session_state.pop("login_error", None)
                            st.experimental_rerun()  # type: ignore[attr-defined]
                        else:
                            st.session_state.login_error = "账号或密码不正确，请重试。"
                elif guest_submit:
                    st.session_state.auth = {
                        "is_authenticated": True,
                        "user_email": "游客模式",
                        "role": "guest",
                    }
                    st.session_state.pop("login_error", None)
                    st.experimental_rerun()  # type: ignore[attr-defined]

            st.markdown("</div>", unsafe_allow_html=True)


        st.markdown(
            "<p style='text-align: center; color: #94a3b8; font-size: 0.85rem; margin-top: 1.2rem;'>"
            "请输入邮箱和密码登录/选择游客模式"
            "</p>",
            unsafe_allow_html=True,
        )


def render_sidebar() -> None:
    """Render sidebar with configuration toggles and session controls."""
    with st.sidebar:
        auth_info = st.session_state.get("auth", {})
        user_email = auth_info.get("user_email") or "游客"
        role = auth_info.get("role", "guest")
        role_label = "游客模式" if role == "guest" else "正式用户"

        st.markdown(
            f"""
            <div style="
                background: linear-gradient(135deg, rgba(79,70,229,0.12), rgba(14,165,233,0.12));
                border-radius: 16px;
                padding: 18px 20px;
                margin-bottom: 12px;
            ">
                <div style="font-size: 0.85rem; color: #64748b;">当前用户</div>
                <div style="font-size: 1rem; font-weight: 600; margin-top: 4px;">{user_email}</div>
                <div style="font-size: 0.85rem; color: #64748b; margin-top: 2px;">{role_label}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        if st.button("退出登录", width="stretch"):
            st.session_state.logout_requested = True
            try:
                st.rerun()
            except AttributeError:
                _perform_logout()
                st.stop()

        st.divider()
        st.subheader("⚙️ Analysis Configuration")

        toggles = {}
        for key, label in [
            ("news", "📰 新闻分析"),
            ("fundamentals", "📊 基本面"),
            ("market", "📈 市场数据"),
            ("sentiment", "💭 市场情绪"),
        ]:
            toggles[key] = st.checkbox(
                label,
                value=st.session_state.analysis_config.get(key, True),
                key=f"analysis_{key}",
            )

        if toggles != st.session_state.analysis_config:
            st.session_state.analysis_config = toggles

        enabled_analysis_types.update(st.session_state.analysis_config)
        _maybe_refresh_agent()

        enabled = [label for key, label in [
            ("news", "新闻"),
            ("fundamentals", "基本面"),
            ("market", "市场"),
            ("sentiment", "情绪"),
        ] if st.session_state.analysis_config.get(key)]
        if len(enabled) == 4:
            st.caption("✅ 所有分析模块已启用")
        elif not enabled:
            st.caption("⚠️ 当前已禁用全部分析模块")
        else:
            st.caption("📊 当前启用：" + "、".join(enabled))

        st.divider()
        st.subheader("💬 对话历史")

        sessions = HISTORY_MANAGER.list_sessions()
        if not sessions:
            st.info("暂无历史对话，点击下方按钮开始新的会话。")
        else:
            current_session = st.session_state.session_id
            if current_session not in sessions:
                current_session = sessions[-1]
                _switch_session(current_session)

            selected = st.selectbox(
                "选择会话",
                options=sessions,
                index=sessions.index(current_session),
                format_func=_format_session_label,
            )
            if selected != st.session_state.session_id:
                _switch_session(selected)
                current_session = selected

            current_id = st.session_state.session_id
            current_name = HISTORY_MANAGER.get_session_name(current_id)
            name_key = f"session_name_{current_id}"
            pending_key = f"pending_session_name_{current_id}"

            if pending_key in st.session_state:
                st.session_state[name_key] = st.session_state[pending_key]
                del st.session_state[pending_key]
            else:
                st.session_state.setdefault(name_key, current_name)

            st.text_input(
                "会话名称",
                key=name_key,
                max_chars=40,
            )
            normalized = st.session_state[name_key].strip()
            latest_name = HISTORY_MANAGER.get_session_name(current_id)
            if normalized and normalized != latest_name:
                HISTORY_MANAGER.rename_session(current_id, normalized)
                updated_name = HISTORY_MANAGER.get_session_name(current_id)
                if updated_name != normalized:
                    st.session_state[pending_key] = updated_name

        col_create, col_delete = st.columns(2)
        if col_create.button("➕ 新建", width="stretch"):
            new_session = HISTORY_MANAGER.create_session()
            _switch_session(new_session)

        if col_delete.button("🗑️ 删除", width="stretch"):
            current = st.session_state.session_id
            HISTORY_MANAGER.clear(session_id=current)
            remaining = HISTORY_MANAGER.list_sessions()
            if remaining:
                _switch_session(remaining[-1])
            else:
                _switch_session(HISTORY_MANAGER.create_session())


def render_chat_interface() -> None:
    '''Render primary chat pane with message history and input box.'''
    render_app_header()

    status_placeholder = st.empty()

    chat_container = st.container(border=True)
    with chat_container:
        if not st.session_state.messages:
            st.info('欢迎使用 Market Lens！请在下方输入股票分析需求，或从侧边栏选择历史会话。')
        for msg in st.session_state.messages:
            with st.chat_message(msg['role']):
                st.markdown(msg['content'])

    user_prompt = st.chat_input('请输入分析需求，例如：分析 AAPL 最新动态')
    if not user_prompt:
        return

    st.session_state.messages.append({'role': 'user', 'content': user_prompt})
    with chat_container:
        with st.chat_message('user'):
            st.markdown(user_prompt)

    lc_history = _build_langchain_history(st.session_state.messages[:-1])

    assistant_message: Dict[str, str] = {'role': 'assistant', 'content': ''}
    st.session_state.messages.append(assistant_message)

    with chat_container:
        with st.chat_message('assistant'):
            response_placeholder = st.empty()
            response_placeholder.markdown('⌛ 正在生成回答…')

    _maybe_refresh_agent()
    agent = st.session_state.agent
    callback = StreamlitAgentCallback(status_placeholder, response_placeholder)

    with st.spinner('AI Agent 正在处理请求…'):
        try:
            result = agent.invoke({'input': user_prompt, 'messages': lc_history}, callbacks=[callback])
        except Exception as exc:  # pragma: no cover - surface to UI
            error_msg = f'⚠️ 调用代理时出错：{exc}'
            callback.emit_error(error_msg)
            final_answer = error_msg
        else:
            streaming_answer = callback.get_response_text()
            final_answer = streaming_answer or result.get('output', '抱歉，未获取到回复。')
            response_placeholder.markdown(final_answer)

    assistant_message['content'] = final_answer
    HISTORY_MANAGER.add(st.session_state.session_id, user_prompt, final_answer)
    status_placeholder.empty()


def main() -> None:
    st.set_page_config(
        page_title='Market Lens AI',
        page_icon=str(ICON_PATH),
        layout='wide',
        initial_sidebar_state='collapsed',
    )

    _ensure_auth_state()

    if st.session_state.logout_requested:
        _perform_logout()

    if not st.session_state.auth.get('is_authenticated'):
        render_login()
        return

    _initialize_session_state()
    render_sidebar()

    if st.session_state.logout_requested:
        _perform_logout()
        render_login()
        return

    render_chat_interface()


if __name__ == "__main__":
    main()
