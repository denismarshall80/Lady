document.addEventListener('DOMContentLoaded', function () {
    const visitSummary = document.querySelector('[data-visit-summary]');
    if (visitSummary) {
        fetch(visitSummary.dataset.visitSummary)
            .then(response => {
                if (!response.ok) throw new Error('visits');
                return response.json();
            })
            .then(data => {
                const keys = ['yesterday','today','month','year','total'];
                if (!keys.every(key => Number.isSafeInteger(data[key]) && data[key] >= 0)
                    || !Number.isInteger(data.month_number) || data.month_number < 1 || data.month_number > 12
                    || !Number.isInteger(data.year_number)) throw new Error('visits');
                const months = ['Січень','Лютий','Березень','Квітень','Травень','Червень',
                    'Липень','Серпень','Вересень','Жовтень','Листопад','Грудень'];
                visitSummary.textContent = `Відвідало: ${data.yesterday}/${data.today}/${data.month}/${data.total}`;
                visitSummary.title = `Вчора: ${data.yesterday}\nСьогодні: ${data.today}\n${months[data.month_number - 1]}: ${data.month}\n${data.year_number} рік: ${data.year}\nВсього: ${data.total}`;
                visitSummary.setAttribute('aria-label', visitSummary.title);
            })
            .catch(() => { visitSummary.textContent = 'Відвідало: —'; visitSummary.title = 'Статистика тимчасово недоступна'; });
    }
    const logForm = document.querySelector('[data-log-period-form]');
    if (logForm) {
        const period = logForm.querySelector('[data-log-period]');
        const updateLogFields = () => {
            logForm.querySelector('[data-log-month]').hidden = period.value !== 'month';
            logForm.querySelector('[data-log-custom]').hidden = period.value !== 'custom';
            logForm.querySelector('[data-log-apply]').hidden = ['today','yesterday'].includes(period.value);
            logForm.querySelector('[name="month"]').disabled = period.value !== 'month';
            logForm.querySelectorAll('[data-log-custom] input').forEach(input => input.disabled = period.value !== 'custom');
        };
        updateLogFields();
        period.addEventListener('change', () => {
            updateLogFields();
            if (['today','yesterday'].includes(period.value)) logForm.requestSubmit();
        });
    }
    document.querySelectorAll('[data-menu-alert]').forEach(alert => {
        alert.querySelector('[data-alert-close]').addEventListener('click', () => alert.remove());
        setTimeout(() => alert.remove(), 10000);
    });
    const topbar = document.querySelector('.topbar');
    // Both layouts are rendered by the server; refresh the mobile copy after editor saves.
    const placeSectionMenu = () => {
        const sectionMenu = document.querySelector('[data-page-preview] > .services-sidebar');
        let mobileMenu = topbar?.querySelector('.mobile-section-menu');
        if (!topbar) return;
        if (!sectionMenu) {
            mobileMenu?.remove();
            return;
        }
        if (!mobileMenu) {
            mobileMenu = document.createElement('nav');
            mobileMenu.className = 'services-sidebar mobile-section-menu';
            topbar.append(mobileMenu);
        }
        mobileMenu.setAttribute('aria-label', sectionMenu.getAttribute('aria-label'));
        mobileMenu.innerHTML = sectionMenu.innerHTML;
    };
    const updateAnchorOffset = () => {
        const pinned = topbar && ['sticky', 'fixed'].includes(getComputedStyle(topbar).position);
        const height = pinned ? topbar.getBoundingClientRect().height : 0;
        document.documentElement.style.setProperty('--anchor-offset', `${Math.ceil(height) + 12}px`);
    };
    updateAnchorOffset();
    if (topbar) new ResizeObserver(updateAnchorOffset).observe(topbar);
    window.addEventListener('resize', updateAnchorOffset);
    const alignServiceHash = () => {
        updateAnchorOffset();
        if (!/^#section-\d+$/.test(location.hash)) return;
        const target = document.getElementById(location.hash.slice(1));
        if (target) target.scrollIntoView({block: 'start'});
    };
    if (document.readyState === 'complete') alignServiceHash();
    else window.addEventListener('load', alignServiceHash, {once: true});
    const footer = document.querySelector('.footer');
    if (footer) {
        const reserveFooterSpace = () => document.body.style.setProperty('--footer-height', `${footer.getBoundingClientRect().height}px`);
        new ResizeObserver(reserveFooterSpace).observe(footer);
        reserveFooterSpace();
    }
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
                if (root.hasAttribute('data-settings-tabs')) {
                    root.querySelector('.settings-save-inline').setAttribute('form', target === 'html' ? 'settings-html-form' : 'settings-config-form');
                    root.querySelector('.settings-panel-scroll').scrollTop = 0;
                }
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

    let serviceSections = [];
    let activeSection;
    let navigationFrame;
    function updateServiceNavigation() {
        navigationFrame = null;
        if (!serviceSections.length) return;
        const offset = parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--anchor-offset')) || 12;
        const targets = [...new Set(serviceSections.map(item => item.target))]
            .sort((a, b) => a.getBoundingClientRect().top - b.getBoundingClientRect().top);
        let current = targets[0];
        for (const target of targets) {
            if (target.getBoundingClientRect().top <= offset + 24) current = target;
            else break;
        }
        if (current === activeSection) return;
        activeSection = current;
        serviceSections.forEach(({link, target}) => {
            const active = target === current;
            link.classList.toggle('active', active);
            if (active) link.setAttribute('aria-current', 'location');
            else link.removeAttribute('aria-current');
            const menu = link.parentElement;
            if (!active || !menu.getClientRects().length) return;
            const itemRect = link.getBoundingClientRect();
            const menuRect = menu.getBoundingClientRect();
            // Scroll only the menu, preserving the page position.
            if (menu.scrollWidth > menu.clientWidth) {
                if (itemRect.left < menuRect.left || itemRect.right > menuRect.right) {
                    menu.scrollTo({left: link.offsetLeft - menu.offsetLeft - (menu.clientWidth - link.offsetWidth) / 2,
                        behavior: 'auto'});
                }
            } else if (itemRect.top < menuRect.top || itemRect.bottom > menuRect.bottom) {
                menu.scrollTop += itemRect.top - menuRect.top - (menu.clientHeight - link.offsetHeight) / 2;
            }
        });
    }
    function scheduleServiceNavigation() {
        if (!navigationFrame) navigationFrame = requestAnimationFrame(updateServiceNavigation);
    }
    window.initServiceNavigation = function () {
        placeSectionMenu();
        serviceSections = Array.from(document.querySelectorAll('[data-service-nav]')).map(link => {
            const href = link.getAttribute('href') || '';
            const target = href.startsWith('#') ? document.getElementById(href.slice(1)) : null;
            return target ? {link, target} : null;
        }).filter(Boolean);
        activeSection = null;
        updateServiceNavigation();
    };
    window.initServiceNavigation();
    window.addEventListener('scroll', scheduleServiceNavigation, {passive: true});
    window.addEventListener('resize', () => {
        activeSection = null;
        scheduleServiceNavigation();
    });
    window.addEventListener('load', scheduleServiceNavigation);

    function positionContextMenu(menu) {
        const trigger = menu.querySelector('summary');
        const panel = menu.querySelector('.context-menu-panel');
        if (!trigger || !panel) return;

        const triggerRect = trigger.getBoundingClientRect();
        const panelRect = panel.getBoundingClientRect();
        const gap = 6;
        const viewportGap = 8;
        let left = triggerRect.right - panelRect.width;
        let top = triggerRect.bottom + gap;

        left = Math.max(viewportGap, Math.min(left, window.innerWidth - panelRect.width - viewportGap));
        if (top + panelRect.height > window.innerHeight - viewportGap) {
            top = triggerRect.top - panelRect.height - gap;
        }
        top = Math.max(viewportGap, Math.min(top, window.innerHeight - panelRect.height - viewportGap));

        menu.style.setProperty('--context-menu-left', left + 'px');
        menu.style.setProperty('--context-menu-top', top + 'px');
    }

    document.querySelectorAll('.context-menu').forEach(function (menu) {
        menu.addEventListener('toggle', function () {
            if (!menu.open) return;
            document.querySelectorAll('.context-menu[open]').forEach(function (otherMenu) {
                if (otherMenu !== menu) otherMenu.removeAttribute('open');
            });
            positionContextMenu(menu);
        });
    });

    window.addEventListener('resize', function () {
        document.querySelectorAll('.context-menu[open]').forEach(positionContextMenu);
    });
    window.addEventListener('scroll', function () {
        document.querySelectorAll('.context-menu[open]').forEach(positionContextMenu);
    }, true);

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
