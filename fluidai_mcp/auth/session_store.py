"""
In-memory session storage for OAuth state and user sessions.

This module provides simple in-memory storage for OAuth CSRF state
tokens and user sessions, with optional persistent database logging.
"""

import secrets
from datetime import datetime, timedelta
from typing import Dict, Optional
from loguru import logger


class SessionStore:
    """In-memory session storage for OAuth state and tokens"""

    def __init__(self, db=None):
        """
        Initialize session store.

        Args:
            db: Optional AuthDatabase instance for persistent logging
        """
        self._states = {}  # OAuth state -> timestamp
        self._sessions = {}  # session_id -> user_data
        self.db = db  # Optional database for persistence

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

    def create_session(self, user_data: Dict, ip_address: Optional[str] = None,
                      user_agent: Optional[str] = None, access_token: Optional[str] = None,
                      expires_at: Optional[str] = None) -> str:
        """
        Create session for authenticated user.

        Args:
            user_data: User information from Auth0
            ip_address: Client IP address (optional)
            user_agent: Client user agent string (optional)
            access_token: JWT access token (optional, for hashing)
            expires_at: Token expiration time (optional)

        Returns:
            Session ID
        """
        # Always create in-memory session first (critical path)
        session_id = secrets.token_urlsafe(32)
        self._sessions[session_id] = {
            'user': user_data,
            'created_at': datetime.utcnow()
        }

        # Try to persist to database (non-blocking, best effort)
        if self.db:
            try:
                # Upsert user profile
                self.db.upsert_user(user_data)

                # Create session record
                self.db.create_session_record({
                    'session_id': session_id,
                    'user_id': user_data.get('sub'),
                    'access_token': access_token,
                    'ip_address': ip_address,
                    'user_agent': user_agent,
                    'expires_at': expires_at or ''
                })

                # Log login event
                self.db.log_auth_event({
                    'event_type': 'login',
                    'user_id': user_data.get('sub'),
                    'session_id': session_id,
                    'ip_address': ip_address,
                    'user_agent': user_agent,
                    'provider': user_data.get('provider', 'unknown'),
                    'success': True
                })

                logger.debug(f"Session persisted to database: {session_id}")

            except Exception as e:
                # Log error but don't fail the session creation
                logger.error(f"Failed to persist session to database: {e}")
                # Session still works with in-memory storage

        return session_id

    def get_session(self, session_id: str) -> Optional[Dict]:
        """Retrieve session data"""
        return self._sessions.get(session_id)

    def delete_session(self, session_id: str, ip_address: Optional[str] = None,
                      user_agent: Optional[str] = None) -> None:
        """
        Delete session and log logout event.

        Args:
            session_id: Session ID to delete
            ip_address: Client IP address (optional)
            user_agent: Client user agent string (optional)
        """
        # Get user_id before deleting session
        user_id = None
        if session_id in self._sessions:
            user_data = self._sessions[session_id].get('user', {})
            user_id = user_data.get('sub')
            del self._sessions[session_id]

        # Try to persist logout to database (non-blocking, best effort)
        if self.db and session_id:
            try:
                # Mark session as logged out
                self.db.mark_session_logged_out(session_id)

                # Log logout event
                if user_id:
                    self.db.log_auth_event({
                        'event_type': 'logout',
                        'user_id': user_id,
                        'session_id': session_id,
                        'ip_address': ip_address,
                        'user_agent': user_agent,
                        'success': True
                    })

                logger.debug(f"Session logout persisted to database: {session_id}")

            except Exception as e:
                # Log error but don't fail the logout
                logger.error(f"Failed to persist logout to database: {e}")

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
