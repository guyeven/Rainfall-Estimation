#!/usr/bin/env python3
"""Batch benchmark builder UI (Gradio).
- Serial 1=newest from GET /files.
- For each file: POST /detect_patches with files=[that_file]; append patches to .jsonl/.ndjson.
- Stop after finishing a file once total>=N. Pause/Resume/Stop. Resume skips seen patch IDs and continues after last source_file.
"""
from __future__ import annotations
import json, os, threading, time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
import gradio as gr, requests

DEFAULT_URL="http://127.0.0.1:8200"
def _now()->str: return time.strftime("%Y-%m-%d %H:%M:%S")
def _path(it:Dict[str,Any])->str: return str(it.get("path") or it.get("filepath") or "")
def _ts(it:Dict[str,Any])->str: return str(it.get("timestamp") or it.get("time") or "")

def fetch_files(url:str, limit:int)->List[Dict[str,Any]]:
    r=requests.get(f"{url}/files", params={"limit":int(limit)}, timeout=60); r.raise_for_status()
    files=r.json(); return sorted(files, key=lambda x:_ts(x) or _path(x), reverse=True)

def detect_one(url:str, file_path:str, params:Dict[str,Any])->List[Dict[str,Any]]:
    body=dict(params); body["files"]=[file_path]
    r=requests.post(f"{url}/detect_patches", json=body, timeout=300); r.raise_for_status()
    return r.json()

def read_jsonl(path:str)->Tuple[int,Optional[str],set]:
    if not os.path.exists(path): return 0, None, set()
    seen,last_src,n=set(),None,0
    with open(path,"r",encoding="utf-8") as f:
        for line in f:
            line=line.strip()
            if not line: continue
            n+=1
            try: obj=json.loads(line)
            except Exception: continue
            if obj.get("id"): seen.add(obj["id"])
            if obj.get("source_file"): last_src=obj["source_file"]
    return n,last_src,seen

@dataclass
class Status: state:str="Idle"; msg:str=""; current_file:str=""; in_file:int=0; total:int=0; last_file:str=""
@dataclass
class Runner:
    lock:threading.Lock=field(default_factory=threading.Lock)
    st:Status=field(default_factory=Status)
    pause_flag:bool=False; stop_flag:bool=False
    thread:Optional[threading.Thread]=None; seen_ids:set=field(default_factory=set)
    def snap(self)->Status: 
        with self.lock: return Status(**self.st.__dict__)
    def _set(self, **kw:Any)->None:
        with self.lock:
            for k,v in kw.items(): setattr(self.st,k,v)
    def pause(self)->None: self.pause_flag=True; self._set(state="Paused", msg=f"[{_now()}] Paused.")
    def resume(self)->None: self.pause_flag=False; self._set(state="Running", msg=f"[{_now()}] Resumed.")
    def stop(self)->None: self.stop_flag=True; self._set(state="Stopped", msg=f"[{_now()}] Stop requested.")
    def start(self, url:str, limit:int, out_path:str, resume:bool, start_serial:int, target_n:int, params:Dict[str,Any])->None:
        if self.thread and self.thread.is_alive(): self._set(state="Error", msg="Already running."); return
        files=fetch_files(url,limit)
        total,last_src,seen=(0,None,set())
        if resume: total,last_src,seen=read_jsonl(out_path)
        self.seen_ids, self.pause_flag, self.stop_flag = seen, False, False
        eff_start=int(start_serial)
        if resume and last_src:
            for i,it in enumerate(files, start=1):
                if _path(it)==last_src: eff_start=i+1; break
        if os.path.exists(out_path): self._set(msg=f"[{_now()}] WARNING: output exists; append-only: {out_path}")
        self._set(state="Running", msg=f"[{_now()}] Starting.", total=total, last_file=last_src or "")
        self.thread=threading.Thread(target=self._run, daemon=True, args=(url,files,eff_start,int(target_n),out_path,params)); self.thread.start()
    def _run(self, url:str, files:List[Dict[str,Any]], start_serial:int, target_n:int, out_path:str, params:Dict[str,Any])->None:
        try:
            if not out_path.lower().endswith((".jsonl",".ndjson")): self._set(state="Error", msg="Output must end with .jsonl/.ndjson"); return
            if start_serial<1 or start_serial>len(files): self._set(state="Error", msg=f"start_serial must be 1..{len(files)}"); return
            os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
            with open(out_path,"a",encoding="utf-8") as f:
                for serial in range(start_serial, len(files)+1):
                    if self.stop_flag: break
                    while self.pause_flag and not self.stop_flag: time.sleep(0.2)
                    it=files[serial-1]; fp,ts=_path(it),_ts(it)
                    label=f"#{serial} {fp}"+(f" ({ts})" if ts else "")
                    self._set(current_file=label, in_file=0, msg=f"[{_now()}] Processing {label}")
                    patches=detect_one(url,fp,params); in_file=0
                    for p in patches:
                        pid=p.get("id")
                        if pid and pid in self.seen_ids: continue
                        if not p.get("source_file"): p["source_file"]=fp
                        f.write(json.dumps(p,ensure_ascii=False)+"\n"); f.flush()
                        if pid: self.seen_ids.add(pid)
                        in_file+=1
                        with self.lock: self.st.in_file=in_file; self.st.total+=1
                    self._set(last_file=label)
                    if self.snap().total>=target_n: break
            end=self.snap().last_file
            self._set(state="Stopped" if self.stop_flag else "Finished", msg=f"[{_now()}] {'Stopped' if self.stop_flag else 'Finished'}. Last file: {end}")
        except requests.RequestException as e: self._set(state="Error", msg=f"Backend request failed: {e}")
        except Exception as e: self._set(state="Error", msg=f"Unexpected error: {e}")

RUNNER=Runner()
def ui_load(url:str, limit:int)->str:
    try: return f"Loaded {len(fetch_files(url,limit))} files. Serial 1=newest."
    except Exception as e: return f"Error loading files: {e}"
def ui_run(url:str, limit:int, out_path:str, resume:bool, start_serial:int, target_n:int,
           threshold:float, avg_y:int, avg_x:int, min_w:float, min_h:float, max_w:float, max_h:float)->str:
    params={"threshold_mm":float(threshold),"avg_window_y":int(avg_y),"avg_window_x":int(avg_x),
            "min_width_km":float(min_w),"min_height_km":float(min_h),
            "max_width_km":None if float(max_w)==0 else float(max_w),
            "max_height_km":None if float(max_h)==0 else float(max_h),
            "max_files":1}
    RUNNER.start(url,int(limit),out_path,bool(resume),int(start_serial),int(target_n),params); return "Run requested."
def ui_poll()->Tuple[str,str,int,int,str]:
    s=RUNNER.snap(); return f"{s.state}\n{s.msg}", s.current_file, s.total, s.in_file, s.last_file

def build_ui()->gr.Blocks:
    with gr.Blocks(title="Rain Patch Benchmark Builder") as demo:
        gr.Markdown("## Batch Benchmark Builder (append-only JSONL/NDJSON)")
        with gr.Row():
            url=gr.Textbox(value=DEFAULT_URL,label="Backend URL")
            limit=gr.Number(value=200,precision=0,label="Files limit")
            load=gr.Button("Load files")
        load_msg=gr.Textbox(label="Files status",interactive=False)
        load.click(ui_load,inputs=[url,limit],outputs=[load_msg])
        with gr.Row():
            start_serial=gr.Number(value=1,precision=0,label="Start serial (1=newest)")
            target_n=gr.Number(value=500,precision=0,label="Target patches")
            out_path=gr.Textbox(value="benchmark.jsonl",label="Output .jsonl/.ndjson")
            resume=gr.Checkbox(value=True,label="Resume/append if exists")
        with gr.Row():
            threshold=gr.Number(value=1.0,label="threshold_mm")
            avg_y=gr.Number(value=1,precision=0,label="avg_window_y")
            avg_x=gr.Number(value=1,precision=0,label="avg_window_x")
        with gr.Row():
            min_w=gr.Number(value=10.0,label="min_width_km")
            min_h=gr.Number(value=10.0,label="min_height_km")
            max_w=gr.Number(value=0.0,label="max_width_km (0=None)")
            max_h=gr.Number(value=0.0,label="max_height_km (0=None)")
        with gr.Row():
            run=gr.Button("Run"); pause=gr.Button("Pause"); resume_btn=gr.Button("Resume"); stop=gr.Button("Stop")
        run.click(ui_run,inputs=[url,limit,out_path,resume,start_serial,target_n,threshold,avg_y,avg_x,min_w,min_h,max_w,max_h],outputs=[load_msg])
        pause.click(lambda:(RUNNER.pause() or "Paused."),outputs=[load_msg])
        resume_btn.click(lambda:(RUNNER.resume() or "Resumed."),outputs=[load_msg])
        stop.click(lambda:(RUNNER.stop() or "Stop requested."),outputs=[load_msg])
        status=gr.Textbox(label="Status",interactive=False,lines=2)
        cur=gr.Textbox(label="Current file",interactive=False)
        with gr.Row():
            total=gr.Number(label="Total patches written",interactive=False)
            in_file=gr.Number(label="Patches in current file",interactive=False)
        last=gr.Textbox(label="Last processed file",interactive=False)
        gr.Timer(0.5).tick(ui_poll,outputs=[status,cur,total,in_file,last])
    return demo

if __name__=="__main__": build_ui().launch()
