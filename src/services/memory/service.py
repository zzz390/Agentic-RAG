import logging
from dataclasses import dataclass
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from src.repositories.conversation import ConversationRepository
from src.services.cache.client import CacheClient

logger = logging.getLogger(__name__)


@dataclass
class ConversationMemoryContext:
    short_term: List[Dict[str, str]]
    long_term: List[Dict[str, str]]

    @property
    def has_memory(self) -> bool:
        return bool(self.short_term or self.long_term)

    def contextualize_query(self, query: str) -> str:
        """Add the last user turn to retrieval so follow-up pronouns remain searchable."""
        for message in reversed(self.short_term or self.long_term):
            if message.get("role") == "user" and message.get("content"):
                return f"上一轮问题：{message['content']}\n当前问题：{query}"
        return query

    def as_agent_context(self, query: str) -> str:
        if not self.has_memory:
            return query
        lines = ["以下是与当前用户相关的会话记忆，仅用于理解上下文："]
        for message in [*self.long_term, *self.short_term]:
            role = "用户" if message.get("role") == "user" else "助手"
            lines.append(f"{role}: {message.get('content', '')}")
        lines.append(f"当前问题：{query}")
        return "\n".join(lines)


class ConversationMemoryService:
    """Redis short-term memory plus PostgreSQL cross-session memory."""

    def __init__(self, cache_client: Optional[CacheClient], session: Session):
        self.cache_client = cache_client
        self.repository = ConversationRepository(session)

    async def load_context(
        self,
        user_id: str,
        session_id: str,
        short_limit: int = 12,
        long_limit: int = 12,
    ) -> ConversationMemoryContext:
        short_term: List[Dict[str, str]] = []
        if self.cache_client:
            try:
                short_term = await self.cache_client.get_conversation_history(
                    user_id=user_id,
                    session_id=session_id,
                    limit=short_limit,
                )
            except Exception as exc:
                logger.warning("Unable to load Redis conversation memory: %s", exc)

        # PostgreSQL is also the fallback if Redis expired or was restarted.
        if not short_term:
            short_term = self.repository.get_recent(
                user_id=user_id,
                session_id=session_id,
                limit=short_limit,
            )

        long_term = self.repository.get_recent(
            user_id=user_id,
            session_id=session_id,
            exclude_session=True,
            limit=long_limit,
        )
        return ConversationMemoryContext(short_term=short_term, long_term=long_term)

    async def record_exchange(
        self,
        user_id: str,
        session_id: str,
        user_message: str,
        assistant_message: str,
    ) -> None:
        # PostgreSQL is authoritative long-term storage.
        self.repository.add_exchange(user_id, session_id, user_message, assistant_message)
        if self.cache_client:
            try:
                await self.cache_client.append_conversation_exchange(
                    user_id=user_id,
                    session_id=session_id,
                    user_message=user_message,
                    assistant_message=assistant_message,
                )
            except Exception as exc:
                logger.warning("Unable to update Redis conversation memory: %s", exc)
