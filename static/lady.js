document.addEventListener('DOMContentLoaded', function () {
    const tabRoots = Array.from(document.querySelectorAll('[data-tabs]'));
    tabRoots.forEach(function (root) {
        const tabButtons = Array.from(root.querySelectorAll('[data-tab-target]'));
        const tabPanels = Array.from(root.querySelectorAll('[data-tab-panel]'));
        tabButtons.forEach(function (button) {
            button.addEventListener('click', function () {
                const target = button.getAttribute('data-tab-target');
                tabButtons.forEach(function (item) {
                    item.classList.toggle('is-active', item === button);
                });
                tabPanels.forEach(function (panel) {
                    panel.classList.toggle('is-active', panel.getAttribute('data-tab-panel') === target);
                });
                const activeInput = root.querySelector('[name="active_tab"]');
                if (activeInput) activeInput.value = target;
            });
        });
    });

    document.querySelectorAll('[data-service-edit-select]').forEach(function (select) {
        const forms = Array.from(document.querySelectorAll('[data-service-edit-form]'));
        function updateForm() {
            const selected = select.value;
            forms.forEach(function (form) {
                form.classList.toggle('is-active', form.getAttribute('data-service-edit-form') === selected);
            });
        }
        select.addEventListener('change', updateForm);
        updateForm();
    });

    document.querySelectorAll('[data-service-edit-open]').forEach(function (button) {
        button.addEventListener('click', function () {
            const target = button.getAttribute('data-service-edit-open');
            const adminRoot = document.querySelector('#services-admin [data-tabs]');
            if (adminRoot) {
                const tabButton = adminRoot.querySelector('[data-tab-target="edit-card"]');
                if (tabButton) tabButton.click();
            }
            const select = document.querySelector('[data-service-edit-select]');
            if (select) {
                select.value = target;
                select.dispatchEvent(new Event('change', { bubbles: true }));
            }
            const form = document.querySelector('[data-service-edit-form="' + target + '"]');
            if (form) form.scrollIntoView({ behavior: 'smooth', block: 'center' });
        });
    });

    function syncImagePicker(root) {
        const checked = root.querySelector('input[name="image_mode"]:checked');
        const mode = checked ? checked.value : 'file';
        root.querySelectorAll('[data-image-mode-panel]').forEach(function (panel) {
            panel.classList.toggle('is-active', panel.getAttribute('data-image-mode-panel') === mode);
        });
    }
    document.querySelectorAll('[data-image-picker]').forEach(function (picker) {
        picker.querySelectorAll('input[name="image_mode"]').forEach(function (radio) {
            radio.addEventListener('change', function () { syncImagePicker(picker); });
        });
        syncImagePicker(picker);
    });

    function buildPriceRow(editor, value) {
        const list = editor.querySelector('[data-price-lines]');
        const row = document.createElement('div');
        row.className = 'price-line-row';
        const input = document.createElement('input');
        input.type = 'text';
        input.value = value || '';
        input.placeholder = '450 грн - Устілка 42-го розміру';
        const remove = document.createElement('button');
        remove.type = 'button';
        remove.className = 'icon-button danger';
        remove.title = 'Видалити ціну';
        remove.textContent = '×';
        row.appendChild(input);
        row.appendChild(remove);
        list.appendChild(row);
        function sync() {
            const source = editor.querySelector('[data-price-source]');
            source.value = Array.from(editor.querySelectorAll('.price-line-row input'))
                .map(function (item) { return item.value.trim(); })
                .filter(Boolean)
                .join('\n');
        }
        input.addEventListener('input', sync);
        remove.addEventListener('click', function () {
            row.remove();
            if (!editor.querySelector('.price-line-row')) buildPriceRow(editor, '');
            sync();
        });
    }

    function initPriceEditor(editor) {
        const source = editor.querySelector('[data-price-source]');
        const list = editor.querySelector('[data-price-lines]');
        if (!source || !list) return;
        list.innerHTML = '';
        const lines = source.value.split(/\r?\n/).map(function (line) { return line.trim(); }).filter(Boolean);
        (lines.length ? lines : ['']).forEach(function (line) { buildPriceRow(editor, line); });
    }

    document.querySelectorAll('[data-price-editor]').forEach(function (editor) {
        initPriceEditor(editor);
        const add = editor.querySelector('[data-price-add]');
        if (add) {
            add.addEventListener('click', function () {
                buildPriceRow(editor, '');
                const input = editor.querySelector('.price-line-row:last-child input');
                if (input) input.focus();
            });
        }
    });

    document.querySelectorAll('[data-form-cancel]').forEach(function (button) {
        button.addEventListener('click', function () {
            const form = button.closest('form');
            if (!form) return;
            form.reset();
            form.querySelectorAll('[data-image-picker]').forEach(syncImagePicker);
            form.querySelectorAll('[data-price-editor]').forEach(initPriceEditor);
        });
    });

    const serviceLinks = Array.from(document.querySelectorAll('[data-service-nav]'));
    const serviceSections = serviceLinks
        .map(function (link) {
            const target = document.querySelector(link.getAttribute('href'));
            return target ? { link: link, target: target } : null;
        })
        .filter(Boolean);
    if ('IntersectionObserver' in window && serviceSections.length) {
        const observer = new IntersectionObserver(function (entries) {
            const visible = entries
                .filter(function (entry) { return entry.isIntersecting; })
                .sort(function (a, b) { return b.intersectionRatio - a.intersectionRatio; })[0];
            if (!visible) return;
            serviceSections.forEach(function (item) {
                item.link.classList.toggle('active', item.target === visible.target);
            });
        }, { rootMargin: '-20% 0px -55% 0px', threshold: [0.05, 0.2, 0.45] });
        serviceSections.forEach(function (item) { observer.observe(item.target); });
    }

    document.addEventListener('click', function (event) {
        document.querySelectorAll('.user-menu[open]').forEach(function (menu) {
            if (!menu.contains(event.target)) {
                menu.removeAttribute('open');
            }
        });
        document.querySelectorAll('.context-menu[open]').forEach(function (menu) {
            if (!menu.contains(event.target)) {
                menu.removeAttribute('open');
            }
        });
    });

    document.querySelectorAll('[data-dialog-open]').forEach(function (button) {
        button.addEventListener('click', function () {
            const dialog = document.getElementById(button.getAttribute('data-dialog-open'));
            const menu = button.closest('.context-menu');
            if (menu) menu.removeAttribute('open');
            if (dialog && typeof dialog.showModal === 'function') dialog.showModal();
        });
    });

    document.querySelectorAll('[data-dialog-close]').forEach(function (button) {
        button.addEventListener('click', function () {
            const dialog = button.closest('dialog');
            if (dialog) dialog.close();
        });
    });

    document.querySelectorAll('dialog').forEach(function (dialog) {
        dialog.addEventListener('click', function (event) {
            if (event.target === dialog) dialog.close();
        });
    });
});
