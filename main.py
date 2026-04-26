"""
main.py — Stateless FastAPI web service for ReminderBot.

The scheduler / APScheduler logic lives entirely in worker.py.
This process only handles HTTP requests and writes to the database.
"""

import os
from contextlib import asynccontextmanager
from typing import List, Optional

from dotenv import load_dotenv
load_dotenv()  # Load .env for local development

from passlib.context import CryptContext
from fastapi import FastAPI, Depends, HTTPException, status, APIRouter
from fastapi.responses import FileResponse, Response, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from pydantic import BaseModel, EmailStr
import json
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

from database import engine, Base, get_db, SQLALCHEMY_DATABASE_URL
import models
import security
import bot_core

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.triggers.interval import IntervalTrigger
from scheduler import sync_all_users
from opportunity_scraper import update_opportunities_cache

# AI hero (optional dependency)
try:
    from google import genai
    has_genai = True
except ImportError:
    has_genai = False

# Create all tables on startup
Base.metadata.create_all(bind=engine)


# ---------------------------------------------------------------------------
# App lifespan — starts the BackgroundScheduler
# ---------------------------------------------------------------------------
scheduler = BackgroundScheduler(
    jobstores={"default": SQLAlchemyJobStore(url=SQLALCHEMY_DATABASE_URL)},
    timezone="UTC",
)

def _sync_wrapper():
    sync_all_users(scheduler)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- Start scheduler ---
    sync_all_users(scheduler)

    scheduler.add_job(
        _sync_wrapper,
        trigger=IntervalTrigger(seconds=60),
        id="sync_all_users",
        replace_existing=True,
    )

    scheduler.add_job(
        update_opportunities_cache,
        trigger=IntervalTrigger(hours=6),
        id="update_opportunities_cache",
        replace_existing=True,
    )
    # Run once on startup
    scheduler.add_job(
        update_opportunities_cache,
        id="update_opportunities_cache_startup",
        replace_existing=True,
    )
    
    scheduler.start()
    logging.info("[Web] Background scheduler started inside web process.")
    
    yield
    
    # Web service stops: tear down
    scheduler.shutdown(wait=False)

app = FastAPI(title="ReminderBot Web", lifespan=lifespan)
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/login")


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------
class UserCreate(BaseModel):
    email: EmailStr
    password: str


class Token(BaseModel):
    access_token: str
    token_type: str


class SettingsUpdate(BaseModel):
    bot_enabled: bool
    notification_time: str
    watch_senders: List[str]
    watch_keywords: Optional[List[str]] = []
    gmail_token_json: str
    twilio_sid: str
    twilio_token: str
    twilio_from: str
    whatsapp_phone: str
    enable_devpost: Optional[bool] = False
    enable_unstop: Optional[bool] = False


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------
def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    payload = security.decode_access_token(token)
    if payload is None:
        raise exc
    email: str = payload.get("sub")
    if not email:
        raise exc
    user = db.query(models.User).filter(models.User.email == email).first()
    if user is None:
        raise exc
    return user


# ---------------------------------------------------------------------------
# API router
# ---------------------------------------------------------------------------
api_router = APIRouter(prefix="/api")


@api_router.post("/signup", response_model=Token)
def signup(user: UserCreate, db: Session = Depends(get_db)):
    if db.query(models.User).filter(models.User.email == user.email).first():
        raise HTTPException(status_code=400, detail="Email already registered")
    new_user = models.User(
        email=user.email,
        hashed_password=security.get_password_hash(user.password),
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    token = security.create_access_token(data={"sub": new_user.email})
    return {"access_token": token, "token_type": "bearer"}


@api_router.post("/login", response_model=Token)
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.email == form_data.username).first()
    if not user or not security.verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = security.create_access_token(data={"sub": user.email})
    return {"access_token": token, "token_type": "bearer"}


@api_router.get("/me")
def read_users_me(current_user: models.User = Depends(get_current_user)):
    return {
        "email": current_user.email,
        "bot_enabled": current_user.bot_enabled,
        "notification_time": current_user.notification_time,
        "watch_senders": current_user.watch_senders,
        "watch_keywords": current_user.watch_keywords,
        "gmail_token_json": current_user.gmail_token_json,
        "twilio_sid": current_user.twilio_sid,
        "twilio_token": current_user.twilio_token,
        "twilio_from": current_user.twilio_from,
        "whatsapp_phone": current_user.whatsapp_phone,
        "enable_devpost": current_user.enable_devpost,
        "enable_unstop": current_user.enable_unstop,
    }


@api_router.post("/settings")
def update_settings(
    settings: SettingsUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """
    Persist settings to DB only.
    The worker picks up changes within 60 seconds via its sync_all_users() loop.
    """
    current_user.bot_enabled = settings.bot_enabled
    current_user.notification_time = settings.notification_time
    current_user.watch_senders = settings.watch_senders
    current_user.watch_keywords = settings.watch_keywords
    current_user.gmail_token_json = settings.gmail_token_json
    current_user.twilio_sid = settings.twilio_sid
    current_user.twilio_token = settings.twilio_token
    current_user.twilio_from = settings.twilio_from
    current_user.whatsapp_phone = settings.whatsapp_phone
    current_user.enable_devpost = settings.enable_devpost
    current_user.enable_unstop = settings.enable_unstop
    db.commit()
    return {"message": "Settings saved. Your bot schedule will update within 60 seconds."}


@api_router.post("/test-whatsapp")
def test_whatsapp(
    settings: SettingsUpdate,
    current_user: models.User = Depends(get_current_user),
):
    test_msg = "Hi! Your ReminderBot is active. You'll receive your daily digest here. ✅"
    success = bot_core.send_whatsapp(
        test_msg,
        settings.twilio_sid,
        settings.twilio_token,
        settings.twilio_from,
        settings.whatsapp_phone,
    )
    if success:
        return {"message": "Test message sent to WhatsApp!"}
    raise HTTPException(status_code=400, detail="Failed to send. Check Twilio credentials.")


@api_router.get("/generate-hero")
def generate_hero():
    """Generates an SVG hero using Gemini 1.5 Flash (optional)."""
    if not has_genai:
        return JSONResponse({"error": "google-genai not installed"}, status_code=500)

    api_key = os.environ.get("GEMINI_API_KEY")
    fallback_svg = (
        '<svg width="100%" height="200" xmlns="http://www.w3.org/2000/svg">'
        '<rect width="100%" height="100%" fill="#f1f5f9"/>'
        '<text x="50%" y="50%" font-family="sans-serif" fill="#475569" '
        'font-size="20" text-anchor="middle" dominant-baseline="middle">'
        "Set GEMINI_API_KEY to enable AI hero</text></svg>"
    )
    if not api_key:
        return Response(content=fallback_svg, media_type="image/svg+xml")

    try:
        client = genai.Client(api_key=api_key)
        prompt = (
            "Generate clean valid SVG: a calm minimal productivity workspace "
            "with soft gradients, floating notification cards, and gentle inbox "
            "aesthetic. Soft whites, light grays, indigo/teal accents. "
            "Output only valid SVG starting with <svg> and ending with </svg>. "
            "No markdown fences."
        )
        response = client.models.generate_content(model="gemini-1.5-flash", contents=prompt)
        svg_text = response.text.replace("```svg", "").replace("```", "").strip()
        if not svg_text.startswith("<svg"):
            raise ValueError("Not valid SVG")
        return Response(content=svg_text, media_type="image/svg+xml")
    except Exception as e:
        return Response(content=fallback_svg, media_type="image/svg+xml")


# ---------------------------------------------------------------------------
# Health check — used by UptimeRobot and self-ping
# ---------------------------------------------------------------------------
@app.get("/health")
def health_check():
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Register API router + static files + page routes
# ---------------------------------------------------------------------------
app.include_router(api_router)

frontend_dir = os.path.join(os.path.dirname(__file__), "frontend")
os.makedirs(frontend_dir, exist_ok=True)
app.mount("/static", StaticFiles(directory=frontend_dir), name="static")


@app.get("/")
def read_index():
    return FileResponse(os.path.join(frontend_dir, "index.html"))

@app.get("/signup")
def read_signup():
    return FileResponse(os.path.join(frontend_dir, "signup.html"))

@app.get("/login")
def read_login():
    return FileResponse(os.path.join(frontend_dir, "login.html"))

@app.get("/dashboard")
def read_dashboard():
    return FileResponse(os.path.join(frontend_dir, "dashboard.html"))

@app.get("/how-it-works")
def read_how_it_works():
    return FileResponse(os.path.join(frontend_dir, "how-it-works.html"))
