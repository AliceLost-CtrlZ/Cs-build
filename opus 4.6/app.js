(() => {
    const canvas = document.getElementById('canvas');
    const ctx = canvas.getContext('2d');

    const COLORS = ['#ff6b6b','#4ecdc4','#45b7d1','#96ceb4','#feca57','#c084fc'];
    const N = COLORS.length;
    const BETA = 0.3;
    const DT = 0.02;

    let W, H, particles = [], attr = [];
    let paused = false, wrap = false;
    let mouseDown = false, mx = 0, my = 0;
    let pps = 120, fric = 0.5, rMax = 100, strength = 5, trailA = 70;

    function resize() {
        const d = devicePixelRatio || 1;
        W = innerWidth; H = innerHeight;
        canvas.width = W * d; canvas.height = H * d;
        canvas.style.width = W + 'px'; canvas.style.height = H + 'px';
        ctx.setTransform(d, 0, 0, d, 0, 0);
    }

    function rndA() { return Math.round((Math.random() * 2 - 1) * 4) / 4; }

    function initAttr() {
        attr = [];
        for (let i = 0; i < N; i++) { attr[i] = []; for (let j = 0; j < N; j++) attr[i][j] = rndA(); }
    }

    function initParts() {
        particles = [];
        for (let s = 0; s < N; s++)
            for (let i = 0; i < pps; i++)
                particles.push({ x: Math.random() * W, y: Math.random() * H, vx: 0, vy: 0, s });
    }

    function frc(r, a) {
        if (r < BETA) return r / BETA - 1;
        if (r < 1) return a * (1 - Math.abs(2 * r - 1 - BETA) / (1 - BETA));
        return 0;
    }

    function simulate() {
        const cs = rMax;
        const cols = Math.ceil(W / cs) + 1, rows = Math.ceil(H / cs) + 1;
        const grid = new Array(cols * rows);
        for (let i = 0; i < grid.length; i++) grid[i] = [];
        const n = particles.length;
        for (let i = 0; i < n; i++) {
            const p = particles[i];
            const k = Math.floor(p.y / cs) * cols + Math.floor(p.x / cs);
            if (k >= 0 && k < grid.length) grid[k].push(i);
        }

        const rSq = rMax * rMax;
        for (let i = 0; i < n; i++) {
            const p = particles[i];
            let fx = 0, fy = 0;
            const cx = Math.floor(p.x / cs), cy = Math.floor(p.y / cs);
            for (let dy = -1; dy <= 1; dy++) for (let dx = -1; dx <= 1; dx++) {
                let nx = cx + dx, ny = cy + dy;
                if (wrap) { nx = ((nx % cols) + cols) % cols; ny = ((ny % rows) + rows) % rows; }
                else if (nx < 0 || nx >= cols || ny < 0 || ny >= rows) continue;
                const cell = grid[ny * cols + nx];
                if (!cell) continue;
                for (let k = 0; k < cell.length; k++) {
                    const j = cell[k];
                    if (j === i) continue;
                    const q = particles[j];
                    let ddx = q.x - p.x, ddy = q.y - p.y;
                    if (wrap) {
                        if (ddx > W / 2) ddx -= W; if (ddx < -W / 2) ddx += W;
                        if (ddy > H / 2) ddy -= H; if (ddy < -H / 2) ddy += H;
                    }
                    const d2 = ddx * ddx + ddy * ddy;
                    if (d2 > rSq || d2 < 1) continue;
                    const d = Math.sqrt(d2);
                    const f = frc(d / rMax, attr[p.s][q.s]) * strength;
                    fx += f * ddx / d; fy += f * ddy / d;
                }
            }
            p.vx = (p.vx + fx * DT) * (1 - fric * DT);
            p.vy = (p.vy + fy * DT) * (1 - fric * DT);
        }

        if (mouseDown) {
            for (let i = 0; i < n; i++) {
                const p = particles[i];
                const ddx = p.x - mx, ddy = p.y - my;
                const d = Math.sqrt(ddx * ddx + ddy * ddy);
                if (d < 120 && d > 1) {
                    const f = 30 * (1 - d / 120);
                    p.vx += f * ddx / d * DT; p.vy += f * ddy / d * DT;
                }
            }
        }

        for (let i = 0; i < n; i++) {
            const p = particles[i];
            p.x += p.vx; p.y += p.vy;
            if (wrap) {
                p.x = ((p.x % W) + W) % W; p.y = ((p.y % H) + H) % H;
            } else {
                if (p.x < 0) { p.x = 0; p.vx *= -0.5; }
                if (p.x > W) { p.x = W; p.vx *= -0.5; }
                if (p.y < 0) { p.y = 0; p.vy *= -0.5; }
                if (p.y > H) { p.y = H; p.vy *= -0.5; }
            }
        }
    }

    function render() {
        ctx.fillStyle = `rgba(8, 8, 14, ${1 - trailA / 100})`;
        ctx.fillRect(0, 0, W, H);
        for (let s = 0; s < N; s++) {
            ctx.fillStyle = COLORS[s];
            ctx.beginPath();
            for (let i = 0; i < particles.length; i++) {
                const p = particles[i];
                if (p.s !== s) continue;
                ctx.moveTo(p.x + 2.2, p.y);
                ctx.arc(p.x, p.y, 2.2, 0, Math.PI * 2);
            }
            ctx.fill();
        }
    }

    let lt = performance.now(), fc = 0, fps = 0;
    function loop(now) {
        requestAnimationFrame(loop);
        fc++;
        if (now - lt >= 1000) { fps = fc; fc = 0; lt = now; document.getElementById('fps').textContent = fps + ' fps'; }
        if (!paused) simulate();
        render();
    }

    // --- Matrix UI ---
    function aCol(v) {
        if (v > 0) return `rgba(60,${80 + v * 175},100,${0.25 + v * 0.6})`;
        if (v < 0) return `rgba(${80 + Math.abs(v) * 175},50,70,${0.25 + Math.abs(v) * 0.6})`;
        return 'rgba(100,100,110,0.12)';
    }

    function setCell(td, i, j) {
        const v = attr[i][j];
        td.style.background = aCol(v);
        td.textContent = (v > 0 ? '+' : '') + v.toFixed(1);
        td.style.color = v === 0 ? 'var(--text-faint)' : 'rgba(255,255,255,0.8)';
    }

    function buildMatrix() {
        const wrap = document.getElementById('matrix-wrap');
        wrap.innerHTML = '';
        const t = document.createElement('table');
        t.className = 'mx';
        const hr = document.createElement('tr');
        hr.appendChild(document.createElement('th'));
        for (let j = 0; j < N; j++) {
            const th = document.createElement('th');
            th.style.color = COLORS[j]; th.textContent = '●';
            hr.appendChild(th);
        }
        t.appendChild(hr);

        for (let i = 0; i < N; i++) {
            const row = document.createElement('tr');
            const lbl = document.createElement('th');
            lbl.style.color = COLORS[i]; lbl.textContent = '●';
            row.appendChild(lbl);
            for (let j = 0; j < N; j++) {
                const td = document.createElement('td');
                setCell(td, i, j);
                td.addEventListener('click', () => {
                    attr[i][j] = Math.min(1, Math.round((attr[i][j] + 0.25) * 4) / 4);
                    if (attr[i][j] > 1) attr[i][j] = -1;
                    setCell(td, i, j);
                });
                td.addEventListener('contextmenu', (e) => {
                    e.preventDefault();
                    attr[i][j] = Math.max(-1, Math.round((attr[i][j] - 0.25) * 4) / 4);
                    if (attr[i][j] < -1) attr[i][j] = 1;
                    setCell(td, i, j);
                });
                row.appendChild(td);
            }
            t.appendChild(row);
        }
        wrap.appendChild(t);
    }

    function refreshMatrix() {
        const cells = document.querySelectorAll('table.mx td');
        let idx = 0;
        for (let i = 0; i < N; i++) for (let j = 0; j < N; j++) { if (cells[idx]) setCell(cells[idx], i, j); idx++; }
    }

    // --- Presets ---
    const presets = {
        random() { initAttr(); },
        snakes() { for (let i = 0; i < N; i++) for (let j = 0; j < N; j++) attr[i][j] = i === j ? 0.25 : (i + 1) % N === j ? 1 : (i + 2) % N === j ? 0.25 : -0.75; },
        clusters() { for (let i = 0; i < N; i++) for (let j = 0; j < N; j++) attr[i][j] = i === j ? 0.75 : -0.5; },
        chains() { for (let i = 0; i < N; i++) for (let j = 0; j < N; j++) attr[i][j] = i === j ? -0.25 : (i + 1) % N === j ? 0.75 : (N + j - i) % N === N - 1 ? 0.5 : 0; },
        sym() { initAttr(); for (let i = 0; i < N; i++) for (let j = i + 1; j < N; j++) attr[j][i] = attr[i][j]; }
    };

    // --- Controls ---
    function wire(sid, vid, get, set) {
        const s = document.getElementById(sid), v = document.getElementById(vid);
        s.addEventListener('input', () => { const val = get(s); v.textContent = typeof val === 'number' && val < 1 ? val.toFixed(2) : val; set(val); });
        return s;
    }
    wire('s-fric', 'v-fric', s => parseInt(s.value) / 100, v => { fric = v; });
    wire('s-rad', 'v-rad', s => parseInt(s.value), v => { rMax = v; });
    wire('s-str', 'v-str', s => parseInt(s.value), v => { strength = v; });
    wire('s-trail', 'v-trail', s => parseInt(s.value), v => { trailA = v; });
    const cs = document.getElementById('s-count');
    cs.addEventListener('input', () => { pps = parseInt(cs.value); document.getElementById('v-count').textContent = pps; });
    cs.addEventListener('change', initParts);

    document.getElementById('tog').addEventListener('click', () => {
        const p = document.getElementById('panel');
        p.classList.toggle('collapsed');
        document.getElementById('tog').innerHTML = p.classList.contains('collapsed') ? '&#x25B2;' : '&#x25BC;';
    });

    document.querySelectorAll('[data-p]').forEach(b => b.addEventListener('click', () => {
        const fn = presets[b.dataset.p]; if (fn) { fn(); refreshMatrix(); }
    }));

    document.getElementById('c-wrap').addEventListener('change', e => { wrap = e.target.checked; });
    document.getElementById('c-pause').addEventListener('change', e => { paused = e.target.checked; });
    document.getElementById('btn-reset').addEventListener('click', initParts);

    document.addEventListener('keydown', e => {
        if (e.key === 'h' || e.key === 'H') {
            const c = document.getElementById('controls');
            c.style.display = c.style.display === 'none' ? 'flex' : 'none';
        }
        if (e.key === ' ') { e.preventDefault(); paused = !paused; document.getElementById('c-pause').checked = paused; }
    });

    // --- Mouse ---
    canvas.addEventListener('mousedown', e => { mouseDown = true; mx = e.clientX; my = e.clientY; });
    canvas.addEventListener('mousemove', e => { mx = e.clientX; my = e.clientY; });
    addEventListener('mouseup', () => { mouseDown = false; });
    canvas.addEventListener('touchstart', e => { e.preventDefault(); mouseDown = true; mx = e.touches[0].clientX; my = e.touches[0].clientY; }, { passive: false });
    canvas.addEventListener('touchmove', e => { e.preventDefault(); mx = e.touches[0].clientX; my = e.touches[0].clientY; }, { passive: false });
    canvas.addEventListener('touchend', () => { mouseDown = false; });

    // --- Init ---
    addEventListener('resize', resize);
    resize(); initAttr(); initParts(); buildMatrix();
    setTimeout(() => { const t = document.getElementById('toast'); if (t) t.style.opacity = '0'; }, 5000);
    requestAnimationFrame(loop);
})();
