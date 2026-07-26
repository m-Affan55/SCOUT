import json
import os
from sqlalchemy.orm import Session
from . import models

PROFILE_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "user_profile.json")

def get_user_profile_from_db(db: Session, user_id: int) -> dict:
    """Get user profile from database and return as dict compatible with agent."""
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        return {}
    
    profile = {}
    
    if user.profile:
        # Personal data
        if user.profile.first_name:
            profile["personal"] = profile.get("personal", {})
            profile["personal"]["first_name"] = user.profile.first_name
        if user.profile.last_name:
            profile["personal"] = profile.get("personal", {})
            profile["personal"]["last_name"] = user.profile.last_name
        if user.profile.phone:
            profile["personal"] = profile.get("personal", {})
            profile["personal"]["phone"] = user.profile.phone
        
        # Merge JSON fields
        if user.profile.personal_data:
            profile["personal"] = {**profile.get("personal", {}), **user.profile.personal_data}
        if user.profile.address_data:
            profile["address"] = user.profile.address_data
        if user.profile.education_data:
            profile["education"] = user.profile.education_data
        if user.profile.professional_data:
            profile["professional"] = user.profile.professional_data
        if user.profile.captcha_solved:
            profile["captcha_solved"] = user.profile.captcha_solved
    
    # Documents
    profile["documents"] = {}
    for doc in user.documents:
        profile["documents"][doc.doc_type] = doc.file_path
    
    return profile

def save_to_profile_db(db: Session, user_id: int, field_key: str, value: str, pause_message: str = ""):
    """Save a user-provided value to database profile."""
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user or not user.profile:
        return False
    
    # Handle top-level keys
    if "." not in field_key:
        if field_key == "captcha_solved":
            user.profile.captcha_solved = value
        elif field_key == "clarification":
            # Store clarifications as a list in personal_data
            if not user.profile.personal_data:
                user.profile.personal_data = {}
            if "clarifications" not in user.profile.personal_data:
                user.profile.personal_data["clarifications"] = []
            # Append new clarification entry
            user.profile.personal_data["clarifications"].append({
                "question": pause_message,
                "answer": value
            })
        db.commit()
        return True
    
    # Handle nested keys using dot notation
    keys = field_key.split(".")
    top_level = keys[0]
    
    if top_level == "personal":
        if not user.profile.personal_data:
            user.profile.personal_data = {}
        obj = user.profile.personal_data
        for k in keys[1:-1]:
            if k not in obj or not isinstance(obj[k], dict):
                obj[k] = {}
            obj = obj[k]
        obj[keys[-1]] = value
    elif top_level == "address":
        if not user.profile.address_data:
            user.profile.address_data = {}
        obj = user.profile.address_data
        for k in keys[1:-1]:
            if k not in obj or not isinstance(obj[k], dict):
                obj[k] = {}
            obj = obj[k]
        obj[keys[-1]] = value
    elif top_level == "education":
        if not user.profile.education_data:
            user.profile.education_data = {}
        obj = user.profile.education_data
        for k in keys[1:-1]:
            if k not in obj or not isinstance(obj[k], dict):
                obj[k] = {}
            obj = obj[k]
        obj[keys[-1]] = value
    elif top_level == "professional":
        if not user.profile.professional_data:
            user.profile.professional_data = {}
        obj = user.profile.professional_data
        for k in keys[1:-1]:
            if k not in obj or not isinstance(obj[k], dict):
                obj[k] = {}
            obj = obj[k]
        obj[keys[-1]] = value
    
    db.commit()
    return True

# Legacy JSON functions for backward compatibility during migration
def save_to_profile_json(field_key: str, value: str):
    """Legacy function - saves to JSON file. Will be deprecated."""
    if not field_key or not value:
        return
    
    try:
        with open(PROFILE_PATH, "r") as f:
            profile = json.load(f)
    except Exception:
        profile = {}
    
    if "." not in field_key:
        profile[field_key] = str(value)
    else:
        keys = field_key.split(".")
        obj = profile
        for k in keys[:-1]:
            if k not in obj or not isinstance(obj[k], dict):
                obj[k] = {}
            obj = obj[k]
        obj[keys[-1]] = str(value)
    
    try:
        with open(PROFILE_PATH, "w") as f:
            json.dump(profile, f, indent=2)
    except Exception as e:
        print(f"[Profile] Failed to save to JSON: {e}")
