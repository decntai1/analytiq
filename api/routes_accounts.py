"""
Account routes — user auth (register/login/logout/me) + saved conversations.

Registration paths:
  - no invite code  -> a personal Free workspace (tenant) is created for the user
  - invite code     -> the user joins that company's tenant (dedicated interface:
                       same data, same connectors, same dedicated model endpoint,
                       shared by everyone in the company)

Sessions are HttpOnly cookies; the existing tenant API-key auth keeps working in
parallel for programmatic access. Single-tenant deployments (MULTI_TENANT=0,
e.g. the public demo) don't require any of this.
"""
from __future__ import annotations

import os
import re

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel

import config
from api import auth
from core.accounts import SESSION_TTL_S

router = APIRouter()
_COOKIE = "aq_session"
_SECURE = os.getenv("COOKIE_SECURE", "0") == "1"   # set 1 behind TLS (prod)


class Credentials(BaseModel):
    email: str
    password: str
    invite_code: str = ""


def _set_session(resp: Response, token: str) -> None:
    resp.set_cookie(_COOKIE, token, httponly=True, samesite="lax",
                    secure=_SECURE, max_age=SESSION_TTL_S, path="/")


def _me_payload(user) -> dict:
    t = auth.store().by_id(user.tenant_id)
    plan_name = (user.plan or (t.plan if t else "free")) or "free"
    plan = config.plan_of(plan_name)
    used = auth.accounts().credits_used(user.user_id)
    return {"email": user.email, "role": user.role,
            "workspace": {"tenant_id": user.tenant_id, "name": t.name if t else "?",
                          "dedicated_llm": bool(t and t.llm_base_url)},
            "plan": {"name": plan_name, "label": plan["label"],
                     "price": plan.get("price", ""), "price_note": plan.get("price_note", ""),
                     "credits_month": plan["credits_month"], "credits_used": used,
                     "credits_remaining": max(0, plan["credits_month"] - used),
                     "memory": plan["memory"], "deck_export": plan["deck_export"]},
            "plans_catalog": [{"name": k, **{f: v[f] for f in
                              ("label", "price", "price_note", "blurb", "credits_month",
                               "memory", "deck_export", "dedicated_llm")}}
                              for k, v in config.PLANS.items()]}


@router.post("/auth/register")
def register(body: Credentials, response: Response):
    if not config.settings.multi_tenant:
        raise HTTPException(400, "This deployment runs without accounts (single-tenant).")
    email = body.email.strip().lower()
    if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
        raise HTTPException(400, "Enter a valid email address.")
    if len(body.password) < 8:
        raise HTTPException(400, "Password must be at least 8 characters.")
    if auth.accounts().by_email(email):
        raise HTTPException(409, "An account with this email already exists. Sign in instead.")

    if body.invite_code:
        tenant = auth.store().by_invite(body.invite_code.strip())
        if not tenant:
            raise HTTPException(400, "That invite code doesn't match any workspace.")
        user = auth.accounts().create_user(email, body.password, tenant.tenant_id, role="member")
    else:
        tenant = auth.store().create(name=email, data_source="upload", plan="free")
        user = auth.accounts().create_user(email, body.password, tenant.tenant_id, role="owner")

    _set_session(response, auth.accounts().open_session(user.user_id))
    return {"ok": True, **_me_payload(user)}


@router.post("/auth/login")
def login(body: Credentials, response: Response):
    if not config.settings.multi_tenant:
        raise HTTPException(400, "This deployment runs without accounts (single-tenant).")
    user = auth.accounts().verify(body.email, body.password)
    if not user:
        raise HTTPException(401, "Email or password is incorrect.")
    _set_session(response, auth.accounts().open_session(user.user_id))
    return {"ok": True, **_me_payload(user)}


@router.post("/auth/logout")
def logout(request: Request, response: Response):
    tok = request.cookies.get(_COOKIE, "")
    if tok:
        auth.accounts().close_session(tok)
    response.delete_cookie(_COOKIE, path="/")
    return {"ok": True}


class PasswordChange(BaseModel):
    current: str
    new: str


@router.post("/auth/change_password")
def change_password(body: PasswordChange, request: Request):
    user = auth.resolve_user(request)
    if not user:
        raise HTTPException(401, "Sign in first.")
    if len(body.new) < 8:
        raise HTTPException(400, "New password must be at least 8 characters.")
    if not auth.accounts().change_password(user.user_id, body.current, body.new):
        raise HTTPException(400, "Current password is incorrect.")
    return {"ok": True}


@router.get("/auth/me")
def me(request: Request):
    user = auth.resolve_user(request)
    if not user:
        raise HTTPException(401, "Not signed in.")
    return _me_payload(user)


# --- saved chat windows ------------------------------------------------------
@router.get("/chats")
def list_chats(request: Request):
    user = auth.resolve_user(request)
    if not user:
        raise HTTPException(401, "Sign in to see saved chats.")
    return {"conversations": auth.accounts().list_conversations(user.user_id)}


@router.post("/chats")
def new_chat(request: Request):
    user = auth.resolve_user(request)
    if not user:
        raise HTTPException(401, "Sign in to save chats.")
    cid = auth.accounts().create_conversation(user.tenant_id, user.user_id)
    return {"conv_id": cid}


@router.get("/chats/{conv_id}")
def get_chat(conv_id: str, request: Request):
    user = auth.resolve_user(request)
    if not user:
        raise HTTPException(401, "Sign in to see saved chats.")
    owner = auth.accounts().conversation_owner(conv_id)
    if not owner or owner[1] != user.user_id:
        raise HTTPException(404, "Chat not found.")
    return {"conv_id": conv_id, "messages": auth.accounts().get_messages(conv_id)}
