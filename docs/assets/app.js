(() => {
  const canvas = document.getElementById("matrix");
  const ctx = canvas.getContext("2d", { alpha: true });

  const params = new URLSearchParams(location.search);
  const calm = params.get("mode") === "calm";

  const state = {
    t: 0,
    pointer: { x: canvas.width * 0.72, y: canvas.height * 0.36, down: false, vx: 0, vy: 0 },
    last: { x: 0, y: 0, ts: performance.now() },
    dpr: Math.max(1, Math.min(2, window.devicePixelRatio || 1)),
  };

  function fitCanvas() {
    const rect = canvas.getBoundingClientRect();
    const cssW = Math.max(520, rect.width);
    const cssH = cssW * (canvas.height / canvas.width);
    canvas.style.height = `${cssH}px`;

    const w = Math.floor(cssW * state.dpr);
    const h = Math.floor(cssH * state.dpr);
    canvas.width = w;
    canvas.height = h;
  }

  function onPointer(e) {
    const rect = canvas.getBoundingClientRect();
    const x = (e.clientX - rect.left) * state.dpr;
    const y = (e.clientY - rect.top) * state.dpr;
    const now = performance.now();
    const dt = Math.max(16, now - state.last.ts);
    const vx = (x - state.last.x) / dt;
    const vy = (y - state.last.y) / dt;
    state.pointer.vx = vx;
    state.pointer.vy = vy;
    state.pointer.x = x;
    state.pointer.y = y;
    state.last.x = x;
    state.last.y = y;
    state.last.ts = now;
  }

  function onDown() {
    state.pointer.down = true;
  }
  function onUp() {
    state.pointer.down = false;
  }

  window.addEventListener("resize", () => {
    fitCanvas();
  });

  canvas.addEventListener("pointermove", (e) => onPointer(e));
  canvas.addEventListener("pointerdown", () => onDown());
  canvas.addEventListener("pointerup", () => onUp());
  canvas.addEventListener("pointerleave", () => onUp());
  canvas.addEventListener("pointerenter", (e) => onPointer(e));

  fitCanvas();

  function colorStops() {
    return {
      a: "rgba(109,94,249,0.95)",
      b: "rgba(154,230,255,0.92)",
      c: "rgba(253,230,138,0.92)",
      grid: "rgba(148,163,184,0.10)",
      faint: "rgba(148,163,184,0.06)",
      text: "rgba(229,231,235,0.86)",
    };
  }

  function draw() {
    const { a, b, c, grid, faint } = colorStops();
    const w = canvas.width;
    const h = canvas.height;
    ctx.clearRect(0, 0, w, h);

    const cols = 44;
    const rows = 28;
    const padX = w * 0.06;
    const padY = h * 0.08;
    const gw = w - padX * 2;
    const gh = h - padY * 2;
    const cellW = gw / cols;
    const cellH = gh / rows;
    const cell = Math.min(cellW, cellH);

    const px = state.pointer.x;
    const py = state.pointer.y;
    const speed = Math.hypot(state.pointer.vx, state.pointer.vy);
    const pressBoost = state.pointer.down ? 1.7 : 1.0;

    const baseAmp = calm ? 0.55 : 1.0;
    const amp = baseAmp * pressBoost * (0.8 + Math.min(1.2, speed * 18));

    const t = state.t;

    // subtle background vignette
    const g0 = ctx.createRadialGradient(px, py, 10, px, py, Math.max(w, h) * 0.8);
    g0.addColorStop(0, "rgba(154,230,255,0.09)");
    g0.addColorStop(0.35, "rgba(109,94,249,0.05)");
    g0.addColorStop(1, "rgba(0,0,0,0)");
    ctx.fillStyle = g0;
    ctx.fillRect(0, 0, w, h);

    // matrix
    for (let r = 0; r < rows; r++) {
      for (let col = 0; col < cols; col++) {
        const x = padX + col * cellW + cellW * 0.5;
        const y = padY + r * cellH + cellH * 0.5;

        const dx = x - px;
        const dy = y - py;
        const dist = Math.hypot(dx, dy);

        // wave that follows pointer
        const wave = Math.sin(dist * 0.032 - t * 1.9);
        const ripple = Math.cos(dist * 0.018 - t * 1.2);

        const local = (0.58 + 0.42 * wave) * (0.72 + 0.28 * ripple);
        const falloff = Math.exp(-dist / (Math.max(w, h) * 0.32));
        const intensity = amp * local * falloff;

        const size = cell * (0.18 + 0.22 * intensity);
        const round = Math.max(2, size * 0.45);

        // color blend: left->right gradient + interactive highlight
        const k = col / Math.max(1, cols - 1);
        const glow = Math.max(0, Math.min(1, intensity));

        let fill;
        if (k < 0.55) fill = a;
        else if (k < 0.82) fill = b;
        else fill = c;

        // base faint grid point
        ctx.fillStyle = faint;
        ctx.beginPath();
        ctx.roundRect(x - cell * 0.12, y - cell * 0.12, cell * 0.24, cell * 0.24, cell * 0.2);
        ctx.fill();

        if (glow > 0.04) {
          // glow ring
          ctx.strokeStyle = `rgba(154,230,255,${0.05 + glow * 0.22})`;
          ctx.lineWidth = Math.max(1, cell * 0.06);
          ctx.beginPath();
          ctx.roundRect(x - size * 1.4, y - size * 1.4, size * 2.8, size * 2.8, round * 1.3);
          ctx.stroke();

          // core
          ctx.fillStyle = fill;
          ctx.globalAlpha = 0.18 + glow * 0.78;
          ctx.beginPath();
          ctx.roundRect(x - size, y - size, size * 2, size * 2, round);
          ctx.fill();
          ctx.globalAlpha = 1;
        }

        // subtle grid lines (very light)
        if (r % 4 === 0 && col % 6 === 0) {
          ctx.strokeStyle = grid;
          ctx.lineWidth = 1;
          ctx.beginPath();
          ctx.moveTo(x, y);
          ctx.lineTo(x + cellW * 1.2, y);
          ctx.stroke();
        }
      }
    }

    // label
    ctx.fillStyle = "rgba(229,231,235,0.42)";
    ctx.font = `${Math.floor(12 * state.dpr)}px ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Arial`;
    ctx.fillText("move / press", Math.floor(w * 0.06), Math.floor(h * 0.06));

    state.t += calm ? 0.010 : 0.014;
    requestAnimationFrame(draw);
  }

  requestAnimationFrame(draw);
})();

