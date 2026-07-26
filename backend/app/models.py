from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.ext.mutable import MutableDict
from .database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    clerk_id = Column(String, unique=True, index=True) # ID from Clerk Auth
    email = Column(String, unique=True, index=True)
    
    profile = relationship("UserProfile", back_populates="user", uselist=False)
    documents = relationship("Document", back_populates="user")

class UserProfile(Base):
    __tablename__ = "user_profiles"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    
    # Keeping it simple for now, mapping closely to user_profile.json
    first_name = Column(String, nullable=True)
    last_name = Column(String, nullable=True)
    phone = Column(String, nullable=True)
    
    # Store complex nested things like education/professional in JSON for flexibility
    personal_data = Column(MutableDict.as_mutable(JSON), default=dict)
    address_data = Column(MutableDict.as_mutable(JSON), default=dict)
    education_data = Column(MutableDict.as_mutable(JSON), default=dict)
    professional_data = Column(MutableDict.as_mutable(JSON), default=dict)
    
    captcha_solved = Column(String, nullable=True)

    user = relationship("User", back_populates="profile")

class Document(Base):
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    doc_type = Column(String) # e.g., "resume", "cnic_front"
    file_path = Column(String) # absolute or relative path to backend/uploads/

    user = relationship("User", back_populates="documents")
