/* Browser-control regression without installing dependencies. Run with node --test. */
"use strict";
const {test} = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const appSource = fs.readFileSync(path.join(__dirname, "..", "ui", "app.js"), "utf8");
const goldSource = fs.readFileSync(path.join(__dirname, "..", "ui", "gold_ui.js"), "utf8");

function createBrowser() {
  const events = {};
  let writes = 0, visiblePage = null, calls = 0;
  const nodes = {};
  const main = {
    set innerHTML(value) {
      writes++;
      visiblePage = /data-current-page="([^"]+)"/.exec(value)?.[1] || null;
    },
    get innerHTML() { return ""; }
  };
  const doc = {
    body: {classList: {toggle() {}}, append() {}},
    addEventListener(name, fn) {events[name] = fn;},
    querySelector(sel) {
      if (sel === "#app") return main;
      if (sel === "#app [data-current-page]") {
        return visiblePage ? {dataset: {currentPage: visiblePage}} : null;
      }
      return null;
    },
    querySelectorAll(selector) {return nodes[selector] || [];},
    getElementById() {return {id: "running-interface"};},
    createElement() {return {className:"",textContent:"",remove() {}};}
  };
  const win = {addEventListener() {}};
  const ctx = vm.createContext({
    document: doc, window: win, location: {search: ""},
    URLSearchParams, console,
    setTimeout() {return 0;}, clearTimeout() {},
    setInterval() {return 0;}, clearInterval() {}
  });
  vm.runInContext(appSource, ctx);
  vm.runInContext(`
    S = {"btn.pause":"Pause", "btn.resume":"Resume", "state.running":"Running"};
    ST = {
      version:"1.3.8",
      cfg: {ui_language:"en", theme:"dark", require_foreground:true},
      engine: {running:true,paused:false,state:"running",runtime:5,input_count:0,
               games:0,cycles:0,rewards:0,history:[]},
      tracker:{rev:0},week:null,guide:{},tpl_counts:{},
      diagnostics:{game_active:false,game_found:true},update:{status:"idle"},
      release_news:[],subscription:{},log:[]
    };
    PAGE.home = () => '<button data-act="stop">Stop</button>';
    PAGE.afk = () => '<button data-act="stop">Stop</button>';
    page = "home";
  `, ctx);
  return {ctx, events, main, nodes, get writes() {return writes;},
    get calls(){return calls;},
    setApi(){win.pywebview = {api: {stop() {calls++;return Promise.resolve();}}};}};
}

test("Live diagnostics report lookup progress and allow Stop while Start is queued", () => {
  const b = createBrowser();
  const stop = {disabled: true};
  const pause = {disabled: false};
  const status = {textContent: ""};
  b.nodes['button[data-act="stop"]'] = [stop];
  b.nodes['button[data-act="pause"]'] = [{...pause, classList: {contains() {return false;}}}];
  b.nodes['[data-live="game-status"]'] = [status];
  vm.runInContext(`
    S["afk.diag_searching"] = "Searching";
    S["afk.diag_lookup_error"] = "Search failed";
    ST.engine.running = false;
    ST.controls = {start_pending: true};
    ST.diagnostics = {game_found: false, game_lookup_pending: true};
    refreshLiveMetrics();
  `, b.ctx);
  assert.equal(stop.disabled, false);
  assert.equal(b.nodes['button[data-act="pause"]'][0].disabled, true);
  assert.equal(status.textContent, "Searching");
  vm.runInContext('ST.controls.start_pending = false; ST.diagnostics.game_lookup_error = "OSError"; refreshLiveMetrics()', b.ctx);
  assert.equal(stop.disabled, true);
  assert.equal(status.textContent, "Search failed (OSError)");
});

test("Home polling does not replace the DOM while engine counters change", () => {
  const b = createBrowser();
  vm.runInContext("render(true)", b.ctx);
  assert.equal(b.writes, 1);
  vm.runInContext("ST.engine.runtime = 8; ST.engine.input_count = 10; ST.engine.state='in_match'; render()", b.ctx);
  assert.equal(b.writes, 1, "polling must not destroy a button under the mouse");
  vm.runInContext("ST.cfg.theme='light'; render()", b.ctx);
  assert.equal(b.writes, 2, "configuration changes must still rebuild the view");
});

test("Anti-AFK polling preserves buttons; stop dispatched once on pointerdown", () => {
  const b = createBrowser();
  b.setApi();
  vm.runInContext("page='afk'; render(true)", b.ctx);
  assert.equal(b.writes, 1);
  vm.runInContext("ST.engine.runtime = 40;ST.engine.input_count=42;render()", b.ctx);
  assert.equal(b.writes, 1);
  const button = {dataset:{act:"stop"},disabled:false,closest(){return this;}};
  b.events.pointerdown({button:0,target:button});
  assert.equal(b.calls, 1, "mouse-down must reach Python even without a click event");
  b.events.click({target:{closest(selector){return selector === "[data-window]" ? null : button;}}});
  assert.equal(b.calls, 1, "normal click following pointerdown must not double-stop");
});

test("Gold popover close does not rerender synchronously during click capture", () => {
  assert.match(goldSource, /setTimeout\(\(\) => renderGold\(true\), 0\)/);
  assert.match(goldSource, /notificationOpen = false; profileOpen = false/);
});
