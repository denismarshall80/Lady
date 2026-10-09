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
            carousel.dataset.initialized = '1'; let index = 0;
            const slides = [...carousel.querySelectorAll('.carousel-slide')];
            carousel.querySelectorAll('[data-carousel-step]').forEach(button => button.addEventListener('click', () => {
                slides[index].hidden = true; index = (index+Number(button.dataset.carouselStep)+slides.length)%slides.length;
                slides[index].hidden = false; carousel.querySelector('[data-carousel-count]').textContent = `${index+1} / ${slides.length}`;
            }));
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
