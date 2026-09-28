#!/usr/bin/env python3
"""Offline preview of an SVG component tree from the dashboard generator, with real item states."""
import json, sys, datetime
DARK = len(sys.argv) > 1 and sys.argv[1] == "dark"
sys.argv = ["x", "update"]
src = open("dashboard_local.py").read().replace("\nmain()\n", "\n")
g = {}
exec(compile(src, "d", "exec"), g)
TARGET = open("preview_target.txt").read().strip() if __import__("os").path.exists("preview_target.txt") else "hp_svg"
tree = eval(TARGET, g)
items = {i["name"]: i for i in json.load(open(__import__("os").environ.get("ITEMS", "items_now.json")))}
html = """<!doctype html><html><head><meta charset="utf-8"><style>
body{margin:0;background:%s;color:%s;font-family:Roboto,Arial,sans-serif}
#c{width:var(--w,900px);padding:16px}</style></head><body><div id="c"></div><script>
const TREE=%s; const RAW=%s;
const items=new Proxy({}, {get:(t,k)=>{const i=RAW[k]||{state:'NULL'}; const n=parseFloat(i.state);
  return {state:i.state, displayState:i.transformedState, numericState: isNaN(n)?undefined:n};}});
const dayjs=(s)=>({format:()=>'12:00', valueOf:()=>Date.now()});
const screen={width:1400};
function ev(v){ if(typeof v==='string' && v.startsWith('=')){ try{ return new Function('items','Math','Number','dayjs','screen','themeOptions','return ('+v.slice(1)+')')(items,Math,Number,dayjs,screen,{dark:'%s'});}catch(e){return 'ERR:'+e;} }
  if(Array.isArray(v)) return v.map(ev); if(v && typeof v==='object'){const o={}; for(const k in v) o[k]=ev(v[k]); return o;} return v;}
const NS='http://www.w3.org/2000/svg';
const HTML=['div','Label'];
function build(node, inSvg){ const cfg=ev(node.config||{}); if(cfg.visible===false) return null;
  const svgNode = inSvg || node.component==='svg';
  const el = svgNode ? document.createElementNS(NS,node.component) : document.createElement(node.component==='Label'?'div':node.component);
  if(node.component==='Label' && cfg.text!==undefined) el.textContent=cfg.text;
  for(const k in cfg){ if(k==='visible'||k==='content'||k==='text') continue;
    if(k==='style'&&typeof cfg[k]==='object'){ for(const s in cfg[k]) el.style.setProperty(s,cfg[k][s]); continue;}
    el.setAttribute(k,cfg[k]); }
  if(cfg.content!==undefined) el.textContent=cfg.content;
  for(const ch of ((node.slots||{}).default||[])){ const c=build(ch, svgNode); if(c) el.appendChild(c);} return el;}
document.getElementById('c').appendChild(build(TREE));
</script></body></html>"""
dark = DARK
open("preview.html", "w").write(html % ("#1e1e1e" if dark else "#ffffff", "#ffffff" if dark else "#222222",
                                        json.dumps(tree), json.dumps(items), "dark" if dark else "light"))
print("preview written")
