document.addEventListener('DOMContentLoaded', () => {
    const root = document.querySelector('[data-page-editor]');
    if (!root) return;
    const form = root.querySelector('[data-page-form]');
    const collapseKey = 'lady.page-editor.open:' + form.querySelector('[name="page_path"]').value;
    try { root.open = location.hash === '#page-editor' || localStorage.getItem(collapseKey) === '1'; }
    catch { root.open = location.hash === '#page-editor'; }
    root.addEventListener('toggle', () => {
        try { localStorage.setItem(collapseKey, root.open ? '1' : '0'); } catch {}
    });
    window.addEventListener('hashchange', () => {
        if (location.hash === '#page-editor') root.open = true;
    });
    const list = root.querySelector('[data-block-list]');
    const status = root.querySelector('[data-page-status]');
    const cancelButton = root.querySelector('[data-page-cancel]');
    let saving = false;
    let savedState;
    function setStatus(message, state = 'error') { status.textContent = message; status.dataset.state = state; }
    function syncActions() { cancelButton.disabled = saving || uploads > 0; }
    function editorState() {
        return structuredClone({blocks, siteBlocks, siteBackground, logoText, pageTitle:form.querySelector('[name="page_title"]').value});
    }
    const siteList = root.querySelector('[data-site-block-list]');
    let siteBlocks = JSON.parse(root.querySelector('[data-site-block-data]').textContent);
    let siteBackground = JSON.parse(root.querySelector('[data-site-background-data]').textContent);
    let blocks = JSON.parse(root.querySelector('[data-page-data]').textContent);
    let logoText = JSON.parse(root.querySelector('[data-logotext-data]').textContent);
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
    const markDirty = () => { dirty = true; revision++; setStatus('Є незбережені зміни.', 'dirty'); };
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
    function elementEditor(parent, label, object, skipText = false, inline = false) {
        const details = inline ? node('div', '', 'node-value-editor') : disclosure(object, 'element', 'element-editor');
        if (!inline) details.append(node('summary', label));
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
    const kinds = {group:'Ноду', heading:'Заголовок усього блоку', image:'Малюнок', title:'Заголовок інформації', text:'Основний текст', button:'Кнопка з надписом і посиланням', auto:'Елемент з автонаповненням', carousel:'Карусель', animation:'Анімація', map:'Мапа', social:'Соціальні мережі', background:'Фон блоку'};
    const effects = {none:'Без анімації', random:'Випадкова', ShortBackLighting:'ShortBackLighting — підсвічування', Flowers:'Flowers — квіточки', Sparkles:'Sparkles — іскри', SoftPulse:'SoftPulse — м’який пульс', Rainbow:'Rainbow — веселковий контур'};
    function makeNode(kind, layout = 'text-image') {
        if (kind === 'auto') {
            const image = makeNode('image');
            const info = {kind:'group', nodes:['title','text','button'].map(kind => makeNode(kind))};
            return {kind:'group', name:'Елемент з автонаповненням', nodes:layout === 'text-image' ? [info,image] : [image,info]};
        }
        if (kind === 'group' || kind === 'carousel') return {kind, nodes:[]};
        if (kind === 'background') return {kind, value:{color:'',image:'',mode:'tile',align:'center',vertical:'top',attachment:'scroll'}};
        if (kind === 'map') return {kind, url:'', title:'Мапа салону'};
        if (kind === 'social') return {kind, value:emptyElement()};
        if (kind === 'animation') return {kind, effect:'random'};
        if (kind === 'image') return {kind, image:'', alt:'', image_mode:'normal', image_align:'center', image_vertical:'center'};
        return {kind, value:emptyElement(kind === 'heading' ? 32 : kind === 'title' ? 28 : 18)};
    }
    // Convert only in editor memory; persisted content changes only on explicit Save.
    [...blocks,...siteBlocks].forEach(block => {
        if (!block.nodes) {
            block.nodes = [];
            if (block.heading?.text) block.nodes.push({kind:'heading', value:block.heading});
            block.items.forEach(item => {
                const image = {kind:'image', image:item.image, alt:item.alt, image_mode:item.image_mode, image_align:item.image_align, image_vertical:item.image_vertical};
                const info = {kind:'group', nodes:['title','text','button'].map(kind => ({kind, value:item[kind]}))};
                const children = block.layout === 'text' ? info.nodes : block.layout === 'image' ? [image] : block.layout === 'text-image' ? [info,image] : [image,info];
                block.nodes.push({kind:'group', name:item.name, nodes:children});
            });
        }
        if (block.background) {
            block.nodes.push({kind:'background', value:block.background});
            delete block.background;
        }
    });
    function addControls(parent, items, carousel = false, layout = 'text-image') {
        const row = node('div', '', 'node-add-row');
        const select = node('select');
        select.setAttribute('aria-label', 'Що додати');
        Object.entries(carousel ? {image:'Малюнок'} : kinds).forEach(([value, label]) => {
            const option = node('option', label); option.value = value; select.append(option);
        });
        row.append(button('Додати', () => {
            if (items.length >= 100) { setStatus('Максимум 100 нод на рівні.'); return; }
            items.push(makeNode(select.value,layout)); markDirty(); render();
        }), select);
        parent.append(row);
    }
    function imageEditor(parent, item) {
        const grid = node('div', '', 'element-fields');
        const imageInput = field(grid, 'Малюнок: URL або /static/…', item, 'image');
        field(grid, 'Опис малюнка (alt)', item, 'alt');
        field(grid, 'Режим малюнка', item, 'image_mode', {normal:'Повністю', stretch:'Розтягнути', tile:'Замостити', cover:'Заповнити з обрізанням'});
        field(grid, 'По горизонталі', item, 'image_align', {left:'Зліва', center:'По центру', right:'Справа'});
        field(grid, 'По вертикалі', item, 'image_vertical', {top:'Вгорі', center:'По центру', bottom:'Внизу'});
        uploadImage(grid,item,imageInput);
        parent.append(grid);
    }
    function uploadImage(grid, item, imageInput) {
        const upload = node('input'); upload.type = 'file'; upload.accept = 'image/png,image/jpeg,image/webp,image/gif';
        const label = node('label', 'Завантажити малюнок'); label.append(upload); grid.append(label);
        upload.addEventListener('change', async () => {
            if (!upload.files.length) return;
            const data = new FormData(); data.append('image_file', upload.files[0]); data.append('csrf', form.querySelector('[name="csrf"]').value);
            uploads++; upload.disabled = true; syncActions();
            try {
                const response = await fetch('/content/image', {method:'POST', body:data});
                if (response.redirected) throw new Error('Сесія завершилася. Увійдіть знову.');
                const result = await response.json(); if (!response.ok) throw new Error(result.error || 'Помилка завантаження');
                item.image = result.url; imageInput.value = result.url; markDirty();
            } catch (error) { setStatus(error.message); }
            finally { uploads--; upload.disabled = false; syncActions(); }
        });
    }
    function backgroundEditor(parent, object) {
        const grid = node('div', '', 'element-fields');
        field(grid,'Колір (#RRGGBB або transparent; порожньо — стандартний)',object,'color');
        const input = field(grid,'Малюнок фону: URL або /static/…',object,'image');
        field(grid,'Режим фону',object,'mode',{tile:'Замостити — повторювати фрагмент', cover:'Заповнити з обрізанням', contain:'Повністю', stretch:'Розтягнути', normal:'Оригінальний розмір'});
        field(grid,'По горизонталі',object,'align',{left:'Зліва',center:'По центру',right:'Справа'});
        field(grid,'По вертикалі',object,'vertical',{top:'Вгорі',center:'По центру',bottom:'Внизу'});
        field(grid,'Прокрутка фону',object,'attachment',{scroll:'Разом зі сторінкою',fixed:'Нерухомий'});
        uploadImage(grid,object,input); parent.append(grid);
    }
    function renderNodes(parent, items, depth = 0) {
        items.forEach((item, index) => {
            const panel = disclosure(item, 'item', 'item-editor');
            const summary = node('summary');
            const header = node('span', '', 'item-header');
            const name = itemName(item, index);
            if (!item.name) name.textContent = kinds[item.kind];
            header.append(name);
            const actions = node('span', '', 'item-actions');
            actions.addEventListener('click', event => { event.preventDefault(); event.stopPropagation(); });
            actions.append(button('↑', () => reorder(items,index,-1)), button('↓', () => reorder(items,index,1)),
                button('Копіювати', () => { items.splice(index+1,0,structuredClone(item)); markDirty(); render(); }),
                button('Видалити', () => { items.splice(index,1); markDirty(); render(); }));
            header.append(actions); summary.append(header); panel.append(summary);
            if (item.kind === 'group' || item.kind === 'carousel') {
                renderNodes(panel, item.nodes, depth+1);
                if (depth < 5) addControls(panel, item.nodes, item.kind === 'carousel');
            } else if (item.kind === 'image') imageEditor(panel,item);
            else if (item.kind === 'background') backgroundEditor(panel,item.value);
            else if (item.kind === 'map') { field(panel,'URL вбудованої Google-мапи (src, без iframe)',item,'url'); field(panel,'Опис мапи',item,'title'); }
            else if (item.kind === 'social') {
                field(panel,'Розташування посилань',item.value,'align',{left:'Зліва',center:'По центру',right:'Справа'});
                const link = node('a','Редагувати соціальні посилання у налаштуваннях'); link.href = '/settings?tab=contacts'; link.target = '_blank'; link.rel = 'noopener'; panel.append(link);
            }
            else if (item.kind === 'animation') field(panel,'Контурна анімація всього блоку',item,'effect',effects);
            else elementEditor(panel,kinds[item.kind],item.value,false,true);
            parent.append(panel);
        });
    }
    function renderList(list, blocks) {
        list.replaceChildren();
        blocks.forEach((block, index) => {
            const wrapper = node('div', '', 'block-editor-wrap');
            const panel = disclosure(block, 'block', 'block-editor');
            const summary = node('summary'); summary.append(node('span', `Блок ${index + 1}`));
            const note = node('input', '', 'block-note'); note.type = 'text'; note.placeholder = 'Нотатка про блок'; note.value = block.note ?? '';
            note.setAttribute('aria-label', `Нотатка про блок ${index+1}`);
            note.addEventListener('click', event => event.stopPropagation());
            note.addEventListener('keydown', event => { event.stopPropagation(); if (event.key === 'Enter') event.preventDefault(); });
            note.addEventListener('input', () => { block.note = note.value; markDirty(); });
            summary.append(note);
            const controls = node('span', '', 'block-toolbar');
            controls.addEventListener('click', event => { event.preventDefault(); event.stopPropagation(); });
            controls.append(button('↑ Вище', () => reorder(blocks,index,-1)), button('↓ Нижче', () => reorder(blocks,index,1)),
                button('Копіювати', () => { blocks.splice(index+1,0,structuredClone(block)); markDirty(); render(); }),
                button('Видалити', () => { if (confirm('Видалити блок?')) { blocks.splice(index,1); markDirty(); render(); } },'danger'));
            // Let the checkbox keep its native checked state inside the summary.
            const enabled = node('label','Показувати блок'); const check = node('input'); check.type = 'checkbox'; check.checked = block.enabled;
            check.addEventListener('click', event => event.stopPropagation());
            check.addEventListener('change', () => { block.enabled = check.checked; markDirty(); });
            enabled.addEventListener('click', event => event.stopPropagation()); enabled.append(check);
            summary.append(controls,enabled); panel.append(summary);
            field(panel,'Тип блоку',block,'layout',layouts);
            renderNodes(panel,block.nodes); addControls(panel,block.nodes,false,block.layout);
            wrapper.append(panel); list.append(wrapper);
        });
    }
    function render() { renderList(list,blocks); renderList(siteList,siteBlocks); }
    root.querySelector('[data-block-add]').addEventListener('click', () => {
        if (blocks.length >= 100) { setStatus('Максимум 100 блоків.'); return; }
        blocks.push({note:'', layout:'text-image', enabled:true, nodes:[], items:[]});
        markDirty(); render(); list.lastElementChild.scrollIntoView({behavior:'smooth', block:'start'});
    });
    root.querySelector('[data-site-block-add]').addEventListener('click', () => {
        if (siteBlocks.length >= 100) { setStatus('Максимум 100 нижніх блоків.'); return; }
        siteBlocks.push({note:'',layout:'text',enabled:true,nodes:[],items:[]});
        markDirty(); render(); siteList.lastElementChild.scrollIntoView({behavior:'smooth',block:'start'});
    });
    form.addEventListener('submit', async event => {
        event.preventDefault();
        if (uploads) { setStatus('Дочекайтеся завантаження малюнків.'); return; }
        if (saving) return;
        const submittedState = editorState();
        const data = new FormData(form); data.append('blocks', JSON.stringify(submittedState.blocks));
        const savedRevision = revision;
        data.append('logotext', JSON.stringify(submittedState.logoText));
        data.append('site_blocks',JSON.stringify(submittedState.siteBlocks));
        data.append('site_background',JSON.stringify(submittedState.siteBackground));
        const submit = form.querySelector('[type="submit"]');
        saving = true; submit.disabled = true; syncActions();
        setStatus('Збереження…','saving');
        try {
            const response = await fetch(form.action, {method:'POST', body:data});
            if (response.redirected) throw new Error('Сесія завершилася. Увійдіть знову.');
            const result = await response.json();
            if (!response.ok) throw new Error(result.error || 'Не вдалося зберегти сторінку');
            savedState = submittedState;
            dirty = revision !== savedRevision;
            setStatus(dirty ? 'Збережено. Є нові незбережені зміни.' : 'Зміни збережено.', dirty ? 'dirty' : 'success');
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
                const newSite = documentPreview.querySelector('.site-blocks');
                const currentSite = document.querySelector('.site-blocks');
                if (newSite && currentSite) currentSite.replaceWith(newSite);
                document.body.setAttribute('style',documentPreview.body.getAttribute('style') || '');
                window.initContentEffects?.();
                const brand = document.querySelector('.brand');
                const updatedBrand = documentPreview.querySelector('.brand');
                if (brand && updatedBrand) brand.replaceWith(updatedBrand);
                document.title = documentPreview.title;
                window.scrollBy({top:root.getBoundingClientRect().top - offset, behavior:'instant'});
            } catch {
                status.textContent += ' Перегляд не оновився; відкрийте «Перегляд як клієнт».';
            }
        } catch (error) { setStatus(error.message); }
        finally { saving = false; submit.disabled = false; syncActions(); }
    });
    window.addEventListener('beforeunload', event => {
        if (dirty) { event.preventDefault(); event.returnValue = ''; }
    });
    form.querySelector('[name="page_title"]').addEventListener('input', markDirty);
    function renderPageFields() {
        const logoEditor = root.querySelector('[data-logotext-editor]');
        logoEditor.replaceChildren();
        field(logoEditor, 'logotext — текст біля логотипа', logoText, 'text');
        elementEditor(logoEditor, 'Шрифт і оформлення logotext', logoText, true);
        const bgEditor = root.querySelector('[data-site-background-editor]');
        bgEditor.replaceChildren(); backgroundEditor(bgEditor,siteBackground);
    }
    cancelButton.addEventListener('click', () => {
        if (saving || uploads || !savedState) return;
        const restored = structuredClone(savedState);
        blocks = restored.blocks; siteBlocks = restored.siteBlocks;
        siteBackground = restored.siteBackground; logoText = restored.logoText;
        form.querySelector('[name="page_title"]').value = restored.pageTitle;
        revision++; dirty = false;
        renderPageFields(); render(); setStatus('Зміни відмінено.','success');
    });
    renderPageFields(); render(); savedState = editorState();
});
