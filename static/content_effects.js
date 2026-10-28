(() => {
    let observer, settle, scrolling = false, active = new Map();
    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)');
    const effects = ['ShortBackLighting', 'Flowers', 'Sparkles', 'SoftPulse', 'Rainbow'];
    function clear(block) {
        const entry = active.get(block);
        if (!entry) return;
        clearTimeout(entry.timer); entry.overlay.remove(); active.delete(block);
    }
    function clearAll() { [...active.keys()].forEach(clear); }
    function fullyVisible(block) {
        const r = block.getBoundingClientRect();
        const header = document.querySelector('.topbar');
        const footer = document.querySelector('.footer');
        const top = header ? Math.max(0,header.getBoundingClientRect().bottom) : 0;
        const bottom = footer ? Math.min(window.innerHeight,footer.getBoundingClientRect().top) : window.innerHeight;
        return r.width > 0 && r.height > 0 && r.top >= top && r.bottom <= bottom && r.left >= 0 && r.right <= window.innerWidth;
    }
    function animate(block) {
        if (scrolling || reduced.matches || active.has(block) || !fullyVisible(block)) return;
        const selected = [...block.querySelectorAll('[data-block-effect]')].map(n => n.dataset.blockEffect).filter(e => e !== 'none');
        if (!selected.length) return;
        let effect = selected[Math.floor(Math.random()*selected.length)];
        if (effect === 'random') effect = effects[Math.floor(Math.random()*effects.length)];
        const overlay = document.createElement('div'); overlay.className = 'block-contour effect-' + effect; overlay.setAttribute('aria-hidden','true');
        if (effect === 'Flowers' || effect === 'Sparkles') {
            const flower = ['🌸','🌼','🌺','🌻','✿'][Math.floor(Math.random()*5)];
            const r = block.getBoundingClientRect();
            const count = Math.min(64,Math.max(12,Math.round((r.width+r.height)/45)));
            const perimeter = 2*(r.width+r.height);
            for (let i=0;i<count;i++) {
                const point = document.createElement('span'); point.textContent = effect === 'Flowers' ? flower : '✧';
                const d = i*perimeter/count;
                let x,y;
                if (d<r.width) { x=d; y=0; }
                else if (d<r.width+r.height) { x=r.width; y=d-r.width; }
                else if (d<2*r.width+r.height) { x=2*r.width+r.height-d; y=r.height; }
                else { x=0; y=perimeter-d; }
                point.style.left = x/r.width*100+'%'; point.style.top = y/r.height*100+'%'; overlay.append(point);
            }
        }
        block.append(overlay);
        active.set(block,{overlay,timer:setTimeout(() => clear(block),2200)});
    }
    function check() { document.querySelectorAll('.content-block').forEach(animate); }
    window.initContentEffects = () => {
        observer?.disconnect(); clearAll();
        document.querySelectorAll('.content-carousel').forEach(carousel => {
            if (carousel.dataset.initialized) return;
            carousel.dataset.initialized = '1';
            const viewport = carousel.querySelector('.carousel-slides');
            const originals = [...viewport.children];
            if (!originals.length) return;
            const track = document.createElement('div'); track.className = 'carousel-track';
            viewport.replaceChildren(track);
            let index = 0, gesture = null, busy = false, ready = false;
            let autoTimer;
            function restartAutoSwipe() {
                clearTimeout(autoTimer);
                if (!carousel.isConnected || originals.length < 2) return;
                autoTimer = setTimeout(() => {
                    if (!carousel.isConnected) return;
                    if (!document.hidden && !gesture && !busy) move(1);
                    restartAutoSwipe();
                }, 40000);
            }
            carousel.setAttribute('aria-busy', 'true');
            const wrap = value => (value + originals.length) % originals.length;
            async function preload(slide) {
                const images = [...slide.querySelectorAll('img, [data-carousel-src]')];
                await Promise.all(images.map(async image => {
                    const src = image.dataset.carouselSrc || image.getAttribute('src');
                    if (!src) return;
                    const loader = new Image();
                    loader.src = src;
                    try { await loader.decode(); } catch { return; }
                    if (image.tagName === 'IMG') {
                        image.loading = 'eager'; image.src = src;
                        try { await image.decode(); } catch {}
                    } else image.style.backgroundImage = `url(${JSON.stringify(src)})`;
                    delete image.dataset.carouselSrc;
                }));
                return images.every(image => image.tagName === 'IMG'
                    ? image.complete && image.naturalWidth > 0 : !image.dataset.carouselSrc);
            }
            function render() {
                track.style.transition = 'none';
                track.style.transform = 'translate3d(-100%,0,0)';
                track.replaceChildren(...[-1,0,1].map(offset => {
                    const slide = originals[wrap(index + offset)].cloneNode(true);
                    slide.hidden = false;
                    slide.setAttribute('aria-hidden', offset ? 'true' : 'false');
                    slide.inert = offset !== 0;
                    slide.querySelectorAll('img').forEach(image => image.draggable = false);
                    return slide;
                }));
            }
            function move(direction) {
                if (busy || !ready || originals.length < 2) return;
                busy = true;
                const reducedMotion = reduced.matches;
                track.style.transition = reducedMotion ? 'none' : 'transform 280ms cubic-bezier(.22,.7,.25,1)';
                track.style.transform = `translate3d(${-viewport.clientWidth * (1 + direction)}px,0,0)`;
                let finished = false, timer;
                const finish = () => {
                    if (finished) return;
                    finished = true; clearTimeout(timer);
                    track.removeEventListener('transitionend', finish);
                    index = wrap(index + direction); render(); busy = false;
                };
                if (reducedMotion) finish();
                else { track.addEventListener('transitionend', finish); timer = setTimeout(finish, 340); }
            }
            // Keep the first photo visible while all originals load and decode.
            const preview = originals[0].cloneNode(true); preview.hidden = false;
            track.append(preview);
            Promise.all(originals.map(preload)).then(loaded => {
                const valid = originals.filter((slide, i) => loaded[i]);
                if (valid.length) { originals.splice(0, originals.length, ...valid); render(); }
                ready = valid.length > 0;
                carousel.setAttribute('aria-busy', 'false');
                restartAutoSwipe();
            });
            carousel.addEventListener('dragstart', event => event.preventDefault());
            viewport.addEventListener('pointerdown', event => {
                if (!ready || busy || originals.length < 2 || !event.isPrimary || (event.pointerType === 'mouse' && event.button !== 0)) return;
                gesture = {id:event.pointerId,x:event.clientX,y:event.clientY,delta:0,horizontal:false};
                clearTimeout(autoTimer);
                viewport.setPointerCapture(event.pointerId);
            });
            viewport.addEventListener('pointermove', event => {
                if (!gesture || gesture.id !== event.pointerId) return;
                const dx = event.clientX - gesture.x, dy = event.clientY - gesture.y;
                if (!gesture.horizontal && Math.abs(dy) > Math.abs(dx) && Math.abs(dy) > 8) { gesture = null; restartAutoSwipe(); return; }
                if (!gesture.horizontal && Math.abs(dx) > 8) {
                    gesture.horizontal = true; carousel.classList.add('is-dragging');
                }
                if (!gesture.horizontal) return;
                gesture.delta = Math.max(-viewport.clientWidth, Math.min(viewport.clientWidth, dx));
                track.style.transition = 'none';
                track.style.transform = `translate3d(${-viewport.clientWidth + gesture.delta}px,0,0)`;
            });
            function end(event, cancel = false) {
                if (!gesture || gesture.id !== event.pointerId) return;
                const current = gesture; gesture = null; carousel.classList.remove('is-dragging');
                restartAutoSwipe();
                if (viewport.hasPointerCapture(event.pointerId)) viewport.releasePointerCapture(event.pointerId);
                if (!current.horizontal) return;
                const threshold = Math.min(80,viewport.clientWidth * .15);
                move(!cancel && Math.abs(current.delta) > threshold ? (current.delta < 0 ? 1 : -1) : 0);
            }
            viewport.addEventListener('pointerup', event => end(event));
            viewport.addEventListener('pointercancel', event => end(event,true));
            viewport.addEventListener('lostpointercapture', event => end(event,true));
            carousel.addEventListener('keydown', event => {
                if (event.key === 'ArrowLeft' || event.key === 'ArrowRight') {
                    event.preventDefault(); move(event.key === 'ArrowLeft' ? -1 : 1);
                    restartAutoSwipe();
                }
            });
        });
        observer = new IntersectionObserver(entries => entries.forEach(entry => {
            if (entry.intersectionRatio === 1) animate(entry.target); else clear(entry.target);
        }), {threshold:[0,1]});
        document.querySelectorAll('.content-block').forEach(block => observer.observe(block));
    };
    document.addEventListener('scroll', () => {
        scrolling = true; clearAll(); clearTimeout(settle); settle = setTimeout(() => { scrolling = false; check(); },180);
    }, {capture:true,passive:true});
    window.addEventListener('resize', () => { scrolling = true; clearAll(); clearTimeout(settle); settle = setTimeout(() => { scrolling = false; check(); },180); });
    reduced.addEventListener('change',clearAll);
    document.addEventListener('DOMContentLoaded',window.initContentEffects);
})();
