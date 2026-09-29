from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base


class SyncRun(Base):
    __tablename__ = "sync_runs"

    id = Column(Integer, primary_key=True, index=True)
    account_id = Column(Integer, ForeignKey("gmail_accounts.id", ondelete="CASCADE"), nullable=False, index=True)
    started_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    completed_at = Column(DateTime, nullable=True)
    history_start = Column(String(128), nullable=True)
    history_end = Column(String(128), nullable=True)
    messages_discovered = Column(Integer, default=0, nullable=False)
    messages_processed = Column(Integer, default=0, nullable=False)
    messages_failed = Column(Integer, default=0, nullable=False)
    
    # Status: RUNNING, SUCCESS, FAILED, PARTIAL
    status = Column(String(32), default="RUNNING", nullable=False)
    error_details = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    account = relationship("GmailAccount", back_populates="sync_runs")

    def __repr__(self):
        return f"<SyncRun id={self.id} account_id={self.account_id} status='{self.status}'>"
