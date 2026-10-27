"""Import a read-only JSON database export into a NEW SQLite file and JSON pages.

Run with: python -m Utils.migrate_storage DATA/migration-backup-.../mysql-export.json
Existing SQLite files are never overwritten. Keep the export and pages backup.
"""
import argparse
import json
from pathlib import Path

from Utils import database, page_content as pc


def import_database(snapshot, target):
    target = Path(target)
    if target.exists():
        raise ValueError('SQLite database already exists; refusing to overwrite it.')
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix('.importing')
    if temporary.exists():
        raise ValueError('An unfinished import exists; inspect it before retrying.')
    conn = database.connect(temporary)
    try:
        database.initialize(conn)
        conn.execute('BEGIN IMMEDIATE')
        # These tables are retained only as an archive of the original service records.
        for table, rows in snapshot.items():
            if not table.replace('_', '').isalnum():
                raise ValueError('Invalid table name')
            columns = list(rows[0]) if rows else []
            exists = conn.execute('SELECT 1 FROM sqlite_master WHERE type=? AND name=?', ('table', table)).fetchone()
            if not exists and columns:
                definitions = ', '.join('"' + name.replace('"', '""') + '" ' +
                                        ('INTEGER' if isinstance(rows[0][name], (int, bool)) else 'TEXT')
                                        for name in columns)
                conn.execute(f'CREATE TABLE "{table}" ({definitions})')
            if rows:
                names = ', '.join('"' + name.replace('"', '""') + '"' for name in columns)
                conn.executemany(f'INSERT INTO "{table}" ({names}) VALUES ({", ".join("?" for _ in columns)})',
                                 [tuple(row[name] for name in columns) for row in rows])
                copied = conn.execute(f'SELECT COUNT(*) AS n FROM "{table}"').fetchone()['n']
                if copied != len(rows):
                    raise ValueError(f'Count mismatch: {table}')
        if conn.execute('PRAGMA integrity_check').fetchone()['integrity_check'] != 'ok':
            raise ValueError('SQLite integrity check failed')
        conn.commit()
        conn.execute('PRAGMA wal_checkpoint(TRUNCATE)')
        conn.execute('PRAGMA journal_mode=DELETE')
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    # Exclusive creation protects an existing target, including concurrent imports.
    with target.open('xb') as output, temporary.open('rb') as source:
        import shutil
        shutil.copyfileobj(source, output)
    temporary.unlink()


def service_page(snapshot, content, intro=''):
    metadata = content.get('services', {})
    blocks = [{'layout': 'text', 'heading': {'text': 'Послуги і ціни', 'size': 34},
               'items': [{'text': {'text': intro}}]}]
    menu = []

    def text(kind, value, size=18, url=''):
        return {'kind': kind, 'value': {'text': value or '', 'size': size, 'url': url}}

    def item_block(item, kind, parent=None):
        source = f'{kind}-{item["Id"]}'
        meta = metadata.get(source, {})
        description = item.get('Description') if kind == 'section' else item.get('ShortDescription')
        info = [text('heading' if kind == 'section' else 'title', item['Title'], 30 if kind == 'section' else 24, meta.get('title_url', '')),
                text('text', description)]
        if kind == 'card':
            info.append(text('text', item.get('PriceText')))
        image = {'kind': 'image', 'image': item.get('ImageUrl') or '', 'alt': item['Title'], 'image_mode': 'normal'}
        group = {'kind': 'group', 'columns': 2, 'nodes': [image, {'kind': 'group', 'nodes': info}]}
        if meta.get('image_position') == 'right':
            group['nodes'].reverse()
        return {'note': item['Title'], 'layout': 'image-text', 'anchor': source,
                'enabled': bool(item.get('IsActive', True)) and (parent is None or bool(parent.get('IsActive', True))),
                'source': source, 'source_parent': f'section-{parent["Id"]}' if parent else '', 'nodes': [group]}

    for section in sorted(snapshot.get('ServiceSections', []), key=lambda row: (row['SortOrder'], row['Id'])):
        blocks.append(item_block(section, 'section'))
        menu.append({'title': section['Title'], 'url': f'#section-{section["Id"]}', 'enabled': bool(section['IsActive'])})
        cards = [card for card in snapshot.get('ServiceCards', []) if card['SectionId'] == section['Id']]
        for card in sorted(cards, key=lambda row: (row['SortOrder'], row['Id'])):
            blocks.append(item_block(card, 'card', section))
    return {'title': 'Послуги і ціни', 'blocks': pc.normalize_blocks(blocks), 'menu': pc.normalize_menu(menu)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('export', type=Path)
    parser.add_argument('--database', type=Path, default=pc.ROOT / 'DATA' / 'lady.db')
    args = parser.parse_args()
    snapshot = json.loads(args.export.read_text(encoding='utf-8'))
    intro = ''
    config_path = pc.ROOT / 'DATA' / 'LadySite.config'
    if config_path.exists():
        for line in config_path.read_text(encoding='utf-8-sig').splitlines():
            if line.startswith('SERVICES_PAGE_INTRO='):
                intro = line.split('=', 1)[1]
    # Validate JSON conversion before creating the database.
    content = pc.read_content()
    if '/services' in content['pages']:
        raise ValueError('JSON services page already exists; refusing to replace manual edits.')
    page = service_page(snapshot, content, intro)
    import_database(snapshot, args.database)
    pc.update_content(lambda data: data['pages'].setdefault('/services', page))
    print('Imported:', {table: len(rows) for table, rows in snapshot.items()})
    print('Services JSON:', len(page['blocks']), 'blocks;', len(page['menu']), 'menu items')


if __name__ == '__main__':
    main()
