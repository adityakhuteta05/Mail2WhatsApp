from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime
from sqlalchemy.orm import relationship
from app.database import Base


class GmailAccount(Base):
    __tablename__ = "gmail_accounts"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    refresh_token_ref = Column(Text, nullable=False)  # Fernet-encrypted refresh token
    access_token = Column(Text, nullable=True)        # Cached transient access token
    token_expiry = Column(DateTime, nullable=True)
    history_id = Column(String(128), nullable=True)   # Latest synchronized history ID
    watch_expiry = Column(DateTime, nullable=True)    # Expiration date of active Gmail watch
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    emails = relationship("Email", back_populates="account", cascade="all, delete-orphan")
    sync_runs = relationship("SyncRun", back_populates="account", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<GmailAccount id={self.id} email='{self.email}' history_id='{self.history_id}'>"
