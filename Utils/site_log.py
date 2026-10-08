"""Daily CSV journal with serialized writes and lossless legacy import."""
import csv
import os
import re
import socket
import tempfile
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from threading import RLock

FIELDS = ('Час', 'Користувач', 'Дія', 'Деталі', 'IP')
_mutex = RLock()


def log_path(root, day):
    return Path(root) / 'logs' / f'Lady_{day}_log.csv'


@contextmanager
def locked(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with _mutex, open(str(path) + '.lock', 'a+b') as handle:
        if os.name == 'nt':
            import msvcrt
            if not handle.tell():
                handle.write(b'0')
                handle.flush()
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl
            fcntl.flock(handle, fcntl.LOCK_EX)
        try:
            yield
        finally:
            if os.name == 'nt':
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle, fcntl.LOCK_UN)


def read_rows(path):
    if not path.exists():
        return []
    with path.open(encoding='utf-8-sig', newline='') as source:
        return list(csv.DictReader(source))


def write_event(root, action, details='', actor='Я (сайт)', ip='', when=None):
    now = when or datetime.now()
    path = log_path(root, now.strftime('%Y-%m-%d'))
    with locked(path):
        fresh = not path.exists() or path.stat().st_size == 0
        with path.open('a', encoding='utf-8-sig' if fresh else 'utf-8', newline='') as target:
            writer = csv.writer(target)
            if fresh:
                writer.writerow(FIELDS)
            writer.writerow((now.strftime('%Y/%m/%d %H:%M:%S'), actor, action, details, ip))
            target.flush()
    return path


def system_ip():
    try:
        return socket.gethostbyname(socket.gethostname())
    except OSError:
        return ''


def action_from_message(message):
    return message.split(':', 1)[0].split('\n', 1)[0]


def legacy_rows(path):
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding='utf-8', errors='replace').splitlines():
        match = re.match(r'^(\d{4}/\d{2}/\d{2} \d{2}:\d{2}:\d{2}) (.*)$', line)
        if not match:
            if rows:
                rows[-1]['Деталі'] += '\n' + line
            elif line:
                rows.append(dict(zip(FIELDS, ('', 'Я (сайт)', 'Повідомлення', line, ''))))
            continue
        when, message = match.groups()
        audit = re.match(r'^AUDIT action=(.*?) actor=(.*?) ip=(.*?) details=(.*)$', message)
        if audit:
            action, actor, ip, details = audit.groups()
        else:
            action, actor, ip, details = action_from_message(message), 'Я (сайт)', '', message
        rows.append(dict(zip(FIELDS, (when, actor, action, details, ip))))
    return rows


def merge_history(root, day, incoming):
    path = log_path(root, day)
    if not incoming and not path.exists():
        return []
    with locked(path):
        rows = read_rows(path)
        # The old text audit truncated details to 1000 characters. Prefer full DB rows.
        def key(row):
            return tuple(str(row.get(field, ''))[:1000] if field == 'Деталі' else str(row.get(field, '')) for field in FIELDS)
        positions = {key(row): index for index, row in enumerate(rows)}
        changed = False
        for row in incoming:
            identity = key(row)
            if identity not in positions:
                positions[identity] = len(rows)
                rows.append(row)
                changed = True
            elif len(row.get('Деталі', '')) > len(rows[positions[identity]].get('Деталі', '')):
                rows[positions[identity]] = row
                changed = True
        if changed:
            rows.sort(key=lambda row: row['Час'])
            fd, name = tempfile.mkstemp(dir=path.parent, prefix='journal-', suffix='.tmp')
            try:
                with os.fdopen(fd, 'w', encoding='utf-8-sig', newline='') as target:
                    writer = csv.DictWriter(target, fieldnames=FIELDS)
                    writer.writeheader()
                    writer.writerows(rows)
                    target.flush()
                    os.fsync(target.fileno())
                os.replace(name, path)
            finally:
                if os.path.exists(name):
                    os.unlink(name)
        return rows
