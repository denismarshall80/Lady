"""SQLite connections and schema; no external database service is required."""
import sqlite3
from datetime import datetime
from pathlib import Path


sqlite3.register_adapter(datetime, lambda value: value.isoformat(' '))
sqlite3.register_converter('DATETIME', lambda value: datetime.fromisoformat(value.decode()))


def connect(path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=15, detect_types=sqlite3.PARSE_DECLTYPES)
    conn.row_factory = lambda cursor, row: dict(zip((col[0] for col in cursor.description), row))
    conn.execute('PRAGMA foreign_keys=ON')
    conn.execute('PRAGMA busy_timeout=15000')
    return conn


def initialize(conn):
    conn.execute('PRAGMA journal_mode=WAL')
    conn.executescript('''
        CREATE TABLE IF NOT EXISTS Users (
            Login TEXT PRIMARY KEY, FullName TEXT, Email TEXT, AvatarUrl TEXT,
            Pass TEXT NOT NULL, Role TEXT NOT NULL DEFAULT 'manager' CHECK(Role IN ('admin','manager')),
            IsBlocked INTEGER NOT NULL DEFAULT 0, Last DATETIME, ActiveSessionId TEXT,
            CreatedAt DATETIME NOT NULL DEFAULT (datetime('now','localtime')),
            UpdatedAt DATETIME NOT NULL DEFAULT (datetime('now','localtime'))
        );
        CREATE TABLE IF NOT EXISTS Appointments (
            Id INTEGER PRIMARY KEY AUTOINCREMENT, VisitAt DATETIME NOT NULL,
            ClientName TEXT NOT NULL, VisitPurpose TEXT NOT NULL, Phone TEXT, Email TEXT,
            create_at DATETIME NOT NULL DEFAULT (datetime('now','localtime')),
            updated_at DATETIME NOT NULL DEFAULT (datetime('now','localtime')),
            SendNow INTEGER NOT NULL DEFAULT 0, SendBeforeCl INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS PageVisits (
            Id INTEGER PRIMARY KEY AUTOINCREMENT, VisitorKey TEXT NOT NULL,
            Path TEXT NOT NULL, Endpoint TEXT, UserAgent TEXT,
            CreatedAt DATETIME NOT NULL DEFAULT (datetime('now','localtime'))
        );
        CREATE TABLE IF NOT EXISTS AuditLog (
            Id INTEGER PRIMARY KEY AUTOINCREMENT, CreatedAt DATETIME NOT NULL,
            Actor TEXT, Action TEXT, Details TEXT, Ip TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_visit_at ON Appointments(VisitAt);
        CREATE INDEX IF NOT EXISTS idx_send_now ON Appointments(SendNow);
        CREATE INDEX IF NOT EXISTS idx_send_before ON Appointments(SendBeforeCl);
        CREATE INDEX IF NOT EXISTS idx_page_visits_created ON PageVisits(CreatedAt);
        CREATE INDEX IF NOT EXISTS idx_page_visits_visitor_day ON PageVisits(VisitorKey, CreatedAt);
        CREATE TRIGGER IF NOT EXISTS users_updated AFTER UPDATE ON Users
        BEGIN UPDATE Users SET UpdatedAt=datetime('now','localtime') WHERE Login=NEW.Login; END;
        CREATE TRIGGER IF NOT EXISTS appointments_updated AFTER UPDATE ON Appointments
        BEGIN UPDATE Appointments SET updated_at=datetime('now','localtime') WHERE Id=NEW.Id; END;
    ''')
