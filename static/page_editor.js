document.addEventListener('DOMContentLoaded', () => {
    const root = document.querySelector('[data-page-editor]');
    if (!root) return;
    const form = root.querySelector('[data-page-form]');
    const list = root.querySelector('[data-block-list]');
    const status = root.querySelector('[data-page-status]');
    let blocks = JSON.parse(root.querySelector('[data-page-data]').textContent);
    const logoText = JSON.parse(root.querySelector('[data-logotext-data]').textContent);
    const expanded = new WeakMap();
    function disclosure(object, key, cls) {
        const panel = node('details', '', cls);
        panel.open = expanded.get(object)?.[key] ?? false;
        panel.addEventListener('toggle', () => {
            const state = expanded.get(object) || {};
            state[key] = panel.open;
            expanded.set(object, state);
        });
        return panel;
    }
    let dirty = false;
    let revision = 0;
    let uploads = 0;
    const layouts = {'text-image':'Інформація зліва + малюнок справа', 'image-text':'Малюнок зліва + інформація справа', text:'Інформація на всю ширину', image:'Малюнок на всю ширину', columns:'Колонки: малюнок + інформація знизу'};
    const emptyElement = (size = 18) => ({text:'', url:'', font:'Arial', size, bold:false, italic:false, underline:false, align:'left', vertical:'top'});
    const emptyItem = () => ({name:'', image:'', alt:'', image_mode:'normal', image_align:'center', image_vertical:'center', title:emptyElement(28), text:emptyElement(), button:emptyElement()});
    const markDirty = () => { dirty = true; revision++; status.textContent = 'Є незбережені зміни.'; };
    function node(tag, text, cls) {
        const result = document.createElement(tag);
        if (text) result.textContent = text;
        if (cls) result.className = cls;
        return result;
    }
    function button(text, action, cls) {
        const result = node('button', text, cls);
        result.type = 'button';
        result.addEventListener('click', action);
        return result;
    }
    function field(parent, label, object, key, options, type = 'text') {
        const wrapper = node('label', label);
        const input = node(options ? 'select' : type === 'textarea' ? 'textarea' : 'input');
        if (options) {
            Object.entries(options).forEach(([value, caption]) => {
                const option = node('option', caption);
                option.value = value;
                input.append(option);
            });
        } else if (type !== 'textarea') input.type = type;
        if (type === 'textarea') input.rows = 4;
        if (type === 'number') { input.min = 10; input.max = 96; }
        if (type === 'checkbox') input.checked = !!object[key];
        else input.value = object[key] ?? '';
        input.addEventListener('input', () => {
            object[key] = type === 'checkbox' ? input.checked : type === 'number' ? Number(input.value) : input.value;
            markDirty();
        });
        wrapper.append(input);
        parent.append(wrapper);
        return input;
    }
    function elementEditor(parent, label, object, skipText = false) {
        const details = disclosure(object, 'element', 'element-editor');
        details.append(node('summary', label));
        const grid = node('div', '', 'element-fields');
        if (!skipText) {
            const text = field(grid, 'Текст (необов’язково)', object, 'text', null, 'textarea');
            text.parentElement.className = 'element-full';
        }
        field(grid, 'Посилання при кліку', object, 'url');
        field(grid, 'Шрифт', object, 'font', {Arial:'Arial', Georgia:'Georgia', Verdana:'Verdana', Tahoma:'Tahoma', 'Times New Roman':'Times New Roman'});
        field(grid, 'Розмір, px', object, 'size', null, 'number');
        field(grid, 'По горизонталі', object, 'align', {left:'Зліва', center:'По центру', right:'Справа'});
        field(grid, 'По вертикалі', object, 'vertical', {top:'Вгорі', center:'По центру', bottom:'Внизу'});
        const styles = node('div', '', 'element-style-options');
        field(styles, 'Жирний', object, 'bold', null, 'checkbox');
        field(styles, 'Курсив', object, 'italic', null, 'checkbox');
        field(styles, 'Підкреслений', object, 'underline', null, 'checkbox');
        grid.append(styles);
        details.append(grid);
        parent.append(details);
    }
    function reorder(items, index, delta) {
        const next = index + delta;
        if (next < 0 || next >= items.length) return;
        [items[index], items[next]] = [items[next], items[index]];
        markDirty(); render();
    }
    function itemName(item, index) {
        const label = node('span', item.name || `Елемент ${index + 1}`, 'item-name');
        label.tabIndex = 0;
        label.title = 'Утримуйте назву 1,5 секунди або натисніть F2, щоб перейменувати';
        let timer, origin, editing = false, suppressClick = false;
        const cancel = () => { clearTimeout(timer); timer = null; };
        function edit() {
            cancel();
            if (editing) return;
            editing = true;
            suppressClick = true;
            const input = node('input', '', 'item-name-input');
            input.type = 'text';
            input.value = item.name || `Елемент ${index + 1}`;
            input.setAttribute('aria-label', 'Назва елемента');
            label.replaceChildren(input);
            function finish(save) {
                if (!editing) return;
                editing = false;
                if (save && input.value !== (item.name || `Елемент ${index + 1}`)) {
                    item.name = input.value;
                    markDirty();
                }
                label.textContent = item.name || `Елемент ${index + 1}`;
            }
            input.addEventListener('blur', () => finish(true));
            input.addEventListener('keydown', event => {
                event.stopPropagation();
                if (event.key === 'Enter' || event.key === 'Escape') {
                    event.preventDefault(); finish(event.key === 'Enter');
                }
            });
            input.focus(); input.select();
        }
        label.addEventListener('pointerdown', event => {
            if (editing || event.button !== 0) return;
            suppressClick = false;
            origin = {x:event.clientX, y:event.clientY};
            timer = setTimeout(edit, 1500);
        });
        label.addEventListener('pointermove', event => {
            if (origin && Math.hypot(event.clientX - origin.x, event.clientY - origin.y) > 8) cancel();
        });
        ['pointerup', 'pointercancel', 'pointerleave'].forEach(type => label.addEventListener(type, cancel));
        label.addEventListener('click', event => {
            if (editing || suppressClick) {
                event.preventDefault(); event.stopPropagation(); suppressClick = false;
            }
        });
        label.addEventListener('contextmenu', event => { cancel(); event.preventDefault(); });
        label.addEventListener('keydown', event => {
            if (!editing && event.key === 'F2') { event.preventDefault(); event.stopPropagation(); edit(); }
        });
        return label;
    }
    function render() {
        list.replaceChildren();
        blocks.forEach((block, index) => {
            const wrapper = node('div', '', 'block-editor-wrap');
            const panel = disclosure(block, 'block', 'block-editor');
            const summary = node('summary');
            summary.append(node('span', `Блок ${index + 1}`));
            const note = node('input', '', 'block-note');
            note.type = 'text';
            note.placeholder = 'Нотатка про блок';
            note.setAttribute('aria-label', `Нотатка про блок ${index + 1}`);
            note.value = block.note ?? '';
            note.addEventListener('click', event => event.stopPropagation());
            ['keydown', 'keypress', 'keyup'].forEach(type => {
                note.addEventListener(type, event => {
                    event.stopPropagation();
                    if (event.key === 'Enter') event.preventDefault();
                });
            });
            note.addEventListener('input', () => { block.note = note.value; markDirty(); });
            panel.append(summary);
            const controls = node('div', '', 'block-toolbar');
            controls.append(button('↑ Вище', () => reorder(blocks, index, -1)), button('↓ Нижче', () => reorder(blocks, index, 1)),
                button('Копіювати', () => { blocks.splice(index + 1, 0, structuredClone(block)); markDirty(); render(); }),
                button('Видалити', () => { if (confirm('Видалити блок?')) { blocks.splice(index, 1); markDirty(); render(); } }, 'danger'));
            field(controls, 'Показувати блок', block, 'enabled', null, 'checkbox');
            panel.append(controls);
            const layout = field(panel, 'Тип блоку', block, 'layout', layouts);
            layout.addEventListener('change', render);
            elementEditor(panel, 'Заголовок усього блоку', block.heading);
            block.items.forEach((item, itemIndex) => {
                const itemPanel = disclosure(item, 'item', 'item-editor');
                const itemSummary = node('summary');
                const header = node('span', '', 'item-header');
                header.append(itemName(item, itemIndex));
                const toolbar = node('span', '', 'item-actions');
                toolbar.addEventListener('click', event => event.stopPropagation());
                toolbar.append(
                    button('↑', () => reorder(block.items, itemIndex, -1)), button('↓', () => reorder(block.items, itemIndex, 1)),
                    button('Видалити елемент', () => { if (confirm('Видалити елемент?')) { block.items.splice(itemIndex, 1); markDirty(); render(); } }));
                header.append(toolbar);
                itemSummary.append(header);
                itemPanel.append(itemSummary);
                if (block.layout !== 'text') {
                    const imagePanel = disclosure(item, 'image', 'element-editor image-editor');
                    imagePanel.append(node('summary', 'Малюнок'));
                    itemPanel.append(imagePanel);
                    const imageInput = field(imagePanel, 'Малюнок: URL або /static/…', item, 'image');
                    field(imagePanel, 'Опис малюнка (alt)', item, 'alt');
                    item.image_mode ??= 'normal';
                    item.image_align ??= 'center';
                    item.image_vertical ??= 'center';
                    field(imagePanel, 'Режим відображення малюнка', item, 'image_mode', {normal:'Нормальний — повністю, зі збереженням пропорцій', stretch:'Розтягнути — на всю область', tile:'Замостити — повторювати малюнок', cover:'Заповнити з обрізанням — зі збереженням пропорцій'});
                    field(imagePanel, 'Малюнок по горизонталі', item, 'image_align', {left:'Зліва', center:'По центру', right:'Справа'});
                    field(imagePanel, 'Малюнок по вертикалі', item, 'image_vertical', {top:'Вгорі', center:'По центру', bottom:'Внизу'});
                    const upload = node('input');
                    upload.type = 'file'; upload.accept = 'image/png,image/jpeg,image/webp,image/gif';
                    const uploadLabel = node('label', 'Завантажити малюнок файлом');
                    uploadLabel.append(upload); imagePanel.append(uploadLabel);
                    upload.addEventListener('change', async () => {
                        if (!upload.files.length) return;
                        const data = new FormData(); data.append('image_file', upload.files[0]);
                        data.append('csrf', form.querySelector('[name="csrf"]').value);
                        uploads++; upload.disabled = true; status.textContent = 'Завантаження малюнка…';
                        try {
                            const response = await fetch('/content/image', {method:'POST', body:data});
                            if (response.redirected) throw new Error('Сесія завершилася. Увійдіть знову.');
                            const result = await response.json();
                            if (!response.ok) throw new Error(result.error || 'Не вдалося завантажити малюнок');
                            item.image = result.url; imageInput.value = result.url; markDirty();
                        } catch (error) { status.textContent = error.message; }
                        finally { uploads--; upload.disabled = false; }
                    });
                }
                if (block.layout !== 'image') {
                    elementEditor(itemPanel, 'Заголовок інформації', item.title);
                    elementEditor(itemPanel, 'Основний текст', item.text);
                    elementEditor(itemPanel, 'Кнопка з написом і посиланням', item.button);
                }
                panel.append(itemPanel);
            });
            panel.append(button(block.layout === 'columns' ? 'Додати колонку' : 'Додати елемент', () => {
                if (block.items.length >= 12) { status.textContent = 'Максимум 12 елементів у блоці.'; return; }
                block.items.push(emptyItem()); markDirty(); render();
            }));
            wrapper.append(panel, note);
            list.append(wrapper);
        });
    }
    root.querySelector('[data-block-add]').addEventListener('click', () => {
        if (blocks.length >= 100) { status.textContent = 'Максимум 100 блоків.'; return; }
        blocks.push({note:'', layout:'text-image', heading:emptyElement(32), enabled:true, items:[emptyItem()]});
        markDirty(); render(); list.lastElementChild.scrollIntoView({behavior:'smooth', block:'start'});
    });
    form.addEventListener('submit', async event => {
        event.preventDefault();
        if (uploads) { status.textContent = 'Дочекайтеся завантаження малюнків.'; return; }
        const data = new FormData(form); data.append('blocks', JSON.stringify(blocks));
        const savedRevision = revision;
        data.append('logotext', JSON.stringify(logoText));
        const submit = form.querySelector('[type="submit"]');
        submit.disabled = true;
        status.textContent = 'Збереження…';
        try {
            const response = await fetch(form.action, {method:'POST', body:data});
            if (response.redirected) throw new Error('Сесія завершилася. Увійдіть знову.');
            const result = await response.json();
            if (!response.ok) throw new Error(result.error || 'Не вдалося зберегти сторінку');
            dirty = revision !== savedRevision;
            status.textContent = dirty ? 'Збережено. Є нові незбережені зміни.' : 'Сторінку збережено.';
            // Refresh the public preview without replacing any editor controls.
            try {
                const preview = await fetch(result.url + '?preview=public', {cache:'no-store'});
                if (!preview.ok || preview.redirected) throw new Error('preview');
                const documentPreview = new DOMParser().parseFromString(await preview.text(), 'text/html');
                const content = documentPreview.querySelector('.content-blocks');
                const current = document.querySelector('.content-blocks');
                if (!content || !current) throw new Error('preview');
                const offset = root.getBoundingClientRect().top;
                current.replaceWith(content);
                const brand = document.querySelector('.brand');
                const updatedBrand = documentPreview.querySelector('.brand');
                if (brand && updatedBrand) brand.replaceWith(updatedBrand);
                document.title = documentPreview.title;
                window.scrollBy({top:root.getBoundingClientRect().top - offset, behavior:'instant'});
            } catch {
                status.textContent += ' Перегляд не оновився; відкрийте «Перегляд як клієнт».';
            }
        } catch (error) { status.textContent = error.message; }
        finally { submit.disabled = false; }
    });
    window.addEventListener('beforeunload', event => {
        if (dirty) { event.preventDefault(); event.returnValue = ''; }
    });
    const logoEditor = root.querySelector('[data-logotext-editor]');
    field(logoEditor, 'logotext — текст біля логотипа', logoText, 'text');
    elementEditor(logoEditor, 'Шрифт і оформлення logotext', logoText, true);
    render();
});
