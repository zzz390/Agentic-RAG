from typing import Dict, List, Optional

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from src.models.conversation import ConversationMessage


class ConversationRepository:
    """PostgreSQL persistence for conversation history."""

    def __init__(self, session: Session):
        self.session = session

    def add_exchange(
        self,
        user_id: str,
        session_id: str,
        user_message: str,
        assistant_message: str,
    ) -> None:
        self.session.add_all(
            [
                ConversationMessage(
                    user_id=user_id,
                    session_id=session_id,
                    role="user",
                    content=user_message,
                ),
                ConversationMessage(
                    user_id=user_id,
                    session_id=session_id,
                    role="assistant",
                    content=assistant_message,
                ),
            ]
        )
        self.session.commit()

    def get_recent(
        self,
        user_id: str,
        limit: int = 12,
        session_id: Optional[str] = None,
        exclude_session: bool = False,
    ) -> List[Dict[str, str]]:
        statement = select(ConversationMessage).where(ConversationMessage.user_id == user_id)
        if session_id:
            condition = ConversationMessage.session_id != session_id if exclude_session else ConversationMessage.session_id == session_id
            statement = statement.where(condition)
        statement = statement.order_by(ConversationMessage.created_at.desc()).limit(limit)
        messages = list(reversed(list(self.session.scalars(statement))))
        return [{"role": message.role, "content": message.content} for message in messages]

    def clear_session(self, user_id: str, session_id: str) -> int:
        result = self.session.execute(
            delete(ConversationMessage).where(
                ConversationMessage.user_id == user_id,
                ConversationMessage.session_id == session_id,
            )
        )
        self.session.commit()
        return int(result.rowcount or 0)
