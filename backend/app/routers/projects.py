import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app import orchestrate, upstream
from app.catalog import get_model
from app.config import get_settings
from app.cost import estimate_upstream_usd, estimate_user_rub
from app.db import SessionLocal, get_db
from app.deps import get_current_user
from app.model_policy import assert_model_allowed, user_model_family
from app.models import Artifact, Chat, Message, Project, UsageLog, User
from app.orchestrate import intents_public, modes_public, normalize_intent, normalize_mode
from app.skills import team_for_intent
from app import workspace as ws
from app import runtime_svc

router = APIRouter(prefix="/projects", tags=["projects"])
settings = get_settings()


def _now() -> datetime:
    return datetime.now(timezone.utc)


class ProjectIn(BaseModel):
    title: str = Field(default="Новый проект", max_length=200)


class ProjectPatchIn(BaseModel):
    title: str | None = Field(default=None, max_length=200)
    brief: str | None = Field(default=None, max_length=8000)


class ChatIn(BaseModel):
    title: str = Field(default="Чат", max_length=200)


class CompleteIn(BaseModel):
    content: str = Field(min_length=1)
    intent: str = Field(default="feature")
    mode: str = Field(default="standard")
    model: str | None = Field(default=None, description="Advanced override — solo model id")
    run_kind: str = Field(default="team", description="team | solo | fork")
    agents: int | None = Field(default=None, ge=1, le=4, description="How many nets: 1–4")
    team_models: list[str] | None = Field(
        default=None,
        description="Cabinet pack: strongest=orchestrator/judge, rest=workers",
    )


def _proj_out(p: Project, chats_count: int | None = None) -> dict:
    if chats_count is None:
        try:
            chats_count = len(p.__dict__.get("chats") or []) if "chats" in p.__dict__ else 0
        except Exception:
            chats_count = 0
    return {
        "id": p.id,
        "title": p.title,
        "brief": p.brief or "",
        "workspace_path": p.workspace_path or "",
        "github_repo": p.github_repo or "",
        "github_default_branch": p.github_default_branch or "main",
        "github_connected_at": p.github_connected_at.isoformat() if p.github_connected_at else None,
        "created_at": p.created_at.isoformat() if p.created_at else None,
        "updated_at": p.updated_at.isoformat() if p.updated_at else None,
        "chats_count": chats_count,
    }


async def _get_user_project(db: AsyncSession, user: User, project_id: int) -> Project:
    p = await db.get(Project, project_id)
    if not p or p.user_id != user.id:
        raise HTTPException(404, "Project not found")
    return p


@router.get("/meta/studio")
async def studio_meta():
    """Intents, modes, default teams — for Studio UI."""
    return {
        "intents": intents_public(),
        "modes": modes_public(),
        "teams": {k: team_for_intent(k) for k in ("feature", "bug", "ui", "api", "tests", "refactor", "ask")},
    }


@router.get("")
async def list_projects(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Project)
        .where(Project.user_id == user.id)
        .options(selectinload(Project.chats))
        .order_by(Project.updated_at.desc())
    )
    return [_proj_out(p) for p in result.scalars().all()]



@router.get("/chats/recent")
async def list_recent_chats(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Flat chat list for beginner Studio sidebar (topics)."""
    result = await db.execute(
        select(Project)
        .where(Project.user_id == user.id)
        .options(selectinload(Project.chats))
        .order_by(Project.updated_at.desc())
    )
    projects = result.scalars().unique().all()
    items = []
    for p in projects:
        title_l = (p.title or "").lower()
        # hide internal trap/eval workspaces from beginner UI
        if (
            title_l.startswith("trap-")
            or title_l.startswith("glue-")
            or title_l.startswith("skill-")
            or "-trap" in title_l
        ):
            continue
        for c in p.chats or []:
            ct = (c.title or "").strip()
            # hide unused default stub chats
            if ct in ("Основной чат",) and len(p.chats or []) > 1:
                continue
            items.append(
                {
                    "id": c.id,
                    "title": c.title or "Чат",
                    "project_id": p.id,
                    "project_title": p.title,
                    "updated_at": (c.updated_at or c.created_at).isoformat()
                    if (c.updated_at or c.created_at)
                    else None,
                }
            )
    items.sort(key=lambda x: x.get("updated_at") or "", reverse=True)
    return items[:80]



@router.post("")
async def create_project(
    body: ProjectIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    p = Project(user_id=user.id, title=body.title.strip() or "Новый проект")
    db.add(p)
    await db.flush()
    root = ws.ensure_workspace(user.id, p.id, title=p.title)
    p.workspace_path = str(root)
    chat = Chat(project_id=p.id, title="Основной чат")
    db.add(chat)
    await db.commit()
    await db.refresh(p)
    result = await db.execute(
        select(Project).where(Project.id == p.id).options(selectinload(Project.chats))
    )
    return _proj_out(result.scalar_one())


@router.get("/{project_id}")
async def get_project(
    project_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Project)
        .where(Project.id == project_id, Project.user_id == user.id)
        .options(selectinload(Project.chats))
    )
    p = result.scalar_one_or_none()
    if not p:
        raise HTTPException(404, "Project not found")
    # ensure workspace exists for legacy projects
    if not p.workspace_path:
        root = ws.ensure_workspace(user.id, p.id, title=p.title)
        p.workspace_path = str(root)
        await db.commit()
    return {
        **_proj_out(p),
        "chats": [
            {
                "id": c.id,
                "title": c.title,
                "created_at": c.created_at.isoformat() if c.created_at else None,
                "updated_at": c.updated_at.isoformat() if c.updated_at else None,
            }
            for c in sorted(p.chats, key=lambda x: x.updated_at or x.created_at, reverse=True)
        ],
    }


@router.patch("/{project_id}")
async def patch_project(
    project_id: int,
    body: ProjectPatchIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    p = await _get_user_project(db, user, project_id)
    if body.title is not None:
        p.title = body.title.strip() or p.title
    if body.brief is not None:
        p.brief = body.brief.strip()
    p.updated_at = _now()
    await db.commit()
    return {
        "id": p.id,
        "title": p.title,
        "brief": p.brief or "",
        "created_at": p.created_at.isoformat() if p.created_at else None,
        "updated_at": p.updated_at.isoformat() if p.updated_at else None,
    }


@router.delete("/{project_id}")
async def delete_project(
    project_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    p = await _get_user_project(db, user, project_id)
    await runtime_svc.stop_preview(project_id)
    ws.remove_workspace(user.id, project_id)
    await db.delete(p)
    await db.commit()
    return {"ok": True}


@router.get("/{project_id}/artifacts")
async def list_artifacts(
    project_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Virtual file tree of project artifacts (workspace bridge)."""
    await _get_user_project(db, user, project_id)
    result = await db.execute(
        select(Artifact).where(Artifact.project_id == project_id).order_by(Artifact.path.asc(), Artifact.id.desc())
    )
    rows = result.scalars().all()
    # latest per path
    seen: set[str] = set()
    out = []
    for a in rows:
        if a.path in seen:
            continue
        seen.add(a.path)
        out.append(
            {
                "id": a.id,
                "kind": a.kind,
                "role": a.role,
                "path": a.path,
                "title": a.title,
                "language": a.language,
                "content": a.content,
                "created_at": a.created_at.isoformat() if a.created_at else None,
            }
        )
    tree = _paths_to_tree([x["path"] for x in out])
    return {"files": out, "tree": tree}


@router.get("/{project_id}/artifacts/{artifact_id}")
async def get_artifact(
    project_id: int,
    artifact_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_user_project(db, user, project_id)
    a = await db.get(Artifact, artifact_id)
    if not a or a.project_id != project_id:
        raise HTTPException(404, "Artifact not found")
    return {
        "id": a.id,
        "kind": a.kind,
        "role": a.role,
        "path": a.path,
        "title": a.title,
        "language": a.language,
        "content": a.content,
        "created_at": a.created_at.isoformat() if a.created_at else None,
    }


def _paths_to_tree(paths: list[str]) -> list[dict]:
    tree_dict: dict = {}

    def insert(tree: dict, parts: list[str]) -> None:
        if not parts:
            return
        head, *rest = parts
        if head not in tree:
            tree[head] = {}
        insert(tree[head], rest)

    for path in paths:
        parts = [p for p in path.strip("/").split("/") if p]
        insert(tree_dict, parts)

    def to_list(d: dict, prefix: str = "") -> list[dict]:
        items = []
        for name, child in sorted(d.items()):
            p = f"{prefix}/{name}"
            if child:
                items.append({"name": name, "path": p, "type": "dir", "children": to_list(child, p)})
            else:
                items.append({"name": name, "path": p, "type": "file", "children": []})
        return items

    return to_list(tree_dict)


@router.post("/{project_id}/chats")
async def create_chat(
    project_id: int,
    body: ChatIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    p = await _get_user_project(db, user, project_id)
    c = Chat(project_id=p.id, title=body.title.strip() or "Чат")
    p.updated_at = _now()
    db.add(c)
    await db.commit()
    await db.refresh(c)
    return {
        "id": c.id,
        "title": c.title,
        "project_id": p.id,
        "created_at": c.created_at.isoformat() if c.created_at else None,
    }


@router.delete("/{project_id}/chats/{chat_id}")
async def delete_chat(
    project_id: int,
    chat_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_user_project(db, user, project_id)
    chat = await db.get(Chat, chat_id)
    if not chat or chat.project_id != project_id:
        raise HTTPException(404, "Chat not found")
    await db.delete(chat)
    await db.commit()
    return {"ok": True}



@router.get("/{project_id}/chats/{chat_id}/messages")
async def list_messages(
    project_id: int,
    chat_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_user_project(db, user, project_id)
    chat = await db.get(Chat, chat_id)
    if not chat or chat.project_id != project_id:
        raise HTTPException(404, "Chat not found")
    result = await db.execute(
        select(Message).where(Message.chat_id == chat_id).order_by(Message.id.asc())
    )
    msgs = result.scalars().all()
    out = []
    for m in msgs:
        meta = {}
        if m.meta:
            try:
                meta = json.loads(m.meta) if m.meta.startswith("{") else {}
            except json.JSONDecodeError:
                meta = {}
        out.append(
            {
                "id": m.id,
                "role": m.role,
                "content": m.content,
                "model": m.model,
                "mode": m.mode,
                "cost_user_rub": round(m.cost_user_usd or 0, 4),
                "prompt_tokens": m.prompt_tokens,
                "completion_tokens": m.completion_tokens,
                "created_at": m.created_at.isoformat() if m.created_at else None,
                "agents": meta.get("agents"),
                "intent": meta.get("intent"),
                "artifacts": meta.get("artifacts_preview"),
            }
        )
    return out


@router.post("/{project_id}/chats/{chat_id}/complete")
async def complete_in_chat(
    project_id: int,
    chat_id: int,
    body: CompleteIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Studio run: intent + mode (+ optional model) → agents → artifacts → charge."""
    p = await _get_user_project(db, user, project_id)
    chat = await db.get(Chat, chat_id)
    if not chat or chat.project_id != project_id:
        raise HTTPException(404, "Chat not found")
    if user.balance_usd <= 0:
        raise HTTPException(402, "Insufficient balance")

    intent = normalize_intent(body.intent)
    mode = normalize_mode(body.mode)
    agents_n = body.agents
    if agents_n:
        mapped = {1: "light", 2: "standard", 3: "ultra", 4: "ultra"}.get(int(agents_n))
        if mapped:
            # Explicit premium stays premium when running full team (3–4)
            if normalize_mode(body.mode) == "premium" and int(agents_n) >= 3:
                mode = "premium"
            else:
                mode = mapped
    model_override = (body.model or "").strip() or None
    if model_override:
        meta = get_model(model_override)
        if meta and not meta.get("ready"):
            raise HTTPException(400, f"Модель {model_override} ещё не подключена.")
        if model_override in ("ultra-mode", "ultra", "onestack-ultra"):
            model_override = None
            mode = "ultra"
    assert_model_allowed(user, model_override)
    for mid in body.team_models or []:
        assert_model_allowed(user, mid)
    family = user_model_family(user)

    # Load prior history (multi-turn)
    hist_q = await db.execute(
        select(Message).where(Message.chat_id == chat_id).order_by(Message.id.asc())
    )
    prior = hist_q.scalars().all()
    history = [{"role": m.role, "content": m.content} for m in prior if m.role in ("user", "assistant")]

    user_msg = Message(
        chat_id=chat.id,
        role="user",
        content=body.content,
        model=model_override or f"studio-{mode}",
        mode=mode,
        meta=json.dumps({"intent": intent, "mode": mode, "agents": agents_n}, ensure_ascii=False),
    )
    db.add(user_msg)
    await db.flush()

    try:
        data = await orchestrate.run_studio(
            user_text=body.content,
            intent=intent,
            mode=mode,
            history=history,
            brief=p.brief or "",
            model_override=model_override,
            agents_n=agents_n,
            team_models=body.team_models,
            model_family=family,
        )
    except upstream.UpstreamError as e:
        raise HTTPException(e.status_code, str(e)) from e

    onestack = data.get("onestack") or {}
    run_mode = onestack.get("mode") or mode

    # Accurate-ish multi-agent billing
    agents = onestack.get("agents") or []
    upstream_cost = 0.0
    charged = 0.0
    prompt = 0
    completion = 0
    for a in agents:
        pt = int(a.get("prompt_tokens") or 0)
        ct = int(a.get("completion_tokens") or 0)
        prompt += pt
        completion += ct
        mid = a.get("model") or settings.DEFAULT_MODEL
        upstream_cost += estimate_upstream_usd(mid, pt, ct)
        charged += estimate_user_rub(mid, pt, ct)

    usage = data.get("usage") or {}
    # Include synth tokens if totals larger than agent sum
    u_prompt = int(usage.get("prompt_tokens") or 0)
    u_completion = int(usage.get("completion_tokens") or 0)
    if u_prompt + u_completion > prompt + completion:
        extra_p = u_prompt - prompt
        extra_c = u_completion - completion
        bill_m = onestack.get("bill_model") or settings.DEFAULT_MODEL
        upstream_cost += estimate_upstream_usd(bill_m, max(extra_p, 0), max(extra_c, 0))
        charged += estimate_user_rub(bill_m, max(extra_p, 0), max(extra_c, 0))
        prompt, completion = u_prompt, u_completion

    if user.balance_usd < charged:
        raise HTTPException(402, f"Недостаточно средств (~{charged:.2f} ₽)")

    text = ""
    try:
        text = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        text = str(data)

    bill_model = data.get("_bill_model") or onestack.get("bill_model") or settings.DEFAULT_MODEL
    user.balance_usd = round(user.balance_usd - charged, 8)

    arts = onestack.get("artifacts") or []
    evd = onestack.get("evidence") or {}
    meta_store = {
        "intent": intent,
        "mode": run_mode,
        "power": onestack.get("power"),
        "team": onestack.get("team"),
        "agents": onestack.get("agents"),
        "wall_s": onestack.get("wall_s"),
        "evidence": {
            "verdict": evd.get("verdict"),
            "gate": evd.get("gate"),
            "score": evd.get("score"),
            "grade": evd.get("grade"),
            "findings": evd.get("gate_findings"),
        }
        if evd
        else None,
        "artifacts_preview": [
            {"kind": a.get("kind"), "path": a.get("path"), "title": a.get("title"), "role": a.get("role")}
            for a in arts[:40]
        ],
    }
    asst = Message(
        chat_id=chat.id,
        role="assistant",
        content=text,
        model=data.get("model") or f"studio-{run_mode}",
        mode=run_mode,
        prompt_tokens=prompt,
        completion_tokens=completion,
        cost_user_usd=charged,
        meta=json.dumps(meta_store, ensure_ascii=False),
    )
    db.add(asst)
    await db.flush()

    for a in arts:
        db.add(
            Artifact(
                project_id=p.id,
                chat_id=chat.id,
                message_id=asst.id,
                kind=a.get("kind") or "code",
                role=a.get("role") or "",
                path=(a.get("path") or "/notes/out.txt")[:400],
                title=(a.get("title") or "")[:200],
                language=(a.get("language") or "")[:40],
                content=a.get("content") or "",
            )
        )

    # persist to real workspace
    try:
        root = ws.ensure_workspace(user.id, p.id, title=p.title)
        p.workspace_path = str(root)
        ws.apply_artifacts(root, arts)
    except Exception:  # noqa: BLE001
        pass

    db.add(
        UsageLog(
            user_id=user.id,
            model=data.get("model") or bill_model,
            mode=run_mode,
            prompt_tokens=prompt,
            completion_tokens=completion,
            cost_upstream_usd=upstream_cost,
            cost_user_usd=charged,
            meta=f"project={p.id};chat={chat.id};intent={intent}",
        )
    )
    chat.updated_at = _now()
    p.updated_at = _now()
    if chat.title in ("Чат", "Основной чат", "Сборка", "Новый чат", "Новый топик") and body.content:
        chat.title = body.content[:48] + ("…" if len(body.content) > 48 else "")
    await db.commit()
    await db.refresh(asst)

    return {
        "message": {
            "id": asst.id,
            "role": "assistant",
            "content": asst.content,
            "model": asst.model,
            "mode": asst.mode,
            "intent": intent,
            "cost_user_rub": round(asst.cost_user_usd or 0, 4),
            "prompt_tokens": asst.prompt_tokens,
            "completion_tokens": asst.completion_tokens,
            "agents": onestack.get("agents"),
            "artifacts": meta_store["artifacts_preview"],
        },
        "billing": {
            "currency": "RUB",
            "charged_rub": round(charged, 4),
            "balance_left_rub": round(user.balance_usd, 4),
            "markup": settings.MARKUP,
        },
        "onestack": onestack,
        "artifacts": arts,
    }


def _sse(data: dict) -> str:
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


@router.post("/{project_id}/chats/{chat_id}/complete/stream")
async def complete_in_chat_stream(
    project_id: int,
    chat_id: int,
    body: CompleteIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Live cooperative run: SSE events per agent think/done + final billed message."""
    p = await _get_user_project(db, user, project_id)
    chat = await db.get(Chat, chat_id)
    if not chat or chat.project_id != project_id:
        raise HTTPException(404, "Chat not found")
    if user.balance_usd <= 0:
        raise HTTPException(402, "Insufficient balance")

    intent = normalize_intent(body.intent)
    mode = normalize_mode(body.mode)
    agents_n = body.agents
    if agents_n:
        mapped = {1: "light", 2: "standard", 3: "ultra", 4: "ultra"}.get(int(agents_n))
        if mapped:
            if normalize_mode(body.mode) == "premium" and int(agents_n) >= 3:
                mode = "premium"
            else:
                mode = mapped
    model_override = (body.model or "").strip() or None
    if model_override:
        meta = get_model(model_override)
        if meta and not meta.get("ready"):
            raise HTTPException(400, f"Модель {model_override} ещё не подключена.")
        if model_override in ("ultra-mode", "ultra", "onestack-ultra"):
            model_override = None
            mode = "ultra"
    assert_model_allowed(user, model_override)
    for mid in body.team_models or []:
        assert_model_allowed(user, mid)
    family = user_model_family(user)

    hist_q = await db.execute(
        select(Message).where(Message.chat_id == chat_id).order_by(Message.id.asc())
    )
    prior = hist_q.scalars().all()
    history = [{"role": m.role, "content": m.content} for m in prior if m.role in ("user", "assistant")]

    user_msg = Message(
        chat_id=chat.id,
        role="user",
        content=body.content,
        model=model_override or f"studio-{mode}",
        mode=mode,
        meta=json.dumps({"intent": intent, "mode": mode, "agents": agents_n}, ensure_ascii=False),
    )
    db.add(user_msg)
    await db.commit()

    user_id = user.id
    project_id_i = p.id
    chat_id_i = chat.id
    brief = p.brief or ""
    content = body.content
    root = ws.ensure_workspace(user.id, p.id, title=p.title)
    if not p.workspace_path:
        p.workspace_path = str(root)
        await db.commit()

    async def event_gen():
        try:
            async for ev in orchestrate.iter_studio_events(
                user_text=content,
                intent=intent,
                mode=mode,
                history=history,
                brief=brief,
                model_override=model_override,
                agents_n=agents_n,
                team_models=body.team_models,
                model_family=family,
            ):
                if ev.get("type") == "agent_done" and ev.get("artifacts"):
                    written = ws.apply_artifacts(root, ev.get("artifacts") or [])
                    if written:
                        yield _sse({"type": "file_changed", "files": written})
                if ev.get("type") == "review_done" and ev.get("artifacts"):
                    written = ws.apply_artifacts(root, ev.get("artifacts") or [])
                    if written:
                        yield _sse({"type": "file_changed", "files": written})
                if ev.get("type") == "synth_done":
                    # synth text may contain fences — applied on final pack
                    pass
                if ev.get("type") != "done":
                    yield _sse(ev)
                    continue

                data = ev["result"]
                onestack = data.get("onestack") or {}
                # write all packed artifacts to disk
                arts = onestack.get("artifacts") or []
                written = ws.apply_artifacts(root, arts)
                if written:
                    yield _sse({"type": "file_changed", "files": written})
                run_mode = onestack.get("mode") or mode
                agents = onestack.get("agents") or []
                upstream_cost = 0.0
                charged = 0.0
                prompt = 0
                completion = 0
                for a in agents:
                    pt = int(a.get("prompt_tokens") or 0)
                    ct = int(a.get("completion_tokens") or 0)
                    prompt += pt
                    completion += ct
                    mid = a.get("model") or settings.DEFAULT_MODEL
                    upstream_cost += estimate_upstream_usd(mid, pt, ct)
                    charged += estimate_user_rub(mid, pt, ct)
                usage = data.get("usage") or {}
                u_prompt = int(usage.get("prompt_tokens") or 0)
                u_completion = int(usage.get("completion_tokens") or 0)
                if u_prompt + u_completion > prompt + completion:
                    bill_m = onestack.get("bill_model") or settings.DEFAULT_MODEL
                    upstream_cost += estimate_upstream_usd(
                        bill_m, max(u_prompt - prompt, 0), max(u_completion - completion, 0)
                    )
                    charged += estimate_user_rub(
                        bill_m, max(u_prompt - prompt, 0), max(u_completion - completion, 0)
                    )
                    prompt, completion = u_prompt, u_completion

                try:
                    text = data["choices"][0]["message"]["content"]
                except (KeyError, IndexError, TypeError):
                    text = str(data)

                async with SessionLocal() as session:
                    u = await session.get(User, user_id)
                    proj = await session.get(Project, project_id_i)
                    ch = await session.get(Chat, chat_id_i)
                    if not u or not proj or not ch:
                        yield _sse({"type": "error", "message": "Сессия потеряна"})
                        return
                    if u.balance_usd < charged:
                        yield _sse(
                            {
                                "type": "error",
                                "message": f"Недостаточно средств (~{charged:.2f} ₽)",
                            }
                        )
                        return
                    u.balance_usd = round(u.balance_usd - charged, 8)
                    meta_store = {
                        "intent": intent,
                        "mode": run_mode,
                        "team": onestack.get("team"),
                        "agents": onestack.get("agents"),
                        "wall_s": onestack.get("wall_s"),
                        "evidence": {
                            "verdict": (onestack.get("evidence") or {}).get("verdict"),
                            "gate": (onestack.get("evidence") or {}).get("gate"),
                            "score": (onestack.get("evidence") or {}).get("score"),
                            "grade": (onestack.get("evidence") or {}).get("grade"),
                            "findings": (onestack.get("evidence") or {}).get("gate_findings"),
                        }
                        if onestack.get("evidence")
                        else None,
                        "artifacts_preview": [
                            {
                                "kind": a.get("kind"),
                                "path": a.get("path"),
                                "title": a.get("title"),
                                "role": a.get("role"),
                            }
                            for a in arts[:40]
                        ],
                        "workspace_files": [w.get("path") for w in written[:40]],
                    }
                    asst = Message(
                        chat_id=ch.id,
                        role="assistant",
                        content=text,
                        model=data.get("model") or f"studio-{run_mode}",
                        mode=run_mode,
                        prompt_tokens=prompt,
                        completion_tokens=completion,
                        cost_user_usd=charged,
                        meta=json.dumps(meta_store, ensure_ascii=False),
                    )
                    session.add(asst)
                    await session.flush()
                    for a in arts:
                        session.add(
                            Artifact(
                                project_id=proj.id,
                                chat_id=ch.id,
                                message_id=asst.id,
                                kind=a.get("kind") or "code",
                                role=a.get("role") or "",
                                path=(a.get("path") or "/notes/out.txt")[:400],
                                title=(a.get("title") or "")[:200],
                                language=(a.get("language") or "")[:40],
                                content=a.get("content") or "",
                            )
                        )
                    session.add(
                        UsageLog(
                            user_id=u.id,
                            model=data.get("model") or onestack.get("bill_model"),
                            mode=run_mode,
                            prompt_tokens=prompt,
                            completion_tokens=completion,
                            cost_upstream_usd=upstream_cost,
                            cost_user_usd=charged,
                            meta=f"project={proj.id};chat={ch.id};intent={intent}",
                        )
                    )
                    ch.updated_at = _now()
                    proj.updated_at = _now()
                    if ch.title in ("Чат", "Основной чат", "Сборка", "Новый чат", "Новый топик") and content:
                        ch.title = content[:48] + ("…" if len(content) > 48 else "")
                    await session.commit()
                    await session.refresh(asst)
                    balance_left = u.balance_usd
                    asst_id = asst.id

                yield _sse(
                    {
                        "type": "final",
                        "message": {
                            "id": asst_id,
                            "role": "assistant",
                            "content": text,
                            "model": data.get("model"),
                            "mode": run_mode,
                            "intent": intent,
                            "cost_user_rub": round(charged, 4),
                            "agents": onestack.get("agents"),
                            "artifacts": meta_store["artifacts_preview"],
                            "evidence": meta_store.get("evidence"),
                        },
                        "billing": {
                            "currency": "RUB",
                            "charged_rub": round(charged, 4),
                            "balance_left_rub": round(balance_left, 4),
                        },
                        "onestack": onestack,
                        "workspace_files": written,
                    }
                )
        except upstream.UpstreamError as e:
            yield _sse({"type": "error", "message": str(e)})
        except Exception as e:  # noqa: BLE001
            yield _sse({"type": "error", "message": str(e)})

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
