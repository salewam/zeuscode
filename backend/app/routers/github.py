"""GitHub OAuth + repo linking for Studio workspaces."""

from __future__ import annotations

import secrets
from datetime import datetime, timezone
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.crypto_util import decrypt_token, encrypt_token
from app.db import get_db
from app.deps import get_current_user
from app import git_ops
from app.models import GitHubAccount, Project, User
from app import workspace as ws

router = APIRouter(prefix="/github", tags=["github"])
settings = get_settings()

# short-lived OAuth state → user_id
_oauth_states: dict[str, int] = {}


def _now() -> datetime:
    return datetime.now(timezone.utc)


class PatIn(BaseModel):
    token: str = Field(min_length=8, max_length=200)
    login: str | None = None


class LinkRepoIn(BaseModel):
    repo: str = Field(description="owner/name")
    clone: bool = True
    create_if_missing: bool = False
    private: bool = True


class CreateRepoIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    private: bool = True
    description: str = ""


async def _get_account(db: AsyncSession, user_id: int) -> GitHubAccount | None:
    r = await db.execute(select(GitHubAccount).where(GitHubAccount.user_id == user_id))
    return r.scalar_one_or_none()


async def _token_for(db: AsyncSession, user_id: int) -> str:
    acc = await _get_account(db, user_id)
    if not acc or not acc.access_token_enc:
        raise HTTPException(400, "GitHub не подключён")
    try:
        return decrypt_token(acc.access_token_enc)
    except ValueError as e:
        raise HTTPException(400, "Токен GitHub повреждён — переподключи") from e


@router.get("/status")
async def github_status(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    acc = await _get_account(db, user.id)
    configured = bool(settings.GITHUB_CLIENT_ID and settings.GITHUB_CLIENT_SECRET)
    return {
        "connected": bool(acc and acc.login),
        "login": acc.login if acc else None,
        "avatar_url": acc.avatar_url if acc else None,
        "oauth_configured": configured,
        "pat_ok": True,  # always allow PAT fallback
    }


@router.get("/connect")
async def github_connect(user: User = Depends(get_current_user)):
    if not settings.GITHUB_CLIENT_ID or not settings.GITHUB_CLIENT_SECRET:
        raise HTTPException(
            400,
            "GitHub OAuth не настроен. Задай GITHUB_CLIENT_ID/SECRET в .env или вставь PAT через /github/pat",
        )
    state = secrets.token_urlsafe(24)
    _oauth_states[state] = user.id
    params = {
        "client_id": settings.GITHUB_CLIENT_ID,
        "redirect_uri": settings.GITHUB_REDIRECT_URI,
        "scope": "repo read:user",
        "state": state,
    }
    url = "https://github.com/login/oauth/authorize?" + urlencode(params)
    return {"url": url}


@router.get("/callback")
async def github_callback(
    code: str = Query(...),
    state: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    user_id = _oauth_states.pop(state, None)
    if not user_id:
        raise HTTPException(400, "Invalid OAuth state")
    async with httpx.AsyncClient(timeout=30) as client:
        tok = await client.post(
            "https://github.com/login/oauth/access_token",
            headers={"Accept": "application/json"},
            data={
                "client_id": settings.GITHUB_CLIENT_ID,
                "client_secret": settings.GITHUB_CLIENT_SECRET,
                "code": code,
                "redirect_uri": settings.GITHUB_REDIRECT_URI,
            },
        )
        data = tok.json()
        access = data.get("access_token")
        if not access:
            raise HTTPException(400, f"OAuth failed: {data}")
        me = await client.get(
            "https://api.github.com/user",
            headers={"Authorization": f"Bearer {access}", "Accept": "application/vnd.github+json"},
        )
        profile = me.json()
    login = profile.get("login") or ""
    avatar = profile.get("avatar_url") or ""
    acc = await _get_account(db, user_id)
    if not acc:
        acc = GitHubAccount(user_id=user_id)
        db.add(acc)
    acc.login = login
    acc.avatar_url = avatar
    acc.access_token_enc = encrypt_token(access)
    acc.scopes = data.get("scope") or "repo"
    acc.updated_at = _now()
    await db.commit()
    return RedirectResponse(f"{settings.APP_PUBLIC_URL}/app?github=connected#projects")


@router.post("/pat")
async def github_pat(
    body: PatIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Connect via Personal Access Token (classic or fine-grained with repo scope)."""
    token = body.token.strip()
    async with httpx.AsyncClient(timeout=20) as client:
        me = await client.get(
            "https://api.github.com/user",
            headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
        )
        if me.status_code >= 400:
            raise HTTPException(400, "Неверный GitHub token")
        profile = me.json()
    login = body.login or profile.get("login") or ""
    acc = await _get_account(db, user.id)
    if not acc:
        acc = GitHubAccount(user_id=user.id)
        db.add(acc)
    acc.login = login
    acc.avatar_url = profile.get("avatar_url") or ""
    acc.access_token_enc = encrypt_token(token)
    acc.scopes = "pat"
    acc.updated_at = _now()
    await db.commit()
    return {"ok": True, "login": login, "avatar_url": acc.avatar_url}


@router.delete("/disconnect")
async def github_disconnect(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    acc = await _get_account(db, user.id)
    if acc:
        await db.delete(acc)
        await db.commit()
    return {"ok": True}


@router.get("/repos")
async def list_repos(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    token = await _token_for(db, user.id)
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(
            "https://api.github.com/user/repos",
            params={"per_page": 50, "sort": "updated"},
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
            },
        )
        if r.status_code >= 400:
            raise HTTPException(r.status_code, r.text[:300])
        repos = r.json()
    return [
        {
            "full_name": x.get("full_name"),
            "private": x.get("private"),
            "default_branch": x.get("default_branch") or "main",
            "html_url": x.get("html_url"),
            "clone_url": x.get("clone_url"),
        }
        for x in repos
    ]


@router.post("/repos")
async def create_repo(
    body: CreateRepoIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    token = await _token_for(db, user.id)
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(
            "https://api.github.com/user/repos",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
            },
            json={
                "name": body.name.strip(),
                "private": body.private,
                "description": body.description or "ZeusCode Studio project",
                "auto_init": False,
            },
        )
        if r.status_code >= 400:
            raise HTTPException(r.status_code, r.text[:400])
        data = r.json()
    return {
        "full_name": data.get("full_name"),
        "clone_url": data.get("clone_url"),
        "html_url": data.get("html_url"),
        "default_branch": data.get("default_branch") or "main",
    }


@router.post("/projects/{project_id}/link")
async def link_project_repo(
    project_id: int,
    body: LinkRepoIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    p = await db.get(Project, project_id)
    if not p or p.user_id != user.id:
        raise HTTPException(404, "Project not found")
    token = await _token_for(db, user.id)
    repo = body.repo.strip().strip("/")
    if "/" not in repo:
        raise HTTPException(400, "repo должен быть owner/name")

    root = ws.ensure_workspace(user.id, p.id, title=p.title)
    clone_url = f"https://github.com/{repo}.git"
    default_branch = "main"

    async with httpx.AsyncClient(timeout=30) as client:
        meta = await client.get(
            f"https://api.github.com/repos/{repo}",
            headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
        )
        if meta.status_code == 404 and body.create_if_missing:
            owner, name = repo.split("/", 1)
            # create under user (ignore owner if different — GitHub API user/repos)
            created = await client.post(
                "https://api.github.com/user/repos",
                headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
                json={"name": name, "private": body.private, "auto_init": True},
            )
            if created.status_code >= 400:
                raise HTTPException(created.status_code, created.text[:400])
            data = created.json()
            repo = data.get("full_name") or repo
            clone_url = data.get("clone_url") or clone_url
            default_branch = data.get("default_branch") or "main"
        elif meta.status_code >= 400:
            raise HTTPException(meta.status_code, meta.text[:400])
        else:
            data = meta.json()
            clone_url = data.get("clone_url") or clone_url
            default_branch = data.get("default_branch") or "main"

    if body.clone:
        try:
            git_ops.clone_into(root, clone_url, token=token)
        except git_ops.GitError as e:
            # empty remote — just set remote
            git_ops.set_remote(root, clone_url)
            if "empty" not in str(e).lower() and "not found" not in str(e).lower():
                # still set link even if clone of empty fails oddly
                pass
    else:
        git_ops.set_remote(root, clone_url)

    p.github_repo = repo
    p.github_default_branch = default_branch
    p.github_connected_at = _now()
    p.workspace_path = str(root)
    p.updated_at = _now()
    await db.commit()
    return {
        "ok": True,
        "repo": repo,
        "branch": default_branch,
        "workspace": str(root),
    }
