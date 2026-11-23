// Screensaver card for the kiosks (S20 phone, Redmi tablet): clocks, canvas effects, GPU scenes and an Immich photo frame.
// Card options: entity (input_select holding the style, default input_select.amoled_saver_style),
// dismiss (switch turned off by a tap, for kiosks whose screensaver lets taps through), gl_scale (render
// resolution of the GPU scenes, default 0.5), photo_seconds (Immich slide time, default 20).
// ?style=<name> overrides the style for testing.
const STYLE_ENTITY = "input_select.amoled_saver_style";
const WEATHER = "weather.forecast_home";
const STYLES = ["Minimal", "Stacked", "Serif", "Orbit", "Analog", "Words", "Terminal", "Corner", "Aurora",
  "Fireflies", "Constellation", "Warp", "Matrix", "Flow", "Galaxy", "Live Weather", "Silk Waves",
  "Lava Lamp", "Liquid", "Plasma", "Northern Lights", "Neon Tunnel", "Kaleidoscope", "Synthwave", "Bokeh",
  "Live Sky", "Ocean Sunset", "Mountain Lake", "Nebula", "Galaxy Core", "Rain Window", "Underwater", "Iridescent",
  "Gradient Mesh", "Dunes", "Ink", "Fractal Zoom", "Neon City", "Snowy Pines", "Sakura", "Firefly Forest",
  "Stained Glass", "Sunbeams", "Ribbons", "Immich Photos"];
const PHOTOS = "Immich Photos";

// Animated backgrounds, drawn on a canvas at up to 30 fps. Mostly black with small moving lights,
// so nothing stays lit in one place. Each has init(w, h, card) -> state and draw(state, ctx, w, h, t, dt, card).
const rand = (a, b) => a + Math.random() * (b - a);
const TAU = Math.PI * 2;
function glowSprite(r, rgb) {
  const c = document.createElement("canvas");
  c.width = c.height = r * 2;
  const g = c.getContext("2d");
  const gr = g.createRadialGradient(r, r, 0, r, r, r);
  gr.addColorStop(0, `rgba(${rgb},1)`);
  gr.addColorStop(0.18, `rgba(${rgb},.55)`);
  gr.addColorStop(1, `rgba(${rgb},0)`);
  g.fillStyle = gr;
  g.fillRect(0, 0, r * 2, r * 2);
  return c;
}
const wrap = (p, w, h, m = 20) => {
  if (p.x < -m) p.x = w + m; else if (p.x > w + m) p.x = -m;
  if (p.y < -m) p.y = h + m; else if (p.y > h + m) p.y = -m;
};

const FX = {
  Fireflies: {
    init: (w, h) => ({
      sprite: glowSprite(32, "255,206,120"),
      p: Array.from({ length: 55 }, () => ({ x: rand(0, w), y: rand(0, h), vx: rand(-.3, .3), vy: rand(-.3, .3), ph: rand(0, TAU), sp: rand(.35, 1.1), s: rand(.45, 1.1) })),
    }),
    draw(S, c, w, h, t, dt) {
      c.globalCompositeOperation = "lighter";
      const k = dt / 16;
      for (const p of S.p) {
        p.vx = (p.vx + rand(-.03, .03)) * .985; p.vy = (p.vy + rand(-.03, .03)) * .985;
        p.x += p.vx * k; p.y += p.vy * k; wrap(p, w, h);
        const a = Math.pow(Math.max(0, Math.sin(t * .001 * p.sp + p.ph)), 3);
        if (a < .02) continue;
        const r = 32 * p.s * (.55 + .45 * a);
        c.globalAlpha = a;
        c.drawImage(S.sprite, p.x - r, p.y - r, r * 2, r * 2);
      }
    },
  },

  Constellation: {
    init: (w, h) => ({
      R: Math.min(w, h) * .3,
      p: Array.from({ length: Math.min(90, Math.round(w * h / 8000)) }, () => ({ x: rand(0, w), y: rand(0, h), vx: rand(-.18, .18), vy: rand(-.18, .18) })),
    }),
    draw(S, c, w, h, t, dt) {
      const k = dt / 16, R2 = S.R * S.R;
      for (const p of S.p) {
        p.x += p.vx * k; p.y += p.vy * k;
        if (p.x < 0 || p.x > w) p.vx *= -1;
        if (p.y < 0 || p.y > h) p.vy *= -1;
      }
      c.lineWidth = .7;
      for (let i = 0; i < S.p.length; i++) {
        const a = S.p[i];
        for (let j = i + 1; j < S.p.length; j++) {
          const b = S.p[j], dx = a.x - b.x, dy = a.y - b.y, d2 = dx * dx + dy * dy;
          if (d2 > R2) continue;
          c.strokeStyle = `rgba(130,170,255,${(1 - Math.sqrt(d2) / S.R) * .6})`;
          c.beginPath(); c.moveTo(a.x, a.y); c.lineTo(b.x, b.y); c.stroke();
        }
      }
      c.fillStyle = "rgba(210,225,255,.85)";
      for (const p of S.p) c.fillRect(p.x - 1, p.y - 1, 2, 2);
    },
  },

  Warp: {
    init: () => ({ s: Array.from({ length: 280 }, () => ({ x: rand(-1, 1), y: rand(-1, 1), z: rand(.05, 1) })) }),
    draw(S, c, w, h, t, dt) {
      const cx = w / 2, cy = h / 2, f = Math.max(w, h) * .5, v = .00011 * dt;
      c.lineCap = "round";
      for (const s of S.s) {
        const pz = s.z;
        s.z -= v;
        if (s.z <= .03) { s.x = rand(-1, 1); s.y = rand(-1, 1); s.z = 1; continue; }
        const x = cx + s.x / s.z * f, y = cy + s.y / s.z * f;
        if (x < 0 || x > w || y < 0 || y > h) { s.z = 1; s.x = rand(-1, 1); s.y = rand(-1, 1); continue; }
        const near = 1 - s.z;
        c.strokeStyle = `rgba(${200 + near * 55},${215 + near * 40},255,${near * .9})`;
        c.lineWidth = .4 + near * 2.2;
        c.beginPath(); c.moveTo(cx + s.x / pz * f, cy + s.y / pz * f); c.lineTo(x, y); c.stroke();
      }
    },
  },

  Matrix: {
    init(w, h) {
      const fs = Math.max(12, Math.round(w / 24));
      return {
        fs, chars: "アイウエオカキクケコサシスセソタチツテトナニヌネノハヒフヘホマミムメモヤユヨラリルレロワン0123456789",
        cols: Array.from({ length: Math.floor(w / fs) }, () => ({ y: rand(-h, 0), sp: rand(.5, 1.3), L: Math.round(rand(8, 24)), trail: [], cell: -1, on: Math.random() < .7 })),
      };
    },
    draw(S, c, w, h, t, dt) {
      c.font = `${S.fs}px "JetBrains Mono", monospace`;
      c.textAlign = "center";
      S.cols.forEach((col, i) => {
        if (!col.on) { if (Math.random() < .002) col.on = true; return; }
        col.y += col.sp * dt * S.fs / 140;
        const cell = Math.floor(col.y / S.fs);
        if (cell !== col.cell) {
          col.cell = cell;
          col.trail.unshift({ ch: S.chars[(Math.random() * S.chars.length) | 0], cell });
          if (col.trail.length > col.L) col.trail.pop();
        }
        if (Math.random() < .02 && col.trail.length > 2) col.trail[(Math.random() * col.trail.length) | 0].ch = S.chars[(Math.random() * S.chars.length) | 0];
        const x = i * S.fs + S.fs / 2;
        col.trail.forEach((g, k) => {
          c.fillStyle = k === 0 ? "rgba(215,255,225,.95)" : `rgba(60,225,120,${(1 - k / col.L) * .75})`;
          c.fillText(g.ch, x, g.cell * S.fs);
        });
        if ((col.cell - col.L) * S.fs > h) { col.y = rand(-h * .6, 0); col.trail = []; col.cell = -1; col.on = Math.random() < .7; }
      });
    },
  },

  Flow: {
    init: (w, h) => ({ p: Array.from({ length: 380 }, () => FX.Flow.spawn(w, h)) }),
    spawn: (w, h) => ({ x: rand(0, w), y: rand(0, h), life: rand(120, 360), hist: [] }),
    draw(S, c, w, h, t, dt) {
      c.globalCompositeOperation = "lighter";
      c.lineWidth = 1.1;
      const k = dt / 16;
      for (let i = 0; i < S.p.length; i++) {
        let p = S.p[i];
        const a = (Math.sin(p.x * .0045 + t * .00007) + Math.cos(p.y * .0038 - t * .00005) + Math.sin((p.x + p.y) * .0021 + t * .00011)) * 1.7;
        p.x += Math.cos(a) * .85 * k; p.y += Math.sin(a) * .85 * k;
        p.hist.push(p.x, p.y);
        if (p.hist.length > 36) p.hist.splice(0, 2);
        if (--p.life < 0 || p.x < -10 || p.x > w + 10 || p.y < -10 || p.y > h + 10) { S.p[i] = FX.Flow.spawn(w, h); continue; }
        const fade = Math.min(1, p.life / 60, p.hist.length / 20);
        c.strokeStyle = `hsla(${185 + 130 * (p.y / h)},85%,62%,${.3 * fade})`;
        c.beginPath(); c.moveTo(p.hist[0], p.hist[1]);
        for (let j = 2; j < p.hist.length; j += 2) c.lineTo(p.hist[j], p.hist[j + 1]);
        c.stroke();
      }
    },
  },

  Galaxy: {
    init(w, h) {
      const R = Math.min(w, h) * .82;
      return {
        R, core: glowSprite(80, "255,200,140"),
        s: Array.from({ length: 1100 }, (_, i) => {
          const r = Math.pow(Math.random(), 1.5) * R + 6;
          return { r, a0: (i % 3) * TAU / 3 + r * .013 + rand(-.38, .38), w: .00022 * Math.sqrt(R / (r + 25)), z: rand(.6, 1.6),
            col: `hsla(${35 + 185 * Math.min(1, r / R)},${70 + 20 * Math.random()}%,${78 - 18 * (r / R)}%,` };
        }),
      };
    },
    draw(S, c, w, h, t) {
      const cx = w / 2, cy = h * .72;
      c.globalCompositeOperation = "lighter";
      c.globalAlpha = .55;
      c.drawImage(S.core, cx - 80, cy - 80 * .55, 160, 160 * .55);
      c.globalAlpha = 1;
      for (const s of S.s) {
        const a = s.a0 + s.w * t;
        const x = cx + Math.cos(a) * s.r, y = cy + Math.sin(a) * s.r * .55;
        c.fillStyle = `${s.col}${.55 + .35 * Math.sin(t * .002 * s.z + s.r)})`;
        c.fillRect(x, y, s.z, s.z);
      }
    },
  },

  "Live Weather": {
    kind(card) {
      const st = card._hass?.states[WEATHER]?.state || "cloudy";
      if (/pouring/.test(st)) return "pour";
      if (/rain|lightning/.test(st)) return "rain";
      if (/snow|hail/.test(st)) return "snow";
      if (st === "clear-night" || (st === "sunny" && card._hass?.states["sun.sun"]?.state === "below_horizon")) return "stars";
      if (st === "sunny") return "motes";
      return "fog";
    },
    init(w, h, card) {
      const kind = FX["Live Weather"].kind(card);
      const n = { pour: 340, rain: 170, snow: 150, stars: 170, motes: 45, fog: 5 }[kind];
      return {
        kind, sprite: kind === "fog" ? glowSprite(120, "120,140,170") : glowSprite(26, "255,214,140"), shoot: null,
        p: Array.from({ length: n }, () => ({ x: rand(0, w), y: rand(0, h), v: rand(.6, 1.4), r: rand(.6, 2.6), ph: rand(0, TAU), len: rand(10, 24) })),
      };
    },
    draw(S, c, w, h, t, dt, card) {
      if ((t | 0) % 300 < 40 && FX["Live Weather"].kind(card) !== S.kind) Object.assign(S, FX["Live Weather"].init(w, h, card));
      const k = dt / 16;
      if (S.kind === "rain" || S.kind === "pour") {
        c.strokeStyle = "rgba(150,185,230,.38)"; c.lineWidth = 1;
        c.beginPath();
        for (const p of S.p) {
          p.y += p.v * 9 * k; p.x -= p.v * 1.2 * k;
          if (p.y > h) { p.y = rand(-40, 0); p.x = rand(0, w + 60); }
          c.moveTo(p.x, p.y); c.lineTo(p.x + p.len * .13, p.y - p.len);
        }
        c.stroke();
      } else if (S.kind === "snow") {
        c.fillStyle = "rgba(240,245,255,.8)";
        for (const p of S.p) {
          p.y += p.v * .7 * k; p.x += Math.sin(t * .0008 + p.ph) * .35 * k;
          if (p.y > h + 5) { p.y = -5; p.x = rand(0, w); }
          c.beginPath(); c.arc(p.x, p.y, p.r, 0, TAU); c.fill();
        }
      } else if (S.kind === "stars") {
        for (const p of S.p) {
          c.fillStyle = `rgba(225,232,255,${.25 + .6 * (.5 + .5 * Math.sin(t * .0012 * p.v + p.ph))})`;
          c.fillRect(p.x, p.y, p.r * .7, p.r * .7);
        }
        if (!S.shoot && Math.random() < .0015) S.shoot = { x: rand(w * .2, w), y: rand(0, h * .4), l: 0 };
        if (S.shoot) {
          const s = S.shoot; s.l += dt;
          const x = s.x - s.l * .5, y = s.y + s.l * .25;
          const g = c.createLinearGradient(x, y, x + 90, y - 45);
          g.addColorStop(0, "rgba(255,255,255,.9)"); g.addColorStop(1, "rgba(255,255,255,0)");
          c.strokeStyle = g; c.lineWidth = 1.4; c.beginPath(); c.moveTo(x, y); c.lineTo(x + 90, y - 45); c.stroke();
          if (s.l > 900) S.shoot = null;
        }
      } else if (S.kind === "motes") {
        c.globalCompositeOperation = "lighter";
        for (const p of S.p) {
          p.y -= p.v * .25 * k; p.x += Math.sin(t * .0005 + p.ph) * .25 * k; wrap(p, w, h);
          c.globalAlpha = .25 + .45 * (.5 + .5 * Math.sin(t * .0015 * p.v + p.ph));
          const r = 10 + p.r * 6;
          c.drawImage(S.sprite, p.x - r, p.y - r, r * 2, r * 2);
        }
      } else {
        c.globalCompositeOperation = "lighter";
        S.p.forEach((p, i) => {
          p.x += (.12 + i * .03) * k * (i % 2 ? 1 : -1);
          const r = w * (.55 + .1 * p.r);
          if (p.x > w + r) p.x = -r; if (p.x < -r) p.x = w + r;
          c.globalAlpha = .09;
          c.drawImage(S.sprite, p.x - r, p.y - r * .45, r * 2, r * .9);
        });
      }
    },
  },

  "Silk Waves": {
    init: () => ({}),
    draw(S, c, w, h, t) {
      c.globalCompositeOperation = "lighter";
      c.lineWidth = 1.3;
      for (let i = 0; i < 8; i++) {
        const base = h * .7 + (i - 4) * h * .012;
        c.strokeStyle = `hsla(${195 + i * 16},85%,62%,.42)`;
        c.beginPath();
        for (let x = -10; x <= w + 10; x += 6) {
          const y = base + Math.sin(x * .011 + t * .0006 + i * .55) * h * .035
            + Math.sin(x * .004 - t * .0004 + i * 1.1) * h * .05
            + Math.sin(x * .023 + t * .0011 - i) * h * .008;
          x < -9 ? c.moveTo(x, y) : c.lineTo(x, y);
        }
        c.stroke();
      }
    },
  },
};

// Vivid full-screen set: saturated colour everywhere, always moving
const PALETTE = [[255, 46, 136], [255, 145, 0], [255, 221, 0], [0, 229, 255], [123, 97, 255], [0, 255, 163], [255, 77, 77], [187, 61, 255]];
function softBlob(r, rgb) {
  const c = document.createElement("canvas");
  c.width = c.height = r * 2;
  const g = c.getContext("2d");
  const gr = g.createRadialGradient(r, r, 0, r, r, r);
  gr.addColorStop(0, `rgba(${rgb},1)`);
  gr.addColorStop(.45, `rgba(${rgb},.65)`);
  gr.addColorStop(1, `rgba(${rgb},0)`);
  g.fillStyle = gr;
  g.fillRect(0, 0, r * 2, r * 2);
  return c;
}
function bokehDisc(r, rgb) {
  const c = document.createElement("canvas");
  c.width = c.height = r * 2;
  const g = c.getContext("2d");
  const gr = g.createRadialGradient(r, r, 0, r, r, r);
  gr.addColorStop(0, `rgba(${rgb},.32)`);
  gr.addColorStop(.82, `rgba(${rgb},.42)`);
  gr.addColorStop(.93, `rgba(${rgb},.75)`);
  gr.addColorStop(1, `rgba(${rgb},0)`);
  g.fillStyle = gr;
  g.fillRect(0, 0, r * 2, r * 2);
  return c;
}
function hsl2rgb(h, s, l) {
  const k = (n) => (n + h / 30) % 12, a = s * Math.min(l, 1 - l);
  const f = (n) => l - a * Math.max(-1, Math.min(k(n) - 3, 9 - k(n), 1));
  return [f(0) * 255, f(8) * 255, f(4) * 255];
}
const VIVID_FX = {
  "Lava Lamp": {
    init: (w, h) => ({
      b: PALETTE.map((rgb, i) => ({ sprite: softBlob(200, rgb.join(",")), fx: rand(.00006, .00016), fy: rand(.00005, .00014), ph: i * 1.7, r: rand(.24, .36) * Math.max(w, h) })),
    }),
    draw(S, c, w, h, t) {
      for (const b of S.b) {
        const x = w / 2 + Math.sin(t * b.fx + b.ph) * w * .5, y = h / 2 + Math.cos(t * b.fy + b.ph * 1.3) * h * .45;
        const r = b.r * (1 + .18 * Math.sin(t * .0003 + b.ph));
        c.globalAlpha = .92;
        c.drawImage(b.sprite, x - r, y - r, r * 2, r * 2);
      }
    },
  },

  Liquid: {
    init: (w, h) => ({
      b: [4, 0, 3, 1, 7, 5].map((p, i) => ({ sprite: softBlob(220, PALETTE[p].join(",")), fx: rand(.00004, .0001), fy: rand(.00003, .00009), ph: i * 2.1, r: rand(.5, .7) * Math.max(w, h) })),
    }),
    draw(S, c, w, h, t) {
      c.fillStyle = "#0a0018";
      c.fillRect(0, 0, w, h);
      for (const b of S.b) {
        const x = w / 2 + Math.sin(t * b.fx + b.ph) * w * .6, y = h / 2 + Math.cos(t * b.fy + b.ph) * h * .55;
        c.globalAlpha = .85;
        c.drawImage(b.sprite, x - b.r, y - b.r, b.r * 2, b.r * 2);
      }
    },
  },

  Plasma: {
    init(w, h) {
      const bw = 72, bh = Math.round(72 * h / w);
      const buf = document.createElement("canvas");
      buf.width = bw; buf.height = bh;
      const pal = Array.from({ length: 256 }, (_, i) => hsl2rgb((i / 256) * 360, .95, .5));
      return { buf, bc: buf.getContext("2d"), img: buf.getContext("2d").createImageData(bw, bh), bw, bh, pal };
    },
    draw(S, c, w, h, t) {
      const { bw, bh, img, pal } = S, d = img.data, tt = t * .0006;
      let i = 0;
      for (let y = 0; y < bh; y++) {
        for (let x = 0; x < bw; x++) {
          const dx = x - bw / 2 - Math.sin(tt * .7) * bw * .3, dy = y - bh / 2 - Math.cos(tt * .5) * bh * .3;
          const v = Math.sin(x * .11 + tt) + Math.sin(y * .07 - tt * .8) + Math.sin((x + y) * .06 + tt * .6) + Math.sin(Math.sqrt(dx * dx + dy * dy) * .14 - tt * 1.3);
          const col = pal[((v + 4) * 32 + t * .012) & 255];
          const shade = .55 + .45 * Math.sin(v * 1.6 + tt);
          d[i++] = col[0] * shade; d[i++] = col[1] * shade; d[i++] = col[2] * shade; d[i++] = 255;
        }
      }
      S.bc.putImageData(img, 0, 0);
      c.imageSmoothingEnabled = true;
      c.imageSmoothingQuality = "high";
      c.drawImage(S.buf, 0, 0, w, h);
    },
  },

  "Northern Lights": {
    init(w, h) {
      const strip = (rgb) => {
        const s = document.createElement("canvas");
        s.width = 1; s.height = 256;
        const g = s.getContext("2d"), gr = g.createLinearGradient(0, 0, 0, 256);
        gr.addColorStop(0, `rgba(${rgb},0)`); gr.addColorStop(.12, `rgba(${rgb},.95)`);
        gr.addColorStop(.45, `rgba(${rgb},.35)`); gr.addColorStop(1, `rgba(${rgb},0)`);
        g.fillStyle = gr; g.fillRect(0, 0, 1, 256);
        return s;
      };
      return {
        stars: Array.from({ length: 90 }, () => ({ x: rand(0, w), y: rand(0, h), ph: rand(0, TAU) })),
        c: [["60,255,150", .16, .0009, .00045], ["40,210,255", .3, .0013, -.0006], ["200,80,255", .08, .0007, .0003], ["255,60,170", .42, .0011, -.00035]]
          .map(([rgb, y, f, s], i) => ({ strip: strip(rgb), y, f, s, i })),
      };
    },
    draw(S, c, w, h, t) {
      for (const s of S.stars) { c.fillStyle = `rgba(220,230,255,${.2 + .4 * (.5 + .5 * Math.sin(t * .001 + s.ph))})`; c.fillRect(s.x, s.y, 1.4, 1.4); }
      c.globalCompositeOperation = "lighter";
      for (const cu of S.c) {
        for (let x = -4; x < w + 4; x += 3) {
          const y = h * cu.y + Math.sin(x * cu.f * 6 + t * cu.s) * h * .06 + Math.sin(x * .013 - t * .0005 + cu.i) * h * .035;
          const len = h * (.32 + .18 * Math.sin(x * .009 + t * .0007 + cu.i * 2));
          c.globalAlpha = .28 + .3 * Math.max(0, Math.sin(x * .021 + t * .0012 + cu.i));
          c.drawImage(cu.strip, x, y, 4, len);
        }
      }
    },
  },

  "Neon Tunnel": {
    init: () => ({ r: Array.from({ length: 28 }, (_, i) => ({ z: (i + 1) / 28 })) }),
    draw(S, c, w, h, t, dt) {
      const cx = w / 2 + Math.sin(t * .00023) * w * .12, cy = h / 2 + Math.cos(t * .00017) * h * .08;
      const base = Math.min(w, h) * .09;
      c.globalCompositeOperation = "lighter";
      S.r.sort((a, b) => b.z - a.z);
      for (const ring of S.r) {
        ring.z -= .00009 * dt;
        if (ring.z <= .04) ring.z += 1;
        const rad = base / ring.z, rot = t * .00012 + ring.z * 2.4;
        const [r, g, b] = hsl2rgb((t * .02 + ring.z * 320) % 360, 1, .58);
        c.strokeStyle = `rgba(${r | 0},${g | 0},${b | 0},${Math.min(1, (1 - ring.z) * 1.6) * .9})`;
        c.lineWidth = Math.min(16, 1.2 / ring.z);
        c.save(); c.translate(cx, cy); c.rotate(rot);
        c.beginPath();
        for (let k = 0; k <= 6; k++) { const a = (k / 6) * TAU; k ? c.lineTo(Math.cos(a) * rad, Math.sin(a) * rad) : c.moveTo(Math.cos(a) * rad, Math.sin(a) * rad); }
        c.stroke(); c.restore();
      }
    },
  },

  Kaleidoscope: {
    init: (w, h) => ({
      sprites: PALETTE.map((p) => glowSprite(64, p.join(","))),
      R: Math.max(w, h) * .62,
      p: Array.from({ length: 16 }, (_, i) => ({ r: rand(.04, 1), a: rand(0, Math.PI / 12), vr: rand(.00004, .00012), va: rand(.0002, .0006), s: rand(24, 80), k: i % PALETTE.length, ph: rand(0, TAU) })),
    }),
    draw(S, c, w, h, t) {
      const cx = w / 2, cy = h / 2, seg = 12;
      c.globalCompositeOperation = "lighter";
      c.globalAlpha = .6;
      for (const p of S.p) {
        const r = S.R * (.08 + .92 * (.5 + .5 * Math.sin(t * p.vr + p.ph)));
        const a = (Math.PI / seg) * (.5 + .5 * Math.sin(t * p.va + p.ph));
        const size = p.s * (.7 + .5 * Math.sin(t * .0009 + p.ph));
        for (let k = 0; k < seg; k++) {
          const base = k * TAU / seg + t * .00005;
          for (const ang of [base + a, base - a]) {
            c.drawImage(S.sprites[p.k], cx + Math.cos(ang) * r - size, cy + Math.sin(ang) * r - size, size * 2, size * 2);
          }
        }
      }
    },
  },

  Synthwave: {
    init(w, h) {
      const sun = document.createElement("canvas");
      sun.width = sun.height = 400;
      return { sun, sc: sun.getContext("2d"),
        stars: Array.from({ length: 60 }, () => ({ x: rand(0, w), y: rand(0, h * .55), ph: rand(0, TAU) })),
        mtn: Array.from({ length: 24 }, (_, i) => rand(.25, 1) * (i % 2 ? .6 : 1)) };
    },
    draw(S, c, w, h, t) {
      const hz = h * .64;
      const sky = c.createLinearGradient(0, 0, 0, hz);
      sky.addColorStop(0, "#07001a"); sky.addColorStop(.55, "#3a0a6b"); sky.addColorStop(.85, "#b0186f"); sky.addColorStop(1, "#ff4f6d");
      c.fillStyle = sky; c.fillRect(0, 0, w, hz);
      for (const s of S.stars) { c.fillStyle = `rgba(255,230,255,${.25 + .5 * (.5 + .5 * Math.sin(t * .0013 + s.ph))})`; c.fillRect(s.x, s.y, 1.5, 1.5); }
      // Striped sun, its gaps slowly sliding down
      const g = S.sc, R = 200;
      g.clearRect(0, 0, 400, 400);
      const sg = g.createLinearGradient(0, 0, 0, 400);
      sg.addColorStop(0, "#ffe259"); sg.addColorStop(.5, "#ff8a3c"); sg.addColorStop(1, "#ff2a85");
      g.fillStyle = sg; g.beginPath(); g.arc(R, R, R, 0, TAU); g.fill();
      g.globalCompositeOperation = "destination-out";
      const off = (t * .012) % 26;
      for (let y = 170; y < 400; y += 26) { const gy = y + off; g.fillRect(0, gy, 400, 3 + (gy - 200) * .06); }
      g.globalCompositeOperation = "source-over";
      const sr = w * .36, sx = w / 2 + Math.sin(t * .00003) * w * .04;
      c.drawImage(S.sun, sx - sr, hz - sr * 1.72, sr * 2, sr * 2);
      // Mountains, scrolling slowly
      c.fillStyle = "#1a0633";
      c.beginPath(); c.moveTo(0, hz);
      const n = S.mtn.length, sh = (t * .004) % (w / (n / 2));
      for (let i = 0; i <= n; i++) c.lineTo(i * w / (n / 2) - sh, hz - S.mtn[i % n] * h * .07);
      c.lineTo(w, hz); c.fill();
      // Floor and neon grid
      c.fillStyle = "#05000d"; c.fillRect(0, hz, w, h - hz);
      c.strokeStyle = "rgba(255,43,214,.85)"; c.lineWidth = 1.4;
      c.beginPath();
      for (let i = -16; i <= 16; i++) { c.moveTo(w / 2 + i * w * .02, hz); c.lineTo(w / 2 + i * w * .2, h); }
      const ph = (t * .00035) % 1;
      for (let j = 0; j < 14; j++) { const f = (j + ph) / 14, y = hz + (h - hz) * f * f; c.moveTo(0, y); c.lineTo(w, y); }
      c.stroke();
      c.strokeStyle = "rgba(255,120,240,.9)"; c.lineWidth = 2;
      c.beginPath(); c.moveTo(0, hz); c.lineTo(w, hz); c.stroke();
    },
  },

  Bokeh: {
    init: (w, h) => ({
      sprites: PALETTE.map((p) => bokehDisc(128, p.join(","))),
      p: Array.from({ length: 30 }, (_, i) => ({ x: rand(0, w), y: rand(0, h), r: rand(26, 115), vx: rand(-.25, .25), vy: rand(-.35, -.08), k: i % PALETTE.length, ph: rand(0, TAU) })),
    }),
    draw(S, c, w, h, t, dt) {
      c.globalCompositeOperation = "lighter";
      const k = dt / 16;
      for (const p of S.p) {
        p.x += p.vx * k; p.y += p.vy * k; wrap(p, w, h, p.r);
        c.globalAlpha = .45 + .3 * Math.sin(t * .0008 + p.ph);
        c.drawImage(S.sprites[p.k], p.x - p.r, p.y - p.r, p.r * 2, p.r * 2);
      }
    },
  },
};
Object.assign(FX, VIVID_FX);

// ── GPU wallpapers ─────────────────────────────────────────────────────────────
// Full-screen WebGL scenes, rendered at a reduced resolution and scaled up (soft by nature, so it
// does not show) to stay cool on phones and tablets. Uniforms: R resolution, T seconds (wraps),
// E sun elevation in degrees (from sun.sun), W weather (cloud cover, rain, snow, fog) for Live Sky.
const GL_COMMON = `
#ifdef GL_FRAGMENT_PRECISION_HIGH
precision highp float;
#else
precision mediump float;
#endif
uniform vec2 R; uniform float T; uniform float E; uniform vec4 W;
float h1(float n){ return fract(sin(n * 12.9898) * 43758.5453); }
float h2(vec2 p){ p = fract(p * vec2(123.34, 456.21)); p += dot(p, p + 45.32); return fract(p.x * p.y); }
vec2 h22(vec2 p){ float n = h2(p); return vec2(n, h2(p + n + 17.17)); }
float noise(vec2 p){ vec2 i = floor(p), f = fract(p); f = f * f * (3.0 - 2.0 * f);
  return mix(mix(h2(i), h2(i + vec2(1.0, 0.0)), f.x), mix(h2(i + vec2(0.0, 1.0)), h2(i + vec2(1.0, 1.0)), f.x), f.y); }
float fbm(vec2 p){ float v = 0.0, a = 0.5; mat2 m = mat2(1.6, 1.2, -1.2, 1.6);
  for (int i = 0; i < 5; i++) { v += a * noise(p); p = m * p; a *= 0.5; } return v; }
float n1(float x){ float i = floor(x), f = fract(x); f = f * f * (3.0 - 2.0 * f); return mix(h1(i), h1(i + 1.0), f); }
float fbm1(float x){ float v = 0.0, a = 0.5; for (int i = 0; i < 5; i++) { v += a * n1(x); x *= 2.03; a *= 0.5; } return v; }
vec3 pal(float t, vec3 a, vec3 b, vec3 c, vec3 d){ return a + b * cos(6.28318 * (c * t + d)); }
float stars(vec2 p){ vec2 g = floor(p), f = fract(p); float r = h2(g); vec2 o = 0.2 + 0.6 * h22(g + 3.1);
  float s = smoothstep(0.07, 0.0, length(f - o)) * step(0.93, r); return s * (0.55 + 0.45 * sin(T * 2.0 + r * 40.0)); }
// Sky colour for a height y (0 horizon .. 1 zenith) at sun elevation e (degrees)
vec3 skyCol(float y, float e){
  float day = smoothstep(-6.0, 10.0, e), gold = exp(-pow((e - 2.0) / 7.0, 2.0));
  vec3 zen = mix(vec3(0.01, 0.02, 0.07), vec3(0.16, 0.38, 0.82), day);
  vec3 hor = mix(vec3(0.05, 0.07, 0.16), vec3(0.62, 0.80, 0.98), day);
  hor = mix(hor, vec3(1.0, 0.52, 0.28), gold * 0.85); zen = mix(zen, vec3(0.32, 0.26, 0.58), gold * 0.45);
  return mix(hor, zen, pow(clamp(y, 0.0, 1.0), 0.6)); }
`;

const GL_FX = {
  "Live Sky": `
float flake(vec2 p, float s){ p *= s; p.y += T * 1.4; p.x += sin(p.y * 0.4 + T * 0.7) * 0.5;
  vec2 g = floor(p); vec2 o = 0.2 + 0.6 * h22(g); return smoothstep(0.1, 0.0, length(fract(p) - o)) * step(0.45, h2(g + 7.0)); }
void main(){
  vec2 uv = gl_FragCoord.xy / R, p = (gl_FragCoord.xy - 0.5 * R) / R.y; float asp = R.x / R.y;
  float day = smoothstep(-6.0, 8.0, E);
  vec3 col = skyCol(uv.y * 1.05, E);
  vec2 sp = vec2(0.22 * asp, clamp(E / 55.0, -0.3, 0.9) * 0.75 - 0.15); float sd = length(p - sp);
  col += day * (vec3(1.0, 0.9, 0.7) * smoothstep(0.055, 0.05, sd) + vec3(1.0, 0.7, 0.4) * exp(-sd * 5.0) * 0.35);
  vec2 mp = vec2(-0.28 * asp, 0.27); float md = length(p - mp);
  col += (1.0 - day) * (vec3(0.92, 0.93, 1.0) * smoothstep(0.045, 0.04, md) * (0.8 + 0.2 * fbm(p * 40.0)) + vec3(0.35, 0.45, 0.8) * exp(-md * 7.0) * 0.25);
  col += (1.0 - day) * (1.0 - W.x) * stars(p * 45.0) * vec3(0.9, 0.95, 1.0);
  vec2 cp = vec2(p.x * 1.1 + T * 0.014, p.y * 2.0 + 0.5);
  float cov = mix(0.22, 0.97, W.x), n = fbm(cp * 2.0 + vec2(0.0, T * 0.004));
  float c = smoothstep(1.0 - cov, 1.0 - cov + 0.32, n) * smoothstep(-0.55, 0.1, p.y + 0.3);
  vec3 lit = mix(vec3(0.10, 0.11, 0.16), vec3(1.0), day);
  lit = mix(lit, vec3(1.0, 0.62, 0.42), exp(-pow((E - 3.0) / 8.0, 2.0)) * 0.75);
  col = mix(col, lit * mix(0.55, 0.85, fbm(cp * 4.5)) * mix(1.0, 0.6, W.y), c * 0.93);
  col = mix(col, mix(vec3(0.12), vec3(0.74, 0.76, 0.8), day), W.w * 0.6);
  vec2 rp = vec2(p.x * 90.0 + p.y * 12.0, p.y * 2.5 + T * 7.0); float rr = step(0.975, h2(floor(rp))) * smoothstep(0.0, 0.7, fract(rp.y));
  col += rr * W.y * 0.35 * mix(vec3(0.35), vec3(0.85), day);
  float sn = flake(p, 9.0) + flake(p + 3.0, 15.0) * 0.7 + flake(p + 7.0, 24.0) * 0.5;
  col += sn * W.z * vec3(1.0);
  gl_FragColor = vec4(col, 1.0);
}`,

  "Ocean Sunset": `
vec3 sunsky(vec3 rd, vec3 sun){ float y = max(rd.y, 0.0);
  vec3 c = mix(vec3(1.0, 0.5, 0.25), vec3(0.25, 0.22, 0.5), pow(y, 0.45)); c = mix(c, vec3(0.05, 0.05, 0.18), smoothstep(0.25, 0.9, y));
  float s = max(dot(rd, sun), 0.0);
  return c + vec3(1.0, 0.55, 0.25) * pow(s, 6.0) * 0.55 + vec3(1.0, 0.85, 0.6) * pow(s, 90.0) * 0.8 + vec3(1.0, 0.95, 0.85) * smoothstep(0.9994, 0.9997, s) * 4.0; }
float wh(vec2 q){ return (fbm(q * 0.35 + vec2(T * 0.15, T * 0.08)) + 0.5 * fbm(q * 0.9 - vec2(T * 0.22, 0.0))) * 0.6; }
void main(){
  vec2 p = (gl_FragCoord.xy - 0.5 * R) / R.y;
  vec3 ro = vec3(0.0, 1.2, 0.0), rd = normalize(vec3(p.x, p.y + 0.03, 1.4)), sun = normalize(vec3(0.0, 0.07, 1.0));
  vec3 col;
  if (rd.y > 0.0) {
    col = sunsky(rd, sun);
    vec2 cp = rd.xz / (rd.y + 0.05) * 0.5 + vec2(T * 0.012, 0.0);
    float c = smoothstep(0.5, 0.85, fbm(cp * 1.3));
    col = mix(col, mix(vec3(0.95, 0.45, 0.35), vec3(0.3, 0.18, 0.32), clamp(rd.y * 3.0, 0.0, 1.0)), c * 0.65 * smoothstep(0.0, 0.08, rd.y));
  } else {
    float t = -ro.y / rd.y; vec2 q = (ro + rd * t).xz; float e = 0.06, h = wh(q);
    vec3 n = normalize(vec3(h - wh(q + vec2(e, 0.0)), e * 1.6, h - wh(q + vec2(0.0, e))));
    n = normalize(mix(n, vec3(0.0, 1.0, 0.0), clamp(t / 70.0, 0.0, 0.92)));
    vec3 rf = reflect(rd, n); rf.y = abs(rf.y);
    float fres = 0.04 + 0.96 * pow(1.0 - max(dot(n, -rd), 0.0), 5.0);
    col = mix(vec3(0.02, 0.05, 0.11), sunsky(rf, sun), fres);
    col += vec3(1.0, 0.7, 0.4) * pow(max(dot(rf, sun), 0.0), 350.0) * 2.5;
    col = mix(col, sunsky(normalize(vec3(rd.x, 0.002, rd.z)), sun), smoothstep(25.0, 140.0, t));
  }
  col = 1.0 - exp(-col * 1.6);
  gl_FragColor = vec4(pow(col, vec3(0.92)), 1.0);
}`,

  "Mountain Lake": `
void main(){
  vec2 uv = gl_FragCoord.xy / R; float asp = R.x / R.y, wl = 0.32;
  vec2 su = uv;
  if (uv.y < wl) { su.y = 2.0 * wl - uv.y; su.x += (noise(vec2(uv.x * 30.0, uv.y * 140.0 - T * 0.9)) - 0.5) * 0.014 * (1.2 - uv.y / wl); }
  float yy = su.y, xx = su.x * asp + T * 0.004, day = smoothstep(-6.0, 8.0, E);
  vec3 col = skyCol((yy - wl) / (1.0 - wl), E);
  col += (1.0 - day) * stars(vec2(xx, yy) * 60.0);
  vec2 mp = vec2(0.78 * asp, 0.8); float md = length(vec2(su.x * asp, yy) - mp);
  col += (1.0 - day) * (vec3(0.95) * smoothstep(0.04, 0.035, md) + vec3(0.4, 0.5, 0.8) * exp(-md * 8.0) * 0.3);
  col += day * vec3(1.0, 0.8, 0.55) * exp(-length(vec2(su.x * asp, yy) - vec2(0.3 * asp, wl + 0.05 + clamp(E, 0.0, 40.0) / 70.0)) * 6.0) * 0.5;
  vec3 fogc = skyCol(0.04, E);
  for (int k = 0; k < 5; k++) {
    float i = float(k);
    float rg = fbm1(xx * (2.4 + i * 1.5) + i * 7.3); rg = 1.0 - abs(rg * 2.0 - 1.0);
    float h = wl + 0.02 + rg * (0.46 - i * 0.075) - i * 0.015;
    if (yy < h) {
      vec3 lc = mix(vec3(0.06, 0.08, 0.14) * (1.0 - i * 0.16), vec3(0.14, 0.2, 0.24) * (1.0 - i * 0.14), day);
      lc = mix(lc, fogc, 0.72 - i * 0.17);
      if (k == 0) lc = mix(lc, mix(vec3(0.35, 0.38, 0.45), vec3(0.96), day), smoothstep(h - 0.07, h - 0.012, yy) * 0.55);
      col = lc;
    }
  }
  if (uv.y < wl) {
    col = col * vec3(0.72, 0.82, 0.88) + skyCol(0.0, E) * 0.06;
    col += vec3(1.0, 0.9, 0.7) * day * smoothstep(0.82, 0.98, noise(vec2(uv.x * 160.0, uv.y * 30.0 + T * 0.6))) * 0.12;
    col = mix(col, col * 0.75, smoothstep(wl * 0.6, 0.0, uv.y));
  }
  gl_FragColor = vec4(col, 1.0);
}`,

  "Nebula": `
void main(){
  vec2 p = (gl_FragCoord.xy - 0.5 * R) / R.y * 1.6; float t = T * 0.015;
  vec2 q = vec2(fbm(p + vec2(0.0, t)), fbm(p + vec2(5.2, 1.3) - t));
  vec2 r = vec2(fbm(p + 3.0 * q + vec2(1.7, 9.2) + t * 0.7), fbm(p + 3.0 * q + vec2(8.3, 2.8) - t * 0.5));
  float f = fbm(p + 3.0 * r);
  vec3 col = mix(vec3(0.05, 0.02, 0.12), vec3(0.78, 0.15, 0.48), clamp(f * f * 2.2, 0.0, 1.0));
  col = mix(col, vec3(0.08, 0.55, 0.88), clamp(length(q) * 0.9 - 0.3, 0.0, 1.0));
  col = mix(col, vec3(1.0, 0.75, 0.4), clamp(r.x * r.x * 1.4 - 0.2, 0.0, 1.0) * 0.7);
  col *= 0.35 + 1.15 * f * f;
  col += stars(p * 55.0) * vec3(0.9, 0.9, 1.0) + stars(p * 23.0 + 3.0) * vec3(1.0, 0.9, 0.8) * 0.7;
  gl_FragColor = vec4(1.0 - exp(-col * 1.8), 1.0);
}`,

  "Galaxy Core": `
void main(){
  vec2 p = (gl_FragCoord.xy - 0.5 * R) / R.y; float a = 0.45;
  vec2 q = mat2(cos(a), -sin(a), sin(a), cos(a)) * p; q.x += T * 0.004;
  float band = exp(-q.y * q.y * 16.0);
  vec2 cq = q - vec2(0.1, 0.0); float core = exp(-dot(cq, cq) * 5.0);
  float dust = fbm(q * vec2(3.0, 9.0) + 3.0) * fbm(q * 7.0);
  vec3 col = vec3(0.01, 0.01, 0.03);
  col += band * mix(vec3(0.25, 0.3, 0.58), vec3(1.0, 0.8, 0.55), core) * (0.5 + 0.8 * fbm(q * vec2(4.0, 10.0)));
  col += core * vec3(1.0, 0.75, 0.5) * 0.6;
  col *= 1.0 - smoothstep(0.25, 0.6, dust) * band * 0.85;
  col += stars(p * 80.0) + stars(p * 35.0 + 7.0) * vec3(0.9, 0.9, 1.0) * 0.8 + band * stars(q * 140.0) * 0.8;
  col += vec3(0.55, 0.2, 0.45) * fbm(q * 2.5 + 9.0) * band * 0.25;
  gl_FragColor = vec4(1.0 - exp(-col * 1.5), 1.0);
}`,

  "Rain Window": `
vec3 city(vec2 uv){
  vec3 c = mix(vec3(0.02, 0.03, 0.07), vec3(0.1, 0.07, 0.16), uv.y);
  for (int i = 0; i < 26; i++) {
    float fi = float(i);
    vec2 pos = vec2(h1(fi * 3.1) * R.x / R.y, h1(fi * 7.7) * 0.85); float r = 0.04 + 0.1 * h1(fi * 1.3);
    vec3 lc = pal(h1(fi * 5.9), vec3(0.6, 0.5, 0.45), vec3(0.4, 0.4, 0.4), vec3(1.0), vec3(0.0, 0.15, 0.25));
    c += lc * smoothstep(r, r * 0.35, length(uv - pos)) * 0.5 * (0.75 + 0.25 * sin(T * 0.5 + fi));
  }
  return c;
}
vec3 drops(vec2 uv, float s, float seed){
  vec2 g = uv * vec2(7.0, 2.6) * s; vec2 id = floor(g); float n = h2(id + seed);
  vec2 f = fract(g) - 0.5; float ph = fract(T * (0.05 + 0.08 * n) + n);
  float y = 0.42 - ph * 0.84 + 0.04 * sin(ph * 18.0 + n * 6.0), x = (n - 0.5) * 0.55 + 0.04 * sin(ph * 9.0 + n * 10.0);
  vec2 d = (f - vec2(x, y)) * vec2(1.0, 1.7);
  float m = smoothstep(0.1, 0.05, length(d)) * step(0.25, n);
  vec2 tf = vec2(f.x - x, fract((f.y - y) * 7.0) - 0.5);
  float trail = smoothstep(0.05, 0.02, length(tf * vec2(1.0, 0.6))) * step(y, f.y) * smoothstep(0.5, 0.0, f.y - y) * step(0.25, n);
  return vec3(d * m * 6.0, max(m, trail * 0.7));
}
void main(){
  vec2 uv = gl_FragCoord.xy / R; vec2 p = vec2(uv.x * R.x / R.y, uv.y);
  vec3 a = drops(p, 1.0, 0.0), b = drops(p * 1.7 + 3.0, 1.0, 9.0);
  vec2 st = p * 40.0; vec2 sg = floor(st); vec2 so = 0.2 + 0.6 * h22(sg);
  float stat = smoothstep(0.12, 0.06, length(fract(st) - so)) * step(0.7, h2(sg));
  float m = clamp(a.z + b.z + stat * 0.6, 0.0, 1.0);
  vec2 off = a.xy + b.xy * 0.8;
  vec3 fogged = city(p) * 0.42 + vec3(0.05, 0.055, 0.08);
  vec3 sharp = city(p - off * 0.16) * 1.5 + 0.02;
  vec3 col = mix(fogged, sharp, m);
  col += vec3(0.85, 0.9, 1.0) * smoothstep(0.55, 1.0, m) * clamp(-off.y * 0.6 + off.x * 0.3, 0.0, 1.0) * 0.35;
  gl_FragColor = vec4(col, 1.0);
}`,

  "Underwater": `
float edges(vec2 p){
  vec2 g = floor(p), f = fract(p); float d1 = 8.0, d2 = 8.0;
  for (int j = -1; j <= 1; j++) for (int i = -1; i <= 1; i++) {
    vec2 b = vec2(float(i), float(j)); vec2 o = h22(g + b); o = 0.5 + 0.4 * sin(T * 0.6 + 6.2831 * o);
    float d = length(b + o - f); if (d < d1) { d2 = d1; d1 = d; } else if (d < d2) d2 = d;
  }
  return d2 - d1;
}
void main(){
  vec2 uv = gl_FragCoord.xy / R, p = (gl_FragCoord.xy - 0.5 * R) / R.y;
  vec3 col = mix(vec3(0.0, 0.07, 0.17), vec3(0.0, 0.45, 0.6), pow(uv.y, 1.4));
  vec2 wp = p + 0.25 * vec2(fbm(p * 2.0 + T * 0.08), fbm(p * 2.0 + 5.0 - T * 0.06));
  float c = pow(smoothstep(0.16, 0.0, edges(wp * 3.6 + vec2(T * 0.05, 0.0))), 2.0) * 0.7 + pow(smoothstep(0.14, 0.0, edges(wp * 6.0 - vec2(0.0, T * 0.04) + 3.0)), 2.0) * 0.45;
  col += vec3(0.45, 0.95, 1.0) * c * (0.25 + 0.75 * uv.y) * 0.55;
  float a = atan(p.x + 0.2, 1.3 - p.y); float rays = fbm(vec2(a * 6.0 + T * 0.05, T * 0.05));
  col += vec3(0.3, 0.7, 0.8) * pow(rays, 3.0) * smoothstep(-0.5, 1.0, p.y) * 0.7;
  vec2 q = p * 12.0; q.y -= T * 0.15; vec2 g = floor(q);
  col += vec3(0.7, 0.9, 1.0) * smoothstep(0.05, 0.0, length(fract(q) - h22(g))) * step(0.7, h2(g + 1.0)) * 0.5;
  col = mix(col, vec3(0.0, 0.03, 0.08), smoothstep(0.35, 0.0, uv.y) * 0.6);
  gl_FragColor = vec4(col, 1.0);
}`,

  "Iridescent": `
void main(){
  vec2 p = (gl_FragCoord.xy - 0.5 * R) / R.y * 1.2; float t = T * 0.05; vec2 q = p;
  for (int i = 0; i < 4; i++) { float fi = float(i); q += 0.35 * vec2(sin(q.y * 1.7 + t * 1.3 + fi), cos(q.x * 1.5 - t * 1.1 + fi * 1.7)); }
  float v = length(q) * 0.6 + fbm(q * 1.2 + t) * 0.5;
  vec3 col = pal(v + t * 0.2, vec3(0.55), vec3(0.45), vec3(1.0), vec3(0.0, 0.33, 0.67));
  col += pow(abs(sin(v * 6.0 + t * 3.0)), 12.0) * 0.25;
  col *= 0.85 + 0.15 * fbm(p * 3.0);
  gl_FragColor = vec4(col, 1.0);
}`,

  "Gradient Mesh": `
void main(){
  vec2 uv = gl_FragCoord.xy / R; float asp = R.x / R.y; vec2 p = uv * vec2(asp, 1.0); float t = T * 0.06;
  vec3 acc = vec3(0.0); float ws = 0.0;
  for (int i = 0; i < 6; i++) {
    float fi = float(i);
    vec2 c = vec2(0.5 * asp, 0.5) + vec2(sin(t * (0.7 + fi * 0.13) + fi * 2.1) * 0.55 * asp, cos(t * (0.6 + fi * 0.11) + fi * 1.3) * 0.45);
    vec3 col = pal(fi / 6.0 + t * 0.03, vec3(0.6, 0.5, 0.6), vec3(0.4, 0.4, 0.35), vec3(1.0), vec3(0.0, 0.2, 0.45));
    float d = length(p - c); float w = 1.0 / (d * d * 4.0 + 0.05); acc += col * w; ws += w;
  }
  vec3 col = acc / ws + (h2(gl_FragCoord.xy + fract(T)) - 0.5) * 0.025;
  gl_FragColor = vec4(col, 1.0);
}`,

  "Dunes": `
float dune(float x, float k){ return 0.5 + 0.5 * sin(x) + 0.25 * sin(x * 2.3 + k) + 0.12 * sin(x * 4.1 + k * 2.0); }
void main(){
  vec2 uv = gl_FragCoord.xy / R; float asp = R.x / R.y, x = uv.x * asp;
  vec3 col = mix(vec3(1.0, 0.62, 0.35), vec3(0.35, 0.4, 0.75), pow(uv.y, 0.8));
  col = mix(col, vec3(0.13, 0.15, 0.4), smoothstep(0.6, 1.0, uv.y));
  float sd = length(vec2(x, uv.y) - vec2(0.62 * asp, 0.56));
  col += vec3(1.0, 0.82, 0.55) * smoothstep(0.07, 0.065, sd) + vec3(1.0, 0.6, 0.3) * exp(-sd * 5.0) * 0.45;
  for (int k = 0; k < 5; k++) {
    float fk = float(k), sx = x * (1.2 + fk * 0.8) + T * 0.01 * (fk + 1.0) + fk * 9.0;
    float h = 0.52 - fk * 0.09 + (dune(sx, fk) - 0.6) * (0.12 - 0.012 * fk);
    if (uv.y < h) {
      float slope = (dune(sx + 0.01, fk) - dune(sx - 0.01, fk)) * 50.0;
      float side = 0.5 + 0.5 * clamp(-slope * 0.6, -1.0, 1.0);
      float depth = smoothstep(0.0, 0.14, h - uv.y);
      vec3 sand = mix(vec3(0.55, 0.24, 0.15), vec3(1.0, 0.74, 0.46), side * (1.0 - depth * 0.45));
      sand += vec3(1.0, 0.85, 0.6) * smoothstep(0.006, 0.0, h - uv.y) * 0.25;
      sand *= mix(0.65, 1.0, fk / 4.0);
      col = mix(sand, vec3(1.0, 0.68, 0.5), 0.55 - fk * 0.13);
    }
  }
  gl_FragColor = vec4(col, 1.0);
}`,

  "Ink": `
void main(){
  vec2 p = (gl_FragCoord.xy - 0.5 * R) / R.y * 1.4; float t = T * 0.02;
  vec2 q = vec2(fbm(p * 1.3 + t), fbm(p * 1.3 + vec2(3.1, 7.4) - t));
  float f = fbm(p * 1.6 + q * 2.2 + vec2(t * 0.6, -t * 0.4));
  float a1 = smoothstep(0.5, 0.75, f), a2 = smoothstep(0.55, 0.8, fbm(p * 1.4 + q * 2.6 + 5.0)), a3 = smoothstep(0.6, 0.85, fbm(p * 2.0 + q * 3.0 + 9.0));
  vec3 col = vec3(0.95, 0.93, 0.89);
  col = mix(col, vec3(0.05, 0.35, 0.45), a1 * 0.85); col = mix(col, vec3(0.78, 0.12, 0.35), a2 * 0.75); col = mix(col, vec3(0.12, 0.12, 0.38), a3 * 0.8);
  col *= 0.97 + 0.03 * noise(gl_FragCoord.xy * 0.7);
  gl_FragColor = vec4(col, 1.0);
}`,

  "Fractal Zoom": `
void main(){
  vec2 p = (gl_FragCoord.xy - 0.5 * R) / R.y; float ph = mod(T * 0.08, 8.0), z = exp(ph);
  vec2 c = vec2(-0.743643887, 0.131825904) + p * 2.5 / z, w = vec2(0.0); float n = 0.0;
  for (int i = 0; i < 140; i++) { w = vec2(w.x * w.x - w.y * w.y, 2.0 * w.x * w.y) + c; if (dot(w, w) > 256.0) break; n += 1.0; }
  vec3 col = vec3(0.0);
  if (n < 139.0) { float sn = n - log2(log2(dot(w, w))) + 4.0; col = pal(sn * 0.025 + T * 0.01, vec3(0.5), vec3(0.5), vec3(1.0), vec3(0.0, 0.1, 0.2)); }
  col *= smoothstep(8.0, 7.6, ph) * smoothstep(0.0, 0.4, ph);
  gl_FragColor = vec4(col, 1.0);
}`,

  "Neon City": `
void main(){
  vec2 uv = gl_FragCoord.xy / R; float asp = R.x / R.y, x = uv.x * asp;
  vec3 col = mix(vec3(0.05, 0.02, 0.12), vec3(0.38, 0.08, 0.36), pow(1.0 - uv.y, 2.0));
  col += vec3(0.95, 0.3, 0.6) * exp(-pow((uv.y - 0.25) * 4.0, 2.0)) * 0.25;
  col += stars(vec2(x, uv.y) * 50.0) * smoothstep(0.5, 0.9, uv.y) * 0.6;
  for (int k = 0; k < 4; k++) {
    float fk = float(k), sc = 16.0 - fk * 3.6, sx = x * sc + T * (0.03 + fk * 0.05) + fk * 31.0;
    float id = floor(sx), fx = fract(sx);
    float h = (0.2 + h1(id + fk * 13.0) * 0.42) * (0.75 + fk * 0.12);
    if (uv.y < h && fx > 0.06 && fx < 0.94) {
      vec3 b = mix(vec3(0.16, 0.08, 0.26), vec3(0.02, 0.01, 0.05), fk / 3.0);
      vec2 wg = vec2(fx * 6.0, uv.y * sc * 4.0); vec2 wi = floor(wg); vec2 wf = fract(wg);
      float lit = step(0.6, h2(wi + id * 7.0 + fk)) * step(0.25, wf.x) * step(wf.x, 0.75) * step(0.3, wf.y) * step(wf.y, 0.7);
      vec3 wc = mix(vec3(1.0, 0.75, 0.4), vec3(0.4, 0.8, 1.0), step(0.75, h2(wi + id * 3.0)));
      b += wc * lit * (0.75 + 0.25 * sin(T * 0.3 + h2(wi + id) * 30.0)) * (0.35 + fk * 0.2);
      b += pal(h1(id * 2.0 + fk), vec3(0.6), vec3(0.4), vec3(1.0), vec3(0.0, 0.33, 0.67)) * smoothstep(0.012, 0.0, abs(uv.y - (h - 0.035))) * step(0.7, h1(id * 5.1)) * 0.9;
      col = b;
    }
  }
  col = mix(col, vec3(0.45, 0.15, 0.45), smoothstep(0.16, 0.0, uv.y) * 0.35);
  col += vec3(0.6, 0.6, 0.85) * 0.18 * step(0.985, h2(floor(vec2(x * 90.0 + uv.y * 14.0, uv.y * 22.0 + T * 30.0))));
  gl_FragColor = vec4(col, 1.0);
}`,

  "Snowy Pines": `
void main(){
  vec2 uv = gl_FragCoord.xy / R; float asp = R.x / R.y; vec2 p = vec2(uv.x * asp, uv.y);
  vec3 col = mix(vec3(0.09, 0.13, 0.3), vec3(0.01, 0.02, 0.07), uv.y);
  float md = length(p - vec2(0.75 * asp, 0.78));
  col += vec3(0.95, 0.95, 1.0) * smoothstep(0.055, 0.05, md) + vec3(0.5, 0.6, 0.9) * exp(-md * 6.0) * 0.35;
  col += stars(p * 70.0) * smoothstep(0.4, 0.8, uv.y);
  for (int k = 0; k < 4; k++) {
    float fk = float(k), sc = 3.0 + (3.0 - fk) * 3.0, sx = p.x * sc + fk * 17.0;
    float id = floor(sx), fx = fract(sx) - 0.5;
    float th = (0.22 + 0.18 * h1(id + fk * 9.0)) * (0.6 + fk * 0.2), base = 0.32 - fk * 0.07;
    float yy = (uv.y - base) / th, tier = fract(yy * 4.0);
    float w = (1.0 - yy) * 0.45 * (0.75 + 0.35 * (1.0 - tier));
    float tree = step(abs(fx), w) * step(0.0, yy) * step(yy, 1.0) * step(0.2, h1(id * 3.3 + fk));
    float ground = step(uv.y, base + 0.015 * sin(p.x * 3.0 + fk));
    if (tree + ground > 0.0) {
      vec3 c = mix(vec3(0.5, 0.58, 0.78), vec3(0.02, 0.04, 0.08), fk / 3.0);
      if (tree < 0.5) c = mix(vec3(0.55, 0.62, 0.82), vec3(0.78, 0.84, 0.97), fk / 3.0);
      else c = mix(c, vec3(0.85, 0.9, 1.0) * (1.0 - fk * 0.15), step(0.85, tier) * 0.6);
      col = c;
    }
  }
  for (int i = 0; i < 3; i++) {
    float fi = float(i), s = 8.0 + fi * 7.0; vec2 q = p * s;
    q.y += T * (0.6 - fi * 0.12) * s * 0.12; q.x += sin(q.y * 0.3 + fi + T * 0.5) * 0.4;
    vec2 g = floor(q);
    col += smoothstep(0.12 - fi * 0.02, 0.0, length(fract(q) - (0.1 + 0.8 * h22(g)))) * step(0.55, h2(g + fi)) * (0.9 - fi * 0.2);
  }
  gl_FragColor = vec4(col, 1.0);
}`,

  "Sakura": `
void main(){
  vec2 uv = gl_FragCoord.xy / R; float asp = R.x / R.y; vec2 p = vec2(uv.x * asp, uv.y);
  vec3 col = mix(vec3(1.0, 0.8, 0.84), vec3(0.5, 0.66, 0.95), pow(uv.y, 0.9));
  col = mix(col, vec3(1.0, 0.93, 0.85), exp(-pow((uv.y - 0.35) * 5.0, 2.0)) * 0.5);
  if (uv.y < 0.3 + 0.06 * sin(p.x * 1.7 + 1.0) + 0.03 * sin(p.x * 4.3)) col = mix(vec3(0.74, 0.58, 0.74), col, 0.45);
  if (uv.y < 0.2 + 0.05 * sin(p.x * 2.3 + 3.0) + 0.02 * sin(p.x * 7.0)) col = vec3(0.52, 0.4, 0.58);
  float canopy = smoothstep(0.55, 0.62, fbm(p * 3.0 + vec2(0.0, T * 0.01)) + (uv.y - 0.72) * 0.9 - (p.x - 0.3) * 0.35);
  col = mix(col, mix(vec3(1.0, 0.62, 0.76), vec3(0.93, 0.38, 0.58), fbm(p * 9.0)), canopy);
  for (int i = 0; i < 3; i++) {
    float fi = float(i), s = 5.0 + fi * 4.0; vec2 q = p * s;
    q += vec2(T * (0.25 + fi * 0.08), T * (0.18 + fi * 0.05)) * s * 0.15; q.x += sin(q.y * 0.7 + T * 0.6 + fi) * 0.3;
    vec2 g = floor(q), d = fract(q) - 0.5 - (h22(g) - 0.5) * 0.5; float a = T * (1.0 + h2(g)) + h2(g) * 6.28;
    d = mat2(cos(a), -sin(a), sin(a), cos(a)) * d;
    float pe = smoothstep(0.1, 0.07, length(d * vec2(1.0, 2.2)));
    col = mix(col, mix(vec3(1.0, 0.72, 0.82), vec3(1.0, 0.9, 0.93), h2(g + 3.0)), pe * step(0.45, h2(g + fi * 3.0)) * (0.95 - fi * 0.15));
  }
  gl_FragColor = vec4(col, 1.0);
}`,

  "Firefly Forest": `
void main(){
  vec2 uv = gl_FragCoord.xy / R; float asp = R.x / R.y; vec2 p = vec2(uv.x * asp, uv.y);
  vec3 col = mix(vec3(0.02, 0.06, 0.08), vec3(0.12, 0.22, 0.3), pow(uv.y, 1.2));
  col += vec3(0.55, 0.35, 0.2) * exp(-pow((uv.y - 0.3) * 3.5, 2.0)) * 0.3;
  for (int k = 0; k < 4; k++) {
    float fk = float(k), sc = 2.5 + (3.0 - fk) * 2.5, sx = p.x * sc + fk * 7.3;
    float id = floor(sx), fx = fract(sx) - 0.5, w = 0.04 + 0.05 * h1(id + fk) + fk * 0.02;
    float trunk = smoothstep(w, w * 0.8, abs(fx + 0.03 * sin(uv.y * 3.0 + id))) * step(0.5, h1(id * 2.7 + fk));
    float can = smoothstep(0.48, 0.56, fbm(vec2(p.x * sc * 0.5 + fk * 3.0, uv.y * 3.0)) + (uv.y - 0.78) * 1.6);
    col = mix(col, mix(vec3(0.09, 0.16, 0.2), vec3(0.0, 0.012, 0.018), fk / 3.0), max(trunk, can) * (0.55 + fk * 0.13));
  }
  col += vec3(0.25, 0.35, 0.35) * smoothstep(0.3, 0.0, uv.y) * (0.4 + 0.3 * fbm(vec2(p.x * 2.0 + T * 0.03, uv.y * 4.0)));
  for (int i = 0; i < 2; i++) {
    float fi = float(i), s = 6.0 + fi * 5.0; vec2 q = p * s, g = floor(q);
    vec2 o = 0.5 + 0.35 * vec2(sin(T * 0.4 * (1.0 + h2(g)) + h2(g) * 6.28), cos(T * 0.33 * (1.0 + h2(g + 1.0)) + h2(g + 2.0) * 6.28));
    float d = length(fract(q) - o), b = pow(0.5 + 0.5 * sin(T * (1.5 + h2(g) * 2.0) + h2(g) * 20.0), 3.0);
    col += vec3(1.0, 0.85, 0.35) * (smoothstep(0.06, 0.0, d) * 1.2 + exp(-d * 12.0) * 0.25) * b * step(0.55, h2(g + 5.0)) * step(uv.y, 0.7);
  }
  gl_FragColor = vec4(col, 1.0);
}`,

  "Stained Glass": `
void main(){
  vec2 p = (gl_FragCoord.xy - 0.5 * R) / R.y * 5.0; vec2 g = floor(p), f = fract(p), id = vec2(0.0); float d1 = 8.0, d2 = 8.0;
  for (int j = -1; j <= 1; j++) for (int i = -1; i <= 1; i++) {
    vec2 b = vec2(float(i), float(j)); vec2 o = h22(g + b); o = 0.5 + 0.35 * sin(T * 0.15 + 6.28 * o);
    float d = length(b + o - f); if (d < d1) { d2 = d1; d1 = d; id = g + b; } else if (d < d2) d2 = d;
  }
  vec3 c = pal(h2(id) + T * 0.01, vec3(0.55, 0.45, 0.5), vec3(0.45, 0.4, 0.4), vec3(1.0), vec3(0.0, 0.25, 0.55));
  vec3 col = c * (0.6 + 0.55 * fbm(p * 0.3 + vec2(T * 0.03, 0.0))) * (1.1 - d1 * 0.4);
  col *= smoothstep(0.02, 0.08, d2 - d1);
  gl_FragColor = vec4(col, 1.0);
}`,

  "Sunbeams": `
void main(){
  vec2 uv = gl_FragCoord.xy / R; float asp = R.x / R.y; vec2 p = vec2(uv.x * asp, uv.y);
  vec2 d = p - vec2(0.75 * asp, 1.15); float ang = atan(d.x, -d.y);
  float rays = fbm(vec2(ang * 9.0, T * 0.04)) * 0.8 + fbm(vec2(ang * 23.0, T * 0.07)) * 0.4;
  rays = pow(rays, 2.0) * smoothstep(1.6, 0.0, length(d));
  vec3 col = mix(vec3(0.04, 0.09, 0.05), vec3(0.25, 0.42, 0.25), uv.y) + vec3(1.0, 0.9, 0.6) * rays * 0.75;
  for (int k = 0; k < 3; k++) {
    float fk = float(k), sc = 1.6 + (2.0 - fk) * 2.0, sx = p.x * sc + fk * 5.0;
    float id = floor(sx), fx = fract(sx) - 0.5, w = 0.05 + 0.06 * h1(id + fk * 3.0) + fk * 0.03;
    float tr = smoothstep(w, w * 0.75, abs(fx + 0.02 * sin(uv.y * 4.0 + id))) * step(0.55, h1(id * 1.7 + fk));
    col = mix(col, vec3(0.03, 0.05, 0.03) * (1.0 + (2.0 - fk) * 0.8), tr * (0.9 - (2.0 - fk) * 0.2));
  }
  float leaves = smoothstep(0.5, 0.6, fbm(p * 4.0 + vec2(T * 0.01, 0.0)) + (uv.y - 0.82) * 2.2);
  col = mix(col, vec3(0.05, 0.12, 0.05) + vec3(0.3, 0.35, 0.1) * rays, leaves * 0.85);
  vec2 q = p * 14.0; q.y -= T * 0.05; vec2 g = floor(q);
  col += vec3(1.0, 0.95, 0.7) * smoothstep(0.05, 0.0, length(fract(q) - h22(g))) * step(0.8, h2(g)) * rays * 2.0;
  gl_FragColor = vec4(col, 1.0);
}`,

  "Ribbons": `
void main(){
  vec2 uv = gl_FragCoord.xy / R, p = (gl_FragCoord.xy - 0.5 * R) / R.y;
  vec3 col = mix(vec3(0.02, 0.01, 0.06), vec3(0.08, 0.03, 0.15), uv.y);
  for (int i = 0; i < 7; i++) {
    float fi = float(i), t = T * (0.15 + fi * 0.02);
    float y = 0.35 * sin(p.x * (1.2 + fi * 0.17) + t + fi * 1.3) * cos(p.x * 0.7 - t * 0.6 + fi) + (fi - 3.0) * 0.06;
    float w = 0.03 + 0.025 * sin(p.x * 2.0 + t * 1.3 + fi), d = abs(p.y - y);
    vec3 c = pal(fi / 7.0 + p.x * 0.15 + T * 0.02, vec3(0.6, 0.5, 0.6), vec3(0.4, 0.45, 0.4), vec3(1.0), vec3(0.0, 0.25, 0.5));
    col += c * (smoothstep(w, 0.0, d) * 0.55 + exp(-d * 18.0) * 0.25);
  }
  gl_FragColor = vec4(1.0 - exp(-col * 1.6), 1.0);
}`,
};

// Weather state -> (cloud cover, rain, snow, fog) for Live Sky
const WX = {
  sunny: [0.08, 0, 0, 0], "clear-night": [0.05, 0, 0, 0], partlycloudy: [0.45, 0, 0, 0], cloudy: [0.88, 0, 0, 0.1],
  fog: [0.7, 0, 0, 0.8], rainy: [0.88, 0.6, 0, 0.15], pouring: [0.97, 1, 0, 0.25], "lightning-rainy": [0.95, 0.9, 0, 0.2],
  lightning: [0.9, 0, 0, 0], snowy: [0.85, 0, 0.8, 0.1], "snowy-rainy": [0.85, 0.4, 0.5, 0.1], hail: [0.9, 0.7, 0, 0.1],
  windy: [0.4, 0, 0, 0], "windy-variant": [0.6, 0, 0, 0], exceptional: [0.5, 0, 0, 0],
};

class GLRunner {
  constructor(canvas) {
    this.cv = canvas;
    this.gl = canvas.getContext("webgl", { antialias: false, alpha: false, depth: false, powerPreference: "low-power" });
    this.progs = {};
    if (!this.gl) return;
    const gl = this.gl;
    this.buf = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, this.buf);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW);
  }

  program(name) {
    if (name in this.progs) return this.progs[name];
    const gl = this.gl;
    const sh = (type, src) => {
      const s = gl.createShader(type);
      gl.shaderSource(s, src);
      gl.compileShader(s);
      if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) throw new Error(`${name}: ${gl.getShaderInfoLog(s)}`);
      return s;
    };
    let prog = null;
    try {
      prog = gl.createProgram();
      gl.attachShader(prog, sh(gl.VERTEX_SHADER, "attribute vec2 a; void main(){ gl_Position = vec4(a, 0.0, 1.0); }"));
      gl.attachShader(prog, sh(gl.FRAGMENT_SHADER, GL_COMMON + GL_FX[name]));
      gl.linkProgram(prog);
      if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) throw new Error(`${name}: ${gl.getProgramInfoLog(prog)}`);
      prog.u = { R: gl.getUniformLocation(prog, "R"), T: gl.getUniformLocation(prog, "T"), E: gl.getUniformLocation(prog, "E"), W: gl.getUniformLocation(prog, "W") };
      prog.a = gl.getAttribLocation(prog, "a");
    } catch (e) {
      console.warn("amoled-saver shader", e.message);
      prog = null;
    }
    this.progs[name] = prog;
    return prog;
  }

  draw(name, t, sunElev, weather) {
    const gl = this.gl, prog = gl && this.program(name);
    if (!prog) return false;
    gl.viewport(0, 0, this.cv.width, this.cv.height);
    gl.useProgram(prog);
    gl.bindBuffer(gl.ARRAY_BUFFER, this.buf);
    gl.enableVertexAttribArray(prog.a);
    gl.vertexAttribPointer(prog.a, 2, gl.FLOAT, false, 0, 0);
    gl.uniform2f(prog.u.R, this.cv.width, this.cv.height);
    gl.uniform1f(prog.u.T, (t / 1000) % 1000);
    gl.uniform1f(prog.u.E, sunElev);
    gl.uniform4f(prog.u.W, weather[0], weather[1], weather[2], weather[3]);
    gl.drawArrays(gl.TRIANGLES, 0, 3);
    return true;
  }
}

const NIGHT = (h) => h >= 23 || h < 7;
const WEATHER_ICONS = {
  "clear-night": "weather-night", cloudy: "weather-cloudy", fog: "weather-fog", hail: "weather-hail",
  lightning: "weather-lightning", "lightning-rainy": "weather-lightning-rainy", partlycloudy: "weather-partly-cloudy",
  pouring: "weather-pouring", rainy: "weather-rainy", snowy: "weather-snowy", "snowy-rainy": "weather-snowy-rainy",
  sunny: "weather-sunny", windy: "weather-windy", "windy-variant": "weather-windy-variant", exceptional: "alert-circle-outline",
};
const HOURS = ["twelve", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven"];
const pad = (n) => String(n).padStart(2, "0");
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

// Fonts load once into the page; without internet the system fonts take over
if (!document.getElementById("amoled-saver-fonts")) {
  const l = document.createElement("link");
  l.id = "amoled-saver-fonts";
  l.rel = "stylesheet";
  l.href = "https://fonts.googleapis.com/css2?family=Inter:wght@100;200;300;500;800&family=Fraunces:ital,opsz,wght@1,9..144,200;1,9..144,300&family=JetBrains+Mono:wght@300;500&display=swap";
  document.head.appendChild(l);
}

class AmoledSaver extends HTMLElement {
  setConfig(config) { this._config = config || {}; }
  get _entity() { return this._config?.entity || STYLE_ENTITY; }
  getCardSize() { return 12; }

  connectedCallback() {
    if (!this.shadowRoot) {
      this.attachShadow({ mode: "open" }).innerHTML = `<style>${CSS}</style><div id="stage"><canvas id="fx"></canvas><canvas id="gl"></canvas><div id="photo"></div><div id="drift"></div></div>`;
      // Taps: the photo buttons tag in Immich; anywhere else dismisses (when the kiosk passes taps through)
      this.shadowRoot.addEventListener("click", (e) => {
        const btn = e.composedPath().find((n) => n.dataset?.act);
        if (btn) { e.stopPropagation(); this._tag(btn.dataset.act); return; }
        const sw = this._config?.dismiss;
        if (sw && this._hass) this._hass.callService("switch", "turn_off", { entity_id: sw }).catch(() => {});
      });
    }
    this._loopBound = (ts) => this._loop(ts);
    this._raf = requestAnimationFrame(this._loopBound);
    this._tick = setInterval(() => this._render(), 1000);
    this._move = setInterval(() => this._drift(), 60000);
    this._drift();
    this._render();
  }

  disconnectedCallback() {
    clearInterval(this._tick);
    clearInterval(this._move);
    cancelAnimationFrame(this._raf);
    this._fxName = null;
    this._unsub?.then((u) => u()).catch(() => {});
    this._unsub = null;
    this._photoStop();
  }

  set hass(hass) {
    this._hass = hass;
    if (!this._unsub && hass.connection) {
      this._notes = {};
      this._unsub = hass.connection.subscribeMessage((ev) => {
        if (ev.type === "removed") for (const id in ev.notifications) delete this._notes[id];
        else Object.assign(this._notes, ev.notifications);
      }, { type: "persistent_notification/subscribe" }).catch(() => null);
    }
  }

  get _style() {
    const q = new URLSearchParams(location.search).get("style");
    const ent = this._hass?.states[this._entity];
    let s = q || ent?.state || "Minimal";
    if (s === "Shuffle") {
      const pool = (ent?.attributes.options || STYLES).filter((o) => STYLES.includes(o) && o !== PHOTOS);
      s = pool[Math.floor(Date.now() / 3600000) % pool.length];
    }
    return STYLES.includes(s) ? s : "Minimal";
  }

  // Moves everything a little every minute so no pixel stays lit in one place
  _drift() {
    const d = this.shadowRoot?.getElementById("drift");
    if (!d) return;
    const r = () => (Math.random() * 2 - 1);
    d.style.transform = this._style === PHOTOS ? "none" : `translate(${r() * 5}vw, ${r() * 6}vh)`;
    this._cornerIdx = ((this._cornerIdx ?? 0) + (Math.random() < 0.2 ? 1 : 0)) % 4;
  }

  // Canvas loop for the animated styles, capped at 30 fps and resolution 1.5x to keep the phone cool
  _loop(ts) {
    this._raf = requestAnimationFrame(this._loopBound);
    if (document.hidden || !this.shadowRoot) return;
    const cv = this.shadowRoot.getElementById("fx");
    const style = this._style;
    if (style === PHOTOS) this._photoStart(); else if (this._ph) this._photoStop();
    const glc = this.shadowRoot.getElementById("gl");
    if (style in GL_FX) {
      if (this._last && ts - this._last < 32) return;
      this._last = ts;
      glc.style.display = "block"; cv.style.display = "none";
      const scale = Math.min(1, this._config?.gl_scale || 0.5), dpr = window.devicePixelRatio || 1;
      const w = Math.max(1, Math.round(glc.clientWidth * dpr * scale)), h = Math.max(1, Math.round(glc.clientHeight * dpr * scale));
      if (glc.width !== w || glc.height !== h) { glc.width = w; glc.height = h; }
      this._glr = this._glr || new GLRunner(glc);
      const st = this._hass?.states || {};
      const elev = Number(st["sun.sun"]?.attributes.elevation ?? (Math.sin(((new Date().getHours() - 6) / 24) * 2 * Math.PI) * 45));
      const wx = WX[st[WEATHER]?.state] || [0.3, 0, 0, 0];
      if (!this._glr.draw(style, ts, elev, wx)) glc.style.display = "none";
      return;
    }
    if (glc.style.display !== "none") glc.style.display = "none";
    if (cv.style.display === "none") cv.style.display = "";
    const fx = FX[style];
    if (!fx) {
      if (this._fxName) { cv.getContext("2d").clearRect(0, 0, cv.width, cv.height); this._fxName = null; }
      return;
    }
    if (this._last && ts - this._last < 32) return;
    const dt = Math.min(100, this._last ? ts - this._last : 33);
    this._last = ts;
    const dpr = Math.min(window.devicePixelRatio || 1, 1.5), w = cv.clientWidth, h = cv.clientHeight;
    if (!w || !h) return;
    if (cv.width !== Math.round(w * dpr) || cv.height !== Math.round(h * dpr)) {
      cv.width = Math.round(w * dpr); cv.height = Math.round(h * dpr); this._fxName = null;
    }
    const c = cv.getContext("2d");
    if (this._fxName !== style) { this._fxState = fx.init(w, h, this); this._fxName = style; }
    c.setTransform(dpr, 0, 0, dpr, 0, 0);
    c.globalCompositeOperation = "source-over";
    c.globalAlpha = 1;
    c.clearRect(0, 0, w, h);
    fx.draw(this._fxState, c, w, h, ts, dt, this);
  }

  _info() {
    const s = this._hass?.states || {};
    const w = s[WEATHER];
    const weather = w && !["unknown", "unavailable"].includes(w.state)
      ? { icon: WEATHER_ICONS[w.state] || "weather-cloudy", temp: Math.round(w.attributes.temperature), unit: w.attributes.temperature_unit || "°" }
      : null;
    const playing = Object.values(s).find((e) => e.entity_id.startsWith("media_player.") && e.state === "playing" && e.attributes.media_title);
    const music = playing ? { title: playing.attributes.media_title, artist: playing.attributes.media_artist || "" } : null;
    const notes = Object.values(this._notes || {}).sort((a, b) => (b.created_at || "").localeCompare(a.created_at || ""));
    return { weather, music, notes };
  }

  // Small pills: weather, now playing, notifications. Kept dim and tiny on purpose.
  _pills(info, mode = "pill") {
    const out = [];
    if (info.weather) out.push(`<span class="${mode}"><ha-icon icon="mdi:${info.weather.icon}"></ha-icon>${info.weather.temp}°</span>`);
    if (info.music) out.push(`<span class="${mode} music"><ha-icon icon="mdi:music-note"></ha-icon>${esc(info.music.title)}${info.music.artist ? ` <i>· ${esc(info.music.artist)}</i>` : ""}</span>`);
    if (info.notes.length) out.push(`<span class="${mode} note"><ha-icon icon="mdi:bell-outline"></ha-icon>${info.notes.length > 1 ? `<b>${info.notes.length}</b> ` : ""}${esc(info.notes[0].title || info.notes[0].message).slice(0, 48)}</span>`);
    return out.join("");
  }

  _render() {
    if (!this.shadowRoot) return;
    const now = new Date();
    const h = now.getHours(), m = now.getMinutes(), sec = now.getSeconds();
    const style = this._style;
    const info = this._info();
    const date = now.toLocaleDateString(undefined, { weekday: "long", month: "long", day: "numeric" });
    const stage = this.shadowRoot.getElementById("stage");
    const animated = style in FX || style in GL_FX;
    const slug = style.toLowerCase().replace(/ /g, "-");
    stage.className = style === PHOTOS ? `photos ${NIGHT(h) ? "night" : ""}`
      : `${animated ? `fx fx-${slug}${style in VIVID_FX || style in GL_FX ? " vivid" : ""}${style in GL_FX ? " gl" : ""}` : slug} ${NIGHT(h) ? "night" : ""}`;
    const html = style === PHOTOS ? this._photos({ h, m, date })
      : animated ? this._fxclock({ h, m, date, info }) : this[`_${style.toLowerCase()}`]({ now, h, m, sec, date, info });
    // Only touch the DOM when something visible changed
    const drift = this.shadowRoot.getElementById("drift");
    if (drift._html !== html) { drift.innerHTML = html; drift._html = html; }
  }

  // Clock drawn over the animated styles: thin, with a black halo so the effect never hurts legibility
  _fxclock({ h, m, date, info }) {
    return `<div class="center"><div class="t">${pad(h)}<span class="colon">:</span>${pad(m)}</div>
      <div class="d">${esc(date)}</div><div class="pills">${this._pills(info)}</div></div>`;
  }

  _minimal({ h, m, date, info }) {
    return `<div class="center"><div class="t">${pad(h)}<span class="colon">:</span>${pad(m)}</div>
      <div class="d">${esc(date)}</div><div class="pills">${this._pills(info)}</div></div>`;
  }

  _stacked({ h, m, date, info }) {
    return `<div class="center"><div class="hh">${pad(h)}</div><div class="mm">${pad(m)}</div>
      <div class="d">${esc(date)}</div><div class="pills">${this._pills(info)}</div></div>`;
  }

  _serif({ h, m, date, info }) {
    return `<div class="center"><div class="t">${h}<span class="colon">:</span>${pad(m)}</div>
      <div class="rule"></div><div class="d">${esc(date)}</div><div class="pills">${this._pills(info, "plain")}</div></div>`;
  }

  _orbit({ h, m, sec, date, info }) {
    const a = (sec / 60) * 2 * Math.PI - Math.PI / 2;
    const x = 150 + 138 * Math.cos(a), y = 150 + 138 * Math.sin(a);
    const arc = (m / 60) * 2 * Math.PI * 138;
    return `<div class="center"><div class="ring">
      <svg viewBox="0 0 300 300"><circle cx="150" cy="150" r="138" class="track"/>
        <circle cx="150" cy="150" r="138" class="progress" stroke-dasharray="${arc} 9999" transform="rotate(-90 150 150)"/>
        <circle cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="5" class="dot"/></svg>
      <div class="inner"><div class="t">${pad(h)}:${pad(m)}</div><div class="d">${esc(date)}</div></div></div>
      <div class="pills">${this._pills(info)}</div></div>`;
  }

  _analog({ h, m, sec, date, info }) {
    const ha = ((h % 12) + m / 60) * 30, ma = (m + sec / 60) * 6, sa = sec * 6;
    const ticks = Array.from({ length: 12 }, (_, i) => `<line x1="150" y1="${i % 3 ? 22 : 14}" x2="150" y2="34" transform="rotate(${i * 30} 150 150)" class="${i % 3 ? "tick" : "tick big"}"/>`).join("");
    return `<div class="center"><svg class="face" viewBox="0 0 300 300">${ticks}
      <line x1="150" y1="150" x2="150" y2="82" class="hand hour" transform="rotate(${ha} 150 150)"/>
      <line x1="150" y1="150" x2="150" y2="44" class="hand min" transform="rotate(${ma} 150 150)"/>
      <line x1="150" y1="168" x2="150" y2="40" class="hand sec" transform="rotate(${sa} 150 150)"/>
      <circle cx="150" cy="150" r="4" class="hub"/></svg>
      <div class="d">${esc(date)}</div><div class="pills">${this._pills(info)}</div></div>`;
  }

  _words({ h, m, date, info }) {
    const five = Math.round(m / 5) * 5;
    const hour = HOURS[(five > 30 ? h + 1 : h) % 12];
    const phrase = { 0: "", 5: "five past", 10: "ten past", 15: "quarter past", 20: "twenty past", 25: "twenty-five past", 30: "half past",
      35: "twenty-five to", 40: "twenty to", 45: "quarter to", 50: "ten to", 55: "five to", 60: "" }[five];
    const end = five === 0 || five === 60 ? "<em>o'clock</em>" : "";
    return `<div class="left"><div class="w dim">it's</div>${phrase ? `<div class="w">${phrase}</div>` : ""}
      <div class="w hi">${hour}</div>${end ? `<div class="w">${end}</div>` : ""}
      <div class="d">${esc(date)} · ${pad(h)}:${pad(m)}</div><div class="pills">${this._pills(info, "plain")}</div></div>`;
  }

  _terminal({ h, m, sec, date, info }) {
    const lines = [`<span class="p">~ $</span> date`, `${esc(date)}, ${pad(h)}:${pad(m)}`];
    if (info.weather) lines.push(`<span class="p">~ $</span> weather`, `${info.weather.temp}° ${esc(this._hass.states[WEATHER].state)}`);
    if (info.music) lines.push(`<span class="p">~ $</span> now-playing`, `${esc(info.music.title)}${info.music.artist ? ` — ${esc(info.music.artist)}` : ""}`);
    lines.push(`<span class="p">~ $</span> notify --count`, `${info.notes.length}${info.notes[0] ? ` · ${esc(info.notes[0].title || "").slice(0, 40)}` : ""}`);
    lines.push(`<span class="p">~ $</span> <span class="cursor ${sec % 2 ? "off" : ""}">▋</span>`);
    return `<div class="left term">${lines.map((l) => `<div>${l}</div>`).join("")}</div>`;
  }

  _corner({ h, m, date, info }) {
    const pos = ["tl", "tr", "br", "bl"][this._cornerIdx || 0];
    return `<div class="corner ${pos}"><div class="t">${pad(h)}:${pad(m)}</div><div class="d">${esc(date)}</div><div class="pills">${this._pills(info, "plain")}</div></div>`;
  }

  // ── Immich photo frame ──
  _photoStart() {
    if (this._ph || !this._hass) return;
    this._ph = { queue: [], cur: null, urls: [] };
    this._photoNext();
    this._photoTimer();
  }

  _photoTimer() {
    clearInterval(this._phTimer);
    this._phTimer = setInterval(() => this._photoNext(), (this._config?.photo_seconds || 20) * 1000);
  }

  _photoStop() {
    clearInterval(this._phTimer);
    this._phTimer = null;
    this._ph?.urls.forEach((u) => URL.revokeObjectURL(u));
    this._ph = null;
    const box = this.shadowRoot?.getElementById("photo");
    if (box) box.innerHTML = "";
  }

  async _photoFill() {
    const ph = this._ph;
    if (!ph || ph.filling || ph.queue.length > 3) return;
    ph.filling = true;
    try { ph.queue.push(...await this._hass.callApi("GET", "immich_frame/next?count=12")); }
    catch (e) { console.warn("immich frame: list", e); }
    ph.filling = false;
  }

  async _photoNext() {
    const ph = this._ph;
    if (!ph || ph.busy) return;
    ph.busy = true;
    try {
      await this._photoFill();
      const item = ph.queue.shift();
      if (!item) return;
      const r = await this._hass.fetchWithAuth(`/api/immich_frame/image/${item.id}${item.original ? "?size=original" : ""}`);
      if (!r.ok) throw new Error(`image ${r.status}`);
      const url = URL.createObjectURL(await r.blob());
      await new Promise((res, rej) => { const im = new Image(); im.onload = res; im.onerror = rej; im.src = url; });
      if (this._ph !== ph) { URL.revokeObjectURL(url); return; }
      const box = this.shadowRoot.getElementById("photo");
      const slide = document.createElement("div");
      slide.className = "slide";
      slide.innerHTML = `<img class="bg" src="${url}"><img class="fg kb${Math.floor(Math.random() * 4)}" src="${url}">`;
      box.appendChild(slide);
      requestAnimationFrame(() => requestAnimationFrame(() => slide.classList.add("in")));
      const old = [...box.children].slice(0, -1);
      setTimeout(() => old.forEach((o) => o.remove()), 2600);
      ph.urls.push(url);
      while (ph.urls.length > 3) URL.revokeObjectURL(ph.urls.shift());
      ph.cur = item;
      this._render();
    } catch (e) {
      console.warn("immich frame", e);
    } finally {
      ph.busy = false;
    }
    this._photoFill();
  }

  async _tag(act) {
    const it = this._ph?.cur;
    if (!it || it.tag || !["keep", "remove"].includes(act)) return;
    it.tag = act;
    this._render();
    try {
      await this._hass.callApi("POST", "immich_frame/tag", { id: it.id, tag: act });
    } catch (e) {
      console.warn("immich frame: tag", e);
      it.tag = null; it.failed = true; this._render();
      return;
    }
    clearInterval(this._phTimer);
    setTimeout(() => { this._photoNext(); this._photoTimer(); }, 1200);
  }

  _photos({ h, m, date }) {
    const it = this._ph?.cur;
    const when = it?.taken ? new Date(it.taken).toLocaleDateString(undefined, { year: "numeric", month: "long", day: "numeric" }) : "";
    let acts = "";
    if (it && it.tag) acts = `<div class="badge ${it.tag}"><ha-icon icon="mdi:${it.tag === "keep" ? "heart" : "delete-outline"}"></ha-icon>${it.tag === "keep" ? "Kept" : "Marked to remove"}</div>`;
    else if (it) acts = `<div class="acts${it.failed ? " failed" : ""}"><button data-act="keep" class="keep"><ha-icon icon="mdi:heart"></ha-icon>Keep</button>
      <button data-act="remove" class="remove"><ha-icon icon="mdi:delete-outline"></ha-icon>Remove</button></div>`;
    return `<div class="ptime"><div class="t">${pad(h)}:${pad(m)}</div><div class="d">${esc(date)}</div></div>
      <div class="pmeta">${when ? `<div class="pw">${esc(when)}</div>` : ""}${it?.place ? `<div class="pp"><ha-icon icon="mdi:map-marker-outline"></ha-icon>${esc(it.place)}</div>` : ""}</div>${acts}`;
  }

  _aurora({ h, m, date, info }) {
    return `<div class="glow g1"></div><div class="glow g2"></div><div class="glow g3"></div>
      <div class="center"><div class="t">${pad(h)}<span class="colon">:</span>${pad(m)}</div><div class="d">${esc(date)}</div>
      <div class="pills">${this._pills(info)}</div></div>`;
  }
}

const CSS = `
:host { position: fixed; inset: 0; z-index: 10; background: #000; color: #e8e8e8; overflow: hidden;
  font-family: Inter, system-ui, sans-serif; -webkit-font-smoothing: antialiased; cursor: none; }
#stage { position: absolute; inset: 0; background: #000; transition: opacity 2s; }
#stage.night { opacity: .55; }
#drift { position: absolute; inset: 0; transition: transform 6s ease-in-out; }
ha-icon { --mdc-icon-size: 1.05em; vertical-align: -0.15em; margin-right: .35em; opacity: .8; }
.center { position: absolute; inset: 0; display: flex; flex-direction: column; align-items: center; justify-content: center; text-align: center; padding: 0 6vw; }
.left { position: absolute; left: 10vw; right: 8vw; top: 50%; transform: translateY(-50%); }
.d { font-size: 4.2vmin; letter-spacing: .18em; text-transform: uppercase; color: #8a8a8a; margin-top: 1.6vh; font-weight: 300; }
.pills { display: flex; flex-wrap: wrap; gap: 2.5vw; justify-content: center; margin-top: 4.5vh; max-width: 88vw; }
.left .pills, .corner .pills { justify-content: flex-start; }
.pill { font-size: 3.6vmin; color: #9a9a9a; border: 1px solid #262626; border-radius: 999px; padding: .55em 1.1em;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 80vw; font-weight: 300; }
.plain { font-size: 3.6vmin; color: #8a8a8a; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 80vw; font-weight: 300; }
.pill i, .plain i { font-style: normal; color: #666; }
.note { color: #c9b27a; border-color: #3a3220; }
.colon { animation: blink 2s steps(1) infinite; }
@keyframes blink { 50% { opacity: .25; } }

#fx, #gl { position: absolute; inset: 0; width: 100%; height: 100%; }
#gl { display: none; }
/* GPU scenes keep their horizon in the middle, so the clock sits in the sky above it, on a soft shade */
.gl .center { justify-content: flex-start; padding-top: 12vh; }
.gl .center::before { content: ""; position: absolute; left: 50%; top: 12vh; width: 120vmin; height: 62vmin; transform: translate(-50%, -18%);
  background: radial-gradient(closest-side, rgba(0,0,0,.32), rgba(0,0,0,0)); z-index: -1; pointer-events: none; }
.gl .center > * { position: relative; }
.gl .t { text-shadow: 0 .3vmin 2.5vmin rgba(0,0,0,.45); }
.fx-ink .t, .fx-ink .d { color: #1c2235; text-shadow: 0 0 2vmin rgba(255,255,255,.6); }
.fx-ink .pill { background: rgba(255,255,255,.55); color: #1c2235; border-color: rgba(0,0,0,.12); }

/* Immich photo frame: blurred fill behind the whole photo, slow Ken Burns, crossfade */
#photo { position: absolute; inset: 0; }
.slide { position: absolute; inset: 0; opacity: 0; transition: opacity 2.4s ease; }
.slide.in { opacity: 1; }
.slide .bg { position: absolute; inset: -6%; width: 112%; height: 112%; object-fit: cover; filter: blur(38px) brightness(.5) saturate(1.2); }
.slide .fg { position: absolute; inset: 0; width: 100%; height: 100%; object-fit: contain; animation: 26s linear forwards; }
.kb0 { animation-name: kb0; } .kb1 { animation-name: kb1; } .kb2 { animation-name: kb2; } .kb3 { animation-name: kb3; }
@keyframes kb0 { from { transform: scale(1.0); } to { transform: scale(1.08) translate(-1.5%, -1%); } }
@keyframes kb1 { from { transform: scale(1.08) translate(1.5%, 1%); } to { transform: scale(1.0); } }
@keyframes kb2 { from { transform: scale(1.02) translate(-1%, 1%); } to { transform: scale(1.09) translate(1.5%, -1%); } }
@keyframes kb3 { from { transform: scale(1.09) translate(0, -1.5%); } to { transform: scale(1.02) translate(0, 1%); } }
.photos .ptime { position: absolute; top: 4vmin; right: 4.5vmin; text-align: right; text-shadow: 0 .3vmin 2vmin rgba(0,0,0,.7); }
.photos .ptime .t { font-size: 11vmin; font-weight: 200; line-height: 1; color: #fff; }
.photos .ptime .d { font-size: 2.6vmin; margin-top: .6vmin; color: rgba(255,255,255,.85); }
.photos .pmeta { position: absolute; left: 4.5vmin; bottom: 4vmin; color: #fff; text-shadow: 0 .3vmin 2vmin rgba(0,0,0,.8); }
.photos .pw { font-size: 4vmin; font-weight: 300; }
.photos .pp { font-size: 2.8vmin; color: rgba(255,255,255,.85); margin-top: .5vmin; }
.photos .acts, .photos .badge { position: absolute; right: 4.5vmin; bottom: 4vmin; display: flex; gap: 2vmin; }
.photos button { all: unset; cursor: pointer; display: flex; align-items: center; gap: 1vmin; font: 500 3vmin Inter, system-ui, sans-serif;
  color: #fff; padding: 1.8vmin 3.4vmin; border-radius: 999px; background: rgba(0,0,0,.38); border: 1px solid rgba(255,255,255,.28);
  backdrop-filter: blur(10px); -webkit-tap-highlight-color: transparent; }
.photos button.keep ha-icon { color: #ff6b8b; } .photos button.remove ha-icon { color: #ffb36b; }
.photos button:active { transform: scale(.96); background: rgba(255,255,255,.2); }
.photos .acts.failed button { border-color: #ff6b6b; }
.photos .badge { font: 500 2.8vmin Inter, system-ui, sans-serif; color: #fff; padding: 1.6vmin 3vmin; border-radius: 999px;
  background: rgba(0,0,0,.38); backdrop-filter: blur(10px); align-items: center; gap: 1vmin; }
.photos .badge.keep ha-icon { color: #ff6b8b; } .photos .badge.remove ha-icon { color: #ffb36b; }
.fx .t { font-size: 24vmin; font-weight: 200; line-height: 1; text-shadow: 0 0 2vmin #000, 0 0 5vmin #000, 0 0 9vmin #000; }
.fx .d { text-shadow: 0 0 2vmin #000, 0 0 4vmin #000; color: #9a9a9a; }
.fx .pill { background: rgba(0,0,0,.72); }
.vivid .t { font-weight: 200; text-shadow: 0 .4vmin 3vmin rgba(0,0,0,.55); }
.vivid .d { color: rgba(255,255,255,.85); text-shadow: 0 .3vmin 2vmin rgba(0,0,0,.6); }
.vivid .pill { background: rgba(0,0,0,.32); border-color: rgba(255,255,255,.18); color: #fff; backdrop-filter: blur(8px); }
.vivid .note { color: #ffe7a8; }
.fx-matrix .t, .fx-matrix .d { font-family: "JetBrains Mono", monospace; font-weight: 300; color: #d8ffe2; }
.fx-matrix .t { font-size: 20vmin; }

/* Minimal: very thin, big */
.minimal .t { font-size: 27vmin; font-weight: 100; letter-spacing: -.02em; line-height: 1; }

/* Stacked: bold numerals with a dim gradient */
.stacked .hh, .stacked .mm { font-size: 42vmin; font-weight: 800; line-height: .86; letter-spacing: -.04em;
  background: linear-gradient(160deg, #7f6bff, #3fc6d9); -webkit-background-clip: text; color: transparent; }
.stacked .mm { background: linear-gradient(160deg, #3fc6d9, #2a5f9e); -webkit-background-clip: text; opacity: .8; }

/* Serif: editorial italic */
.serif { color: #efe6d6; }
.serif .t { font-family: Fraunces, Georgia, serif; font-style: italic; font-weight: 200; font-size: 28vmin; line-height: 1; letter-spacing: .04em; }
.serif .rule { width: 16vw; height: 1px; background: #5a5040; margin: 3vh 0 1vh; }
.serif .d { font-family: Fraunces, Georgia, serif; font-style: italic; text-transform: none; letter-spacing: .02em; color: #a89c88; font-size: 5vmin; }

/* Orbit: seconds circle the time */
.ring { position: relative; width: 82vmin; height: 82vmin; }
.ring svg { position: absolute; inset: 0; width: 100%; height: 100%; }
.track { fill: none; stroke: #161616; stroke-width: 1.5; }
.progress { fill: none; stroke: #2f6f88; stroke-width: 1.5; stroke-linecap: round; }
.dot { fill: #6fd3f0; }
.ring .inner { position: absolute; inset: 0; display: flex; flex-direction: column; align-items: center; justify-content: center; }
.orbit .t { font-size: 17vmin; font-weight: 200; }
.orbit .d { font-size: 3.4vmin; }

/* Analog: hairline hands */
.face { width: 80vmin; height: 80vmin; }
.tick { stroke: #3a3a3a; stroke-width: 1.5; stroke-linecap: round; }
.tick.big { stroke: #8a8a8a; stroke-width: 2.5; }
.hand { stroke-linecap: round; }
.hand.hour { stroke: #e8e8e8; stroke-width: 5; }
.hand.min { stroke: #cfcfcf; stroke-width: 3; }
.hand.sec { stroke: #e2574c; stroke-width: 1.2; }
.hub { fill: #e2574c; }

/* Words */
.words .w { font-size: 13vmin; font-weight: 200; line-height: 1.08; color: #bdbdbd; }
.words .w.dim { color: #4a4a4a; }
.words .w.hi { font-weight: 500; color: #fff; }
.words em { font-style: normal; color: #6a6a6a; }
.words .d { text-transform: none; letter-spacing: .06em; margin-top: 4vh; }

/* Terminal: phosphor green */
.term { font-family: "JetBrains Mono", ui-monospace, monospace; font-weight: 300; font-size: 4.4vmin; line-height: 1.75; color: #5fd38a; }
.term .p { color: #2f7a4c; }
.cursor.off { opacity: 0; }

/* Corner: tiny, wanders between corners */
.corner { position: absolute; max-width: 80vw; }
.corner.tl { top: 8vh; left: 8vw; } .corner.tr { top: 8vh; right: 8vw; text-align: right; }
.corner.br { bottom: 8vh; right: 8vw; text-align: right; } .corner.bl { bottom: 8vh; left: 8vw; }
.corner .t { font-size: 14vmin; font-weight: 200; line-height: 1; }
.corner .d { font-size: 3.2vmin; margin-top: .8vh; }
.corner .pills { margin-top: 1.5vh; flex-direction: column; gap: .6vh; }
.corner.tr .pills, .corner.br .pills { align-items: flex-end; }

/* Aurora: slow drifting light behind thin numerals */
.aurora .t { font-size: 25vmin; font-weight: 100; color: #f2f2f2; }
.glow { position: absolute; width: 90vw; height: 90vw; border-radius: 50%; filter: blur(14vw); opacity: .28; }
.g1 { background: #3b2bbf; left: -30vw; top: 10vh; animation: a1 47s ease-in-out infinite alternate; }
.g2 { background: #0f7f8f; right: -35vw; top: 40vh; animation: a2 61s ease-in-out infinite alternate; }
.g3 { background: #7a1f6a; left: 0; bottom: -40vw; animation: a3 73s ease-in-out infinite alternate; opacity: .18; }
@keyframes a1 { to { transform: translate(40vw, 30vh) scale(1.2); } }
@keyframes a2 { to { transform: translate(-45vw, -25vh) scale(.85); } }
@keyframes a3 { to { transform: translate(30vw, -35vh) scale(1.3); } }
`;

customElements.define("amoled-saver", AmoledSaver);
window.customCards = window.customCards || [];
window.customCards.push({ type: "amoled-saver", name: "Kiosk screensaver" });
