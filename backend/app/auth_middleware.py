import os
import urllib.request
import json
from fastapi import HTTPException, Security, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError
from dotenv import load_dotenv

load_dotenv()

security = HTTPBearer()

jwks_cache = None

def get_jwks(token: str):
    global jwks_cache
    if jwks_cache:
        return jwks_cache
        
    try:
        # Get the issuer from the unverified token to find the JWKS URL
        unverified_claims = jwt.get_unverified_claims(token)
        iss = unverified_claims.get("iss")
        if iss:
            url = f"{iss.rstrip('/')}/.well-known/jwks.json"
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req) as response:
                jwks_cache = json.loads(response.read().decode('utf-8'))
                return jwks_cache
    except Exception as e:
        print(f"Failed to fetch JWKS: {e}")
    return None

async def verify_clerk_token(credentials: HTTPAuthorizationCredentials = Security(security)) -> str:
    """Verify Clerk JWT token and return the user ID."""
    token = credentials.credentials
    
    try:
        jwks = get_jwks(token)
        if not jwks:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Could not fetch JWKS for token verification"
            )

        # Decode and verify the JWT token using the JWKS public keys
        payload = jwt.decode(
            token,
            jwks,
            algorithms=["RS256"],
            options={"verify_aud": False}
        )
        
        # Extract user ID from the token
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token: missing user ID"
            )
        
        return user_id
        
    except JWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {str(e)}"
        )
