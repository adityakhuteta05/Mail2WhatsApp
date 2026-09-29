from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base


class DeliveryLog(Base):
    __tablename__ = "delivery_logs"

    id = Column(Integer, primary_key=True, index=True)
    email_id = Column(Integer, ForeignKey("emails.id", ondelete="CASCADE"), nullable=False, index=True)
    whatsapp_message_id = Column(String(256), unique=True, index=True, nullable=True)
    recipient = Column(String(64), nullable=False)
    message_type = Column(String(32), default="text", nullable=False)  # text, document, image, etc.
    
    # Status: sent, delivered, read, failed
    status = Column(String(32), default="sent", index=True, nullable=False)
    sent_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    delivered_at = Column(DateTime, nullable=True)
    read_at = Column(DateTime, nullable=True)
    error = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    email = relationship("Email", back_populates="delivery_logs")

    def __repr__(self):
        return f"<DeliveryLog id={self.id} wa_id='{self.whatsapp_message_id}' status='{self.status}'>"
