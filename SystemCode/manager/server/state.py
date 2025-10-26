import copy
from typing import Dict, Optional

from manager.agent_stream_gradio import enabled_analysis_types


class UserStateStore:
    """Maintain per-auth-session UI state such as analysis configuration."""

    def __init__(self) -> None:
        self._analysis_config: Dict[str, Dict[str, bool]] = {}
        self._active_session: Dict[str, Optional[str]] = {}

    def get_analysis_config(self, session_token: str) -> Dict[str, bool]:
        if session_token not in self._analysis_config:
            self._analysis_config[session_token] = copy.deepcopy(enabled_analysis_types)
        return self._analysis_config[session_token]

    def update_analysis_config(self, session_token: str, payload: Dict[str, bool]) -> Dict[str, bool]:
        config = self.get_analysis_config(session_token)
        for key, value in payload.items():
            if key in enabled_analysis_types:
                config[key] = bool(value)
        return config

    def reset_analysis_config(self, session_token: str) -> Dict[str, bool]:
        self._analysis_config[session_token] = copy.deepcopy(enabled_analysis_types)
        return self._analysis_config[session_token]

    def get_active_session(self, session_token: str) -> Optional[str]:
        return self._active_session.get(session_token)

    def set_active_session(self, session_token: str, session_id: Optional[str]) -> None:
        self._active_session[session_token] = session_id

    def drop_session(self, session_token: str) -> None:
        self._analysis_config.pop(session_token, None)
        self._active_session.pop(session_token, None)


USER_STATE = UserStateStore()
