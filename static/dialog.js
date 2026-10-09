// Shared accessible confirmation dialog. Closing returns cancel.
window.ladyDialog = function(message) {
    return new Promise(resolve => {
        if (document.querySelector('.lady-dialog[open]')) { resolve('cancel'); return; }
        const previous = document.activeElement;
        const dialog = document.createElement('dialog');
        dialog.className = 'lady-dialog';
        dialog.setAttribute('aria-labelledby', 'lady-dialog-title');
        dialog.innerHTML = `<button type="button" class="dialog-close" aria-label="Відміна">×</button><h2 id="lady-dialog-title"></h2><div class="dialog-actions"><button type="button" class="dialog-yes">Так</button><button type="button" class="dialog-no">Ні</button></div>`;
        dialog.querySelector('h2').textContent = message;
        const finish = value => dialog.close(value);
        dialog.querySelector('.dialog-yes').onclick = () => finish('yes');
        dialog.querySelector('.dialog-no').onclick = () => finish('no');
        dialog.querySelector('.dialog-close').onclick = () => finish('cancel');
        dialog.addEventListener('cancel', event => { event.preventDefault(); finish('cancel'); });
        dialog.addEventListener('close', () => {
            const result = dialog.returnValue || 'cancel'; dialog.remove(); previous?.focus(); resolve(result);
        }, {once:true});
        document.body.append(dialog); dialog.showModal(); dialog.querySelector('.dialog-yes').focus();
    });
};
document.addEventListener('submit', async event => {
    const trigger = event.submitter;
    if (!trigger?.dataset.confirm || trigger.dataset.confirmed === '1') return;
    event.preventDefault();
    if (await window.ladyDialog(trigger.dataset.confirm) !== 'yes') return;
    trigger.dataset.confirmed = '1';
    try { event.target.requestSubmit(trigger); } finally { delete trigger.dataset.confirmed; }
});
