"""File-backed page map. Reads on every request; serialized atomic updates."""
import copy
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
ANIMATIONS = {'none', 'random', 'ShortBackLighting', 'Flowers', 'Sparkles', 'SoftPulse', 'Rainbow'}


def background(raw):
    if not isinstance(raw, dict):
        raise ValueError('Некоректний фон.')
    color = str(raw.get('color', '')).strip()
    if color and color != 'transparent' and not re.fullmatch(r'#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})', color):
        raise ValueError('Колір фону: #RGB, #RRGGBB, #RRGGBBAA або transparent.')
    image = safe_url(raw.get('image'))
    if image and not (image.startswith('/') or urlsplit(image).scheme in {'http', 'https'}):
        raise ValueError('Малюнок фону має бути URL або локальним шляхом.')
    return {'color': color, 'image': image,
            'mode': raw.get('mode') if raw.get('mode') in {'tile', 'cover', 'contain', 'stretch', 'normal'} else 'tile',
            'align': raw.get('align') if raw.get('align') in {'left', 'center', 'right'} else 'center',
            'vertical': raw.get('vertical') if raw.get('vertical') in {'top', 'center', 'bottom'} else 'top',
            'attachment': 'fixed' if raw.get('attachment') == 'fixed' else 'scroll'}


def block_background(block):
    result = block.get('background', {})
    def visit(nodes):
        nonlocal result
        for node in nodes:
            if node['kind'] == 'background':
                result = node['value']
            elif node['kind'] == 'group':
                visit(node['nodes'])
    visit(block.get('nodes', []))
    return result


def normalize_nodes(raw, depth=0):
    if not isinstance(raw, list) or len(raw) > 100 or depth > 5:
        raise ValueError('Дозволено до 100 нод на рівні та до 5 рівнів вкладення.')
    result = []
    for node in raw:
        kind = node.get('kind') if isinstance(node, dict) else None
        if kind not in {'group', 'heading', 'image', 'title', 'text', 'button', 'carousel', 'animation', 'map', 'social', 'background'}:
            raise ValueError('Невідомий тип ноди.')
        value = {'kind': kind, 'name': str(node.get('name', ''))}
        if kind == 'group':
            value['nodes'] = normalize_nodes(node.get('nodes', []), depth + 1)
        elif kind in {'heading', 'title', 'text', 'button'}:
            value['value'] = element(node.get('value', {}))
        elif kind == 'image':
            image = safe_url(node.get('image'))
            if image and not (image.startswith('/') or urlsplit(image).scheme in {'http', 'https'}):
                raise ValueError('Малюнок має бути URL або локальним шляхом /static/…')
            value.update(image=image, alt=str(node.get('alt', '')),
                         image_mode=node.get('image_mode') if node.get('image_mode') in IMAGE_MODES else 'normal',
                         image_align=node.get('image_align') if node.get('image_align') in {'left', 'center', 'right'} else 'center',
                         image_vertical=node.get('image_vertical') if node.get('image_vertical') in {'top', 'center', 'bottom'} else 'center')
        elif kind == 'carousel':
            value['nodes'] = normalize_nodes(node.get('nodes', []), depth + 1)
            if any(child['kind'] != 'image' for child in value['nodes']):
                raise ValueError('Карусель містить лише малюнки.')
        elif kind == 'map':
            value.update(url=safe_url(node.get('url')), title=str(node.get('title', 'Мапа салону')))
            if value['url'] and urlsplit(value['url']).scheme not in {'http', 'https'}:
                raise ValueError('Мапа має бути посиланням http:// або https://.')
        elif kind == 'background':
            value['value'] = background(node.get('value', {}))
        elif kind == 'social':
            value['value'] = element(node.get('value', {}))
            if 'links' in node:
                value['links'] = {key: safe_url(node['links'].get(key, '')) for key in ('telegram', 'facebook', 'instagram', 'tiktok', 'youtube')}
        else:
            effect = node.get('effect', 'random')
            value['effect'] = effect if effect in ANIMATIONS else 'none'
        result.append(value)
    return result


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
        if 'nodes' in block:
            normalized['nodes'] = normalize_nodes(block['nodes'])
        if 'background' in block:
            normalized['background'] = background(block['background'])
        for item in items:
            if not isinstance(item, dict):
                raise ValueError('Некоректна колонка.')
            image = safe_url(item.get('image'))
            if image and not (image.startswith('/') or urlsplit(image).scheme in {'http', 'https'}):
                raise ValueError('Малюнок має бути URL або локальним шляхом /static/…')
            normalized['items'].append({'name': str(item.get('name', '')), 'image': image, 'alt': str(item.get('alt', ''))[:500],
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


CONTACT_DEFAULTS = {
    'address': "Кам’янець-Подільський, вул. Лесі Українки, 41",
    'comment': 'На території дитячої поліклініки.',
    'phone': '+38 093 299-59-21', 'email': '',
    'hours': 'Пн–Пт: 09:00–17:00\nСб: 09:00–13:00\nНд: вихідний',
    'telegram': '', 'facebook': 'https://www.facebook.com/profile.php?id=61581148067506', 'instagram': '', 'tiktok': '', 'youtube': '',
    'note': 'Інформація про салон поступово доповнюється.'
}


def contact_settings(content, config):
    result = {**CONTACT_DEFAULTS, **content.get('contacts', {})}
    result.setdefault('map_url', config.get('MAP_URL', ''))
    result.setdefault('map_embed_url', config.get('MAP_EMBED_URL', ''))
    return result


def has_visible_nodes(nodes):
    for node in nodes:
        kind = node['kind']
        if kind in {'group', 'carousel'} and has_visible_nodes(node['nodes']):
            return True
        if kind == 'map' and node.get('url'):
            return True
        if kind == 'social':
            return True
        if kind == 'image' and node.get('image'):
            return True
        if kind in {'heading', 'title', 'text', 'button'} and node['value'].get('text'):
            return True
    return False


DISCLAIMER = ("Інформація, розміщена на сайті, призначена тільки для ознайомлювальних цілей.\n"
              "Якщо у вас виникла проблема зі здоров'ям, зверніться до сімейного лікаря.")


def site_blocks(content, config):
    # Missing key is the one-time legacy fallback; an explicit empty list stays empty.
    if 'site_blocks' in content:
        blocks = copy.deepcopy(content['site_blocks'])
        contacts = contact_settings(content, config)
        def migrate(nodes):
            for node in nodes:
                if node['kind'] == 'group':
                    migrate(node['nodes'])
                elif node['kind'] == 'social' and 'links' not in node:
                    node['links'] = {key: contacts[key] for key in ('telegram', 'facebook', 'instagram', 'tiktok', 'youtube')}
                    if not node['links']['facebook']:
                        node['links']['facebook'] = CONTACT_DEFAULTS['facebook']
        for block in blocks:
            migrate(block.get('nodes', []))
        return blocks
    contacts = contact_settings(content, config)
    def text(kind, value, name='', **style):
        return {'kind': kind, 'name': name, 'value': {'text': value, **style}}
    address = {'note': 'Адреса салону та графік роботи', 'layout': 'text-image', 'nodes': [
        text('heading', 'Адреса салону та графік роботи', size=28),
        {'kind':'group', 'nodes':[
            {'kind':'group', 'nodes':[
                text('text', contacts['address'], name='Адреса салону', bold=True),
                text('text', contacts['comment'], name='Коментар до адреси'),
                text('title', 'Графік роботи', size=22),
                text('text', contacts['hours'], name='Графік роботи'),
                text('button', 'Відкрити в Google Maps', url=contacts['map_url'])]},
            {'kind':'map', 'name':'Google-мапа', 'url': contacts['map_embed_url'], 'title':'Адреса салону на Google Maps'}]}]}
    contact_nodes = [text('heading', 'Контакти:', size=24)]
    if contacts['phone']:
        contact_nodes.append(text('text', contacts['phone'], name='Телефон', url='tel:' + contacts['phone'].replace(' ', '')))
    if contacts['email']:
        contact_nodes.append(text('text', contacts['email'], name='Email', url='mailto:' + contacts['email']))
    contact_nodes.append({'kind':'social', 'value': {'text':'Ми у соціальних мережах', 'align':'left'}})
    if contacts['note']:
        contact_nodes.append(text('text', contacts['note'], name='Примітка контактів', size=14))
    footer = {'note':'Контакти', 'layout':'text', 'background':{'color':'#f7efe7'}, 'nodes':contact_nodes}
    disclaimer = {'note':'Інформація для відвідувачів', 'layout':'text', 'nodes':[
        text('text', DISCLAIMER, name='Інформація для відвідувачів', align='center', size=14)]}
    return normalize_blocks([address, footer, disclaimer])
