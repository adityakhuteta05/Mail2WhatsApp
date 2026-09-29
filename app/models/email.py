from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base


class Email(Base):
    __tablename__ = "emails"

    id = Column(Integer, primary_key=True, index=True)
    account_id = Column(Integer, ForeignKey("gmail_accounts.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Critical requirement FR-09: UNIQUE(gmail_message_id) must prevent duplicate processing
    gmail_message_id = Column(String(128), unique=True, index=True, nullable=False)
    thread_id = Column(String(128), nullable=True)
    
    sender = Column(String(512), nullable=True)
    recipients = Column(Text, nullable=True)  # Formatted string or JSON list of recipients
    subject = Column(Text, nullable=True)
    received_at = Column(DateTime, index=True, nullable=True)
    
    body_text = Column(Text, nullable=True)
    body_html = Column(Text, nullable=True)
    body_ref = Column(String(512), nullable=True)  # Pointer if external storage used
    
    # State machine (Section 15):
    # DISCOVERED -> PROCESSING -> [RETRY_WAIT, FAILED, SENT] -> DELIVERY_PENDING -> [DELIVERED, READ]
    # Also PARTIAL for attachments too large/unsupported
    status = Column(String(64), default="DISCOVERED", index=True, nullable=False)
    error_message = Column(Text, nullable=True)
    retry_count = Column(Integer, default=0, nullable=False)
    next_retry_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    account = relationship("GmailAccount", back_populates="emails")
    attachments = relationship("Attachment", back_populates="email", cascade="all, delete-orphan")
    delivery_logs = relationship("DeliveryLog", back_populates="email", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Email id={self.id} msg_id='{self.gmail_message_id}' status='{self.status}'>"
