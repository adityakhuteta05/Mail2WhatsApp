from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base


class Attachment(Base):
    __tablename__ = "attachments"

    id = Column(Integer, primary_key=True, index=True)
    email_id = Column(Integer, ForeignKey("emails.id", ondelete="CASCADE"), nullable=False, index=True)
    gmail_attachment_id = Column(String(512), nullable=False)
    filename = Column(String(512), nullable=False)
    mime_type = Column(String(128), nullable=False)
    size = Column(Integer, nullable=False)  # in bytes
    whatsapp_media_id = Column(String(256), nullable=True)
    
    # Status: PENDING, UPLOADED, SENT, FAILED, SKIPPED
    status = Column(String(64), default="PENDING", nullable=False)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    email = relationship("Email", back_populates="attachments")

    def __repr__(self):
        return f"<Attachment id={self.id} filename='{self.filename}' size={self.size} status='{self.status}'>"
