"""
In-memory session storage for OAuth state and user sessions.

This module provides simple in-memory storage for OAuth CSRF state
tokens and user sessions.
"""

import secrets
from datetime import datetime, timedelta
from typing import Dict, Optional


class SessionStore:
    """In-memory session storage for OAuth state and tokens"""

    def __init__(self):
        self._states = {}  # OAuth state -> timestamp
        self._sessions = {}  # session_id -> user_data

    def create_state(self) -> str:
        """Generate and store OAuth state parameter"""
        state = secrets.token_urlsafe(32)
        self._states[state] = datetime.utcnow()
        return state

    def validate_state(self, state: str) -> bool:
        """Validate OAuth state and remove if valid"""
        if state not in self._states:
            return False

        # Check if state is not expired (5 minutes)
        created_at = self._states[state]
        if datetime.utcnow() - created_at > timedelta(minutes=5):
            del self._states[state]
            return False

        del self._states[state]
        return True

    def create_session(self, user_data: Dict) -> str:
        """Create session for authenticated user"""
        session_id = secrets.token_urlsafe(32)
        self._sessions[session_id] = {
            'user': user_data,
            'created_at': datetime.utcnow()
        }
        return session_id

    def get_session(self, session_id: str) -> Optional[Dict]:
        """Retrieve session data"""
        return self._sessions.get(session_id)

    def delete_session(self, session_id: str) -> None:
        """Delete session"""
        if session_id in self._sessions:
            del self._sessions[session_id]

    def cleanup_expired(self) -> None:
        """Remove expired states (older than 5 minutes)"""
        now = datetime.utcnow()
        expired_states = [
            state for state, created_at in self._states.items()
            if now - created_at > timedelta(minutes=5)
        ]
        for state in expired_states:
            del self._states[state]


# Global session store instance
session_store = SessionStore()
