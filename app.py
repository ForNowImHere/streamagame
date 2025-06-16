# app.py
import asyncio, json, io, time, base64, threading
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Form
from fastapi.responses import HTMLResponse
from PIL import ImageGrab
import pygetwindow as gw
import keyboard, mouse
import uvicorn

app = FastAPI()
share = {"bbox":None, "frame":None, "viewers":set(), "running":False}
MAX_VIEWERS = 3

def capture_loop():
    while True:
        if share["running"] and share["bbox"]:
            img = ImageGrab.grab(bbox=share["bbox"]).resize((640,360))
            buffer = io.BytesIO(); img.save(buffer,"JPEG",quality=50)
            share["frame"] = base64.b64encode(buffer.getvalue()).decode()
        time.sleep(0.1)
threading.Thread(target=capture_loop, daemon=True).start()

INDEX = """<html><body>
<h2>Select Window</h2><form action="/share" method="post">
<select name="title">{options}</select><button type="submit">Share</button>
</form></body></html>"""

SHARE = """<html><body>
<h2>Sharing: {t}</h2><p>Viewer link: <a href="/view">{url}</a></p>
<img id="img" style="border:1px solid #444"/><script>
const ws=new WebSocket("ws://"+location.host+"/ws/stream");
ws.onmessage=e=>{
 let m=JSON.parse(e.data); if(m.t==="f") img.src="data:image/jpeg;base64,"+m.d;
};
</script></body></html>"""

VIEW = """<html><body>
<h2>Viewer</h2><img id="v" style="border:1px solid #333"/>
<script>
const v=document.getElementById("v"), ws=new WebSocket("ws://"+location.host+"/ws/view");
ws.onmessage=e=>{let m=JSON.parse(e.data); if(m.t==="f") v.src="data:image/jpeg;base64,"+m.d};
["keydown","keyup"].forEach(ev=>window.addEventListener(ev, e=> ws.send(JSON.stringify({t:ev[0]=='k'?'k':ev.type, k:e.key}))));
["mousedown","mouseup"].forEach(ev=>window.addEventListener(ev, e=> ws.send(JSON.stringify({t:ev[0]=='m'?'m':ev.type, b:e.button}))));
</script></body></html>"""

@app.get("/", response_class=HTMLResponse)
def index():
    wins = [w for w in gw.getAllTitles() if w.strip()]
    options = "".join(f'<option value="{w}">{w}</option>' for w in wins)
    return INDEX.format(options=options)

@app.post("/share", response_class=HTMLResponse)
def share_form(title: str = Form(...)):
    wins = [w for w in gw.getWindowsWithTitle(title) if w.isVisible]
    if not wins: return HTMLResponse("Not found", status_code=404)
    w = wins[0]; share["bbox"]=(w.left,w.top,w.right,w.bottom); share["running"]=True
    url = "https://" + (os.getenv("RENDER_EXTERNAL_HOSTNAME") or "localhost:5000") + "/view"
    return SHARE.format(t=title, url=url)

@app.get("/view", response_class=HTMLResponse)
def view():
    if not share["running"]: return HTMLResponse("No share",404)
    return VIEW

@app.websocket("/ws/stream")
async def ws_stream(ws: WebSocket):
    await ws.accept()
    try:
        while share["running"]:
            if share["frame"]:
                await ws.send_text(json.dumps({"t":"f","d":share["frame"]}))
            await asyncio.sleep(0.1)
    except WebSocketDisconnect:
        pass

@app.websocket("/ws/view")
async def ws_view(ws: WebSocket):
    await ws.accept()
    if len(share["viewers"])>=MAX_VIEWERS:
        await ws.close(); return
    share["viewers"].add(ws)
    try:
        while True:
            m = json.loads(await ws.receive_text())
            if m['t']=='k': keyboard.press(m['k'])
            elif m['t']=='keyup': keyboard.release(m['k'])
    except WebSocketDisconnect:
        share["viewers"].remove(ws)

if __name__=="__main__":
    uvicorn.run(app, host="0.0.0.0", port=5000)
