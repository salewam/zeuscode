"""Studio filesystem, git, preview, fork APIs on /projects/{id}/..."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import git_ops, runtime_svc, workspace as ws
from app.config import get_settings
from app.crypto_util import decrypt_token
from app.db import get_db
from app.deps import get_current_user, get_current_user_preview
from app.models import GitHubAccount, Project, User
from app import orchestrate
from app.orchestrate import CHEAP_MODEL
from app import upstream

router = APIRouter(prefix="/projects", tags=["studio-fs"])
settings = get_settings()


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def _proj(db: AsyncSession, user: User, project_id: int) -> Project:
    p = await db.get(Project, project_id)
    if not p or p.user_id != user.id:
        raise HTTPException(404, "Project not found")
    return p


def _root(user: User, p: Project) -> Path:
    return ws.ensure_workspace(user.id, p.id, title=p.title)


async def _gh_token(db: AsyncSession, user_id: int) -> str | None:
    r = await db.execute(select(GitHubAccount).where(GitHubAccount.user_id == user_id))
    acc = r.scalar_one_or_none()
    if not acc or not acc.access_token_enc:
        return None
    try:
        return decrypt_token(acc.access_token_enc)
    except ValueError:
        return None


class FilePutIn(BaseModel):
    path: str
    content: str = ""


class CommitIn(BaseModel):
    message: str = Field(default="chore: studio update", max_length=500)


class ForkPickIn(BaseModel):
    fork_id: str


class ForkRunIn(BaseModel):
    content: str = Field(min_length=1)
    models: list[str] | None = None
    intent: str = "feature"


@router.get("/{project_id}/fs/tree")
async def fs_tree(
    project_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    p = await _proj(db, user, project_id)
    root = _root(user, p)
    if not p.workspace_path:
        p.workspace_path = str(root)
        await db.commit()
    files = ws.list_tree(root)
    return {"files": files, "tree": ws.paths_to_tree([f["path"] for f in files]), "root": str(root)}


@router.get("/{project_id}/fs/file")
async def fs_read(
    project_id: int,
    path: str = Query(...),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    p = await _proj(db, user, project_id)
    root = _root(user, p)
    try:
        return ws.read_file(root, path)
    except FileNotFoundError:
        raise HTTPException(404, "File not found") from None
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.put("/{project_id}/fs/file")
async def fs_write(
    project_id: int,
    body: FilePutIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    p = await _proj(db, user, project_id)
    root = _root(user, p)
    try:
        info = ws.write_file(root, body.path, body.content)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    p.updated_at = _now()
    await db.commit()
    return info


@router.delete("/{project_id}/fs/file")
async def fs_delete(
    project_id: int,
    path: str = Query(...),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    p = await _proj(db, user, project_id)
    root = _root(user, p)
    try:
        ws.delete_file(root, path)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    p.updated_at = _now()
    await db.commit()
    return {"ok": True}


@router.get("/{project_id}/git/status")
async def git_status(
    project_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    p = await _proj(db, user, project_id)
    root = _root(user, p)
    st = git_ops.status(root)
    return {
        **st,
        "github_repo": p.github_repo or None,
        "github_branch": p.github_default_branch or "main",
    }


@router.get("/{project_id}/git/diff")
async def git_diff(
    project_id: int,
    staged: bool = False,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    p = await _proj(db, user, project_id)
    root = _root(user, p)
    return {"diff": git_ops.diff(root, staged=staged)}


@router.post("/{project_id}/git/commit")
async def git_commit(
    project_id: int,
    body: CommitIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    p = await _proj(db, user, project_id)
    root = _root(user, p)
    try:
        result = git_ops.commit(root, body.message)
    except git_ops.GitError as e:
        raise HTTPException(400, str(e)) from e
    p.updated_at = _now()
    await db.commit()
    return result


@router.post("/{project_id}/git/push")
async def git_push(
    project_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    p = await _proj(db, user, project_id)
    root = _root(user, p)
    token = await _gh_token(db, user.id)
    if p.github_repo and not git_ops.status(root).get("remote"):
        git_ops.set_remote(root, f"https://github.com/{p.github_repo}.git")
    try:
        return git_ops.push(root, token=token, branch=p.github_default_branch or None)
    except git_ops.GitError as e:
        raise HTTPException(400, str(e)) from e


@router.post("/{project_id}/git/pull")
async def git_pull(
    project_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    p = await _proj(db, user, project_id)
    root = _root(user, p)
    token = await _gh_token(db, user.id)
    try:
        return git_ops.pull(root, token=token)
    except git_ops.GitError as e:
        raise HTTPException(400, str(e)) from e


@router.post("/{project_id}/preview/start")
async def preview_start(
    project_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    p = await _proj(db, user, project_id)
    root = _root(user, p)
    return await runtime_svc.start_preview(project_id, root)


@router.post("/{project_id}/preview/stop")
async def preview_stop(
    project_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _proj(db, user, project_id)
    return await runtime_svc.stop_preview(project_id)


@router.get("/{project_id}/preview/status")
async def preview_status(
    project_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _proj(db, user, project_id)
    info = runtime_svc.preview_info(project_id)
    return info or {"running": False}


@router.api_route("/{project_id}/preview/{path:path}", methods=["GET", "HEAD"])
@router.api_route("/{project_id}/preview/", methods=["GET", "HEAD"])
async def preview_proxy(
    project_id: int,
    path: str = "",
    user: User = Depends(get_current_user_preview),
    db: AsyncSession = Depends(get_db),
):
    """Proxy to local preview http.server (auth: Bearer, cookie, or ?token=)."""
    await _proj(db, user, project_id)
    port = runtime_svc.get_preview_port(project_id)
    if not port:
        raise HTTPException(404, "Preview не запущен — нажми Start preview")
    url = f"http://127.0.0.1:{port}/{path}"
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(url)
    return Response(
        content=r.content,
        status_code=r.status_code,
        media_type=r.headers.get("content-type"),
    )


@router.post("/{project_id}/fork/run")
async def fork_run(
    project_id: int,
    body: ForkRunIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Run same prompt on 3 models in isolated worktrees; return candidates."""
    p = await _proj(db, user, project_id)
    if user.balance_usd <= 0:
        raise HTTPException(402, "Insufficient balance")
    root = _root(user, p)
    models = [CHEAP_MODEL, CHEAP_MODEL, CHEAP_MODEL]
    # caller may pass models= — still force cheap Flash everywhere
    _ = body.models  # ignored: Studio fork always gemini-2.5-flash
    while len(models) < 3:
        models.append(CHEAP_MODEL)

    async def event_gen():
        try:
            async for ev in orchestrate.iter_fork_events(
                user_text=body.content,
                intent=body.intent,
                models=models,
                brief=p.brief or "",
                workspace=root,
            ):
                yield f"data: {__import__('json').dumps(ev, ensure_ascii=False)}\n\n"
        except upstream.UpstreamError as e:
            yield f"data: {__import__('json').dumps({'type': 'error', 'message': str(e)}, ensure_ascii=False)}\n\n"
        except Exception as e:  # noqa: BLE001
            yield f"data: {__import__('json').dumps({'type': 'error', 'message': str(e)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


@router.post("/{project_id}/fork/pick")
async def fork_pick(
    project_id: int,
    body: ForkPickIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    p = await _proj(db, user, project_id)
    root = _root(user, p)
    fork_dir = root / ".onestack" / "forks" / body.fork_id
    if not fork_dir.exists():
        raise HTTPException(404, "Fork not found")
    written = git_ops.copy_tree_files(fork_dir, root)
    # cleanup all forks
    forks = root / ".onestack" / "forks"
    if forks.exists():
        for child in list(forks.iterdir()):
            git_ops.remove_worktree(root, child.name)
    p.updated_at = _now()
    await db.commit()
    return {"ok": True, "files": written[:200], "count": len(written)}


@router.websocket("/{project_id}/term")
async def term_ws(websocket: WebSocket, project_id: int):
    """PTY terminal in project workspace. Auth via ?token=JWT."""
    token = websocket.query_params.get("token") or ""
    await websocket.accept()
    from app.auth import decode_access_token
    from app.db import SessionLocal

    payload = decode_access_token(token)
    if not payload or "sub" not in payload:
        await websocket.send_json({"type": "error", "message": "Unauthorized"})
        await websocket.close()
        return

    async with SessionLocal() as session:
        user = await session.get(User, int(payload["sub"]))
        p = await session.get(Project, project_id)
        if not user or not p or p.user_id != user.id:
            await websocket.send_json({"type": "error", "message": "Project not found"})
            await websocket.close()
            return
        root = ws.ensure_workspace(user.id, p.id, title=p.title)

    try:
        sess = runtime_svc.spawn_shell(project_id, root)
    except Exception as e:  # noqa: BLE001
        await websocket.send_json({"type": "error", "message": str(e)})
        await websocket.close()
        return

    await websocket.send_json({"type": "ready", "cwd": str(root)})

    async def reader():
        loop = asyncio.get_event_loop()
        while True:
            try:
                data = await loop.run_in_executor(None, lambda: __import__("os").read(sess.master_fd, 4096))
            except OSError:
                break
            if not data:
                await asyncio.sleep(0.05)
                continue
            try:
                await websocket.send_text(data.decode("utf-8", errors="replace"))
            except Exception:  # noqa: BLE001
                break

    reader_task = asyncio.create_task(reader())
    try:
        while True:
            msg = await websocket.receive()
            if msg.get("type") == "websocket.disconnect":
                break
            text = msg.get("text")
            data = msg.get("bytes")
            payload_b = text.encode("utf-8") if text is not None else (data or b"")
            if payload_b:
                try:
                    __import__("os").write(sess.master_fd, payload_b)
                except OSError:
                    break
    except WebSocketDisconnect:
        pass
    finally:
        reader_task.cancel()
        runtime_svc.kill_term(sess)
