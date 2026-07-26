"""مجال الملفات والأمن — TourismFile, SecureFile, PoliceNotification."""
import datetime
from sqlalchemy import Column, Integer, String, Date, DateTime, Text, ForeignKey
from sqlalchemy.orm import relationship
from models import Base


class TourismFile(Base):
    __tablename__ = "tourism_files"
    id = Column(Integer, primary_key=True)
    created_date = Column(Date, default=datetime.date.today)
    title = Column(String, nullable=False)
    category = Column(String)
    related_to = Column(String)
    file_path = Column(String)
    notes = Column(Text)


class SecureFile(Base):
    __tablename__ = "secure_files"
    id = Column(Integer, primary_key=True)
    owner_user_id = Column(Integer, nullable=True)
    category = Column(String, default="doc")
    record_type = Column(String, nullable=True)
    record_id = Column(Integer, nullable=True)
    stored_name = Column(String, nullable=False)
    original_name = Column(String, nullable=False)
    mime = Column(String, nullable=False)
    size = Column(Integer, default=0)
    sha256 = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)


class PoliceNotification(Base):
    __tablename__ = "police_notifications"
    id = Column(Integer, primary_key=True)
    created_date = Column(Date, default=datetime.date.today)
    group_leader = Column(String, nullable=False)
    nationality = Column(String)
    tourists_count = Column(Integer, default=1)
    hotel_id = Column(Integer, ForeignKey("hotels.id"), nullable=True)
    arrival_date = Column(Date)
    notification_date = Column(Date)
    status = Column(String, default="pending")
    notes = Column(Text)
    hotel = relationship("Hotel")
