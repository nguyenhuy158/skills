# Relations through the Plane web UI

The plane MCP cannot add `Relates to` / `Duplicate of`: `workitem_relation list` and
`list_definitions` return 404 on this Plane edition, and `create` only takes dependency types
(`blocking`, `blocked_by`, `start_before`, …). Use the browser-use CLI (read `skill://browser-use`).

- Host: `PLANE_BASE_URL` of the plane MCP server (`rg -o '"PLANE_BASE_URL": *"[^"]*' ~/.claude.json`).
- Slug: `workspace retrieve` → `slug`.
- The menu and the result rows need real clicks (`click_at_xy`); JS `.click()` does nothing there.
- Clicking the identifier text does not select a row; click the row's checkbox.

```bash
BU_NAME=plane-relation-<IDENTIFIER-N> browser-use <<'PY'
import json, time

SOURCE = "https://<host>/<slug>/browse/DICHVUFARM-158/"
TARGET = "DICHVUFARM-157"
KIND = "Relates to"  # or "Duplicate of", "Blocked by", "Blocking"

def center(text, scope="button, [role=menuitem], [role=option], li, span"):
    return js("(()=>{const t=%s;const els=[...document.querySelectorAll(%s)].filter(e=>e.getClientRects().length&&(e.innerText||'').trim()===t);if(!els.length)return null;const r=els[els.length-1].getBoundingClientRect();return [r.x+r.width/2,r.y+r.height/2]})()" % (json.dumps(text), json.dumps(scope)))

def click(text, scope="button, [role=menuitem], [role=option], li, span"):
    xy = center(text, scope)
    assert xy, f"not found on page: {text}"
    click_at_xy(*xy)
    time.sleep(1.5)

def row_checkbox(identifier):
    return js("(()=>{const t=%s;const id=[...document.querySelectorAll('span,p,div')].filter(e=>e.getClientRects().length&&(e.innerText||'').trim()===t).pop();let p=id;while(p&&!p.querySelector('input[type=checkbox],[role=checkbox]'))p=p.parentElement;if(!p)return null;const c=p.querySelector('input[type=checkbox],[role=checkbox]');const r=(c.getClientRects().length?c:c.parentElement).getBoundingClientRect();return [r.x+r.width/2,r.y+r.height/2]})()" % json.dumps(identifier))

new_tab(SOURCE)
cdp("Emulation.setDeviceMetricsOverride", width=1500, height=1000, deviceScaleFactor=1, mobile=False)
time.sleep(6)
click("Add relation")
click(KIND)
type_text(TARGET.split("-")[-1])
time.sleep(2.5)
xy = row_checkbox(TARGET)
assert xy, f"{TARGET} not in the search results"
click_at_xy(*xy)
time.sleep(1)
click("Add selected work items", "button")
time.sleep(2)
print(js("(()=>{const h=[...document.querySelectorAll('*')].find(e=>e.childElementCount===0&&(e.innerText||'').trim()==='Relations');let p=h;for(let i=0;i<6&&p;i++)p=p.parentElement;return p?p.innerText.replace(/\\s+/g,' '):'no relations'})()"))
close_tab()
PY
```

Done when the printed Relations block lists `KIND` and `TARGET`. Search results cover the current project
only; the dialog has a "Workspace level" toggle for tasks in another project (not exercised yet — verify the
result block after using it).
