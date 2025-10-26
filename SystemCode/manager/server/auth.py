import json
import os
import secrets
import time
from dataclasses import dataclass
from typing import Dict, Optional


DEFAULT_CREDENTIALS = {"admin": "123456"}


def get_allowed_users() -> Dict[str, str]:
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


def validate_credentials(email: str, password: str) -> bool:
    """Return True if provided credentials match configured users."""
    if not email or not password:
        return False
    normalized_email = email.strip().lower()
    return get_allowed_users().get(normalized_email) == password


@dataclass
class AuthSession:
    token: str
    email: str
    role: str
    created_at: float
    display_name: str


class AuthManager:
    """Simple in-memory auth session store."""

    def __init__(self) -> None:
        self._sessions: Dict[str, AuthSession] = {}

    def create_session(self, email: str, role: str, display_name: Optional[str] = None) -> AuthSession:
        token = secrets.token_urlsafe(32)
        session = AuthSession(
            token=token,
            email=email,
            role=role,
            created_at=time.time(),
            display_name=display_name or email,
        )
        self._sessions[token] = session
        return session

    def get_session(self, token: str) -> Optional[AuthSession]:
        if not token:
            return None
        return self._sessions.get(token)

    def delete_session(self, token: str) -> None:
        self._sessions.pop(token, None)


AUTH_MANAGER = AuthManager()
