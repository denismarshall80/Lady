from __future__ import annotations

import io
import hashlib
import json
import os
import re
import smtplib
import uuid
import time
from threading import Lock
import zipfile
from xml.etree import ElementTree as ET
from contextlib import contextmanager
from datetime import datetime, timedelta
from email.message import EmailMessage
from pathlib import Path
from typing import Any
import requests
from apscheduler.schedulers.background import BackgroundScheduler
from flask import (Flask, Response, flash, g,has_request_context,redirect,render_template,request,send_file,session,url_for)
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

import Utils.myfunct as mf
import Utils.page_content as pc
import Utils.site_log as sl

import sqlite3
import calendar
import Utils.database as database

#Ver = "LadySite v0.5.13" # first build 2024-07-01
#Ver = "LadySite v0.5.14" #оновили ціни
#Ver = "LadySite v0.5.15" #лічильник відвідин
#Ver = "LadySite v0.8.18" #редагування послуг
#Ver = "LadySite v0.8.19" #адмінка зручніше
#Ver = "LadySite v0.88.21" #редагування цін і адмінки
#Ver = "LadySite v0.90.02 (2026-07-06)" #додали включення/виключення сайту!
#Ver = "LadySite v0.91.04 (2026-10-08)" #редактор блоків, сторінки послуг, глобальний HTML-код
#Ver = "LadySite v0.91.05 (2026-10-08)" #згортання редактора, нотатки блоків, назва вкладки, футер, малюнки без обрізання
#Ver = "LadySite v0.92.02 (2026-10-08)" #переходи до розділів з урахуванням висоти закріпленого меню #компактний футер, версія зліва, оновлення кешу стилів
#Ver = "LadySite v0.93.02 (2026-10-08)" #короткі лічильники футера, приховування записів при вимкненому онлайн-записі #кнопка вставки метатега Google AdSense у налаштуваннях HTML-коду
#Ver = "LadySite v0.94.06 (2026-10-08)" #пробіли в нотатках не розгортають блоки, оновлення кешу редактора; окрема вкладка HTML для скриптів і метатегів; прибрано кнопку вставки метатега AdSense; алерти в меню, logotext, одна кнопка налаштувань; єдиний CSV-журнал, експорт і очищення; однакові вкладки налаштувань і прокрутка всередині секції; /profile
# Ver = "LadySite v0.95.05 (2026-10-09)" #режими й положення малюнків; збереження сторінки без згортання редактора та втрати позиції #керування елементами в заголовку; згорнуті налаштування малюнка; перейменування елемента довгим натисканням  #компактний редактор нод; каруселі, контурні анімації, контакти й адреса з графіком #редаговані нижні блоки; редактор після всього вмісту; фон сайту й окремих блоків
# Ver = "LadySite v0.95.06 (2026-10-09)" #висота тексту та кнопок; Facebook-іконка й посилання у нижньому блоці
#Ver = "LadySite v0.95.07 (2026-10-09)" #публічний футер; період відвідувачів; діалоги, колонки й панель редактора
#Ver = "LadySite v0.96.01 (2026-10-10)" #поточні календарні періоди та загальна кількість відвідувачів
#Ver = "LadySite v0.97 (2026-10-13)" #robots.txt та автоматична карта сайту sitemap.xml
#Ver = "LadySite v1.00 (2026-10-26)" #публічний маршрут ads.txt для AdSense
#Ver = "LadySite v1.00.01 (2026-10-27)" #автоматичне приховування банера waifly
#Ver = "LadySite v1.00.02 (2026-10-27)" #SQLite, JSON-послуги, компактне меню та журнал
#Ver = "LadySite v1.00.03 (2026-10-27)" #згортання секцій редактора, блок партнерів із редагованим HTML
#Ver = "LadySite v1.00.04 (2026-10-27)" #клієнтський лічильник відвідин: вчора, сьогодні, місяць, всього
#Ver = "LadySite v1.00.05 (2026-10-27)" #оновлена головна, меню розділів та кнопки наверх
#Ver = "LadySite v1.00.06 (2026-10-27)" #вертикальне меню головної, компактні послуги, вкладки налаштувань
#Ver = "LadySite v1.00.07 (2026-10-27)" #клієнтська фотокарусель, посилання меню та накладена кнопка наверх
#Ver = "LadySite v1.00.08 (2026-10-27)" #плавна циклічна карусель перетягуванням, роздільники меню та адреса
#Ver = "LadySite v1.00.09 (2026-10-27)" #попереднє завантаження каруселі, фото послуг та компактна іконка наверх
#Ver = "LadySite v1.00.10 (2026-10-28)" #горизонтальні закріплені меню та центровані написи кнопок на мобільному
#Ver = "LadySite v1.00.11 (2026-10-28)" #мобільне меню без миготіння та прихований редактор блоків
#Ver = "LadySite v1.00.12 (2026-10-28)" #спокійні кольори, головна для гостей та автопрокрутка активного меню
#Ver = "LadySite v1.00.13 (2026-10-28)" #ще 10 зображень у каруселі студії
Ver = "LadySite v1.00.14 (2026-10-28)" #автоматичне гортання каруселі кожні 40 секунд


HOST = "localhost" if os.name == "nt" else "0.0.0.0"
PORT = 5000
PPath = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(PPath, "DATA", "LadySite.config")
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
runtime_state = {"schema_ready": False,    "schema_error": "",    "last_log_clear": datetime.min,    "last_appointments_cleanup": datetime.min,    "next_report_send": datetime.min,}


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
        "SQLITE_PATH": "DATA/lady.db",
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
        "SITE_MAINTENANCE_ENABLED": "0",
        "ALERT_MAX_WIDTH": "240",
        "VISITOR_PERIOD_VALUE": "7",
        "VISITOR_PERIOD_UNIT": "days",
        "VISITOR_CURRENT_ENABLED": "0",
        "VISITOR_CURRENT_PERIOD": "month",
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
        "SQLITE_PATH",
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
        "SITE_MAINTENANCE_ENABLED",
        "SERVICES_PAGE_INTRO",
        "MAP_URL",
        "MAP_EMBED_URL",
        "ALERT_MAX_WIDTH",
        "VISITOR_PERIOD_VALUE",
        "VISITOR_PERIOD_UNIT",
        "VISITOR_CURRENT_ENABLED",
        "VISITOR_CURRENT_PERIOD",
    ]
    lines = ["# LadySite configuration", "# SQLite database path, relative to the application directory"]
    for key in order:
        lines.append(f"{key}={config.get(key, '')}")
    for key in sorted(set(config) - set(order)):
        if not key.startswith("MYSQL_"):
            lines.append(f"{key}={config[key]}")
    with open(CONFIG_PATH, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")


def database_path():
    path = Path(load_config().get("SQLITE_PATH", "DATA/lady.db"))
    return path if path.is_absolute() else Path(PPath) / path


@contextmanager
def db_cursor(commit: bool = False):
    conn = database.connect(database_path())
    try:
        if commit:
            conn.execute("BEGIN IMMEDIATE")
        yield conn.cursor()
        if commit:
            conn.commit()
        else:
            conn.rollback()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def ensure_schema() -> None:
    if runtime_state["schema_ready"]:
        return
    try:
        conn = database.connect(database_path())
        try:
            database.initialize(conn)
        finally:
            conn.close()
        runtime_state["schema_ready"] = True
        runtime_state["schema_error"] = ""
    except Exception as ex:
        runtime_state["schema_ready"] = False
        runtime_state["schema_error"] = str(ex)
        mf.tolog(f"ensure_schema() failed: {ex}")


def current_user() -> dict[str, Any] | None:
    login = session.get("login")
    if not login:
        return None
    with db_cursor() as cur:
        cur.execute("SELECT Login, FullName, Email, AvatarUrl, Role, IsBlocked, ActiveSessionId FROM Users WHERE Login=?", (login,))
        user = cur.fetchone()
    if not user or user.get("IsBlocked"):
        session.clear()
        return None
    return user


def is_admin(user: dict[str, Any] | None) -> bool:
    return bool(user and user.get("Role") == "admin")


def config_flag(config: dict[str, str], key: str, default: str = "0") -> bool:
    return config.get(key, default).strip().lower() in {"1", "true", "yes", "on"}


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
        actor = (session.get("login") or "anonymous") if has_request_context() else "Я (сайт)"
        sl.write_event(PPath, action, details, actor, log_ip())
    except Exception as ex:
        mf.tolog(f"log_action({action}) failed: {ex}")


def log_ip():
    if has_request_context():
        return request.headers.get("X-Forwarded-For", "").split(",", 1)[0].strip() or request.remote_addr or ""
    return sl.system_ip()


def write_system_log(message):
    sl.write_event(PPath, sl.action_from_message(message), message, "Я (сайт)", log_ip())


mf.LogWriter = write_system_log


def log_user_event(text: str) -> None:
    actor = session.get("login") or "anonymous"
    message = f"User {actor} {text}"
    log_action("user_event", message)


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


def uploaded_service_image_url(field_name: str = "image_file") -> str:
    file = request.files.get(field_name)
    if not file or not file.filename:
        return ""
    original = secure_filename(file.filename)
    suffix = Path(original).suffix.lower()
    if suffix not in {".jpg", ".jpeg", ".png", ".webp", ".gif"}:
        flash("Картинка має бути JPG, PNG, WEBP або GIF.", "error")
        return ""
    filename = f"Image_{uuid.uuid4().hex[:12]}{suffix}"
    target = os.path.join(SERVICE_IMAGE_DIR, filename)
    file.save(target)
    return f"/static/service_images/{filename}"


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
                VALUES (?, ?, ?, ?)
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
        cur.execute("DELETE FROM Appointments WHERE VisitAt < ?", (cutoff,))
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
                    cur.execute("UPDATE Appointments SET SendNow=TRUE WHERE Id=?", (row["Id"],))

            remind_hours = parse_int(config.get("REMIND_BEFORE_HOURS", "2"), 2, 1, 240)
            cur.execute(
                """
                SELECT * FROM Appointments
                WHERE SendBeforeCl=FALSE AND VisitAt BETWEEN ? AND ?
                ORDER BY VisitAt
                LIMIT 50
                """,
                (now, now + timedelta(hours=remind_hours)),
            )
            rows = cur.fetchall()
            for row in rows:
                text = build_appointment_text(row, f"Нагадування: клієнт прийде через {remind_hours} год.")
                if notify_staff("ЛЕДІ: нагадування про клієнта", text, config):
                    cur.execute("UPDATE Appointments SET SendBeforeCl=TRUE WHERE Id=?", (row["Id"],))

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
    session.setdefault("content_csrf", uuid.uuid4().hex)
    user = None
    try:
        user = current_user()
    except Exception:
        user = None
    try:
        global_config = load_config()
        site_maintenance = config_flag(global_config, "SITE_MAINTENANCE_ENABLED")
        footer_online_enabled = global_config.get("ONLINE_APPOINTMENT_ENABLED", "1").strip().lower() not in {"0", "false", "no", "off"}
    except Exception:
        site_maintenance = False
        footer_online_enabled = False
        global_config = {}
    content = pc.read_content()
    return {
        "global_code": content.get("global_code", {}),
        "site_contacts": pc.contact_settings(content, {"MAP_URL": DEFAULT_MAP_URL, "MAP_EMBED_URL": DEFAULT_MAP_EMBED_URL, **global_config}),
        "alert_max_width": parse_int(global_config.get("ALERT_MAX_WIDTH", "240"), 240, 40, 2000),
        "site_logotext": content.get("pages", {}).get("/", {}).get("logotext", pc.element({"text": "" if is_admin(user) else "Центр краси і здоров'я “ЛЕДІ”", "size": 18, "bold": True})),
        "site_blocks": pc.site_blocks(content, {"MAP_URL": DEFAULT_MAP_URL, "MAP_EMBED_URL": DEFAULT_MAP_EMBED_URL, **global_config}),
        "site_background": content.get("site_background", pc.background({})),
        "content_csrf": session["content_csrf"],
        "app_version": Ver,
        "appointment_count": total_appointment_count,
        "user": user,
        "is_admin": is_admin(user),
        "can_manage_services": can_manage_services(user),
        "site_maintenance": site_maintenance,
        "footer_online_enabled": footer_online_enabled,
    }


app.jinja_env.globals.update(user_display_name=user_display_name, avatar_initials=avatar_initials, has_visible_nodes=pc.has_visible_nodes, block_background=pc.block_background)


@app.before_request
def show_maintenance_for_non_admins():
    if request.endpoint in {"static", "login", "logout", "robots_txt", "sitemap_xml", "ads_txt"}:
        return None
    config = load_config()
    if not config_flag(config, "SITE_MAINTENANCE_ENABLED"):
        return None
    try:
        user = current_user()
    except Exception as ex:
        mf.tolog(f"maintenance user check failed: {ex}")
        user = None
    if is_admin(user):
        return None
    return render_template(
        "maintenance.html",
        config=config,
        active_page="maintenance",
        maintenance_mode=True,
    ), 503


@app.before_request
def track_page_visit_before_request():
    record_page_visit()


@app.after_request
def set_visit_cookie(response: Response):
    visitor_id = getattr(g, "set_visit_cookie", "")
    if visitor_id:
        response.set_cookie(VISIT_COOKIE, visitor_id, max_age=60 * 60 * 24 * 365, samesite="Lax")
    return response


def visitor_period(config):
    unit = 'months' if config.get('VISITOR_PERIOD_UNIT') == 'months' else 'days'
    value = parse_int(config.get('VISITOR_PERIOD_VALUE', '7'), 7, 1, 120 if unit == 'months' else 3650)
    return value, unit


def visitor_current_period(config):
    period = config.get('VISITOR_CURRENT_PERIOD', 'month')
    return period if period in {'day', 'week', 'month', 'year', 'ten_days'} else 'month'


def visitor_period_label(config, now=None):
    if config_flag(config, 'VISITOR_CURRENT_ENABLED'):
        now = now or datetime.now()
        period = visitor_current_period(config)
        if period == 'month':
            months = ('Січень', 'Лютий', 'Березень', 'Квітень', 'Травень', 'Червень',
                      'Липень', 'Серпень', 'Вересень', 'Жовтень', 'Листопад', 'Грудень')
            return f'за {months[now.month - 1]}'
        if period == 'year':
            return f'за {now.year} рік'
        return {'day': 'за сьогодні', 'week': 'за поточний тиждень',
                'ten_days': 'за поточні 10 днів'}[period]
    value, unit = visitor_period(config)
    return f"за останні {value} {'міс.' if unit == 'months' else 'дн.'}"


def visitor_period_start(config, now):
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    if config_flag(config, 'VISITOR_CURRENT_ENABLED'):
        period = visitor_current_period(config)
        if period == 'week':
            return midnight - timedelta(days=now.weekday())
        if period == 'month':
            return midnight.replace(day=1)
        if period == 'year':
            return midnight.replace(month=1, day=1)
        if period == 'ten_days':
            return midnight.replace(day=min(21, ((now.day - 1) // 10) * 10 + 1))
        return midnight
    value, unit = visitor_period(config)
    if unit == 'days':
        return now - timedelta(days=value)
    month_index = now.year * 12 + now.month - 1 - value
    year, month = divmod(month_index, 12)
    return now.replace(year=year, month=month + 1,
                       day=min(now.day, calendar.monthrange(year, month + 1)[1]))


def total_visit_count() -> int:
    try:
        if not runtime_state["schema_ready"]:
            ensure_schema()
        with db_cursor() as cur:
            config = load_config()
            now = datetime.now()
            start = visitor_period_start(config, now)
            cur.execute("SELECT COUNT(DISTINCT VisitorKey) AS cnt FROM PageVisits WHERE CreatedAt >= ? AND CreatedAt <= ?", (start, now))
            return int(cur.fetchone()["cnt"])
    except Exception as ex:
        mf.tolog(f"total_visit_count() failed: {ex}")
        return 0


def all_time_visit_count() -> int:
    try:
        if not runtime_state["schema_ready"]:
            ensure_schema()
        with db_cursor() as cur:
            cur.execute("SELECT COUNT(DISTINCT VisitorKey) AS cnt FROM PageVisits WHERE CreatedAt <= datetime('now','localtime')")
            return int(cur.fetchone()["cnt"])
    except Exception as ex:
        mf.tolog(f"all_time_visit_count() failed: {ex}")
        return 0


_visit_summary_cache = {}
_visit_summary_lock = Lock()


def read_visit_summary(now):
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    with db_cursor() as cur:
        cur.execute('''
            SELECT
                COUNT(DISTINCT CASE WHEN CreatedAt >= ? AND CreatedAt < ? THEN VisitorKey END) AS yesterday,
                COUNT(DISTINCT CASE WHEN CreatedAt >= ? THEN VisitorKey END) AS today,
                COUNT(DISTINCT CASE WHEN CreatedAt >= ? THEN VisitorKey END) AS month,
                COUNT(DISTINCT CASE WHEN CreatedAt >= ? THEN VisitorKey END) AS year,
                COUNT(DISTINCT VisitorKey) AS total
            FROM PageVisits WHERE CreatedAt <= ?
        ''', (today - timedelta(days=1), today, today, today.replace(day=1),
              today.replace(month=1, day=1), now))
        result = {key: int(value) for key, value in cur.fetchone().items()}
    return {**result, 'month_number': now.month, 'year_number': now.year}


@app.route('/api/visits/summary')
def visit_summary_api():
    now = datetime.now()
    try:
        with _visit_summary_lock:
            if (_visit_summary_cache.get('day') != now.date()
                    or _visit_summary_cache.get('expires', 0) <= time.monotonic()):
                if not runtime_state['schema_ready']:
                    ensure_schema()
                data = read_visit_summary(now)
                _visit_summary_cache.update(day=now.date(), expires=time.monotonic() + 30, data=data)
            return _visit_summary_cache['data'], 200, {'Cache-Control': 'public, max-age=30'}
    except Exception as ex:
        mf.tolog(f'visit summary failed: {ex}')
        return {'error': 'Статистика тимчасово недоступна'}, 503, {'Cache-Control': 'no-store'}


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


@app.route("/ads.txt")
def ads_txt():
    return send_file(Path(PPath, "ads.txt"), mimetype="text/plain")


@app.route("/robots.txt")
def robots_txt():
    rules = Path(PPath, "robots.txt").read_text(encoding="utf-8")
    return Response(rules.rstrip() + "\n\nSitemap: " + url_for("sitemap_xml", _external=True) + "\n",
                    mimetype="text/plain")


@app.route("/sitemap.xml")
def sitemap_xml():
    pages = pc.read_content().get("pages", {})
    active_sources = pc.active_service_sources(pc.read_content())
    urls = [url_for(endpoint, _external=True) for endpoint in ("index", "services", "about")]
    for path, page in sorted(pages.items()):
        if not path.startswith("/services/") or "/" in path[len("/services/"):] or not path[len("/services/"):]:
            continue
        if page.get("source") and page["source"] not in active_sources:
            continue
        urls.append(url_for("content_page", slug=path[len("/services/"):], _external=True))
    root = ET.Element("urlset", xmlns="http://www.sitemaps.org/schemas/sitemap/0.9")
    for location in dict.fromkeys(urls):
        ET.SubElement(ET.SubElement(root, "url"), "loc").text = location
    return Response(ET.tostring(root, encoding="utf-8", xml_declaration=True), mimetype="application/xml")


@app.route("/")
def index():
    config = load_config()
    online_enabled = config.get("ONLINE_APPOINTMENT_ENABLED", "1").strip().lower() not in {"0", "false", "no", "off"}
    return render_template("index.html", config=config, online_enabled=online_enabled, active_page="home",
                           page=pc.read_content()["pages"]["/"], page_path="/",
                           manager_view=can_manage_services(current_user()) and request.args.get("preview") != "public")


@app.route("/services")
def services():
    content = pc.read_content()
    return render_template("services.html", page=content["pages"]["/services"], page_path="/services",
                           service_sources=pc.active_service_sources(content),
                           manager_view=can_manage_services(current_user()) and request.args.get("preview") != "public",
                           active_page="services")


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
                VALUES (?, ?, ?, ?, ?)
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
                cur.execute("SELECT * FROM Users WHERE Login=?", (login_value,))
                user = cur.fetchone()
                if user and not user.get("IsBlocked") and check_password_hash(user["Pass"], password):
                    sid = os.urandom(16).hex()
                    cur.execute("UPDATE Users SET Last=?, ActiveSessionId=? WHERE Login=?", (datetime.now(), sid, login_value))
                    session["login"] = login_value
                    session["session_id"] = sid
                    log_action("login_success")
                    target = "admin_appointments" if config_flag(load_config(), "ONLINE_APPOINTMENT_ENABLED", "1") else "index"
                    return redirect(url_for(target))
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
                    "UPDATE Users SET ActiveSessionId=NULL WHERE Login=? AND ActiveSessionId=?",
                    (login_value, sid),
                )
        except Exception as ex:
            mf.tolog(f"logout session clear failed: {ex}")
    session.clear()
    return redirect(url_for("index"))


@app.route("/profile", methods=["GET", "POST"])
def profile():
    user = require_user()
    if not isinstance(user, dict):
        return user
    session.setdefault("profile_csrf", uuid.uuid4().hex)
    if request.method == "POST":
        if request.form.get("csrf") != session["profile_csrf"]:
            return "Оновіть сторінку та повторіть збереження.", 400
        password = request.form.get("new_password", "")
        if password and (len(password) < 5 or password != request.form.get("confirm_password", "")):
            flash("Новий пароль має містити щонайменше 5 символів, а підтвердження — збігатися.", "error")
            return redirect(url_for("profile"))
        try:
            with db_cursor(commit=True) as cur:
                cur.execute("SELECT FullName, Email, AvatarUrl, Pass FROM Users WHERE Login=?", (user["Login"],))
                previous = cur.fetchone()
                if not previous:
                    return "Користувача не знайдено.", 404
                if password and not check_password_hash(previous["Pass"], request.form.get("current_password", "")):
                    flash("Поточний пароль неправильний.", "error")
                    return redirect(url_for("profile"))
                avatar = previous.get("AvatarUrl") or ""
                if request.form.get("remove_avatar") == "1":
                    avatar = ""
                upload = request.files.get("avatar_file")
                if upload and upload.filename:
                    avatar_upload = uploaded_service_image_url("avatar_file")
                    if not avatar_upload:
                        return redirect(url_for("profile"))
                    avatar = avatar_upload
                name = request.form.get("full_name", "")
                email = request.form.get("email", "")
                cur.execute("UPDATE Users SET FullName=?, Email=?, AvatarUrl=? WHERE Login=?",
                            (name, email, avatar or None, user["Login"]))
                new_sid = uuid.uuid4().hex if password else None
                if password:
                    cur.execute("UPDATE Users SET Pass=?, ActiveSessionId=? WHERE Login=?",
                                (generate_password_hash(password), new_sid, user["Login"]))
            if new_sid:
                session["session_id"] = new_sid
            changes = {key: {"old": previous.get(key) or "", "new": value} for key, value in
                       (("FullName", name), ("Email", email), ("AvatarUrl", avatar)) if (previous.get(key) or "") != value}
            if password:
                changes["password_changed"] = True
            log_action("profile_update", json.dumps(changes, ensure_ascii=False))
            flash("Профіль збережено.", "success")
        except Exception as ex:
            _report_critical_error("profile update failed", ex)
            flash("Не вдалося зберегти профіль.", "error")
        return redirect(url_for("profile"))
    return render_template("profile.html", profile=user, csrf=session["profile_csrf"], active_page="profile")


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
                "SELECT * FROM Appointments WHERE VisitAt >= ? AND VisitAt < ? ORDER BY VisitAt",
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
                WHERE CreatedAt >= ? AND CreatedAt < ?
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
    if active_tab not in {"maintenance", "email", "tg", "html", "alert", "users"}:
        active_tab = "maintenance"
    if request.method == "POST":
        action = request.form.get("action", "save")
        form_config = config.copy()
        form_config["SITE_MAINTENANCE_ENABLED"] = "1" if "cfg_SITE_MAINTENANCE_ENABLED" in request.form else "0"
        form_config["VISITOR_CURRENT_ENABLED"] = "1" if "cfg_VISITOR_CURRENT_ENABLED" in request.form else "0"
        for key in list(form_config.keys()):
            field = f"cfg_{key}"
            if field in request.form:
                value = request.form.get(field, "").strip()
                if key in {"SMTP_PASSWORD"} and not value:
                    continue
                form_config[key] = value
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
    if active_tab == "users":
        return redirect(url_for("users"))
    session.setdefault("code_csrf", uuid.uuid4().hex)
    return render_template("settings.html", config=config, active_tab=active_tab, active_page="settings",
                           code=pc.read_content().get("global_code", {}), csrf=session["code_csrf"])


@app.route("/users")
def users_legacy():
    return redirect(url_for("users"))


@app.route("/settings/users", methods=["GET", "POST"])
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
                    "INSERT INTO Users (Login, FullName, Email, Pass, Role) VALUES (?, ?, ?, ?, ?)",
                    (login_value, full_name, email or None, generate_password_hash(password), role),
                )
            log_action("user_create", login_value)
            flash("Користувача створено.", "success")
        except Exception as ex:
            if isinstance(ex, sqlite3.IntegrityError):
                flash("Такий логін вже існує.", "error")
            else:
                _report_critical_error("user create failed", ex)
                flash(str(ex), "error")
        return redirect(url_for("users"))
    with db_cursor() as cur:
        cur.execute("SELECT Login, FullName, Email, Role, IsBlocked, Last, CreatedAt FROM Users ORDER BY Login")
        rows = cur.fetchall()
    return render_template("users.html", users=rows, active_page="settings")


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
            cur.execute("DELETE FROM Users WHERE Login=?", (login_value,))
            log_action("user_delete", login_value)
        elif action == "block":
            cur.execute("UPDATE Users SET IsBlocked=TRUE, ActiveSessionId=NULL WHERE Login=?", (login_value,))
            log_action("user_block", login_value)
        elif action == "unblock":
            cur.execute("UPDATE Users SET IsBlocked=FALSE WHERE Login=?", (login_value,))
            log_action("user_unblock", login_value)
        elif action == "password":
            password = request.form.get("password", "")
            if len(password) < 5:
                flash("Пароль має бути мінімум 5 символів.", "error")
                return redirect(url_for("users"))
            cur.execute("UPDATE Users SET Pass=?, ActiveSessionId=NULL WHERE Login=?", (generate_password_hash(password), login_value))
            log_action("user_password_change", login_value)
        elif action == "role":
            role = "admin" if request.form.get("role") == "admin" else "manager"
            if login_value == session.get("login") and role != "admin":
                flash("Не можна забрати адмінські права у себе.", "error")
                return redirect(url_for("users"))
            cur.execute("UPDATE Users SET Role=? WHERE Login=?", (role, login_value))
            log_action("user_role_change", f"{login_value} -> {role}")
    flash("Готово.", "success")
    return redirect(url_for("users"))


def log_period(args, now=None):
    today = (now or datetime.now()).date()
    mode = args.get('period', 'today')
    if 'date' in args and 'period' not in args:
        day = datetime.strptime(args['date'], '%Y-%m-%d').date()
        return day, day, 'custom'
    if mode == 'today':
        return today, today, mode
    if mode == 'yesterday':
        day = today - timedelta(days=1)
        return day, day, mode
    if mode == 'month':
        month = datetime.strptime(args.get('month', today.strftime('%Y-%m')), '%Y-%m').date()
        return month, month.replace(day=calendar.monthrange(month.year, month.month)[1]), mode
    if mode != 'custom':
        raise ValueError('Оберіть період.')
    start = datetime.strptime(args.get('start_date', ''), '%Y-%m-%d').date()
    end = datetime.strptime(args.get('end_date', ''), '%Y-%m-%d').date()
    if end < start or (end - start).days > 3660:
        raise ValueError('Оберіть коректний період до 10 років.')
    return start, end, mode


@app.route("/logs")
def logs():
    user = require_admin()
    if not isinstance(user, dict):
        return user
    try:
        start, end, mode = log_period(request.args)
    except ValueError:
        return "Некоректний діапазон дат", 400
    rows = []
    day = start
    while day <= end:
        rows.extend(load_journal(day.isoformat()))
        day += timedelta(days=1)
    today = datetime.now().date()
    filename = sl.log_path(PPath, start.isoformat()).name if start == end else f"{sl.log_path(PPath, start.isoformat()).name} … {sl.log_path(PPath, end.isoformat()).name}"
    return render_template("logs.html", journal=sorted(rows, key=lambda row: row['Час'], reverse=True),
                           period=mode, today=today.isoformat(), yesterday=(today - timedelta(days=1)).isoformat(),
                           month=start.strftime('%Y-%m'), start_date=start.isoformat(), end_date=end.isoformat(),
                           filename=filename, active_page="logs")


def load_journal(day):
    path = sl.log_path(PPath, day)
    legacy = Path(PPath) / 'logs' / f'{day}.log'
    history = []
    if legacy.exists() or not path.exists():
        start = datetime.strptime(day, '%Y-%m-%d')
        try:
            with db_cursor() as cur:
                cur.execute('SELECT CreatedAt, Actor, Action, Details, Ip FROM AuditLog WHERE CreatedAt >= ? AND CreatedAt < ? ORDER BY CreatedAt',
                            (start, start + timedelta(days=1)))
                for row in cur.fetchall():
                    history.append(dict(zip(sl.FIELDS, (row['CreatedAt'].strftime('%Y/%m/%d %H:%M:%S'), row['Actor'], row['Action'], row['Details'] or '', row['Ip'] or ''))))
        except Exception:
            # Legacy text remains readable even if the old DB is unavailable.
            pass
        history.extend(sl.legacy_rows(legacy))
    return sl.merge_history(PPath, day, history)


@app.route("/logs/download/range")
def logs_download_range():
    user = require_admin()
    if not isinstance(user, dict):
        return user
    try:
        args = request.args.to_dict()
        args.setdefault('period', 'custom')
        start_date, end_date, _ = log_period(args)
    except ValueError:
        return "Некоректний діапазон дат", 400
    start_raw, end_raw = start_date.isoformat(), end_date.isoformat()
    mem = io.BytesIO()
    with zipfile.ZipFile(mem, "w", zipfile.ZIP_DEFLATED) as zf:
        current = start_date
        while current <= end_date:
            name = current.strftime("%Y-%m-%d")
            load_journal(name)
            path = sl.log_path(PPath, name)
            if path.exists():
                with sl.locked(path):
                    zf.write(path, arcname=path.name)
            current += timedelta(days=1)
    mem.seek(0)
    return send_file(mem, as_attachment=True, download_name=f"LadySite_logs_{start_raw}_{end_raw}.zip", mimetype="application/zip")


@app.route("/services/<slug>")
def content_page(slug):
    path = "/services/" + slug
    content = pc.read_content()
    page = content.get("pages", {}).get(path)
    if page is None:
        return "Сторінку не знайдено", 404
    manager_view = can_manage_services(current_user()) and request.args.get("preview") != "public"
    source = page.get("source")
    if source and not manager_view and source not in pc.active_service_sources(content):
        return "Сторінку не знайдено", 404
    return render_template("content_page.html", page=page, page_path=path,
                           manager_view=manager_view, active_page="services")


@app.route("/content/save", methods=["POST"])
def content_save():
    user = require_user()
    if not isinstance(user, dict):
        return user
    if not can_manage_services(user):
        return "Недостатньо прав", 403
    if not session.get("content_csrf") or request.form.get("csrf") != session["content_csrf"]:
        return {"error": "Оновіть сторінку та повторіть збереження."}, 400
    path = request.form.get("page_path", "")
    if path not in pc.read_content().get("pages", {}):
        return "Сторінку не знайдено", 404
    try:
        blocks = pc.normalize_blocks(json.loads(request.form.get("blocks", "[]")))
        shared_blocks = pc.normalize_blocks(json.loads(request.form["site_blocks"])) if "site_blocks" in request.form else None
        site_background = pc.background(json.loads(request.form["site_background"])) if "site_background" in request.form else None
        title = request.form.get("page_title", "").strip()[:250]
        if not title:
            raise ValueError("Назва сторінки обов’язкова.")
        menu = pc.normalize_menu(json.loads(request.form["menu"])) if path in {"/", "/services"} and "menu" in request.form else None
        def change(content):
            content["pages"][path].update(title=title, blocks=blocks)
            if menu is not None:
                content["pages"][path]["menu"] = menu
            if shared_blocks is not None:
                content["site_blocks"] = shared_blocks
            if site_background is not None:
                content["site_background"] = site_background
            if "logotext" in request.form:
                content["pages"][path]["logotext"] = pc.element(json.loads(request.form["logotext"]))
        pc.update_content(change)
    except (ValueError, TypeError, KeyError) as ex:
        return {"error": str(ex)}, 400
    log_action("page_update", path)
    return {"ok": True, "url": path}


@app.route("/content/image", methods=["POST"])
def content_image():
    user = require_user()
    if not isinstance(user, dict):
        return user
    if not can_manage_services(user):
        return "Недостатньо прав", 403
    if not session.get("content_csrf") or request.form.get("csrf") != session["content_csrf"]:
        return {"error": "Оновіть сторінку та повторіть завантаження."}, 400
    image = uploaded_service_image_url()
    if not image:
        return {"error": "Оберіть файл PNG, JPEG, WebP або GIF."}, 400
    return {"url": image}


@app.route("/settings/contacts", methods=["POST"])
def site_contacts_settings():
    user = require_admin()
    if not isinstance(user, dict):
        return user
    if not session.get("content_csrf") or request.form.get("csrf") != session["content_csrf"]:
        return "Оновіть сторінку та повторіть збереження", 400
    try:
        values = pc.contact_settings(pc.read_content(), load_config())
        values.update({key: request.form[key] for key in pc.CONTACT_DEFAULTS if key in request.form})
        for key in ("telegram", "facebook", "instagram", "tiktok", "youtube", "map_url", "map_embed_url"):
            values[key] = pc.safe_url(request.form.get(key, values.get(key, "")))
            if values[key] and not values[key].startswith(("https://", "http://")):
                raise ValueError("Вкажіть посилання http:// або https://.")
        pc.update_content(lambda content: content.update(contacts=values))
    except ValueError as ex:
        return str(ex), 400
    log_action("site_contacts_update", "contacts, address, hours, social links")
    flash("Контакти збережено.", "success")
    return redirect(url_for("settings", tab="contacts"))


@app.route("/settings/code", methods=["GET", "POST"])
def site_code_settings():
    user = require_admin()
    if not isinstance(user, dict):
        return user
    session.setdefault("code_csrf", uuid.uuid4().hex)
    if request.method == "POST":
        if request.form.get("csrf") != session["code_csrf"]:
            return "Оновіть сторінку та повторіть збереження", 400
        code = {key: request.form.get(key, "") for key in ("head", "body_end")}
        if any(len(value) > 100000 for value in code.values()):
            return "Код перевищує 100 000 символів", 400
        pc.update_content(lambda content: content.update(global_code=code))
        log_action("site_code_update", "head, body_end")
        flash("Код для всіх сторінок збережено.", "success")
        return redirect(url_for("settings", tab="html"))
    return render_template("site_code.html", code=pc.read_content().get("global_code", {}),
                           csrf=session["code_csrf"], active_page="settings")


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
