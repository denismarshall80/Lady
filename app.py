from __future__ import annotations

import io
import json
import os
import re
import smtplib
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


Ver = "LadySite v0.5.13" # first build 2024-07-01

HOST = "localhost" if os.name == "nt" else "0.0.0.0"
PORT = 5000
PPath = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(PPath, "DATA", "LadySite.config")
DEFAULT_SERVICES_PATH = os.path.join(PPath, "DATA", "default_services.json")
REPORT_DIR = os.path.join(PPath, "Report")
REPORT_SEND_DIR = os.path.join(REPORT_DIR, "Send")
DEFAULT_MAP_URL = "https://www.google.com/maps/place/%D0%B2%D1%83%D0%BB%D0%B8%D1%86%D1%8F+%D0%9B%D0%B5%D1%81%D1%96+%D0%A3%D0%BA%D1%80%D0%B0%D1%97%D0%BD%D0%BA%D0%B8,+41,+%D0%9A%D0%B0%D0%BC'%D1%8F%D0%BD%D0%B5%D1%86%D1%8C-%D0%9F%D0%BE%D0%B4%D1%96%D0%BB%D1%8C%D1%81%D1%8C%D0%BA%D0%B8%D0%B9,+%D0%A5%D0%BC%D0%B5%D0%BB%D1%8C%D0%BD%D0%B8%D1%86%D1%8C%D0%BA%D0%B0+%D0%BE%D0%B1%D0%BB%D0%B0%D1%81%D1%82%D1%8C,+32300/@48.6759436,26.5838751,18.42z/data=!4m6!3m5!1s0x4733b87712b10bb7:0xc879ff1bd73b8e22!8m2!3d48.6759926!4d26.5847011!16s%2Fg%2F11g1lfpndx?entry=ttu"
DEFAULT_MAP_EMBED_URL = "https://www.google.com/maps?q=48.6759926,26.5847011&z=18&output=embed"

mf.PPath = PPath
for folder in ("DATA", "logs", "Report", os.path.join("Report", "Send")):
    mf.CreateDir(os.path.join(PPath, folder))

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
        "user": user,
        "is_admin": is_admin(user),
        "can_manage_services": can_manage_services(user),
    }


app.jinja_env.globals.update(user_display_name=user_display_name, avatar_initials=avatar_initials)


@app.route("/")
def index():
    config = load_config()
    online_enabled = config.get("ONLINE_APPOINTMENT_ENABLED", "1").strip().lower() not in {"0", "false", "no", "off"}
    return render_template("index.html", config=config, online_enabled=online_enabled, active_page="home")


@app.route("/services")
def services():
    try:
        ensure_schema()
        sections = load_service_sections(include_inactive=can_manage_services(current_user()))
        config = load_config()
    except Exception as ex:
        _report_critical_error("services page failed", ex)
        sections = []
        config = load_config()
        flash(f"Послуги тимчасово недоступні: {ex}", "error")
    return render_template("services.html", sections=sections, config=config, active_page="services")


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
    image_url = request.form.get("image_url", "").strip()
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
    log_action("service_section_create", title)
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
    image_url = request.form.get("image_url", "").strip()
    if not section_id or not title:
        flash("Оберіть розділ і вкажіть назву картки.", "error")
        return redirect(url_for("services"))
    with db_cursor(commit=True) as cur:
        cur.execute("SELECT COALESCE(MAX(SortOrder), 0) + 10 AS next_order FROM ServiceCards WHERE SectionId=%s", (section_id,))
        sort_order = int(cur.fetchone()["next_order"])
        cur.execute(
            """
            INSERT INTO ServiceCards (SectionId, Title, ShortDescription, PriceText, ImageUrl, SortOrder)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (section_id, title, description or None, price or "від ХХ грн", image_url or None, sort_order),
        )
    log_action("service_card_create", title)
    flash("Картку послуги додано.", "success")
    return redirect(url_for("services"))


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
        elif action == "show":
            cur.execute(f"UPDATE {table} SET IsActive=TRUE WHERE Id=%s", (item_id,))
        elif action == "delete":
            if kind == "section":
                cur.execute("DELETE FROM ServiceCards WHERE SectionId=%s", (item_id,))
            cur.execute(f"DELETE FROM {table} WHERE Id=%s", (item_id,))
        else:
            flash("Невідома дія.", "error")
            return redirect(url_for("services"))
    log_action("service_item_update", f"{kind}:{item_id}:{action}")
    flash("Зміни збережено.", "success")
    return redirect(url_for("services"))


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
    days = parse_int(request.args.get("days", "7"), 7, 7, 365)
    start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=days)
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
    return render_template("admin_appointments.html", appointments=rows, days=days, active_page="admin")


@app.route("/settings", methods=["GET", "POST"])
def settings():
    user = require_admin()
    if not isinstance(user, dict):
        return user
    config = load_config()
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
            return redirect(url_for("settings"))
        if action == "test_notify":
            save_config(form_config)
            ok = notify_staff("ЛЕДІ: тест повідомлень", "Тестове повідомлення з сайту ЛЕДІ.", form_config)
            flash("Тестове повідомлення відправлено." if ok else "Повідомлення не відправлено. Перевірте журнал.", "success" if ok else "error")
            return redirect(url_for("settings"))
        if action == "clear_logs":
            save_config(form_config)
            scheduler_job(force_cleanup=True)
            log_action("clear_logs")
            flash("Очищення виконано.", "success")
            return redirect(url_for("settings"))
        save_config(form_config)
        log_action("settings_update")
        flash("Налаштування збережено.", "success")
        return redirect(url_for("settings"))
    return render_template("settings.html", config=config, active_page="settings")


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
