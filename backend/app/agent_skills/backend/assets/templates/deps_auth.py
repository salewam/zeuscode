"""Template: auth dependency sketch (Bearer current user).

Greenfield Studio: keep beside routers as deps.py.
ZeusCode cabinet: prefer existing app.deps — do not reinvent.
"""

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

security = HTTPBearer(auto_error=True)


async def get_current_user(
    creds: HTTPAuthorizationCredentials = Depends(security),
):
    token = creds.credentials
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    # user = decode_and_load(token)
    # if not user:
    #     raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token")
    # return user
    raise HTTPException(
        status.HTTP_501_NOT_IMPLEMENTED,
        "Template only — wire token verify",
    )
