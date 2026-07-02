from __future__ import annotations

import io
import hashlib
import json
import os
import re
import smtplib
import uuid
import zipfile
from contextlib import contextmanager
from datetime import datetime, timedelta
from email.message import EmailMessage
from pathlib import Path
from typing import Any

import requests
from apscheduler.schedulers.background import BackgroundScheduler
from flask import (
    Flask,
    Response,
    flash,
    g,
    redirect,
    render_template,
    request,
    send_file,
    session,
    url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash

import utils.myfunct as mf

try:
    import pymysql
    from pymysql.cursors import DictCursor
except Exception:
    pymysql = None
    DictCursor = None


#Ver = "LadySite v0.5.13" # first build 2024-07-01
#Ver = "LadySite v0.5.14" #оновили ціни
#Ver = "LadySite v0.5.15" #лічильник відвідин
#Ver = "LadySite v0.8.18" #редагування послуг
#Ver = "LadySite v0.8.19" #адмінка зручніше
Ver = "LadySite v0.8.20" #текст товарів

HOST = "localhost" if os.name == "nt" else "0.0.0.0"
PORT = 5000
PPath = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(PPath, "DATA", "LadySite.config")
DEFAULT_SERVICES_PATH = os.path.join(PPath, "DATA", "default_services.json")
SERVICE_CONTENT_VERSION = "2026-07-02-price-2"
VISIT_COOKIE = "lady_visitor"
VISIT_TRACK_ENDPOINTS = {"index", "services", "about"}
REPORT_DIR = os.path.join(PPath, "Report")
REPORT_SEND_DIR = os.path.join(REPORT_DIR, "Send")
SERVICE_IMAGE_DIR = os.path.join(PPath, "static", "service_images")
DEFAULT_MAP_URL = "https://www.google.com/maps/place/%D0%B2%D1%83%D0%BB%D0%B8%D1%86%D1%8F+%D0%9B%D0%B5%D1%81%D1%96+%D0%A3%D0%BA%D1%80%D0%B0%D1%97%D0%BD%D0%BA%D0%B8,+41,+%D0%9A%D0%B0%D0%BC'%D1%8F%D0%BD%D0%B5%D1%86%D1%8C-%D0%9F%D0%BE%D0%B4%D1%96%D0%BB%D1%8C%D1%81%D1%8C%D0%BA%D0%B8%D0%B9,+%D0%A5%D0%BC%D0%B5%D0%BB%D1%8C%D0%BD%D0%B8%D1%86%D1%8C%D0%BA%D0%B0+%D0%BE%D0%B1%D0%BB%D0%B0%D1%81%D1%82%D1%8C,+32300/@48.6759436,26.5838751,18.42z/data=!4m6!3m5!1s0x4733b87712b10bb7:0xc879ff1bd73b8e22!8m2!3d48.6759926!4d26.5847011!16s%2Fg%2F11g1lfpndx?entry=ttu"
DEFAULT_MAP_EMBED_URL = "https://www.google.com/maps?q=48.6759926,26.5847011&z=18&output=embed"

mf.PPath = PPath
for folder in ("DATA", "logs", "Report", os.path.join("Report", "Send")):
    mf.CreateDir(os.path.join(PPath, folder))
mf.CreateDir(SERVICE_IMAGE_DIR)

app = Flask(__name__)
app.secret_key = os.environ.get("LADY_SITE_SECRET", "lady-site-local-secret-change-me")
scheduler = BackgroundScheduler(daemon=True)
runtime_state = {
    "schema_ready": False,
    "schema_error": "",
    "last_log_clear": datetime.min,
    "last_appointments_cleanup": datetime.min,
    "next_report_send": datetime.min,
}


def _strip_inline_comment(value: str) -> str:
    clean = value.strip()
    if "#" in clean and not re.fullmatch(r"#[0-9A-Fa-f]{6}", clean):
        clean = clean.split("#", 1)[0].strip()
    return clean


def load_config() -> dict[str, str]:
    config: dict[str, str] = {}
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "r", encoding="utf-8-sig") as fh:
            for raw in fh:
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                config[key.strip()] = _strip_inline_comment(value)

    defaults = {
        "MYSQL_USER": "lady",
        "MYSQL_PASSWORD": "",
        "MYSQL_HOST": "mysql-lady.alwaysdata.net",
        "MYSQL_PORT": "3306",
        "MYSQL_DATABASE": "lady_db",
        "SMTP_HOST": "",
        "SMTP_PORT": "587",
        "SMTP_USER": "",
        "SMTP_PASSWORD": "",
        "SMTP_FROM": "",
        "SMTP_TLS": "1",
        "NOTIFY_EMAILS": "",
        "TELEGRAM_BOT_TOKEN": "",
        "TELEGRAM_CHAT_ID": "",
        "REMIND_BEFORE_HOURS": "2",
        "CLEAR_LOG_DAYS": "10",
        "CLEAR_LOG_HOURS": "12",
        "DELETE_OLD_APPOINTMENTS_DAYS": "60",
        "SEND_ERR_TIME_IN_MINUTES": "360",
        "ONLINE_APPOINTMENT_ENABLED": "1",
        "SERVICES_PAGE_INTRO": "Тут розділи і напрямки, якими займається наш центр.",
        "SERVICE_CONTENT_VERSION": "",
        "MAP_URL": DEFAULT_MAP_URL,
        "MAP_EMBED_URL": DEFAULT_MAP_EMBED_URL,
    }
    changed = False
    for key, value in defaults.items():
        if key not in config:
            config[key] = value
            changed = True
    if changed:
        save_config(config)
    return config


def save_config(config: dict[str, str]) -> None:
    order = [
        "MYSQL_USER",
        "MYSQL_PASSWORD",
        "MYSQL_HOST",
        "MYSQL_PORT",
        "MYSQL_DATABASE",
        "SMTP_HOST",
        "SMTP_PORT",
        "SMTP_USER",
        "SMTP_PASSWORD",
        "SMTP_FROM",
        "SMTP_TLS",
        "NOTIFY_EMAILS",
        "TELEGRAM_BOT_TOKEN",
        "TELEGRAM_CHAT_ID",
        "REMIND_BEFORE_HOURS",
        "CLEAR_LOG_DAYS",
        "CLEAR_LOG_HOURS",
        "DELETE_OLD_APPOINTMENTS_DAYS",
        "SEND_ERR_TIME_IN_MINUTES",
        "ONLINE_APPOINTMENT_ENABLED",
        "SERVICES_PAGE_INTRO",
        "SERVICE_CONTENT_VERSION",
        "MAP_URL",
        "MAP_EMBED_URL",
    ]
    lines = ["# LadySite configuration", "", "# MySQL"]
    for key in order[:5]:
        lines.append(f"{key}={config.get(key, '')}")
    lines.extend(["", "# SMTP"])
    for key in order[5:12]:
        lines.append(f"{key}={config.get(key, '')}")
    lines.extend(["", "# Telegram"])
    for key in order[12:14]:
        lines.append(f"{key}={config.get(key, '')}")
    lines.extend(["", "# Site"])
    for key in order[14:]:
        lines.append(f"{key}={config.get(key, '')}")
    with open(CONFIG_PATH, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")


@contextmanager
def db_cursor(commit: bool = False):
    if pymysql is None:
        raise RuntimeError("PyMySQL не встановлено. Виконайте: pip install -r requirements.txt")
    config = load_config()
    conn = pymysql.connect(
        host=config["MYSQL_HOST"],
        user=config["MYSQL_USER"],
        password=config["MYSQL_PASSWORD"],
        database=config["MYSQL_DATABASE"],
        port=int(config.get("MYSQL_PORT", "3306") or 3306),
        charset="utf8mb4",
        cursorclass=DictCursor,
        autocommit=False,
    )
    try:
        with conn.cursor() as cur:
            yield cur
        if commit:
            conn.commit()
        else:
            conn.rollback()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def mysql_error_code(ex: Exception) -> int | None:
    if not getattr(ex, "args", None):
        return None
    try:
        return int(ex.args[0])
    except (TypeError, ValueError):
        return None


def ensure_schema() -> None:
    try:
        with db_cursor(commit=True) as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS Users (
                    Login VARCHAR(120) PRIMARY KEY,
                    FullName VARCHAR(255) NULL,
                    Email VARCHAR(255) NULL,
                    Pass VARCHAR(255) NOT NULL,
                    Role ENUM('admin','manager') NOT NULL DEFAULT 'manager',
                    IsBlocked BOOLEAN NOT NULL DEFAULT FALSE,
                    Last DATETIME NULL,
                    ActiveSessionId VARCHAR(80) NULL,
                    CreatedAt DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    UpdatedAt DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS Appointments (
                    Id BIGINT AUTO_INCREMENT PRIMARY KEY,
                    VisitAt DATETIME NOT NULL,
                    ClientName VARCHAR(255) NOT NULL,
                    VisitPurpose TEXT NOT NULL,
                    Phone VARCHAR(80) NULL,
                    Email VARCHAR(255) NULL,
                    create_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    SendNow BOOLEAN NOT NULL DEFAULT FALSE,
                    SendBeforeCl BOOLEAN NOT NULL DEFAULT FALSE,
                    INDEX idx_visit_at (VisitAt),
                    INDEX idx_send_now (SendNow),
                    INDEX idx_send_before (SendBeforeCl)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS AuditLog (
                    Id BIGINT AUTO_INCREMENT PRIMARY KEY,
                    CreatedAt DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    Actor VARCHAR(120) NOT NULL,
                    Action VARCHAR(255) NOT NULL,
                    Details TEXT NULL,
                    Ip VARCHAR(80) NULL,
                    INDEX idx_audit_created (CreatedAt),
                    INDEX idx_audit_actor (Actor)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS ServiceSections (
                    Id BIGINT AUTO_INCREMENT PRIMARY KEY,
                    Title VARCHAR(255) NOT NULL,
                    Description TEXT NULL,
                    ImageUrl TEXT NULL,
                    SortOrder INT NOT NULL DEFAULT 100,
                    IsActive BOOLEAN NOT NULL DEFAULT TRUE,
                    CreatedAt DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS ServiceCards (
                    Id BIGINT AUTO_INCREMENT PRIMARY KEY,
                    SectionId BIGINT NOT NULL,
                    Title VARCHAR(255) NOT NULL,
                    ShortDescription TEXT NULL,
                    PriceText VARCHAR(120) NULL,
                    ImageUrl TEXT NULL,
                    SortOrder INT NOT NULL DEFAULT 100,
                    IsActive BOOLEAN NOT NULL DEFAULT TRUE,
                    CreatedAt DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    INDEX idx_service_cards_section (SectionId)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS PageVisits (
                    Id BIGINT AUTO_INCREMENT PRIMARY KEY,
                    VisitorKey CHAR(64) NOT NULL,
                    Path VARCHAR(255) NOT NULL,
                    Endpoint VARCHAR(120) NULL,
                    UserAgent VARCHAR(500) NULL,
                    CreatedAt DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    INDEX idx_page_visits_created (CreatedAt),
                    INDEX idx_page_visits_visitor_day (VisitorKey, CreatedAt)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """
            )
            cur.execute("SELECT COUNT(*) AS cnt FROM Users WHERE Login=%s", ("denis",))
            if int(cur.fetchone()["cnt"]) == 0:
                cur.execute(
                    """
                    INSERT INTO Users (Login, FullName, Email, Pass, Role, IsBlocked)
                    VALUES (%s, %s, %s, %s, 'admin', FALSE)
                    """,
                    ("denis", "Денис", None, generate_password_hash("DenMar15")),
                )
            seed_service_content(cur)
            config = load_config()
            if config.get("SERVICE_CONTENT_VERSION") != SERVICE_CONTENT_VERSION:
                sync_default_service_content(cur)
                config["SERVICE_CONTENT_VERSION"] = SERVICE_CONTENT_VERSION
                save_config(config)
        runtime_state["schema_ready"] = True
        runtime_state["schema_error"] = ""
    except Exception as ex:
        runtime_state["schema_ready"] = False
        runtime_state["schema_error"] = str(ex)
        mf.tolog(f"ensure_schema() failed: {ex}")


def load_default_services() -> list[dict[str, Any]]:
    try:
        with open(DEFAULT_SERVICES_PATH, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        sections = data.get("sections", [])
        return sections if isinstance(sections, list) else []
    except Exception as ex:
        _report_critical_error("load_default_services() failed", ex)
        return []


def seed_service_content(cur) -> None:
    cur.execute("SELECT COUNT(*) AS cnt FROM ServiceSections")
    if int(cur.fetchone()["cnt"]) > 0:
        return
    for index, section in enumerate(load_default_services(), start=1):
        title = str(section.get("title") or "").strip()
        if not title:
            continue
        description = str(section.get("description") or "").strip()
        image_url = str(section.get("image_url") or "").strip()
        cur.execute(
            "INSERT INTO ServiceSections (Title, Description, ImageUrl, SortOrder) VALUES (%s, %s, %s, %s)",
            (title, description or None, image_url or None, index * 10),
        )
        section_id = cur.lastrowid
        cards = section.get("cards", [])
        if not isinstance(cards, list):
            continue
        for card_index, card in enumerate(cards, start=1):
            card_title = str(card.get("title") or "").strip()
            if not card_title:
                continue
            cur.execute(
                """
                INSERT INTO ServiceCards (SectionId, Title, ShortDescription, PriceText, ImageUrl, SortOrder)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (
                    section_id,
                    card_title,
                    str(card.get("description") or "").strip() or None,
                    str(card.get("price") or "").strip() or "від ХХ грн",
                    str(card.get("image_url") or "").strip() or None,
                    card_index * 10,
                ),
            )


def sync_default_service_content(cur) -> None:
    aliases = {
        "Пірсинг": [
            "Медичний пірсинг",
            "Пірсинг вух",
            "Пірсинг носа",
            "Пірсинг брови",
            "Пірсинг язика",
            "Пірсинг пупка",
            "Додатково",
        ],
        "Прикраси": ["Італійська медична позолота"],
    }
    for index, section in enumerate(load_default_services(), start=1):
        title = str(section.get("title") or "").strip()
        if not title:
            continue
        description = str(section.get("description") or "").strip() or None
        image_url = str(section.get("image_url") or "").strip() or None
        lookup_titles = [title, *aliases.get(title, [])]
        placeholders = ",".join(["%s"] * len(lookup_titles))
        cur.execute(f"SELECT Id FROM ServiceSections WHERE Title IN ({placeholders}) ORDER BY Id", lookup_titles)
        rows = cur.fetchall()
        if rows:
            section_id = int(rows[0]["Id"])
            duplicate_section_ids = [int(row["Id"]) for row in rows[1:]]
            if duplicate_section_ids:
                duplicate_placeholders = ",".join(["%s"] * len(duplicate_section_ids))
                cur.execute(
                    f"UPDATE ServiceCards SET SectionId=%s WHERE SectionId IN ({duplicate_placeholders})",
                    (section_id, *duplicate_section_ids),
                )
                cur.execute(f"DELETE FROM ServiceSections WHERE Id IN ({duplicate_placeholders})", duplicate_section_ids)
            cur.execute(
                """
                UPDATE ServiceSections
                SET Title=%s, Description=%s, ImageUrl=%s, SortOrder=%s, IsActive=TRUE
                WHERE Id=%s
                """,
                (title, description, image_url, index * 10, section_id),
            )
        else:
            cur.execute(
                "INSERT INTO ServiceSections (Title, Description, ImageUrl, SortOrder) VALUES (%s, %s, %s, %s)",
                (title, description, image_url, index * 10),
            )
            section_id = int(cur.lastrowid)

        cards = section.get("cards", [])
        if not isinstance(cards, list):
            cards = []
        active_titles: list[str] = []
        for card_index, card in enumerate(cards, start=1):
            card_title = str(card.get("title") or "").strip()
            if not card_title:
                continue
            active_titles.append(card_title)
            card_values = (
                str(card.get("description") or "").strip() or None,
                str(card.get("price") or "").strip() or "від ХХ грн",
                str(card.get("image_url") or "").strip() or None,
                card_index * 10,
            )
            cur.execute("SELECT Id FROM ServiceCards WHERE SectionId=%s AND Title=%s ORDER BY Id", (section_id, card_title))
            existing_rows = cur.fetchall()
            if existing_rows:
                card_id = int(existing_rows[0]["Id"])
                duplicate_card_ids = [int(row["Id"]) for row in existing_rows[1:]]
                if duplicate_card_ids:
                    duplicate_placeholders = ",".join(["%s"] * len(duplicate_card_ids))
                    cur.execute(f"DELETE FROM ServiceCards WHERE Id IN ({duplicate_placeholders})", duplicate_card_ids)
                cur.execute(
                    """
                    UPDATE ServiceCards
                    SET ShortDescription=%s, PriceText=%s, ImageUrl=%s, SortOrder=%s, IsActive=TRUE
                    WHERE Id=%s
                    """,
                    (*card_values, card_id),
                )
            else:
                cur.execute(
                    """
                    INSERT INTO ServiceCards (SectionId, Title, ShortDescription, PriceText, ImageUrl, SortOrder)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    (section_id, card_title, *card_values),
                )
        if active_titles:
            placeholders = ",".join(["%s"] * len(active_titles))
            cur.execute(
                f"UPDATE ServiceCards SET IsActive=FALSE WHERE SectionId=%s AND Title NOT IN ({placeholders})",
                (section_id, *active_titles),
            )


def load_service_sections(include_inactive: bool = False) -> list[dict[str, Any]]:
    where = "" if include_inactive else "WHERE IsActive=TRUE"
    with db_cursor() as cur:
        cur.execute(f"SELECT * FROM ServiceSections {where} ORDER BY SortOrder, Id")
        sections = cur.fetchall()
        cur.execute(
            f"""
            SELECT c.*
            FROM ServiceCards c
            JOIN ServiceSections s ON s.Id=c.SectionId
            {"WHERE c.IsActive=TRUE" if not include_inactive else ""}
            ORDER BY c.SortOrder, c.Id
            """
        )
        cards = cur.fetchall()
    by_section: dict[int, list[dict[str, Any]]] = {}
    for card in cards:
        by_section.setdefault(int(card["SectionId"]), []).append(card)
    for section in sections:
        section["Cards"] = by_section.get(int(section["Id"]), [])
    return sections


def current_user() -> dict[str, Any] | None:
    login = session.get("login")
    if not login:
        return None
    with db_cursor() as cur:
        cur.execute("SELECT Login, FullName, Email, Role, IsBlocked, ActiveSessionId FROM Users WHERE Login=%s", (login,))
        user = cur.fetchone()
    if not user or user.get("IsBlocked"):
        session.clear()
        return None
    return user


def is_admin(user: dict[str, Any] | None) -> bool:
    return bool(user and user.get("Role") == "admin")


def can_manage_services(user: dict[str, Any] | None) -> bool:
    return bool(user and user.get("Role") in {"admin", "manager"})


def user_display_name(user: dict[str, Any] | None) -> str:
    if not user:
        return ""
    return (user.get("FullName") or user.get("Login") or "").strip()


def avatar_initials(name: str) -> str:
    parts = [part for part in re.split(r"\s+", (name or "").strip()) if part]
    if len(parts) >= 2:
        return (parts[0][0] + parts[1][0]).upper()
    if parts:
        return parts[0][:2].upper()
    return "U"


def require_user() -> dict[str, Any] | Response:
    user = current_user()
    if not user:
        flash("Увійдіть, будь ласка.", "error")
        return redirect(url_for("login"))
    return user


def require_admin() -> dict[str, Any] | Response:
    user = current_user()
    if not is_admin(user):
        flash("Потрібні права адміністратора.", "error")
        return redirect(url_for("admin_appointments"))
    return user


def log_action(action: str, details: str = "") -> None:
    try:
        actor = session.get("login") or "anonymous"
        ip = request.headers.get("X-Forwarded-For", "").split(",", 1)[0].strip() if request else ""
        if not ip and request:
            ip = request.remote_addr or ""
        with db_cursor(commit=True) as cur:
            cur.execute(
                "INSERT INTO AuditLog (Actor, Action, Details, Ip) VALUES (%s, %s, %s, %s)",
                (actor, action[:255], details[:60000] if details else None, ip or None),
            )
        mf.tolog(f"AUDIT action={action} actor={actor} ip={ip or 'unknown'} details={details[:1000]}")
    except Exception as ex:
        mf.tolog(f"log_action({action}) failed: {ex}")


def log_user_event(text: str) -> None:
    actor = session.get("login") or "anonymous"
    message = f"User {actor} {text}"
    log_action("user_event", message)
    mf.tolog(message)


def parse_visit_at(date_value: str, time_value: str) -> datetime | None:
    raw = f"{date_value.strip()} {time_value.strip()}"
    try:
        return datetime.strptime(raw, "%Y-%m-%d %H:%M")
    except ValueError:
        return None


def parse_int(value: str, default: int, low: int = 1, high: int = 100000) -> int:
    try:
        return min(high, max(low, int(value)))
    except (TypeError, ValueError):
        return default


def parse_date(value: str) -> datetime | None:
    try:
        return datetime.strptime(value.strip(), "%Y-%m-%d")
    except (AttributeError, ValueError):
        return None


def localize_image_url(image_url: str) -> str:
    image_url = (image_url or "").strip()
    if not image_url or not image_url.lower().startswith(("http://", "https://")):
        return image_url
    try:
        response = requests.get(image_url, timeout=15)
        response.raise_for_status()
        content_type = response.headers.get("Content-Type", "").lower()
        ext = ".jpg"
        if "png" in content_type:
            ext = ".png"
        elif "webp" in content_type:
            ext = ".webp"
        elif "gif" in content_type:
            ext = ".gif"
        existing = sorted(Path(SERVICE_IMAGE_DIR).glob("Image_*.*"))
        next_num = 1
        if existing:
            nums = []
            for path in existing:
                match = re.search(r"Image_(\d+)", path.stem)
                if match:
                    nums.append(int(match.group(1)))
            next_num = (max(nums) + 1) if nums else 1
        filename = f"Image_{next_num:05d}{ext}"
        target = os.path.join(SERVICE_IMAGE_DIR, filename)
        with open(target, "wb") as fh:
            fh.write(response.content)
        return f"/static/service_images/{filename}"
    except Exception as ex:
        mf.tolog(f"localize_image_url() failed for {image_url}: {ex}")
        return image_url


def visitor_key(raw_id: str) -> str:
    return hashlib.sha256(raw_id.encode("utf-8")).hexdigest()


def should_track_visit() -> bool:
    return request.method == "GET" and request.endpoint in VISIT_TRACK_ENDPOINTS


def record_page_visit() -> None:
    if not should_track_visit():
        return
    visitor_id = request.cookies.get(VISIT_COOKIE, "").strip()
    if not re.fullmatch(r"[0-9a-fA-F-]{32,40}", visitor_id):
        visitor_id = uuid.uuid4().hex
        g.set_visit_cookie = visitor_id
    try:
        if not runtime_state["schema_ready"]:
            ensure_schema()
        with db_cursor(commit=True) as cur:
            cur.execute(
                """
                INSERT INTO PageVisits (VisitorKey, Path, Endpoint, UserAgent)
                VALUES (%s, %s, %s, %s)
                """,
                (
                    visitor_key(visitor_id),
                    request.path[:255],
                    (request.endpoint or "")[:120] or None,
                    (request.headers.get("User-Agent") or "")[:500] or None,
                ),
            )
    except Exception as ex:
        mf.tolog(f"record_page_visit() failed: {ex}")


def notification_recipients(config: dict[str, str]) -> list[str]:
    raw = config.get("NOTIFY_EMAILS", "")
    return [email.strip() for email in re.split(r"[,\n;]+", raw) if email.strip()]


def build_appointment_text(row: dict[str, Any], prefix: str) -> str:
    visit_at = row["VisitAt"]
    if isinstance(visit_at, str):
        visit_text = visit_at
    else:
        visit_text = visit_at.strftime("%d.%m.%Y о %H:%M")
    return (
        f"{prefix}\n"
        f"Клієнт: {row.get('ClientName', '')}\n"
        f"Коли: {visit_text}\n"
        f"Ціль візиту: {row.get('VisitPurpose', '')}\n"
        f"Телефон: {row.get('Phone') or '-'}\n"
        f"Email: {row.get('Email') or '-'}"
    )


def send_email_message(subject: str, body: str, config: dict[str, str], recipients: list[str], attachments: list[str] | None = None) -> str:
    if not recipients:
        return ""
    smtp_host = config.get("SMTP_HOST", "").strip()
    smtp_from = config.get("SMTP_FROM", "").strip() or config.get("SMTP_USER", "").strip()
    if not smtp_host or not smtp_from:
        return "SMTP не налаштовано."
    try:
        smtp_port = int(config.get("SMTP_PORT") or 587)
    except ValueError:
        return "SMTP_PORT некоректний."

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = smtp_from
    msg["To"] = ", ".join(recipients)
    msg.set_content(body)
    for path in attachments or []:
        try:
            with open(path, "rb") as fh:
                data = fh.read()
            msg.add_attachment(data, maintype="application", subtype="octet-stream", filename=os.path.basename(path))
        except Exception as ex:
            mf.tolog(f"Attachment skipped {path}: {ex}")

    try:
        with smtplib.SMTP(smtp_host, smtp_port, timeout=25) as smtp:
            if config.get("SMTP_TLS", "1").strip().lower() not in {"0", "false", "no", "off"}:
                smtp.starttls()
            smtp_user = config.get("SMTP_USER", "").strip()
            if smtp_user:
                smtp.login(smtp_user, config.get("SMTP_PASSWORD", ""))
            smtp.send_message(msg)
        return ""
    except Exception as ex:
        return str(ex)


def send_telegram_message(body: str, config: dict[str, str]) -> str:
    token = config.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = config.get("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        return ""
    try:
        response = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data={"chat_id": chat_id, "text": body},
            timeout=25,
        )
        if response.status_code == 200:
            return ""
        return f"Telegram status={response.status_code} body={response.text[:500]}"
    except Exception as ex:
        return str(ex)


def notify_staff(subject: str, body: str, config: dict[str, str] | None = None, attachments: list[str] | None = None) -> bool:
    config = config or load_config()
    ok = True
    emails = notification_recipients(config)
    email_error = send_email_message(subject, body, config, emails, attachments)
    if email_error:
        ok = False
        mf.tolog(f"Email notification failed: {email_error}")
    tg_error = send_telegram_message(body, config)
    if tg_error:
        ok = False
        mf.tolog(f"Telegram notification failed: {tg_error}")
    return ok


def _report_file_path() -> str:
    return os.path.join(REPORT_SEND_DIR, f"LadySite_report_{datetime.now():%Y-%m-%d}.log")


def _report_critical_error(message: str, ex: Exception | None = None) -> None:
    text = f"{datetime.now():%Y-%m-%d %H:%M:%S} {message}"
    if ex:
        text += f" Exception: {ex}"
    mf.AppendFile(_report_file_path(), text)
    mf.tolog(text)


def _send_report_files() -> int:
    config = load_config()
    files = [str(path) for path in Path(REPORT_SEND_DIR).glob("*.log")]
    if not files:
        return 0
    sent = 0
    for path in files:
        body = f"Звіт LadySite: {os.path.basename(path)}"
        if notify_staff("LadySite: звіт", body, config, [path]):
            target = os.path.join(REPORT_DIR, os.path.basename(path))
            try:
                os.replace(path, target)
            except OSError:
                pass
            sent += 1
    return sent


def delete_old_appointments(days: int) -> int:
    cutoff = datetime.now() - timedelta(days=max(1, days))
    with db_cursor(commit=True) as cur:
        cur.execute("DELETE FROM Appointments WHERE VisitAt < %s", (cutoff,))
        return cur.rowcount


def scheduler_job(force_cleanup: bool = False) -> None:
    config = load_config()
    now = datetime.now()
    try:
        if not runtime_state["schema_ready"]:
            ensure_schema()
        if not runtime_state["schema_ready"]:
            return

        with db_cursor(commit=True) as cur:
            cur.execute("SELECT * FROM Appointments WHERE SendNow=FALSE ORDER BY create_at LIMIT 50")
            rows = cur.fetchall()
            for row in rows:
                text = build_appointment_text(row, "Новий запис у центр краси і здоров'я ЛЕДІ")
                if notify_staff("ЛЕДІ: новий запис", text, config):
                    cur.execute("UPDATE Appointments SET SendNow=TRUE WHERE Id=%s", (row["Id"],))

            remind_hours = parse_int(config.get("REMIND_BEFORE_HOURS", "2"), 2, 1, 240)
            cur.execute(
                """
                SELECT * FROM Appointments
                WHERE SendBeforeCl=FALSE AND VisitAt BETWEEN %s AND %s
                ORDER BY VisitAt
                LIMIT 50
                """,
                (now, now + timedelta(hours=remind_hours)),
            )
            rows = cur.fetchall()
            for row in rows:
                text = build_appointment_text(row, f"Нагадування: клієнт прийде через {remind_hours} год.")
                if notify_staff("ЛЕДІ: нагадування про клієнта", text, config):
                    cur.execute("UPDATE Appointments SET SendBeforeCl=TRUE WHERE Id=%s", (row["Id"],))

        clear_hours = parse_int(config.get("CLEAR_LOG_HOURS", "12"), 12, 1, 720)
        if force_cleanup or runtime_state["last_log_clear"] + timedelta(hours=clear_hours) <= now:
            clear_days = parse_int(config.get("CLEAR_LOG_DAYS", "10"), 10, 1, 3650)
            deleted_logs = mf.ClearOldLog(os.path.join(PPath, "logs"), clear_days)
            mf.tolog(f"Очищення логів: видалено {deleted_logs} файлів старіше {clear_days} днів")
            runtime_state["last_log_clear"] = now

        if force_cleanup or runtime_state["last_appointments_cleanup"] + timedelta(hours=clear_hours) <= now:
            delete_days = parse_int(config.get("DELETE_OLD_APPOINTMENTS_DAYS", "60"), 60, 1, 3650)
            deleted_rows = delete_old_appointments(delete_days)
            mf.tolog(f"Очищення записів: видалено {deleted_rows} записів старіше {delete_days} днів")
            runtime_state["last_appointments_cleanup"] = now

        send_minutes = parse_int(config.get("SEND_ERR_TIME_IN_MINUTES", "360"), 360, 1, 10080)
        if runtime_state["next_report_send"] <= now:
            sent = _send_report_files()
            if sent:
                mf.tolog(f"Відправлено звітів: {sent}")
            runtime_state["next_report_send"] = now + timedelta(minutes=send_minutes)
    except Exception as ex:
        _report_critical_error("scheduler_job() failed", ex)


@app.context_processor
def inject_globals():
    user = None
    try:
        user = current_user()
    except Exception:
        user = None
    return {
        "app_version": Ver,
        "visit_count": total_visit_count,
        "appointment_count": total_appointment_count,
        "user": user,
        "is_admin": is_admin(user),
        "can_manage_services": can_manage_services(user),
    }


app.jinja_env.globals.update(user_display_name=user_display_name, avatar_initials=avatar_initials)


@app.before_request
def track_page_visit_before_request():
    record_page_visit()


@app.after_request
def set_visit_cookie(response: Response):
    visitor_id = getattr(g, "set_visit_cookie", "")
    if visitor_id:
        response.set_cookie(VISIT_COOKIE, visitor_id, max_age=60 * 60 * 24 * 365, samesite="Lax")
    return response


def total_visit_count() -> int:
    try:
        if not runtime_state["schema_ready"]:
            ensure_schema()
        with db_cursor() as cur:
            cur.execute("SELECT COUNT(DISTINCT VisitorKey) AS cnt FROM PageVisits")
            return int(cur.fetchone()["cnt"])
    except Exception as ex:
        mf.tolog(f"total_visit_count() failed: {ex}")
        return 0


def total_appointment_count() -> int:
    try:
        if not runtime_state["schema_ready"]:
            ensure_schema()
        with db_cursor() as cur:
            cur.execute("SELECT COUNT(*) AS cnt FROM Appointments")
            return int(cur.fetchone()["cnt"])
    except Exception as ex:
        mf.tolog(f"total_appointment_count() failed: {ex}")
        return 0


@app.route("/")
def index():
    config = load_config()
    online_enabled = config.get("ONLINE_APPOINTMENT_ENABLED", "1").strip().lower() not in {"0", "false", "no", "off"}
    return render_template("index.html", config=config, online_enabled=online_enabled, active_page="home")


@app.route("/services")
def services():
    preview_public = request.args.get("preview") == "public"
    manager_view = can_manage_services(current_user()) and not preview_public
    try:
        ensure_schema()
        sections = load_service_sections(include_inactive=manager_view)
        config = load_config()
    except Exception as ex:
        _report_critical_error("services page failed", ex)
        sections = []
        config = load_config()
        flash(f"Послуги тимчасово недоступні: {ex}", "error")
    return render_template(
        "services.html",
        sections=sections,
        config=config,
        manager_view=manager_view,
        active_page="services",
    )


@app.route("/services/intro", methods=["POST"])
def service_intro_update():
    user = require_user()
    if not isinstance(user, dict):
        return user
    if not can_manage_services(user):
        flash("Недостатньо прав для редагування послуг.", "error")
        return redirect(url_for("services"))
    intro = request.form.get("services_intro", "").strip()
    config = load_config()
    config["SERVICES_PAGE_INTRO"] = intro or "Тут розділи і напрямки, якими займається наш центр."
    save_config(config)
    log_action("services_intro_update")
    flash("Текст сторінки послуг оновлено.", "success")
    return redirect(url_for("services") + "#services-admin")


@app.route("/services/section", methods=["POST"])
def service_section_create():
    user = require_user()
    if not isinstance(user, dict):
        return user
    if not can_manage_services(user):
        flash("Недостатньо прав для редагування послуг.", "error")
        return redirect(url_for("services"))
    title = request.form.get("title", "").strip()
    description = request.form.get("description", "").strip()
    image_url = localize_image_url(request.form.get("image_url", "").strip())
    if not title:
        flash("Назва розділу обов'язкова.", "error")
        return redirect(url_for("services"))
    with db_cursor(commit=True) as cur:
        cur.execute("SELECT COALESCE(MAX(SortOrder), 0) + 10 AS next_order FROM ServiceSections")
        sort_order = int(cur.fetchone()["next_order"])
        cur.execute(
            "INSERT INTO ServiceSections (Title, Description, ImageUrl, SortOrder) VALUES (%s, %s, %s, %s)",
            (title, description or None, image_url or None, sort_order),
        )
    log_user_event(f'додав розділ "{title}"')
    flash("Розділ додано.", "success")
    return redirect(url_for("services"))


@app.route("/services/card", methods=["POST"])
def service_card_create():
    user = require_user()
    if not isinstance(user, dict):
        return user
    if not can_manage_services(user):
        flash("Недостатньо прав для редагування послуг.", "error")
        return redirect(url_for("services"))
    section_id = parse_int(request.form.get("section_id", "0"), 0, 0, 999999999)
    title = request.form.get("title", "").strip()
    description = request.form.get("description", "").strip()
    price = request.form.get("price", "").strip()
    image_url = localize_image_url(request.form.get("image_url", "").strip())
    if not section_id or not title:
        flash("Оберіть розділ і вкажіть назву картки.", "error")
        return redirect(url_for("services"))
    with db_cursor(commit=True) as cur:
        cur.execute("SELECT Title FROM ServiceSections WHERE Id=%s", (section_id,))
        section = cur.fetchone()
        section_title = section["Title"] if section else ""
        cur.execute("SELECT COALESCE(MAX(SortOrder), 0) + 10 AS next_order FROM ServiceCards WHERE SectionId=%s", (section_id,))
        sort_order = int(cur.fetchone()["next_order"])
        cur.execute(
            """
            INSERT INTO ServiceCards (SectionId, Title, ShortDescription, PriceText, ImageUrl, SortOrder)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (section_id, title, description or None, price or "від ХХ грн", image_url or None, sort_order),
        )
    log_user_event(f'додав картку "{title}" в розділ "{section_title}"')
    flash("Картку послуги додано.", "success")
    return redirect(url_for("services"))


@app.route("/services/item/<kind>/<int:item_id>/edit", methods=["POST"])
def service_item_edit(kind: str, item_id: int):
    user = require_user()
    if not isinstance(user, dict):
        return user
    if not can_manage_services(user):
        flash("Недостатньо прав для редагування послуг.", "error")
        return redirect(url_for("services"))
    title = request.form.get("title", "").strip()
    description = request.form.get("description", "").strip()
    image_url = localize_image_url(request.form.get("image_url", "").strip())
    price = request.form.get("price", "").strip()
    section_id = parse_int(request.form.get("section_id", "0"), 0, 0, 999999999)
    if not title:
        flash("Назва обов'язкова.", "error")
        return redirect(url_for("services") + "#services-admin")
    with db_cursor(commit=True) as cur:
        if kind == "section":
            cur.execute(
                "UPDATE ServiceSections SET Title=%s, Description=%s, ImageUrl=%s WHERE Id=%s",
                (title, description or None, image_url or None, item_id),
            )
            log_text = f'відредагував розділ "{title}"'
        elif kind == "card":
            cur.execute("SELECT Title FROM ServiceSections WHERE Id=%s", (section_id,))
            section = cur.fetchone()
            if not section:
                flash("Оберіть розділ для картки.", "error")
                return redirect(url_for("services") + "#services-admin")
            cur.execute("SELECT SectionId, SortOrder FROM ServiceCards WHERE Id=%s", (item_id,))
            current_card = cur.fetchone()
            sort_order = current_card["SortOrder"] if current_card else 100
            if current_card and int(current_card["SectionId"]) != section_id:
                cur.execute("SELECT COALESCE(MAX(SortOrder), 0) + 10 AS next_order FROM ServiceCards WHERE SectionId=%s", (section_id,))
                sort_order = int(cur.fetchone()["next_order"])
            cur.execute(
                """
                UPDATE ServiceCards
                SET SectionId=%s, Title=%s, ShortDescription=%s, PriceText=%s, ImageUrl=%s, SortOrder=%s
                WHERE Id=%s
                """,
                (section_id, title, description or None, price or "від ХХ грн", image_url or None, sort_order, item_id),
            )
            log_text = f'відредагував картку "{title}" в розділі "{section["Title"]}"'
        else:
            flash("Невідомий тип елемента.", "error")
            return redirect(url_for("services") + "#services-admin")
    log_user_event(log_text)
    flash("Зміни збережено.", "success")
    return redirect(url_for("services") + "#services-admin")


@app.route("/services/item/<kind>/<int:item_id>/move", methods=["POST"])
def service_item_move(kind: str, item_id: int):
    user = require_user()
    if not isinstance(user, dict):
        return user
    if not can_manage_services(user):
        flash("Недостатньо прав для редагування послуг.", "error")
        return redirect(url_for("services"))
    direction = request.form.get("direction", "")
    if direction not in {"up", "down"}:
        flash("Невідомий напрямок переміщення.", "error")
        return redirect(url_for("services") + "#services-admin")
    with db_cursor(commit=True) as cur:
        if kind == "section":
            table = "ServiceSections"
            scope_sql = ""
            scope_args: tuple[Any, ...] = ()
            cur.execute("SELECT Id, Title, SortOrder FROM ServiceSections WHERE Id=%s", (item_id,))
            current = cur.fetchone()
            label = "розділ"
        elif kind == "card":
            table = "ServiceCards"
            cur.execute(
                """
                SELECT c.Id, c.Title, c.SortOrder, c.SectionId, s.Title AS SectionTitle
                FROM ServiceCards c
                JOIN ServiceSections s ON s.Id=c.SectionId
                WHERE c.Id=%s
                """,
                (item_id,),
            )
            current = cur.fetchone()
            scope_sql = "AND SectionId=%s"
            scope_args = (current["SectionId"],) if current else ()
            label = "картку"
        else:
            flash("Невідомий тип елемента.", "error")
            return redirect(url_for("services") + "#services-admin")
        if not current:
            flash("Елемент не знайдено.", "error")
            return redirect(url_for("services") + "#services-admin")
        compare = "<" if direction == "up" else ">"
        order = "DESC" if direction == "up" else "ASC"
        cur.execute(
            f"""
            SELECT Id, SortOrder FROM {table}
            WHERE SortOrder {compare} %s {scope_sql}
            ORDER BY SortOrder {order}, Id {order}
            LIMIT 1
            """,
            (current["SortOrder"], *scope_args),
        )
        neighbor = cur.fetchone()
        if not neighbor:
            flash("Далі рухати нікуди.", "error")
            return redirect(url_for("services") + "#services-admin")
        cur.execute(f"UPDATE {table} SET SortOrder=%s WHERE Id=%s", (neighbor["SortOrder"], current["Id"]))
        cur.execute(f"UPDATE {table} SET SortOrder=%s WHERE Id=%s", (current["SortOrder"], neighbor["Id"]))
    log_user_event(f'{"підняв" if direction == "up" else "опустив"} {label} "{current["Title"]}" {"вверх" if direction == "up" else "вниз"}')
    flash("Порядок оновлено.", "success")
    return redirect(url_for("services") + "#services-admin")


@app.route("/services/item/<kind>/<int:item_id>", methods=["POST"])
def service_item_update(kind: str, item_id: int):
    user = require_user()
    if not isinstance(user, dict):
        return user
    if not can_manage_services(user):
        flash("Недостатньо прав для редагування послуг.", "error")
        return redirect(url_for("services"))
    action = request.form.get("action", "")
    with db_cursor(commit=True) as cur:
        if kind == "section":
            table = "ServiceSections"
        elif kind == "card":
            table = "ServiceCards"
        else:
            flash("Невідомий тип елемента.", "error")
            return redirect(url_for("services"))
        if action == "hide":
            cur.execute(f"UPDATE {table} SET IsActive=FALSE WHERE Id=%s", (item_id,))
            cur.execute(f"SELECT Title FROM {table} WHERE Id=%s", (item_id,))
            row = cur.fetchone()
            log_text = f'приховав {"розділ" if kind == "section" else "картку"} "{row["Title"] if row else item_id}"'
        elif action == "show":
            cur.execute(f"UPDATE {table} SET IsActive=TRUE WHERE Id=%s", (item_id,))
            cur.execute(f"SELECT Title FROM {table} WHERE Id=%s", (item_id,))
            row = cur.fetchone()
            log_text = f'показав {"розділ" if kind == "section" else "картку"} "{row["Title"] if row else item_id}"'
        elif action == "delete":
            if kind == "section":
                cur.execute("SELECT Title FROM ServiceSections WHERE Id=%s", (item_id,))
                row = cur.fetchone()
                cur.execute("DELETE FROM ServiceCards WHERE SectionId=%s", (item_id,))
                log_text = f'видалив розділ "{row["Title"] if row else item_id}"'
            else:
                cur.execute("SELECT Title FROM ServiceCards WHERE Id=%s", (item_id,))
                row = cur.fetchone()
                log_text = f'видалив картку "{row["Title"] if row else item_id}"'
            cur.execute(f"DELETE FROM {table} WHERE Id=%s", (item_id,))
        else:
            flash("Невідома дія.", "error")
            return redirect(url_for("services") + "#services-admin")
    log_user_event(log_text)
    flash("Зміни збережено.", "success")
    return redirect(url_for("services") + "#services-admin")


@app.route("/about")
def about():
    config = load_config()
    return render_template("about.html", config=config, active_page="about")


@app.route("/appointment", methods=["POST"])
def appointment_create():
    config = load_config()
    if config.get("ONLINE_APPOINTMENT_ENABLED", "1").strip().lower() in {"0", "false", "no", "off"}:
        flash("Онлайн запис тимчасово вимкнено. Будь ласка, зв'яжіться з нами телефоном.", "error")
        return redirect(url_for("index") + "#appointment")
    visit_at = parse_visit_at(request.form.get("visit_date", ""), request.form.get("visit_time", ""))
    client_name = request.form.get("client_name", "").strip()
    purpose = request.form.get("visit_purpose", "").strip()
    phone = request.form.get("phone", "").strip()
    email = request.form.get("email", "").strip()
    if not visit_at or not client_name or not purpose or (not phone and not email):
        flash("Заповніть дату, час, ім'я, ціль візиту та телефон або email.", "error")
        return redirect(url_for("index") + "#appointment")
    if visit_at < datetime.now() - timedelta(minutes=5):
        flash("Оберіть майбутню дату і час.", "error")
        return redirect(url_for("index") + "#appointment")
    try:
        ensure_schema()
        with db_cursor(commit=True) as cur:
            cur.execute(
                """
                INSERT INTO Appointments (VisitAt, ClientName, VisitPurpose, Phone, Email)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (visit_at, client_name, purpose, phone or None, email or None),
            )
        log_action("appointment_create", f"{client_name} {visit_at:%Y-%m-%d %H:%M}")
        flash("Дякуємо! Запис прийнято, ми зв'яжемося з вами.", "success")
    except Exception as ex:
        _report_critical_error("appointment_create failed", ex)
        flash("Не вдалося зберегти запис. Спробуйте ще раз або зателефонуйте нам.", "error")
    return redirect(url_for("index") + "#appointment")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        login_value = request.form.get("login", "").strip()
        password = request.form.get("password", "")
        try:
            ensure_schema()
            with db_cursor(commit=True) as cur:
                cur.execute("SELECT * FROM Users WHERE Login=%s", (login_value,))
                user = cur.fetchone()
                if user and not user.get("IsBlocked") and check_password_hash(user["Pass"], password):
                    sid = os.urandom(16).hex()
                    cur.execute("UPDATE Users SET Last=%s, ActiveSessionId=%s WHERE Login=%s", (datetime.now(), sid, login_value))
                    session["login"] = login_value
                    session["session_id"] = sid
                    log_action("login_success")
                    return redirect(url_for("admin_appointments"))
            session["login"] = login_value or "anonymous"
            log_action("login_failed")
            session.clear()
        except Exception as ex:
            _report_critical_error("login failed", ex)
            flash(f"Помилка підключення до бази: {ex}", "error")
            return render_template("login.html", active_page="login")
        flash("Невірний логін або пароль.", "error")
    return render_template("login.html", active_page="login")


@app.route("/logout")
def logout():
    login_value = session.get("login")
    sid = session.get("session_id")
    log_action("logout")
    if login_value and sid:
        try:
            with db_cursor(commit=True) as cur:
                cur.execute(
                    "UPDATE Users SET ActiveSessionId=NULL WHERE Login=%s AND ActiveSessionId=%s",
                    (login_value, sid),
                )
        except Exception as ex:
            mf.tolog(f"logout session clear failed: {ex}")
    session.clear()
    return redirect(url_for("index"))


@app.route("/admin")
def admin_appointments():
    user = require_user()
    if not isinstance(user, dict):
        return user
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    if "days" in request.args:
        days = parse_int(request.args.get("days", "7"), 7, 7, 365)
        start = today
        end = today + timedelta(days=days)
        session["appointment_filter_mode"] = str(days)
        session.pop("appointment_filter_from", None)
        session.pop("appointment_filter_to", None)
    elif "date_from" in request.args or "date_to" in request.args:
        date_from = parse_date(request.args.get("date_from", ""))
        date_to = parse_date(request.args.get("date_to", ""))
        if not date_from or not date_to or date_to < date_from:
            flash("Оберіть коректний період записів.", "error")
            date_from = today
            date_to = today + timedelta(days=6)
        start = date_from.replace(hour=0, minute=0, second=0, microsecond=0)
        end = date_to.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
        session["appointment_filter_mode"] = "custom"
        session["appointment_filter_from"] = start.strftime("%Y-%m-%d")
        session["appointment_filter_to"] = (end - timedelta(days=1)).strftime("%Y-%m-%d")
    elif session.get("appointment_filter_mode") == "custom":
        start = parse_date(session.get("appointment_filter_from", "")) or today
        date_to = parse_date(session.get("appointment_filter_to", "")) or today + timedelta(days=6)
        start = start.replace(hour=0, minute=0, second=0, microsecond=0)
        end = date_to.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
    else:
        days = parse_int(session.get("appointment_filter_mode", "7"), 7, 7, 365)
        start = today
        end = today + timedelta(days=days)
        session["appointment_filter_mode"] = str(days)
    days = max(1, (end.date() - start.date()).days)
    try:
        ensure_schema()
        with db_cursor() as cur:
            cur.execute(
                "SELECT * FROM Appointments WHERE VisitAt >= %s AND VisitAt < %s ORDER BY VisitAt",
                (start, end),
            )
            rows = cur.fetchall()
    except Exception as ex:
        _report_critical_error("admin appointments failed", ex)
        rows = []
        flash(f"Не вдалося прочитати записи: {ex}", "error")
    return render_template(
        "admin_appointments.html",
        appointments=rows,
        days=days,
        mode=session.get("appointment_filter_mode", "7"),
        date_from=start.strftime("%Y-%m-%d"),
        date_to=(end - timedelta(days=1)).strftime("%Y-%m-%d"),
        active_page="admin",
    )


@app.route("/admin/visits")
def visit_stats():
    user = require_user()
    if not isinstance(user, dict):
        return user
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    if "days" in request.args:
        days = parse_int(request.args.get("days", "14"), 14, 7, 60)
        start = today - timedelta(days=days - 1)
        end = today + timedelta(days=1)
        session["visit_stats_mode"] = str(days)
        session.pop("visit_stats_from", None)
        session.pop("visit_stats_to", None)
    elif "date_from" in request.args or "date_to" in request.args:
        date_from = parse_date(request.args.get("date_from", ""))
        date_to = parse_date(request.args.get("date_to", ""))
        if not date_from or not date_to or date_to < date_from:
            flash("Оберіть коректний період від і до.", "error")
            date_to = today
            date_from = today - timedelta(days=13)
        start = date_from.replace(hour=0, minute=0, second=0, microsecond=0)
        end = date_to.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
        session["visit_stats_mode"] = "custom"
        session["visit_stats_from"] = start.strftime("%Y-%m-%d")
        session["visit_stats_to"] = (end - timedelta(days=1)).strftime("%Y-%m-%d")
    elif session.get("visit_stats_mode") == "custom":
        start = parse_date(session.get("visit_stats_from", "")) or today - timedelta(days=13)
        date_to = parse_date(session.get("visit_stats_to", "")) or today
        start = start.replace(hour=0, minute=0, second=0, microsecond=0)
        end = date_to.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
    else:
        days = parse_int(session.get("visit_stats_mode", "14"), 14, 7, 60)
        start = today - timedelta(days=days - 1)
        end = today + timedelta(days=1)
        session["visit_stats_mode"] = str(days)
    days = max(1, (end.date() - start.date()).days)
    labels = [(start + timedelta(days=offset)).date() for offset in range(days)]
    counts_by_day = {day: 0 for day in labels}
    try:
        ensure_schema()
        with db_cursor() as cur:
            cur.execute(
                """
                SELECT DATE(CreatedAt) AS VisitDay, COUNT(DISTINCT VisitorKey) AS VisitCount
                FROM PageVisits
                WHERE CreatedAt >= %s AND CreatedAt < %s
                GROUP BY DATE(CreatedAt)
                ORDER BY VisitDay
                """,
                (start, end),
            )
            for row in cur.fetchall():
                visit_day = row["VisitDay"]
                if isinstance(visit_day, str):
                    visit_day = datetime.strptime(visit_day, "%Y-%m-%d").date()
                counts_by_day[visit_day] = int(row["VisitCount"])
    except Exception as ex:
        _report_critical_error("visit stats failed", ex)
        flash(f"Не вдалося прочитати статистику відвідин: {ex}", "error")
    chart = [
        {
            "date": day,
            "label": day.strftime("%d.%m"),
            "count": counts_by_day[day],
        }
        for day in labels
    ]
    max_count = max([item["count"] for item in chart] or [1]) or 1
    today_count = counts_by_day.get(today.date(), 0)
    yesterday_count = counts_by_day.get((today - timedelta(days=1)).date(), 0)
    total_count = sum(item["count"] for item in chart)
    return render_template(
        "visit_stats.html",
        chart=chart,
        max_count=max_count,
        today_count=today_count,
        yesterday_count=yesterday_count,
        total_count=total_count,
        days=days,
        mode=session.get("visit_stats_mode", "14"),
        date_from=start.strftime("%Y-%m-%d"),
        date_to=(end - timedelta(days=1)).strftime("%Y-%m-%d"),
        active_page="visits",
    )


@app.route("/settings", methods=["GET", "POST"])
def settings():
    user = require_admin()
    if not isinstance(user, dict):
        return user
    config = load_config()
    active_tab = request.args.get("tab", "maintenance")
    if request.method == "POST":
        action = request.form.get("action", "save")
        form_config = config.copy()
        for key in list(form_config.keys()):
            field = f"cfg_{key}"
            if field in request.form:
                value = request.form.get(field, "").strip()
                if key in {"MYSQL_PASSWORD", "SMTP_PASSWORD"} and not value:
                    continue
                form_config[key] = value
        if action == "test_mysql":
            try:
                save_config(form_config)
                ensure_schema()
                if runtime_state["schema_ready"]:
                    flash("MySQL підключення працює.", "success")
                else:
                    flash(f"MySQL помилка: {runtime_state['schema_error']}", "error")
            except Exception as ex:
                flash(f"MySQL помилка: {ex}", "error")
            return redirect(url_for("settings", tab="mysql"))
        if action == "test_notify":
            save_config(form_config)
            ok = notify_staff("ЛЕДІ: тест повідомлень", "Тестове повідомлення з сайту ЛЕДІ.", form_config)
            flash("Тестове повідомлення відправлено." if ok else "Повідомлення не відправлено. Перевірте журнал.", "success" if ok else "error")
            return redirect(url_for("settings", tab=request.form.get("active_tab", "email")))
        if action == "clear_logs":
            save_config(form_config)
            scheduler_job(force_cleanup=True)
            log_action("clear_logs")
            flash("Очищення виконано.", "success")
            return redirect(url_for("settings", tab="maintenance"))
        save_config(form_config)
        log_action("settings_update")
        flash("Налаштування збережено.", "success")
        return redirect(url_for("settings", tab=request.form.get("active_tab", "maintenance")))
    return render_template("settings.html", config=config, active_tab=active_tab, active_page="settings")


@app.route("/users", methods=["GET", "POST"])
def users():
    user = require_admin()
    if not isinstance(user, dict):
        return user
    if request.method == "POST":
        login_value = request.form.get("login", "").strip()
        full_name = request.form.get("full_name", "").strip() or login_value
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")
        role = request.form.get("role", "manager")
        role = "admin" if role == "admin" else "manager"
        if not login_value or not password:
            flash("Логін і пароль обов'язкові.", "error")
            return redirect(url_for("users"))
        try:
            with db_cursor(commit=True) as cur:
                cur.execute(
                    "INSERT INTO Users (Login, FullName, Email, Pass, Role) VALUES (%s, %s, %s, %s, %s)",
                    (login_value, full_name, email or None, generate_password_hash(password), role),
                )
            log_action("user_create", login_value)
            flash("Користувача створено.", "success")
        except Exception as ex:
            if mysql_error_code(ex) == 1062:
                flash("Такий логін вже існує.", "error")
            else:
                _report_critical_error("user create failed", ex)
                flash(str(ex), "error")
        return redirect(url_for("users"))
    with db_cursor() as cur:
        cur.execute("SELECT Login, FullName, Email, Role, IsBlocked, Last, CreatedAt FROM Users ORDER BY Login")
        rows = cur.fetchall()
    return render_template("users.html", users=rows, active_page="users")


@app.route("/users/<login_value>/update", methods=["POST"])
def user_update(login_value: str):
    user = require_admin()
    if not isinstance(user, dict):
        return user
    action = request.form.get("action", "")
    if login_value == session.get("login") and action in {"block", "delete"}:
        flash("Свій акаунт не можна заблокувати або видалити тут.", "error")
        return redirect(url_for("users"))
    with db_cursor(commit=True) as cur:
        if action == "delete":
            cur.execute("DELETE FROM Users WHERE Login=%s", (login_value,))
            log_action("user_delete", login_value)
        elif action == "block":
            cur.execute("UPDATE Users SET IsBlocked=TRUE, ActiveSessionId=NULL WHERE Login=%s", (login_value,))
            log_action("user_block", login_value)
        elif action == "unblock":
            cur.execute("UPDATE Users SET IsBlocked=FALSE WHERE Login=%s", (login_value,))
            log_action("user_unblock", login_value)
        elif action == "password":
            password = request.form.get("password", "")
            if len(password) < 5:
                flash("Пароль має бути мінімум 5 символів.", "error")
                return redirect(url_for("users"))
            cur.execute("UPDATE Users SET Pass=%s, ActiveSessionId=NULL WHERE Login=%s", (generate_password_hash(password), login_value))
            log_action("user_password_change", login_value)
        elif action == "role":
            role = "admin" if request.form.get("role") == "admin" else "manager"
            if login_value == session.get("login") and role != "admin":
                flash("Не можна забрати адмінські права у себе.", "error")
                return redirect(url_for("users"))
            cur.execute("UPDATE Users SET Role=%s WHERE Login=%s", (role, login_value))
            log_action("user_role_change", f"{login_value} -> {role}")
    flash("Готово.", "success")
    return redirect(url_for("users"))


@app.route("/logs")
def logs():
    user = require_admin()
    if not isinstance(user, dict):
        return user
    today = datetime.now().strftime("%Y-%m-%d")
    raw_date = request.args.get("date", today)
    date = raw_date if re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw_date or "") else today
    path = os.path.join(PPath, "logs", f"{date}.log")
    content = ""
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            content = fh.read()
    audit = []
    try:
        with db_cursor() as cur:
            cur.execute("SELECT * FROM AuditLog ORDER BY CreatedAt DESC LIMIT 200")
            audit = cur.fetchall()
    except Exception as ex:
        flash(f"AuditLog недоступний: {ex}", "error")
    return render_template("logs.html", date=date, log_content=content, audit=audit, active_page="logs")


@app.route("/logs/download/range")
def logs_download_range():
    user = require_admin()
    if not isinstance(user, dict):
        return user
    start_raw = request.args.get("start_date", "")
    end_raw = request.args.get("end_date", "")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", start_raw) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", end_raw):
        return ("Некоректний діапазон дат", 400)
    start_date = datetime.strptime(start_raw, "%Y-%m-%d").date()
    end_date = datetime.strptime(end_raw, "%Y-%m-%d").date()
    mem = io.BytesIO()
    with zipfile.ZipFile(mem, "w", zipfile.ZIP_DEFLATED) as zf:
        current = start_date
        while current <= end_date:
            name = current.strftime("%Y-%m-%d")
            path = os.path.join(PPath, "logs", f"{name}.log")
            if os.path.exists(path):
                zf.write(path, arcname=f"{name}.log")
            current += timedelta(days=1)
    mem.seek(0)
    return send_file(mem, as_attachment=True, download_name=f"LadySite_logs_{start_raw}_{end_raw}.zip", mimetype="application/zip")


try:
    load_config()
    ensure_schema()
except Exception as ex:
    mf.tolog(f"Startup schema check failed: {ex}")

if not scheduler.running:
    scheduler.add_job(scheduler_job, "interval", minutes=5, id="lady_site_5min", replace_existing=True)
    scheduler.start()


if __name__ == "__main__":
    app.run(host=HOST, port=PORT, debug=True)
