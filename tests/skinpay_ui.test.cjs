"use strict";
const {test} = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const code = fs.readFileSync(path.join(__dirname, "..", "ui", "skinpay.js"), "utf8");
const html = fs.readFileSync(path.join(__dirname, "..", "ui", "index.html"), "utf8");

function browser(){
  const callbacks = {};
  const fields = {
    "skin-name": {value:""},
    "skin-estimate": {value:""},
    "skin-target": {value:""},
  };
  const ctx = vm.createContext({
    ST:{cfg:{ui_language:"ru"},payment_hub:{games:[
      {id:"dota2",name:"Dota 2"}, {id:"rust",name:"Rust"},
      {id:"cs2",name:"Counter-Strike 2",trade_protected:true},
    ]}},
    payMethod:"steam_items",payGame:"dota2",
    paymentHubMarkup(){return '<section class="card">BASE</section>';},
    esc(s){return String(s).replace(/&/g,"&amp;").replace(/</g,"&lt;")
        .replace(/>/g,"&gt;").replace(/"/g,"&quot;");},
    toast(){},render(){},console,Intl,
    window:{},
    document:{
      addEventListener(name,cb){callbacks[name] = cb;},
      getElementById(name){return fields[name] || null;},
    },
  });
  vm.runInContext(code,ctx);
  const action = (name,id) => callbacks.click({target:{closest(){return {
    dataset:{skinAction:name,skinId:id},};}}});
  return {ctx,fields,action,markup:()=>vm.runInContext("paymentHubMarkup()",ctx),
    getDraft:()=>ctx.window.skinpayDraftSelection()};
}

test("SkinPay UI loads only for Steam item method and has no live payment links",()=>{
  const b=browser();
  const markup=b.markup();
  assert.match(markup,/SKINPAY/);
  assert.match(markup,/Dota 2/);
  assert.match(markup,/Rust/);
  assert.match(markup,/Counter-Strike 2/);
  assert.match(markup,/data-skin-action="add"/); // item cards appear only after manual entries
});
test("Manual money parser uses integer kopeks, not floating point quotes",()=>{
  const b=browser(), p=b.ctx.window.skinpayPlanner;
  assert.equal(p.moneyFromText("499,50"),49950);
  assert.equal(p.moneyFromText("0"),null);
  assert.equal(p.moneyFromText("50000000"),null);
  assert.equal(p.moneyFromText("1.123"),null);
});
test("Manual inventory items can be selected and matched to a planning total",()=>{
  const b=browser();
  b.fields["skin-name"].value='Dota item <test>';
  b.fields["skin-estimate"].value="300";
  b.action("add");
  b.fields["skin-name"].value="Other Dota item";
  b.fields["skin-estimate"].value="200";
  b.action("add");
  assert.equal(b.getDraft().items.length,2);
  assert.equal(b.getDraft().items[0].estimate_kopeks,30000);
  assert.match(b.markup(),/&lt;test&gt;/);
  b.fields["skin-target"].value="500";
  b.action("match");
  assert.equal(b.getDraft().target_kopeks,50000);
  assert.equal(b.getDraft().items.length,2);
  b.action("game","rust");
  assert.equal(b.getDraft().items.length,0);
});
test("Closest matching prioritizes minimum overpay then minimum items",()=>{
  const b=browser(), select=b.ctx.window.skinpayPlanner.chooseBest;
  const all=[{id:1,estimate_kopeks:30000},{id:2,estimate_kopeks:20000},
    {id:3,estimate_kopeks:51000}];
  const picked=select(all,50000);
  assert.equal(picked.sum,50000);
  assert.deepEqual([...picked.ids], [1,2]);
  assert.equal(select(all,102000),null);
});
test("Checkout source never collects card, Steam password or creates trades",()=>{
  assert.match(html,/skinpay\.css/);
  assert.match(html,/skinpay\.js/);
  assert.ok(html.indexOf('src="app.js"') < html.indexOf('src="skinpay.js"'));
  assert.ok(html.indexOf('src="skinpay.js"') < html.indexOf('src="gold_ui.js"'));
  assert.doesNotMatch(code,/fetch\(|XMLHttpRequest|payment\.succeeded|tradeoffer\/new\//);
});
