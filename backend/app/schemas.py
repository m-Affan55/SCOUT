from pydantic import BaseModel
from typing import Optional, Dict, Any, List

class DocumentSchema(BaseModel):
    id: int
    doc_type: str
    file_path: str

    class Config:
        from_attributes = True

class UserProfileSchema(BaseModel):
    id: int
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    phone: Optional[str] = None
    personal_data: Dict[str, Any] = {}
    address_data: Dict[str, Any] = {}
    education_data: Dict[str, Any] = {}
    professional_data: Dict[str, Any] = {}
    captcha_solved: Optional[str] = None

    class Config:
        from_attributes = True

class UserSchema(BaseModel):
    id: int
    clerk_id: str
    email: str
    profile: Optional[UserProfileSchema] = None
    documents: List[DocumentSchema] = []

    class Config:
        from_attributes = True

class OnboardingRequest(BaseModel):
    clerk_id: str
    email: str
    first_name: str
    last_name: str
    phone: str
