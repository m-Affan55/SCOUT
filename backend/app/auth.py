import os
from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException
from sqlalchemy.orm import Session
from . import models, schemas
from .database import get_db
from .auth_middleware import verify_clerk_token

router = APIRouter(prefix="/api/auth", tags=["auth"])

UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

# File upload validation
ALLOWED_FILE_TYPES = {"application/pdf", "application/msword", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB

def validate_file_upload(file: UploadFile) -> None:
    """Validate file upload for security."""
    if not file:
        return
    
    # Check file size
    file.file.seek(0, 2)  # Seek to end
    file_size = file.file.tell()
    file.file.seek(0)  # Seek back to beginning
    
    if file_size > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"File size exceeds maximum allowed size of {MAX_FILE_SIZE // (1024*1024)}MB"
        )
    
    # Check file type
    if file.content_type not in ALLOWED_FILE_TYPES:
        raise HTTPException(
            status_code=415,
            detail=f"File type {file.content_type} not allowed. Allowed types: {', '.join(ALLOWED_FILE_TYPES)}"
        )

@router.post("/onboarding")
async def onboarding(
    first_name: str = Form(...),
    last_name: str = Form(...),
    phone: str = Form(...),
    father_name: str = Form(""),
    date_of_birth: str = Form(""),
    gender: str = Form(""),
    cnic: str = Form(""),
    resume: UploadFile = File(None),
    db: Session = Depends(get_db),
    clerk_id: str = Depends(verify_clerk_token)
):
    # Get email from Clerk token (would need to be extracted in middleware)
    # For now, we'll skip email validation since Clerk handles it
    email = f"{clerk_id}@placeholder.com"  # Ensure unique email to avoid constraint violation
    
    # Check if user already exists
    user = db.query(models.User).filter(models.User.clerk_id == clerk_id).first()
    if not user:
        user = models.User(clerk_id=clerk_id, email=email)
        db.add(user)
        db.commit()
        db.refresh(user)
        
    personal_data = {
        "father_name": father_name,
        "date_of_birth": date_of_birth,
        "gender": gender,
        "cnic": cnic
    }
        
    # Check profile
    if not user.profile:
        profile = models.UserProfile(
            user_id=user.id,
            first_name=first_name,
            last_name=last_name,
            phone=phone,
            personal_data=personal_data
        )
        db.add(profile)
    else:
        user.profile.first_name = first_name
        user.profile.last_name = last_name
        user.profile.phone = phone
        user.profile.personal_data = personal_data

    db.commit()

    # Handle file upload with validation
    if resume:
        validate_file_upload(resume)
        
        # Sanitize filename
        safe_filename = "".join(c for c in resume.filename if c.isalnum() or c in ('.', '_', '-')).rstrip()
        if not safe_filename:
            safe_filename = "upload"
            
        file_path = os.path.join(UPLOAD_DIR, f"{user.id}_{safe_filename}")
        with open(file_path, "wb") as buffer:
            buffer.write(await resume.read())
            
        doc = db.query(models.Document).filter(
            models.Document.user_id == user.id, 
            models.Document.doc_type == "resume"
        ).first()
        
        if not doc:
            doc = models.Document(user_id=user.id, doc_type="resume", file_path=file_path)
            db.add(doc)
        else:
            doc.file_path = file_path
            
        db.commit()

    return {"message": "Onboarding complete"}
