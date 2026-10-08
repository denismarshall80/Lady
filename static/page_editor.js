document.addEventListener('DOMContentLoaded', () => {
    const root = document.querySelector('[data-page-editor]');
    if (!root) return;
    const form = root.querySelector('[data-page-form]');
    const list = root.querySelector('[data-block-list]');
    const status = root.querySelector('[data-page-status]');
    let blocks = JSON.parse(root.querySelector('[data-page-data]').textContent);
    let dirty = false;
    let uploads = 0;
    const layouts = {'text-image':'Інформація зліва + малюнок справа', 'image-text':'Малюнок зліва + інформація справа', text:'Інформація на всю ширину', image:'Малюнок на всю ширину', columns:'Колонки: малюнок + інформація знизу'};
    const emptyElement = (size = 18) => ({text:'', url:'', font:'Arial', size, bold:false, italic:false, underline:false, align:'left', vertical:'top'});
    const emptyItem = () => ({image:'', alt:'', title:emptyElement(28), text:emptyElement(), button:emptyElement()});
    const markDirty = () => { dirty = true; status.textContent = 'Є незбережені зміни.'; };
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
    function elementEditor(parent, label, object) {
        const details = node('details', '', 'element-editor');
        details.append(node('summary', label));
        const grid = node('div', '', 'element-fields');
        const text = field(grid, 'Текст (необов’язково)', object, 'text', null, 'textarea');
        text.parentElement.className = 'element-full';
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
    function render() {
        list.replaceChildren();
        blocks.forEach((block, index) => {
            const panel = node('details', '', 'block-editor');
            panel.open = true;
            panel.append(node('summary', `Блок ${index + 1}: ${layouts[block.layout]}`));
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
                const itemPanel = node('div', '', 'item-editor');
                const toolbar = node('div', '', 'block-toolbar');
                toolbar.append(node('strong', `Елемент ${itemIndex + 1}`),
                    button('↑', () => reorder(block.items, itemIndex, -1)), button('↓', () => reorder(block.items, itemIndex, 1)),
                    button('Видалити елемент', () => { if (confirm('Видалити елемент?')) { block.items.splice(itemIndex, 1); markDirty(); render(); } }));
                itemPanel.append(toolbar);
                if (block.layout !== 'text') {
                    const imageInput = field(itemPanel, 'Малюнок: URL або /static/…', item, 'image');
                    field(itemPanel, 'Опис малюнка (alt)', item, 'alt');
                    const upload = node('input');
                    upload.type = 'file'; upload.accept = 'image/png,image/jpeg,image/webp,image/gif';
                    const uploadLabel = node('label', 'Завантажити малюнок файлом');
                    uploadLabel.append(upload); itemPanel.append(uploadLabel);
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
            list.append(panel);
        });
    }
    root.querySelector('[data-block-add]').addEventListener('click', () => {
        if (blocks.length >= 100) { status.textContent = 'Максимум 100 блоків.'; return; }
        blocks.push({layout:'text-image', heading:emptyElement(32), enabled:true, items:[emptyItem()]});
        markDirty(); render(); list.lastElementChild.scrollIntoView({behavior:'smooth', block:'start'});
    });
    form.addEventListener('submit', async event => {
        event.preventDefault();
        if (uploads) { status.textContent = 'Дочекайтеся завантаження малюнків.'; return; }
        const data = new FormData(form); data.append('blocks', JSON.stringify(blocks));
        const submit = form.querySelector('[type="submit"]');
        submit.disabled = true;
        status.textContent = 'Збереження…';
        try {
            const response = await fetch(form.action, {method:'POST', body:data});
            if (response.redirected) throw new Error('Сесія завершилася. Увійдіть знову.');
            const result = await response.json();
            if (!response.ok) throw new Error(result.error || 'Не вдалося зберегти сторінку');
            dirty = false;
            history.replaceState(null, '', result.url + '#page-editor');
            window.location.reload();
        } catch (error) { status.textContent = error.message; submit.disabled = false; }
    });
    window.addEventListener('beforeunload', event => {
        if (dirty) { event.preventDefault(); event.returnValue = ''; }
    });
    render();
});
