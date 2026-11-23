// Home panel: music and TV now-playing cards, lights, and Jellyfin/Music Assistant libraries.
// Entities come from the card config (see README in this folder); these are placeholders.
let PLAYERS = [["media_player.living_room", "Living room"]];
let LIGHTS = [];
const FAVOURITES = "favourites";
const TABS = [[FAVOURITES, "Favourites"]];
const PAGE = 60;
const NEWEST = "timestamp_added_desc";
const TYPES = [
  ["playlist", "Playlists"],
  ["album", "Albums"],
  ["track", "Tracks"],
  ["artist", "Artists"],
  ["radio", "Radio"],
];
let TV = "media_player.android_tv";
let TV_ADB = "media_player.android_tv_adb";
let TV_REMOTE = "remote.android_tv";
const TV_APPS = [];
// script.tv_vibe plays random relaxing YouTube videos from its pool; running it again skips to another
let VIBE = "script.tv_vibe";
let VIBE_NOW = "input_text.vibe_now";
const TV_SCREENS = {
  "com.google.android.tvlauncher": "Home screen",
  "com.google.android.backdrop": "Screensaver",
  "com.mediatek.wwtv.tvcenter": "HDMI input",
};
// Both desk monitors switch together: Home is the AM5 rig, Work is the Dell mini PC
let MONITORS = [];
let AMP = "";
// Away alarm (script.intruder_alert): armed toggle (shows the phone's mute timer) and a Stop button while it runs
let ALARM_ARMED = "";
let ALARM_ACTIVE = "";
let ALARM_SNOOZE = "";
let AMP_POWER = "";
let WEATHER = "weather.forecast_home";
const STORE_KEY = "home-panel-player";
const TAB_KEY = "home-panel-tab";
const LYRICS_KEY = "home-panel-lyrics";
const REPEAT_NEXT = { off: "all", all: "one", one: "off" };
const clock = (sec) => {
  const t = Math.max(0, Math.round(sec));
  const h = Math.floor(t / 3600);
  return `${h ? h + ":" : ""}${String(Math.floor(t / 60) % 60).padStart(h ? 2 : 1, "0")}:${String(t % 60).padStart(2, "0")}`;
};
const CONDITIONS = { partlycloudy: "Partly cloudy", cloudy: "Cloudy", sunny: "Sunny", "clear-night": "Clear", rainy: "Rain",
  pouring: "Heavy rain", snowy: "Snow", "snowy-rainy": "Sleet", fog: "Fog", hail: "Hail", lightning: "Storm",
  "lightning-rainy": "Storm", windy: "Windy", "windy-variant": "Windy", exceptional: "Exceptional" };

const esc = (v) =>
  String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
// HA sends microseconds, which older Android WebViews can't parse, so keep milliseconds only
const stamp = (iso) => Date.parse(String(iso).replace(/(\.\d{3})\d+/, "$1"));
const live = (s) => s && !["unavailable", "unknown"].includes(s.state);
const on = (s) => s && s.state === "on";

const STYLE = `
:host { display: block; color: var(--primary-text-color); --r: 18px; --gap: 16px;
  --tile: var(--ha-card-background, var(--card-background-color, #1c1c1e));
  --dim: var(--secondary-text-color); --accent: var(--primary-color); }
* { box-sizing: border-box; }
.wrap { max-width: 1240px; margin: 0 auto; padding: 20px 20px 48px; }
header { display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 16px; }
h1 { font-size: 26px; font-weight: 500; margin: 0; letter-spacing: -.5px; }
.sub { color: var(--dim); font-size: 14px; }
h2 { font-size: 13px; font-weight: 600; text-transform: uppercase; letter-spacing: .8px; color: var(--dim); margin: 22px 0 10px; }
/* Wide: music beside TV, tiles beside the poem. Tablet: music alone, then TV and poem, then tiles. Phone: one column.
   The library stays last in every layout because it is a long list. */
.grid { display: grid; gap: 16px; grid-template-columns: minmax(0, 7fr) minmax(0, 5fr); grid-template-areas: "music tv" "tiles poem"; }
.grid > * { min-width: 0; display: flex; flex-direction: column; }
#player { grid-area: music; } #tv { grid-area: tv; } #lights { grid-area: tiles; } #poem { grid-area: poem; }
#player .now { flex: 1; }
@media (max-width: 1180px) {
  .grid { grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); grid-template-areas: "music music" "tv poem" "tiles tiles"; }
}
@media (max-width: 700px) {
  .grid { grid-template-columns: minmax(0, 1fr); grid-template-areas: "music" "tv" "tiles" "poem"; }
}
/* The poem never sets the row height: it shows the lines that fit and fades out the rest */
.poem { flex: 1; min-height: 196px; border-radius: var(--r); background: var(--tile); padding: 16px 20px; display: flex; flex-direction: column; }
.poem .lbl { font-size: 12px; font-weight: 600; text-transform: uppercase; letter-spacing: .8px; color: var(--dim); display: flex; align-items: center; gap: 6px; --mdc-icon-size: 16px; }
.poem .pt { font-size: 17px; font-weight: 500; margin-top: 6px; }
.poem .pa { font-size: 13px; color: var(--dim); margin-top: 2px; }
.poem .tx { flex: 1 1 0; min-height: 3em; overflow: hidden; white-space: pre-line; font-size: 15px; line-height: 1.5; margin-top: 10px; font-family: Georgia, "Times New Roman", serif; }
.poem.clipped .tx { -webkit-mask-image: linear-gradient(#000 70%, transparent); mask-image: linear-gradient(#000 70%, transparent); }
.poem:not(.clipped) .more { display: none; }
.sheet.read { max-width: 560px; } .sheet.read .h { font-size: 19px; } .sheet.read .h2 { font-size: 14px; } .sheet.read .tx { white-space: pre-line; font-size: 16px; line-height: 1.6; margin: 12px 4px 8px; font-family: Georgia, "Times New Roman", serif; }
.poem .more { margin-top: 8px; font-size: 13px; color: var(--accent); align-self: flex-start; }
#lights { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); grid-auto-rows: minmax(56px, 1fr); gap: 10px; }
/* A short last row is filled by stretching the last tile, so the block stays rectangular */
#lights > :last-child:nth-child(4n + 3) { grid-column: span 2; } #lights > :last-child:nth-child(4n + 1) { grid-column: span 4; } #lights > :last-child:nth-child(4n + 2) { grid-column: span 3; }
@media (max-width: 700px) {
  #lights { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  #lights > :last-child { grid-column: auto !important; } #lights > :last-child:nth-child(odd) { grid-column: span 2 !important; }
  #player .chips { flex-wrap: nowrap; overflow-x: auto; scrollbar-width: none; }
  #player .chip { flex: none; }
}
.bar { display: flex; flex-wrap: wrap; align-items: center; gap: 10px 14px; margin: 22px 0 14px; }
.bar .tabs { margin: 0; } .bar .chips { margin: 0 0 0 auto; }
.seg { display: inline-flex; background: var(--tile); border-radius: 999px; padding: 4px; }
.seg button { padding: 8px 22px; border-radius: 999px; font-size: 14px; color: var(--dim); }
.seg button.sel { background: var(--accent); color: var(--text-primary-color, #fff); }
[hidden] { display: none !important; }
button { font: inherit; color: inherit; background: none; border: 0; cursor: pointer; padding: 0; }
.chips { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 12px; }
.chip { padding: 8px 14px; border-radius: 999px; background: var(--tile); font-size: 14px; display: flex; align-items: center; gap: 6px; }
.chip.sel { background: var(--accent); color: var(--text-primary-color, #fff); }
.chip .dot { width: 7px; height: 7px; border-radius: 50%; background: #4cd964; }
.now { position: relative; overflow: hidden; border-radius: var(--r); background: var(--tile); padding: 20px; display: flex; gap: 20px; align-items: center; }
#now { touch-action: pan-y; transition: transform .18s ease-out; }
.now .bg { position: absolute; inset: -40px; background-size: cover; background-position: center; filter: blur(40px) brightness(.45); opacity: .8; }
.now > :not(.bg) { position: relative; }
.art { width: 132px; height: 132px; flex: none; border-radius: 12px; object-fit: cover; background: rgba(127,127,127,.2); display: flex; align-items: center; justify-content: center; --mdc-icon-size: 48px; color: var(--dim); }
.meta { flex: 1; min-width: 0; }
.title { font-size: 20px; font-weight: 500; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.artist { color: var(--dim); font-size: 14px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; margin-top: 2px; }
.has-art .artist { color: rgba(255,255,255,.75); } .has-art .title, .has-art .ctl { color: #fff; }
.ctl { display: flex; align-items: center; gap: 14px; margin-top: 14px; }
.ctl button { display: flex; --mdc-icon-size: 26px; }
.ctl .play { width: 46px; height: 46px; border-radius: 50%; background: var(--accent); color: var(--text-primary-color, #fff); align-items: center; justify-content: center; }
.vol { flex: 1; display: flex; align-items: center; gap: 10px; min-width: 110px; font-size: 13px; --mdc-icon-size: 20px; }
input[type=range] { flex: 1; min-width: 0; accent-color: var(--accent); }
.head { display: flex; align-items: flex-start; gap: 6px; } .head .ti { flex: 1; min-width: 0; }
.head button { display: flex; padding: 4px; --mdc-icon-size: 22px; opacity: .6; } .head button.on { opacity: 1; color: var(--accent); }
.ctl .mode { --mdc-icon-size: 20px; opacity: .5; } .ctl .mode.on { opacity: 1; color: var(--accent); }
/* Timeline and lyrics take the same space, so switching between them doesn't resize the card */
.tl, .lyr { height: 38px; margin-top: 8px; overflow: hidden; }
.tl { display: flex; align-items: center; gap: 8px; font-size: 12px; font-variant-numeric: tabular-nums; opacity: .8; }
.lyr { display: flex; flex-direction: column; justify-content: center; }
.lyr .cur { font-size: 15px; line-height: 20px; font-weight: 500; } .lyr .nx { font-size: 13px; line-height: 18px; opacity: .55; }
.lyr div { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
@media (max-width: 520px) { .now { flex-direction: column; align-items: stretch; } .art { width: 100%; height: 160px; } div.art { display: none; } .ctl { flex-wrap: wrap; } .vol { flex-basis: 100%; } }
.search { width: 100%; padding: 12px 16px; border-radius: 12px; border: 0; background: var(--tile); color: inherit; font: inherit; outline: none; }
.search:focus { box-shadow: 0 0 0 2px var(--accent); }
.tabs { display: flex; flex-wrap: wrap; gap: 6px; margin: 12px 0; }
.tabs button { padding: 6px 12px; border-radius: 999px; font-size: 13px; color: var(--dim); }
.tabs button.sel { background: var(--tile); color: var(--primary-text-color); }
#items h2:first-child { margin-top: 0; }
.items { display: grid; grid-template-columns: repeat(auto-fill, minmax(124px, 1fr)); gap: 12px; }
.item { text-align: left; min-width: 0; position: relative; cursor: pointer; user-select: none; -webkit-user-select: none; -webkit-touch-callout: none; }
.sheet-bg { position: fixed; inset: 0; background: #0008; z-index: 8; display: flex; align-items: flex-end; justify-content: center; }
.sheet { width: 100%; max-width: 420px; background: var(--tile); border-radius: 18px 18px 0 0; padding: 16px; }
.sheet .h { font-weight: 500; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; } .sheet .h2 { font-size: 13px; color: var(--dim); margin-bottom: 8px; }
.sheet button { display: flex; align-items: center; gap: 14px; width: 100%; padding: 13px 4px; font-size: 15px; --mdc-icon-size: 22px; }
.item .cover { width: 100%; aspect-ratio: 1; border-radius: 12px; object-fit: cover; display: flex; align-items: center; justify-content: center; background: var(--tile); color: var(--dim); --mdc-icon-size: 36px; transition: transform .12s; }
.item:hover .cover { transform: scale(1.03); }
.item .n { font-size: 13px; margin-top: 6px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.item .s { font-size: 12px; color: var(--dim); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.empty { color: var(--dim); font-size: 14px; padding: 16px 0; }
.tile { background: var(--tile); border-radius: 14px; padding: 10px 12px; text-align: left; display: flex; align-items: center; gap: 10px; --mdc-icon-size: 20px; min-width: 0; }
.tile .t { min-width: 0; display: flex; flex-direction: column; }
.tile.active { background: var(--accent); color: var(--text-primary-color, #fff); }
.tile .l { font-size: 14px; } .tile .v { font-size: 12px; opacity: .7; }
.tile[disabled] { opacity: .4; cursor: default; }
.sw { margin-left: auto; flex: none; width: 36px; height: 20px; border-radius: 10px; background: rgba(127,127,127,.4); position: relative; transition: background .15s; }
.sw::after { content: ""; position: absolute; top: 2px; left: 2px; width: 16px; height: 16px; border-radius: 50%; background: #fff; transition: left .15s; }
.sw.on { background: var(--accent); } .sw.on::after { left: 18px; } .sw.mid::after { left: 10px; }
.row { display: flex; gap: 12px; overflow-x: auto; padding-bottom: 8px; scrollbar-width: none; }
.row .poster { flex: 0 0 116px; }
.posters { display: grid; grid-template-columns: repeat(auto-fill, minmax(112px, 1fr)); gap: 14px 12px; margin-top: 12px; }
.poster { text-align: left; position: relative; min-width: 0; }
.poster .img { width: 100%; aspect-ratio: 2 / 3; border-radius: 12px; background: var(--tile) center / cover no-repeat; display: flex; align-items: center; justify-content: center; position: relative; overflow: hidden; }
.poster .bar { position: absolute; left: 0; bottom: 0; height: 4px; background: var(--accent); }
.poster .n { font-size: 13px; margin-top: 6px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.poster .s { font-size: 12px; color: var(--dim); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.poster.all .img { color: var(--dim); --mdc-icon-size: 40px; }
.poster.all.open .img { background: var(--accent); color: var(--text-primary-color, #fff); }
.ep { display: flex; flex-direction: column; align-items: flex-start !important; gap: 2px !important; padding: 10px 4px !important; }
.ep span { font-size: 12px; color: var(--dim); }
.sheet { max-height: 80vh; overflow-y: auto; }
.tvc { flex: 1; border-radius: var(--r); background: var(--tile); padding: 20px; display: flex; flex-direction: column; justify-content: center; gap: 14px; }
.tvhead { display: flex; align-items: center; gap: 12px; color: var(--dim); --mdc-icon-size: 24px; } .tvhead .title { color: var(--primary-text-color); }
.tvtop { display: flex; gap: 16px; align-items: center; min-width: 0; }
.tvart { width: 72px; height: 108px; flex: none; border-radius: 10px; background: rgba(127,127,127,.2) center / cover no-repeat; display: flex; align-items: center; justify-content: center; color: var(--dim); --mdc-icon-size: 34px; }
.prog { height: 4px; border-radius: 2px; background: rgba(127,127,127,.3); margin-top: 10px; overflow: hidden; } .prog div { height: 100%; background: var(--accent); }
.time { font-size: 12px; color: var(--dim); margin-top: 4px; }
.tvctl { display: flex; align-items: center; justify-content: center; gap: 14px; flex-wrap: wrap; }
.rnd { width: 42px; height: 42px; border-radius: 50%; display: flex; align-items: center; justify-content: center; background: rgba(127,127,127,.15); --mdc-icon-size: 24px; touch-action: manipulation; }
.rnd:active { background: var(--accent); }
.rnd.big { width: 54px; height: 54px; background: var(--accent); color: var(--text-primary-color, #fff); --mdc-icon-size: 30px; }
.sep { width: 1px; height: 28px; background: rgba(127,127,127,.3); }
.pills { display: flex; flex-wrap: wrap; gap: 8px; }
.pill { display: flex; align-items: center; gap: 6px; padding: 7px 12px; border-radius: 999px; background: rgba(127,127,127,.15); font-size: 13px; --mdc-icon-size: 18px; }
.pill.on { background: var(--accent); color: var(--text-primary-color, #fff); }
.pill .spin { width: 16px; height: 16px; border-width: 2px; }
.spin { width: 22px; height: 22px; border-radius: 50%; border: 2.5px solid rgba(127,127,127,.35); border-top-color: currentColor; animation: spin .8s linear infinite; }
.poster .spin { width: 36px; height: 36px; color: #fff; filter: drop-shadow(0 0 4px #000); }
@keyframes spin { to { transform: rotate(360deg); } }
.remote { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; margin-top: 6px; }
.remote-sheet .remote button { height: 56px; }
.remote button { display: flex; align-items: center; justify-content: center; height: 48px; padding: 0; border-radius: 14px; background: rgba(127,127,127,.15); --mdc-icon-size: 26px; touch-action: manipulation; }
.remote button:active { background: var(--accent); color: var(--text-primary-color, #fff); }
.remote .ok { background: var(--accent); color: var(--text-primary-color, #fff); font-weight: 600; }
.toast { position: fixed; left: 50%; bottom: 24px; white-space: nowrap; transform: translateX(-50%); background: #000c; color: #fff; padding: 10px 16px; border-radius: 10px; font-size: 14px; z-index: 9; }
`;

class HomePanel extends HTMLElement {
  // Card config keys (all optional): players, lights, tv, tv_adb, tv_remote, vibe, vibe_now, monitors,
  // amp, amp_power, alarm_armed, alarm_active, alarm_snooze, weather. Empty string or [] hides a feature.
  setConfig(c = {}) {
    if (c.players) PLAYERS = c.players;
    if (c.lights) LIGHTS = c.lights;
    if (c.monitors) MONITORS = c.monitors;
    if (c.tv !== undefined) TV = c.tv;
    if (c.tv_adb !== undefined) TV_ADB = c.tv_adb;
    if (c.tv_remote !== undefined) TV_REMOTE = c.tv_remote;
    if (c.vibe !== undefined) VIBE = c.vibe;
    if (c.vibe_now !== undefined) VIBE_NOW = c.vibe_now;
    if (c.amp !== undefined) AMP = c.amp;
    if (c.amp_power !== undefined) AMP_POWER = c.amp_power;
    if (c.alarm_armed !== undefined) ALARM_ARMED = c.alarm_armed;
    if (c.alarm_active !== undefined) ALARM_ACTIVE = c.alarm_active;
    if (c.alarm_snooze !== undefined) ALARM_SNOOZE = c.alarm_snooze;
    if (c.weather !== undefined) WEATHER = c.weather;
  }
  getCardSize() { return 12; }
  getGridOptions() { return { columns: "full" }; }

  connectedCallback() {
    this._timer ||= setInterval(() => this._refreshNow(), 5000);
    this._clock ||= setInterval(() => this._tick(), 1000);
    this._resyncTimer ||= setInterval(() => { if (!document.hidden) { this._resync(); this._loadPoem(); } }, 10000);
    // Kiosk screens sleep and pause timers, so catch up as soon as one wakes
    if (!this._onVisible) {
      this._onVisible = () => { if (!document.hidden) this._resync(); };
      document.addEventListener("visibilitychange", this._onVisible);
    }
    if (this.shadowRoot) return;
    this.attachShadow({ mode: "open" }).innerHTML = `<style>${STYLE}</style>
      <div class="wrap">
        <header><h1 id="hello"></h1><div class="sub" id="weather"></div></header>
        <div class="grid">
          <div id="player"><div class="chips" id="chips"></div><div id="now" style="flex:1;display:flex;flex-direction:column"></div></div>
          <div id="tv"></div>
          <div id="lights"></div>
          <div id="poem"></div>
        </div>
        <div class="bar">
          <div class="seg" id="seg"></div>
          <div class="tabs" id="views"></div>
          <div class="tabs" id="tabs"></div>
          <div class="chips" id="devices"></div>
        </div>
        <section id="watch">
          <h2 style="margin-top:0">Continue watching</h2>
          <div class="row" id="cont"></div>
          <div id="browse" hidden>
            <input class="search" id="lq" type="search" placeholder="Search movies and shows" autocomplete="off">
            <div class="posters" id="lib"></div>
          </div>
        </section>
        <section id="music">
          <input class="search" id="q" type="search" placeholder="Search Music Assistant" autocomplete="off">
          <div id="items" style="margin-top:12px"></div>
        </section>
        <div id="end"></div>
      </div>`;
    this._type = FAVOURITES;
    this._img = {};
    this._cache = {};
    this._results = null;
    const root = this.shadowRoot;
    root.addEventListener("click", (e) => this._click(e));
    const items = root.getElementById("items");
    // HA owns the page scroller, so watch for the end of the list instead
    new IntersectionObserver((seen) => { if (seen[0].isIntersecting) this._more(); }, { rootMargin: "400px" })
      .observe(root.getElementById("end"));
    items.addEventListener("contextmenu", (e) => {
      const it = e.composedPath().find((n) => n.classList?.contains("item"));
      if (it) { e.preventDefault(); this._sheet(it.dataset); }
    });
    items.addEventListener("pointerdown", (e) => {
      const it = e.composedPath().find((n) => n.classList?.contains("item"));
      if (!it) return;
      this._press = { x: e.clientX, y: e.clientY, t: setTimeout(() => { this._skipClick = true; this._sheet(it.dataset); }, 500) };
    });
    items.addEventListener("pointermove", (e) => {
      if (this._press && Math.hypot(e.clientX - this._press.x, e.clientY - this._press.y) > 10) clearTimeout(this._press.t);
    });
    for (const ev of ["pointerup", "pointercancel"]) items.addEventListener(ev, () => this._press && clearTimeout(this._press.t));
    root.getElementById("now").addEventListener("input", (e) => {
      if (e.target.id === "vol") root.getElementById("volv").textContent = e.target.value + "%";
      if (e.target.id === "seek") { this._seeking = true; root.getElementById("pos").textContent = clock(e.target.value); }
      this._dragging = true;
    });
    root.getElementById("now").addEventListener("change", (e) => {
      this._dragging = false;
      if (e.target.id === "seek") { this._seeking = false; this._seek(Number(e.target.value)); return; }
      if (e.target.id !== "vol") return;
      this._svc("media_player", "volume_set", { entity_id: this._player, volume_level: e.target.value / 100 });
    });
    root.getElementById("q").addEventListener("input", (e) => {
      const q = e.target.value.trim();
      clearTimeout(this._t);
      this._t = setTimeout(() => this._search(q), 400);
    });
    const now = root.getElementById("now");
    now.addEventListener("pointerdown", (e) => {
      if (e.composedPath()[0].tagName !== "INPUT") this._swipe = { x: e.clientX, y: e.clientY };
    });
    now.addEventListener("pointermove", (e) => {
      if (this._swipe) now.style.transform = `translateX(${(e.clientX - this._swipe.x) * 0.3}px)`;
    });
    now.addEventListener("pointerup", (e) => {
      const start = this._swipe;
      this._swipe = null;
      now.style.transform = "";
      if (!start) return;
      const dx = e.clientX - start.x;
      if (Math.abs(dx) > 60 && Math.abs(dx) > Math.abs(e.clientY - start.y) * 1.5) {
        this._skipClick = true;
        setTimeout(() => { this._skipClick = false; }, 300);
        this._cyclePlayer(dx < 0 ? 1 : -1);
      }
    });
    now.addEventListener("pointercancel", () => { this._swipe = null; now.style.transform = ""; });
    root.getElementById("lq").addEventListener("input", (e) => {
      const q = e.target.value.trim();
      clearTimeout(this._lt);
      this._lt = setTimeout(() => { this._lib.q = q; this._libLoad(true); }, 400);
    });
    this._lib = { parent: "", q: "", items: [], total: 0 };
    this._tab = localStorage.getItem(TAB_KEY) || "watch";
    this._lyricsOn = localStorage.getItem(LYRICS_KEY) === "1";
    this._drawTab();
    this._draw();
    this._load();
    this._loadWatch();
    this._loadPoem();
  }

  disconnectedCallback() {
    clearInterval(this._timer);
    clearInterval(this._clock);
    clearInterval(this._resyncTimer);
    document.removeEventListener("visibilitychange", this._onVisible);
    this._timer = this._clock = this._resyncTimer = this._onVisible = null;
  }

  set hass(hass) {
    this._watchPlayer(hass);
    this._hass = hass;
    this._draw();
    if (!this._entry) this._load();
    if (!this._watch) this._loadWatch();
  }

  get _player() {
    const s = this._hass.states;
    const usable = PLAYERS.filter(([id]) => live(s[id]));
    if (usable.some(([id]) => id === this._sel)) return this._sel;
    const saved = localStorage.getItem(STORE_KEY);
    if (usable.some(([id]) => id === saved)) return saved;
    return (usable.find(([id]) => s[id].state === "playing") || usable[0] || PLAYERS[0])[0];
  }

  _cyclePlayer(step) {
    const s = this._hass.states;
    const ids = PLAYERS.filter(([id]) => live(s[id])).map(([id]) => id);
    if (!ids.length) return;
    this._sel = ids[(ids.indexOf(this._player) + step + ids.length) % ids.length];
    localStorage.setItem(STORE_KEY, this._sel);
    this._draw();
    this._resync();
  }

  _set(id, html) {
    const el = this.shadowRoot.getElementById(id);
    if (el._html !== html) { el.innerHTML = html; el._html = html; }
  }

  _draw() {
    if (!this.shadowRoot || !this._hass) return;
    const s = this._hass.states;
    const w = s[WEATHER];
    const h = new Date().getHours();
    this._set("hello", h < 12 ? "Good morning" : h < 18 ? "Good afternoon" : "Good evening");
    this._set("weather", w ? `${esc(w.attributes.temperature)}${esc(w.attributes.temperature_unit)} \u00b7 ${esc(CONDITIONS[w.state] || w.state)}` : "");
    const cur = this._player;
    this._set("chips", PLAYERS.filter(([id]) => live(s[id])).map(([id, name]) =>
      `<button class="chip ${id === cur ? "sel" : ""}" data-player="${id}">${s[id].state === "playing" ? '<span class="dot"></span>' : ""}${esc(name)}</button>`).join(""));
    this._drawNow(s[cur]);
    const watts = s[AMP_POWER] && live(s[AMP_POWER]) ? `${s[AMP_POWER].state} W` : "";
    this._set("lights", LIGHTS.map(([id, name, icon]) => this._tile(id, name, icon)).join("") +
      (AMP ? this._tile(AMP, "Amp", "mdi:amplifier", watts) : "") + this._deskTile() + this._alarmTiles() +
      `<button class="tile" data-script="script.minden_le"><ha-icon icon="mdi:power"></ha-icon><div class="t"><span class="l">All off</span></div></button>`);
    this._drawTv();
  }

  _drawTv() {
    const s = this._hass.states;
    const tv = s[TV];
    const tvOn = live(tv) && tv.state !== "off";
    const running = (id) => s[id]?.state === "on";
    const n = this._now?.playing ? this._now : null;
    const waking = running("script.tv_wake");
    const appId = tv?.attributes.app_id;
    const appName = tv?.attributes.app_name || "";
    const app = TV_SCREENS[appId] || (appName.includes(".") ? "" : appName);
    const vibing = tvOn && running(VIBE);
    const vibeTitle = vibing && /youtube/i.test(`${appId} ${appName}`) ? s[VIBE_NOW]?.state : "";
    const title = n?.name || (waking ? "Waking\u2026" : !tvOn ? "TV is off" : vibeTitle || app || "TV is on");
    // Other apps can still be playing even when Jellyfin isn't
    const media = n || (tvOn && s[TV_ADB]?.state === "playing" && !(appId in TV_SCREENS));
    const paused = n ? n.paused : s[TV_ADB]?.state !== "playing";
    const rnd = (attr, icon, cls = "") => `<button class="rnd ${cls}" ${attr} aria-label="${icon}"><ha-icon icon="mdi:${icon}"></ha-icon></button>`;
    const pill = (attr, icon, label, busy, active) => `<button class="pill ${active ? "on" : ""}" ${attr}>${busy ? '<div class="spin"></div>' : `<ha-icon icon="${icon}"></ha-icon>`}${label}</button>`;
    const art = n ? this._img[n.id] : null;
    const pct = n?.runtime ? Math.min(100, (n.position / n.runtime) * 100) : 0;
    const volume = `${rnd('data-key="VOLUME_DOWN"', "volume-minus")}
          ${rnd('data-key="VOLUME_MUTE"', "volume-mute")}
          ${rnd('data-key="VOLUME_UP"', "volume-plus")}`;
    const body = media ? `<div class="tvctl">
          ${rnd('data-tv="rewind"', "rewind-10")}
          ${rnd('data-tv="playpause"', paused ? "play" : "pause", "big")}
          ${rnd('data-tv="forward"', "fast-forward-30")}
          ${n ? rnd('data-tv="stop"', "stop") : ""}
          <span class="sep"></span>${volume}
        </div>`
      : tvOn ? `<div class="tvctl">${volume}</div>` : "";
    this._set("tv", `<div class="tvc">
      ${n ? `<div class="tvtop">
        <div class="tvart" ${art ? `style="background-image:url(${art})"` : ""}>${art ? "" : '<ha-icon icon="mdi:television"></ha-icon>'}</div>
        <div class="meta">
          <div class="title">${esc(title)}</div>
          <div class="artist">${esc(n.subtitle || "")}</div>
          <div class="prog"><div style="width:${pct}%"></div></div><div class="time">${clock(n.position)} / ${clock(n.runtime)}${n.paused ? " \u00b7 Paused" : ""}</div>
        </div>
      </div>` : `<div class="tvhead"><ha-icon icon="mdi:television"></ha-icon><div class="title">${esc(title)}</div></div>`}
      ${body}
      <div class="pills">
        ${pill("data-power", "mdi:power", tvOn ? "On" : "Off", waking, tvOn)}
        ${pill("data-pad", "mdi:remote-tv", "Remote")}
        ${pill('data-script="script.tv_to_pc"', "mdi:monitor", "PC", running("script.tv_to_pc"))}
        ${pill('data-script="script.tv_ambient_light"', "mdi:image-filter-hdr", "Ambient", running("script.tv_ambient_light"))}
        ${pill(`data-script="${VIBE}"`, vibing ? "mdi:skip-next" : "mdi:weather-night", vibing ? "Next" : "Vibe", false, vibing)}
        ${TV_APPS.map(([pkg, name, ic]) => pill(`data-app="${pkg}"`, ic, name, running("script.tv_open_app") && this._app === pkg)).join("")}
      </div></div>`);
  }

  async _refreshNow() {
    const tv = this._hass?.states[TV];
    if (document.hidden || !live(tv) || tv.state === "off") {
      if (this._now) { this._now = null; this._drawTv(); }
      return;
    }
    const wasPlaying = this._now?.playing;
    try {
      this._now = await this._hass.callApi("GET", `jellyfin_panel/now?device=${this._device || "tv"}`);
      // A film just ended or stopped, so the history row is out of date
      if (wasPlaying && !this._now.playing) this._loadWatch();
      if (this._now.playing) await this._image(this._now.id);
    } catch (e) { this._now = null; }
    this._drawTv();
  }

  async _tvAction(action) {
    if (!this._now?.playing) {
      const keys = { playpause: "MEDIA_PLAY_PAUSE", rewind: "MEDIA_REWIND", forward: "MEDIA_FAST_FORWARD" };
      return this._key(keys[action]);
    }
    try {
      await this._hass.callApi("POST", "jellyfin_panel/control", { device: this._device || "tv", action });
    } catch (e) { this._toast(e.body?.error || "The TV didn't respond"); }
    setTimeout(() => this._refreshNow(), 800);
  }

  // One poem a day from /local/poems, the same on every screen: day N since "start" picks file N
  async _loadPoem() {
    const d = new Date();
    const today = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
    if (this._poemDay === today || this._poemLoading) return;
    this._poemLoading = true;
    try {
      this._poemMeta ||= await (await fetch("/local/poems/meta.json", { cache: "no-cache" })).json();
      const start = this._poemMeta.start.split("-").map(Number);
      const days = Math.round((new Date(d.getFullYear(), d.getMonth(), d.getDate()) - new Date(start[0], start[1] - 1, start[2])) / 86400000);
      const n = ((days % this._poemMeta.count) + this._poemMeta.count) % this._poemMeta.count;
      this._poem = await (await fetch(`/local/poems/p/${n}.json`)).json();
      this._poemDay = today;
    } catch (e) { this._poem = null; }
    this._poemLoading = false;
    this._drawPoem();
  }

  // The card shows the first lines; the whole poem opens on top, so the dashboard layout never moves
  _drawPoem() {
    const p = this._poem;
    if (!p) return this._set("poem", "");
    this._set("poem", `<div class="poem">
      <div class="lbl"><ha-icon icon="mdi:feather"></ha-icon>Poem of the day</div>
      <div class="pt">${esc(p.title)}</div>
      <div class="pa">${esc(p.author)}${p.year ? ` \u00b7 ${esc(p.year)}` : ""}</div>
      <div class="tx">${esc(p.text.trim())}</div>
      <button class="more" data-poem>Read the whole poem</button>
    </div>`);
    this._fitPoem();
  }

  // Marks the card when the text is cut off, which fades the last line and shows the button
  _fitPoem() {
    const card = this.shadowRoot.querySelector(".poem");
    const tx = card?.querySelector(".tx");
    if (!tx) return;
    card.classList.toggle("clipped", tx.scrollHeight > tx.clientHeight + 2);
    if (!this._poemWatch && window.ResizeObserver) {
      this._poemWatch = new ResizeObserver(() => this._fitPoem());
      this._poemWatch.observe(this.shadowRoot.getElementById("poem"));
    }
  }

  _remoteSheet() {
    this._closeSheet();
    const keys = [["BACK", "arrow-left"], ["DPAD_UP", "chevron-up"], ["HOME", "home"], ["DPAD_LEFT", "chevron-left"], null,
      ["DPAD_RIGHT", "chevron-right"], ["VOLUME_DOWN", "volume-minus"], ["DPAD_DOWN", "chevron-down"], ["VOLUME_UP", "volume-plus"],
      ["VOLUME_MUTE", "volume-mute"], ["MEDIA_PLAY_PAUSE", "play-pause"], ["MENU", "menu"]];
    const bg = document.createElement("div");
    bg.className = "sheet-bg";
    bg.innerHTML = `<div class="sheet remote-sheet"><div class="h">TV remote</div><div class="h2">Tap outside to close</div>
      <div class="remote">${keys.map((k) => k ? `<button data-key="${k[0]}" aria-label="${k[0]}"><ha-icon icon="mdi:${k[1]}"></ha-icon></button>` : '<button class="ok" data-key="DPAD_CENTER">OK</button>').join("")}</div></div>`;
    bg.addEventListener("click", (e) => { if (e.target === bg) this._closeSheet(); });
    this.shadowRoot.append(bg);
    this._sheetEl = bg;
  }

  _poemSheet() {
    const p = this._poem;
    this._closeSheet();
    const bg = document.createElement("div");
    bg.className = "sheet-bg";
    bg.innerHTML = `<div class="sheet read"><div class="h">${esc(p.title)}</div>
      <div class="h2">${esc(p.author)}${p.year ? ` \u00b7 ${esc(p.year)}` : ""}</div>
      <div class="tx">${esc(p.text)}</div></div>`;
    bg.addEventListener("click", (e) => { if (e.target === bg) this._closeSheet(); });
    this.shadowRoot.append(bg);
    this._sheetEl = bg;
  }

  _drawTab() {
    const root = this.shadowRoot;
    this._set("seg", [["watch", "Watch"], ["music", "Music"]].map(([t, n]) =>
      `<button class="${t === this._tab ? "sel" : ""}" data-seg="${t}">${n}</button>`).join(""));
    root.getElementById("watch").hidden = this._tab !== "watch";
    root.getElementById("music").hidden = this._tab !== "music";
    root.getElementById("views").hidden = this._tab !== "watch";
    root.getElementById("devices").hidden = this._tab !== "watch";
    root.getElementById("tabs").hidden = this._tab !== "music";
  }

  async _loadWatch() {
    if (!this._hass || !this.shadowRoot || this._watchLoading) return;
    this._watchLoading = true;
    try {
      this._watch = await this._hass.callApi("GET", "jellyfin_panel/home");
      this._device = this._watch.devices[0]?.id;
    } catch (e) {
      this._watch = { error: true };
    }
    this._watchLoading = false;
    this._drawWatch();
    this._refreshNow();
  }

  _drawWatch() {
    const root = this.shadowRoot;
    const w = this._watch;
    if (w.error) {
      this._set("cont", '<div class="empty">Could not reach Jellyfin.</div>');
      return;
    }
    this._set("devices", w.devices.map((d) => `<button class="chip ${d.id === this._device ? "sel" : ""}" data-device="${d.id}">${esc(d.name)}</button>`).join(""));
    const open = !root.getElementById("browse").hidden;
    this._set("cont", `<button class="poster all ${open ? "open" : ""}" data-browse>
        <div class="img"><ha-icon icon="mdi:view-grid-outline"></ha-icon></div>
        <div class="n">All titles</div><div class="s">${open ? "Tap to hide" : "Whole library"}</div></button>` +
      w.watched.map((i) => this._poster(i)).join(""));
    this._set("views", [{ id: "", name: "All" }, ...w.views].map((v) =>
      `<button class="${open && v.id === this._lib.parent ? "sel" : ""}" data-view="${v.id}">${esc(v.name)}</button>`).join(""));
    this._hydrate(root.getElementById("cont"));
  }

  _poster(i) {
    const kind = i.type === "Series" ? "series" : "item";
    const url = this._img[i.img || i.id];
    return `<button class="poster" data-${kind}="${i.id}" data-pos="${i.position || 0}" data-name="${esc(i.name)}">
      <div class="img" data-img="${i.img || i.id}" style="${url ? `background-image:url(${url})` : ""}">
        ${i.id === this._starting ? '<div class="spin"></div>' : ""}
        ${i.percent ? `<div class="bar" style="width:${i.percent}%"></div>` : ""}
      </div>
      <div class="n">${esc(i.name)}</div><div class="s">${esc(i.subtitle || "")}</div></button>`;
  }

  async _image(id) {
    if (id in this._img) return this._img[id];
    this._img[id] = "";
    try {
      const r = await this._hass.fetchWithAuth(`/api/jellyfin_panel/image/${id}`);
      if (r.ok) this._img[id] = URL.createObjectURL(await r.blob());
    } catch (e) { /* the tile just stays blank */ }
    return this._img[id];
  }

  // Posters need an auth header, so they load through fetch rather than an img src
  _hydrate(root) {
    root.querySelectorAll("[data-img]").forEach(async (el) => {
      const url = await this._image(el.dataset.img);
      if (url) el.style.backgroundImage = `url(${url})`;
    });
  }

  async _libLoad(reset) {
    const lib = this._lib;
    if (lib.loading) { if (reset) lib.again = true; return; }
    if (reset) { lib.items = []; lib.total = Infinity; }
    if (lib.items.length >= lib.total) return;
    lib.loading = true;
    const el = this.shadowRoot.getElementById("lib");
    try {
      const params = new URLSearchParams({ start: lib.items.length, parent: lib.parent, q: lib.q });
      const r = await this._hass.callApi("GET", `jellyfin_panel/library?${params}`);
      lib.items.push(...r.items);
      lib.total = r.total;
      const html = r.items.map((i) => this._poster(i)).join("");
      if (reset) el.innerHTML = html || '<div class="empty">Nothing found.</div>';
      else el.insertAdjacentHTML("beforeend", html);
      this._hydrate(el);
    } catch (e) { this._toast("Could not load the library"); lib.total = 0; }
    lib.loading = false;
    if (lib.again) { lib.again = false; this._libLoad(true); }
  }

  _showLibrary(open) {
    this.shadowRoot.getElementById("browse").hidden = !open;
    this._drawWatch();
    if (open && !this._lib.items.length) this._libLoad(true);
  }

  _pickView(id) {
    const open = !this.shadowRoot.getElementById("browse").hidden;
    if (open && id === this._lib.parent) return this._showLibrary(false);
    this._lib.parent = id;
    this._showLibrary(true);
    this._libLoad(true);
  }

  async _episodes(id, name) {
    this._closeSheet();
    const bg = document.createElement("div");
    bg.className = "sheet-bg";
    bg.innerHTML = `<div class="sheet"><div class="h">${esc(name)}</div><div class="h2">Loading\u2026</div></div>`;
    bg.addEventListener("click", (e) => { if (e.target === bg) this._closeSheet(); });
    this.shadowRoot.append(bg);
    this._sheetEl = bg;
    try {
      const r = await this._hass.callApi("GET", `jellyfin_panel/episodes/${id}`);
      bg.querySelector(".h2").textContent = `${r.items.length} episodes`;
      bg.querySelector(".sheet").insertAdjacentHTML("beforeend", r.items.map((i) =>
        `<button class="ep" data-item="${i.id}" data-pos="${i.position || 0}">${esc(i.name)}<span>${esc(i.subtitle)}${i.percent ? ` \u00b7 ${Math.round(i.percent)}%` : ""}</span></button>`).join(""));
    } catch (e) { bg.querySelector(".h2").textContent = "Could not load episodes"; }
  }

  async _playItem(id, position) {
    if (this._starting) return;
    this._closeSheet();
    this._starting = id;
    this._drawWatch();
    this._toast("Starting on TV\u2026");
    try {
      await this._hass.callApi("POST", "jellyfin_panel/play", { item_id: id, device: this._device, position });
      this._toast("Playing");
    } catch (e) {
      this._toast(e.body?.error || "Could not start it");
    }
    this._starting = null;
    this._drawWatch();
    this._refreshNow();
  }

  // The TV briefly drops off the network in standby, so wait for it rather than fail
  async _key(cmd) {
    for (let i = 0; i < 10; i++) {
      if (live(this._hass.states[TV])) {
        return this._svc("remote", "send_command", { entity_id: TV_REMOTE, command: cmd });
      }
      await new Promise((r) => setTimeout(r, 2000));
    }
    this._toast("The TV isn't responding");
  }

  _tile(id, name, icon, value) {
    const st = this._hass.states[id];
    const ok = live(st);
    return `<button class="tile ${on(st) ? "active" : ""}" data-toggle="${id}" ${ok ? "" : "disabled"}>
      <ha-icon icon="${icon}"></ha-icon><div class="t"><span class="l">${esc(name)}</span><span class="v">${ok ? esc(value || st.state) : "unavailable"}</span></div></button>`;
  }

  _alarmTiles() {
    if (!ALARM_ARMED) return "";
    const s = this._hass.states;
    const armed = s[ALARM_ARMED], snooze = s[ALARM_SNOOZE], ringing = on(s[ALARM_ACTIVE]);
    const until = snooze?.state === "active" && snooze.attributes.finishes_at
      ? new Date(snooze.attributes.finishes_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : "";
    const label = !live(armed) ? "unavailable" : on(armed) ? "Armed" : until ? `Muted until ${until}` : "Off";
    const toggle = `<button class="tile ${on(armed) ? "active" : ""}" data-toggle="${ALARM_ARMED}" ${live(armed) ? "" : "disabled"}>
      <ha-icon icon="mdi:${on(armed) ? "shield-home" : "shield-off-outline"}"></ha-icon><div class="t"><span class="l">Away alarm</span><span class="v">${label}</span></div></button>`;
    // The test button lives on the Overview dashboard (script.intruder_alert_test); here only a Stop while an alarm runs
    const test = ringing
      ? `<button class="tile active" data-script="script.intruder_alert_stop"><ha-icon icon="mdi:alarm-light-off"></ha-icon><div class="t"><span class="l">Stop alarm</span><span class="v">Alarm running</span></div></button>`
      : "";
    return toggle + test;
  }

  get _desk() {
    const s = this._hass.states;
    if (!MONITORS.length || !MONITORS.every(([id]) => live(s[id]))) return null;
    const actual = MONITORS.every(([id, home]) => s[id].state === home) ? "Home"
      : MONITORS.every(([id, , work]) => s[id].state === work) ? "Work" : "Mixed";
    // The monitors take several seconds to report a new input, so show the requested one meanwhile
    const p = this._deskPending;
    if (p && p.to !== actual && Date.now() < p.until) return p.to;
    this._deskPending = null;
    return actual;
  }

  // The monitor inputs come from the Dell, so the switch is off while it sleeps at night
  _deskTile() {
    const desk = this._desk;
    return `<button class="tile" role="switch" aria-checked="${desk === "Work"}" data-desk ${desk ? "" : "disabled"}>
      <ha-icon icon="mdi:${desk === "Work" ? "briefcase-outline" : "desktop-tower-monitor"}"></ha-icon>
      <div class="t"><span class="l">Monitors</span><span class="v">${desk || "Dell is off"}</span></div>
      <span class="sw ${desk === "Work" ? "on" : desk === "Mixed" ? "mid" : ""}"></span></button>`;
  }

  // Anything but a clean Home setup switches to Home, so a mixed state is one tap from fixed
  _switchDesk() {
    if (!this._desk) return;
    const toWork = this._desk === "Home";
    this._deskPending = { to: toWork ? "Work" : "Home", until: Date.now() + 20000 };
    for (const [id, home, work] of MONITORS) this._svc("select", "select_option", { entity_id: id, option: toWork ? work : home });
    this._draw();
    this._toast(toWork ? "Monitors to Work (Dell)" : "Monitors to Home (AM5)");
  }

  _drawNow(p) {
    if (!p) return this._set("now", "");
    const a = p.attributes;
    // MA's image URLs are LAN-only, so load them through HA's proxy
    const pic = a.entity_picture_local || "";
    const vol = Math.round((a.volume_level ?? 0) * 100);
    const playing = p.state === "playing";
    const hasMedia = !!a.media_title;
    const uri = a.media_content_id;
    if (hasMedia && uri !== this._track?.uri) this._trackChanged(p);
    const fav = this._track?.fav;
    const repeat = a.repeat || "off";
    const timeline = !hasMedia || !a.media_duration ? ""
      : this._lyricsOn ? '<div class="lyr" id="lyr"></div>'
      : `<div class="tl"><span id="pos"></span><input id="seek" type="range" min="0" max="${Math.round(a.media_duration)}" step="1"><span>${clock(a.media_duration)}</span></div>`;
    const html = `<div class="now ${pic ? "has-art" : ""}">
      ${pic ? `<div class="bg" style="background-image:url('${esc(pic)}')"></div><img class="art" src="${esc(pic)}" alt="">` : '<div class="art"><ha-icon icon="mdi:music"></ha-icon></div>'}
      <div class="meta">
        <div class="head"><div class="ti">
          <div class="title">${esc(hasMedia ? a.media_title : "Nothing playing")}</div>
          <div class="artist">${esc(hasMedia ? [a.media_artist, a.media_album_name].filter(Boolean).join(" \u00b7 ") : a.friendly_name)}</div></div>
          ${hasMedia ? `<button class="${fav ? "on" : ""}" data-like aria-label="Like"><ha-icon icon="mdi:${fav ? "heart" : "heart-outline"}"></ha-icon></button>
          <button class="${this._lyricsOn ? "on" : ""}" data-lyrics aria-label="Lyrics"><ha-icon icon="mdi:microphone-variant"></ha-icon></button>` : ""}
        </div>
        <div class="ctl">
          <button class="mode ${a.shuffle ? "on" : ""}" data-shuffle aria-label="Shuffle"><ha-icon icon="mdi:shuffle-variant"></ha-icon></button>
          <button data-act="media_previous_track" aria-label="Previous"><ha-icon icon="mdi:skip-previous"></ha-icon></button>
          <button class="play" data-act="media_play_pause" aria-label="Play or pause"><ha-icon icon="mdi:${playing ? "pause" : "play"}"></ha-icon></button>
          <button data-act="media_next_track" aria-label="Next"><ha-icon icon="mdi:skip-next"></ha-icon></button>
          <button class="mode ${repeat !== "off" ? "on" : ""}" data-repeat aria-label="Repeat ${repeat}"><ha-icon icon="mdi:${repeat === "one" ? "repeat-once" : repeat === "all" ? "repeat" : "repeat-off"}"></ha-icon></button>
          <div class="vol"><ha-icon icon="mdi:volume-high"></ha-icon><input id="vol" type="range" min="0" max="100" value="${vol}"><span id="volv">${vol}%</span></div>
        </div>
        ${timeline}
      </div></div>`;
    if (!this._dragging) { this._set("now", html); this._tick(); }
  }

  // HA rounds the position down to whole seconds and old tablets miss some of its updates,
  // so ask MA's queue, which answers with the exact position at that moment
  _watchPlayer(hass) {
    if (!this._hass) return;
    const before = this._hass.states[this._player];
    const now = hass.states[this._player];
    if (!now || !before) return;
    const key = (s) => [s.state, s.attributes.media_content_id, s.attributes.media_position_updated_at].join("|");
    if (key(before) !== key(now)) this._resync(500);
  }

  _resync(delay = 0) {
    clearTimeout(this._syncT);
    this._syncT = setTimeout(async () => {
      if (!this._hass || this._syncing) return;
      const entity = this._player;
      this._syncing = true;
      const sent = Date.now();
      try {
        const r = await this._hass.callWS({ type: "call_service", domain: "music_assistant", service: "get_queue",
          service_data: { entity_id: entity }, return_response: true });
        const q = r.response?.[entity];
        const uri = q?.current_item?.media_item?.uri;
        // Count from halfway through the round trip, on this device's own clock
        if (uri && typeof q.elapsed_time === "number") this._sync = { entity, uri, pos: q.elapsed_time, at: (sent + Date.now()) / 2 };
      } catch (e) { this._sync = null; }
      this._syncing = false;
      this._tick();
    }, delay);
  }

  // Where the song is now: from MA's last answer if it fits, otherwise from HA's state
  _position() {
    const p = this._hass.states[this._player];
    const a = p?.attributes || {};
    if (a.media_position == null) return 0;
    const playing = p.state === "playing";
    const s = this._sync;
    let pos;
    if (s && s.entity === this._player && s.uri === a.media_content_id && Date.now() - s.at < 30000) {
      pos = s.pos + (playing ? (Date.now() - s.at) / 1000 : 0);
    } else {
      pos = a.media_position;
      const at = stamp(a.media_position_updated_at);
      if (playing && Number.isFinite(at)) pos += Math.max(0, Date.now() - at) / 1000;
    }
    if (this._fix?.uri === a.media_content_id) pos += this._fix.d;
    return Math.max(0, Math.min(pos, a.media_duration || pos));
  }

  // Runs every second: moves the timeline and the lyric line without redrawing the card
  _tick() {
    const root = this.shadowRoot;
    if (!root || !this._hass) return;
    const pos = this._position();
    const seek = root.getElementById("seek");
    if (seek && !this._seeking) { seek.value = Math.round(pos); root.getElementById("pos").textContent = clock(pos); }
    const lyr = root.getElementById("lyr");
    if (!lyr) return;
    const lines = this._track?.lyrics;
    let html;
    if (lines === undefined) html = '<div class="nx">Loading lyrics\u2026</div>';
    else if (!lines) html = '<div class="nx">No synced lyrics found</div>';
    else {
      let i = -1;
      while (i + 1 < lines.length && lines[i + 1][0] <= pos + 0.3) i++;
      html = `<div class="cur">${esc(i >= 0 ? lines[i][1] || "\u266b" : "\u266b")}</div><div class="nx">${esc(lines[i + 1]?.[1] || "")}</div>`;
    }
    if (lyr._html !== html) { lyr.innerHTML = html; lyr._html = html; }
  }

  _trackChanged(p) {
    const a = p.attributes;
    const track = { uri: a.media_content_id, fav: false };
    this._track = track;
    this._fix = null;
    // MA's queue knows whether the song is already a favourite
    this._hass.callWS({ type: "call_service", domain: "music_assistant", service: "get_queue",
      service_data: { entity_id: p.entity_id }, return_response: true }).then((r) => {
      const item = r.response?.[p.entity_id]?.current_item?.media_item;
      if (this._track === track && item?.uri === track.uri) { track.fav = !!item.favorite; this._draw(); }
    }).catch(() => {});
    if (this._lyricsOn) this._loadLyrics(track, a);
  }

  async _loadLyrics(track, a) {
    if (track.lyrics !== undefined || track.lyricsLoading) return;
    track.lyricsLoading = true;
    const base = "https://lrclib.net/api/";
    const q = { artist_name: a.media_artist || "", track_name: a.media_title || "", album_name: a.media_album_name || "", duration: Math.round(a.media_duration || 0) };
    let synced = null;
    try {
      let r = await fetch(base + "get?" + new URLSearchParams(q));
      let d = r.ok ? await r.json() : null;
      if (!d?.syncedLyrics) {
        // Album names and lengths often differ between Tidal and LRCLIB, so fall back to a search
        r = await fetch(base + "search?" + new URLSearchParams({ artist_name: q.artist_name, track_name: q.track_name }));
        const list = r.ok ? await r.json() : [];
        d = list.filter((x) => x.syncedLyrics).sort((x, y) => Math.abs(x.duration - q.duration) - Math.abs(y.duration - q.duration))[0];
      }
      if (d?.syncedLyrics) {
        synced = d.syncedLyrics.split("\n").map((l) => l.match(/^\[(\d+):(\d+(?:\.\d+)?)\]\s*(.*)$/))
          .filter(Boolean).map((m) => [Number(m[1]) * 60 + Number(m[2]), m[3]]);
      }
    } catch (e) { /* offline or blocked: show "not found" */ }
    track.lyrics = synced && synced.length ? synced : null;
    this._tick();
  }

  // MA's per-player button adds the playing song to the library favourites; HA has no way to remove one
  _like() {
    if (!this._track) return;
    if (this._track.fav) return this._toast("Already in your favourites");
    this._svc("button", "press", { entity_id: this._player.replace("media_player.", "button.") + "_favorite_current_song" });
    this._track.fav = true;
    delete this._cache[FAVOURITES];
    this._toast("Added to favourites");
    this._draw();
  }

  _seek(to) {
    const p = this._hass.states[this._player];
    const uri = p?.attributes.media_content_id;
    this._fix = null;
    this._svc("media_player", "media_seek", { entity_id: this._player, seek_position: to });
    // Some players (the Pi) report the wrong position after a seek, so correct it from what was asked for
    const asked = Date.now();
    setTimeout(() => {
      const now = this._hass.states[this._player];
      if (now?.attributes.media_content_id !== uri) return;
      this._fix = null;
      const expected = to + (now.state === "playing" ? (Date.now() - asked) / 1000 : 0);
      const d = expected - this._position();
      if (Math.abs(d) > 2) this._fix = { uri, d };
    }, 4000);
  }

  _drawLibrary() {
    this._set("tabs", this._results ? "" : [...TABS, ...TYPES].map(([t, n]) =>
      `<button class="${t === this._type ? "sel" : ""}" data-type="${t}">${n}</button>`).join(""));
    if (this._results) {
      const groups = TYPES.map(([t, n]) => [n, this._results[t + "s"] || this._results[t] || []]).filter(([, l]) => l.length);
      this._set("items", groups.length
        ? groups.map(([n, l]) => `<h2>${n}</h2>${this._grid(l)}`).join("")
        : '<div class="empty">No results.</div>');
      return;
    }
    const list = this._cache[this._type]?.items;
    this._set("items", !list ? '<div class="empty">Loading\u2026</div>'
      : list.length ? this._grid(list)
      : '<div class="empty">Nothing here yet.</div>');
  }

  _grid(list) {
    return `<div class="items">${list.map((it) => {
      const sub = (it.artists || []).map((x) => x.name).join(", ") || it.album?.name || "";
      const data = `data-uri="${esc(it.uri)}" data-kind="${esc(it.media_type)}" data-name="${esc(it.name)}" data-sub="${esc(sub)}"`;
      const img = typeof it.image === "string" ? it.image : it.image?.path;
      return `<div class="item" role="button" ${data}>
        ${img ? `<img class="cover" loading="lazy" src="${esc(img)}" alt="">` : '<div class="cover"><ha-icon icon="mdi:music-note"></ha-icon></div>'}
        <div class="n">${esc(it.name)}</div><div class="s">${esc(sub)}</div></div>`;
    }).join("")}</div>`;
  }

  async _ws(service, data) {
    const r = await this._hass.callWS({ type: "call_service", domain: "music_assistant", service,
      service_data: { config_entry_id: this._entry, ...data }, return_response: true });
    return r.response;
  }

  async _load() {
    if (!this._hass || this._loading) return;
    this._loading = true;
    try {
      if (!this._entry) {
        const entries = await this._hass.callWS({ type: "config_entries/get", domain: "music_assistant" });
        this._entry = entries[0]?.entry_id;
      }
      await this._favourites(this._type);
    } finally { this._loading = false; }
  }

  async _favourites(type) {
    this._type = type;
    this._drawLibrary();
    if (!this._cache[type]) {
      try {
        if (type === FAVOURITES) {
          const parts = await Promise.all(TYPES.map(([t]) =>
            this._ws("get_library", { media_type: t, favorite: true, limit: 100, order_by: NEWEST })));
          this._cache[type] = { items: parts.flatMap((r) => r.items || []), done: true };
        } else {
          const r = await this._ws("get_library", { media_type: type, limit: PAGE, order_by: NEWEST });
          const got = r.items || [];
          this._cache[type] = { items: got, done: got.length < PAGE };
        }
      } catch (e) { this._cache[type] = { items: [], done: true }; this._toast("Could not load library"); }
    }
    if (type === this._type) this._drawLibrary();
  }

  async _more() {
    if (this._tab === "watch") {
      if (!this.shadowRoot.getElementById("browse").hidden) this._libLoad(false);
      return;
    }
    const c = this._cache[this._type];
    if (this._results || !c || c.done || this._paging) return;
    const type = this._type;
    this._paging = true;
    try {
      const r = await this._ws("get_library", { media_type: type, limit: PAGE, offset: c.items.length, order_by: NEWEST });
      const got = r.items || [];
      c.items.push(...got);
      c.done = got.length < PAGE;
      if (type === this._type && got.length) {
        const el = this.shadowRoot.getElementById("items");
        el.querySelector(".items").insertAdjacentHTML("beforeend", this._grid(got).replace(/^<div class="items">|<\/div>$/g, ""));
        el._html = null;
      }
    } catch (e) { this._toast("Could not load more"); } finally { this._paging = false; }
  }

  _play(d, opts) {
    const name = PLAYERS.find(([id]) => id === this._player)?.[1];
    this._svc("music_assistant", "play_media", { entity_id: this._player, media_id: d.uri, media_type: d.kind, ...opts });
    this._toast(`${opts.enqueue === "next" ? "Up next on" : opts.enqueue === "add" ? "Queued on" : "Playing on"} ${name}`);
  }

  _sheet(d) {
    this._closeSheet();
    const radio = d.kind !== "radio";
    const row = (act, icon, label) => `<button data-sheet="${act}"><ha-icon icon="${icon}"></ha-icon>${label}</button>`;
    const bg = document.createElement("div");
    bg.className = "sheet-bg";
    bg.innerHTML = `<div class="sheet"><div class="h">${esc(d.name)}</div><div class="h2">${esc(d.sub)}</div>
      ${radio ? row("radio", "mdi:radio-tower", "Start radio") : ""}
      ${row("now", "mdi:play", "Play only this")}
      ${row("next", "mdi:playlist-play", "Play next")}
      ${row("add", "mdi:playlist-plus", "Add to queue")}</div>`;
    bg.addEventListener("click", (e) => {
      const act = e.composedPath().find((n) => n.dataset?.sheet)?.dataset.sheet;
      if (act === "radio") this._play(d, { enqueue: "replace", radio_mode: true });
      if (act === "now") this._play(d, { enqueue: "replace" });
      if (act === "next") this._play(d, { enqueue: "next" });
      if (act === "add") this._play(d, { enqueue: "add" });
      this._closeSheet();
    });
    this.shadowRoot.append(bg);
    this._sheetEl = bg;
  }

  _closeSheet() { this._sheetEl?.remove(); this._sheetEl = null; }

  async _search(q) {
    if (!q) { this._results = null; this._drawLibrary(); return; }
    this._qId = (this._qId || 0) + 1;
    const id = this._qId;
    try {
      const r = await this._ws("search", { name: q, limit: 20 });
      if (id === this._qId) { this._results = r; this._drawLibrary(); }
    } catch (e) { this._toast("Search failed"); }
  }

  _svc(domain, service, data) {
    return this._hass.callService(domain, service, data).catch((e) => this._toast(e.message || "Action failed"));
  }

  _toast(msg) {
    const t = document.createElement("div");
    t.className = "toast";
    t.textContent = msg;
    this.shadowRoot.append(t);
    setTimeout(() => t.remove(), 2500);
  }

  _click(e) {
    if (this._skipClick) { this._skipClick = false; return; }
    const b = e.composedPath().find((n) => n.dataset && (n.tagName === "BUTTON" || n.classList?.contains("item")));
    if (!b) return;
    const d = b.dataset;
    if (d.player) { this._sel = d.player; localStorage.setItem(STORE_KEY, d.player); this._draw(); this._resync(); }
    else if (d.act) this._svc("media_player", d.act, { entity_id: this._player });
    else if ("shuffle" in d) this._svc("media_player", "shuffle_set", { entity_id: this._player, shuffle: !this._hass.states[this._player].attributes.shuffle });
    else if ("repeat" in d) this._svc("media_player", "repeat_set", { entity_id: this._player, repeat: REPEAT_NEXT[this._hass.states[this._player].attributes.repeat] || "all" });
    else if ("like" in d) this._like();
    else if ("lyrics" in d) {
      this._lyricsOn = !this._lyricsOn;
      localStorage.setItem(LYRICS_KEY, this._lyricsOn ? "1" : "0");
      if (this._lyricsOn && this._track) this._loadLyrics(this._track, this._hass.states[this._player].attributes);
      this._draw();
    }
    else if (d.type) this._favourites(d.type);
    // A tapped track keeps going as a radio; albums and playlists queue themselves
    else if (d.uri) this._play(d, { enqueue: "replace", ...(d.kind === "track" ? { radio_mode: true } : {}) });
    else if (d.toggle) this._svc("homeassistant", "toggle", { entity_id: d.toggle });
    else if ("desk" in d) this._switchDesk();
    else if (d.script) this._svc("script", "turn_on", { entity_id: d.script });
    else if (d.app) { this._app = d.app; this._svc("script", "tv_open_app", { package: d.app }); }
    else if (d.item) this._playItem(d.item, Number(d.pos) || 0);
    else if (d.series) this._episodes(d.series, d.name);
    else if (d.tv) this._tvAction(d.tv);
    else if (d.seg) { this._tab = d.seg; localStorage.setItem(TAB_KEY, d.seg); this._drawTab(); }
    else if ("poem" in d) this._poemSheet();
    else if ("browse" in d) this._showLibrary(this.shadowRoot.getElementById("browse").hidden);
    else if ("view" in d) this._pickView(d.view);
    else if ("pad" in d) this._remoteSheet();
    else if (d.device) { this._device = d.device; this._drawWatch(); }
    else if (d.key) this._key(d.key);
    else if ("power" in d) {
      const tv = this._hass.states[TV];
      if (live(tv) && tv.state !== "off") this._svc("media_player", "turn_off", { entity_id: TV });
      else this._svc("script", "turn_on", { entity_id: "script.tv_wake" });
    }
  }
}

customElements.define("home-panel", HomePanel);
window.customCards = window.customCards || [];
window.customCards.push({ type: "home-panel", name: "Home panel" });
