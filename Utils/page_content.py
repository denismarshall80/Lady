"""File-backed page map. Reads on every request; serialized atomic updates."""
import json
import os
import re
import tempfile
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
CONTENT_PATH = ROOT / 'DATA' / 'pages.json'
DEFAULT_CODE = '<script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=ca-pub-2294227136369675" crossorigin="anonymous"></script>'
FONTS = {'Arial', 'Georgia', 'Verdana', 'Tahoma', 'Times New Roman'}
LAYOUTS = {'text-image', 'image-text', 'text', 'image', 'columns'}
IMAGE_MODES = {'normal', 'stretch', 'tile', 'cover'}


def read_content():
    if CONTENT_PATH.exists():
        with CONTENT_PATH.open(encoding='utf-8') as source:
            return json.load(source)
    with (ROOT / 'default_pages.json').open(encoding='utf-8') as source:
        return json.load(source)


@contextmanager
def content_lock():
    CONTENT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(str(CONTENT_PATH) + '.lock', 'a+b') as lock:
        lock.seek(0)
        if os.name == 'nt':
            import msvcrt
            if not lock.read(1):
                lock.write(b'0')
                lock.flush()
            lock.seek(0)
            msvcrt.locking(lock.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl
            fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            yield
        finally:
            if os.name == 'nt':
                lock.seek(0)
                msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(lock, fcntl.LOCK_UN)


def update_content(change):
    with content_lock():
        content = read_content()
        result = change(content)
        fd, name = tempfile.mkstemp(dir=CONTENT_PATH.parent, prefix='pages-', suffix='.tmp')
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as target:
                json.dump(content, target, ensure_ascii=False, indent=2)
                target.write('\n')
                target.flush()
                os.fsync(target.fileno())
            os.replace(name, CONTENT_PATH)
        finally:
            if os.path.exists(name):
                os.unlink(name)
        return result


def safe_url(value):
    value = str(value or '').strip()
    if any(ord(char) < 32 for char in value) or '\\' in value:
        raise ValueError('Некоректне посилання.')
    parts = urlsplit(value)
    if value and not ((value.startswith('/') and not value.startswith('//')) or value.startswith('#') or (parts.scheme in {'http', 'https', 'tel', 'mailto'})):
        raise ValueError('Посилання має починатися з /, #, https://, http://, tel: або mailto:.')
    return value


def element(raw):
    if not isinstance(raw, dict):
        raise ValueError('Некоректний елемент блоку.')
    size = int(raw.get('size', 18))
    return {'text': str(raw.get('text', ''))[:20000], 'url': safe_url(raw.get('url')),
            'font': raw.get('font') if raw.get('font') in FONTS else 'Arial',
            'size': max(10, min(96, size)), 'bold': bool(raw.get('bold')),
            'italic': bool(raw.get('italic')), 'underline': bool(raw.get('underline')),
            'align': raw.get('align') if raw.get('align') in {'left', 'center', 'right'} else 'left',
            'vertical': raw.get('vertical') if raw.get('vertical') in {'top', 'center', 'bottom'} else 'top'}


def normalize_blocks(raw):
    if not isinstance(raw, list) or len(raw) > 100:
        raise ValueError('Дозволено до 100 блоків.')
    blocks = []
    for block in raw:
        if not isinstance(block, dict) or block.get('layout') not in LAYOUTS:
            raise ValueError('Оберіть тип блоку.')
        items = block.get('items', [])
        if not isinstance(items, list) or len(items) > 12:
            raise ValueError('Дозволено до 12 колонок у блоці.')
        normalized = {'note': str(block.get('note', '')), 'layout': block['layout'], 'heading': element(block.get('heading', {})),
                      'items': [], 'enabled': block.get('enabled', True) is not False}
        for item in items:
            if not isinstance(item, dict):
                raise ValueError('Некоректна колонка.')
            image = safe_url(item.get('image'))
            if image and not (image.startswith('/') or urlsplit(image).scheme in {'http', 'https'}):
                raise ValueError('Малюнок має бути URL або локальним шляхом /static/…')
            normalized['items'].append({'image': image, 'alt': str(item.get('alt', ''))[:500],
                'image_mode': item.get('image_mode') if item.get('image_mode') in IMAGE_MODES else 'normal',
                'image_align': item.get('image_align') if item.get('image_align') in {'left', 'center', 'right'} else 'center',
                'image_vertical': item.get('image_vertical') if item.get('image_vertical') in {'top', 'center', 'bottom'} else 'center',
                **{key: element(item.get(key, {})) for key in ('title', 'text', 'button')}})
        blocks.append(normalized)
    return blocks


def slugify(title):
    alphabet = dict(zip('абвгґдеєжзиіїйклмнопрстуфхцчшщьюя',
                        ['a','b','v','g','g','d','e','ye','zh','z','i','i','yi','y','k','l','m','n','o','p','r','s','t','u','f','kh','ts','ch','sh','shch','','yu','ya']))
    text = ''.join(alphabet.get(char, char) for char in title.lower())
    return re.sub(r'[^a-z0-9]+', '-', text).strip('-') or 'page'


def save_service_metadata(kind, item_id, title, description, form):
    key = f'{kind}-{item_id}'
    link = safe_url(form.get('title_url', ''))
    def change(content):
        metadata = content.setdefault('services', {}).setdefault(key, {})
        metadata['title_url'] = link
        if kind == 'section':
            metadata['image_position'] = 'right' if form.get('image_position') == 'right' else 'left'
        if form.get('page_action') == 'open':
            path = metadata.get('page_path')
            if not path or path not in content['pages']:
                base = '/services/' + slugify(title)
                path = base
                number = 2
                while path in content['pages'] or path in {'/services/intro', '/services/section', '/services/card'}:
                    path = f'{base}-{number}'
                    number += 1
                content['pages'][path] = {'title': title, 'blocks': normalize_blocks([
                    {'layout': 'text', 'heading': {'text': title, 'size': 34},
                     'items': [{'text': {'text': description}}]}]), 'source': key}
                metadata['page_path'] = path
            metadata['title_url'] = path
            return path
        return None
    return update_content(change)
