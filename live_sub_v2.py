import os
# --- 核心配置：国内镜像源 ---
os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"

import sounddevice as sd
import numpy as np
import queue
import threading
import tkinter as tk
from tkinter import ttk, messagebox
from faster_whisper import WhisperModel
import argostranslate.package
import argostranslate.translate
import sys

# --- 全局配置 ---
MODEL_SIZE = "small" # 多语言模型必须去掉.en后缀，使用通用模型
COMPUTE_TYPE = "float32" # 1060 专用

# 语言映射 (显示名 -> ISO代码)
LANG_MAP = {
    "English (英语)": "en",
    "French (法语)": "fr",
    "Japanese (日语)": "ja",
    "German (德语)": "de",
    "Spanish (西语)": "es",
    "Russian (俄语)": "ru",
    "Korean (韩语)": "ko"
}

class AppState:
    def __init__(self):
        self.src_lang = "en"
        self.running = True
        self.alpha = 0.8
        self.model_ready = False
        self.status_msg = "初始化中..."

state = AppState()
q = queue.Queue()

# --- 翻译模型管理 (自动下载) ---
def install_translation_package(from_code, to_code):
    """下载指定的翻译包"""
    print(f"正在检查翻译包: {from_code} -> {to_code} ...")
    argostranslate.package.update_package_index()
    available_packages = argostranslate.package.get_available_packages()
    package = next(
        filter(lambda x: x.from_code == from_code and x.to_code == to_code, available_packages), 
        None
    )
    if package:
        # 检查是否已安装
        installed = argostranslate.package.get_installed_packages()
        if any(p.from_code == from_code and p.to_code == to_code for p in installed):
            print(f"包 {from_code}->{to_code} 已安装。")
            return
            
        print(f"开始下载包: {package}")
        argostranslate.package.install_from_path(package.download())
        print(f"安装完成: {from_code} -> {to_code}")
    else:
        print(f"错误: 未找到 {from_code} 到 {to_code} 的翻译包")

def prepare_translation_models(src_code):
    """准备翻译链路：源语言 -> 英文 -> 中文"""
    try:
        # 1. 确保有 英文 -> 中文
        install_translation_package("en", "zh")
        
        # 2. 如果源语言不是英文，确保有 源语言 -> 英文
        if src_code != "en":
            install_translation_package(src_code, "en")
        
        state.status_msg = f"模型就绪 ({src_code} -> zh)"
        print(state.status_msg)
    except Exception as e:
        state.status_msg = f"模型下载失败: {str(e)}"
        print(state.status_msg)

# --- 翻译逻辑 (桥接翻译) ---
def translate_text(text, src_code):
    try:
        if src_code == "en":
            return argostranslate.translate.translate(text, "en", "zh")
        else:
            # 先转英文，再转中文
            text_en = argostranslate.translate.translate(text, src_code, "en")
            text_zh = argostranslate.translate.translate(text_en, "en", "zh")
            return text_zh
    except Exception as e:
        return f"[翻译错误] {str(e)}"

# --- GUI 界面 ---
class SubtitleOverlay:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Kali Live Sub")
        self.root.geometry("800x160+100+600")
        self.root.wm_attributes("-topmost", True)
        self.root.wm_attributes("-alpha", state.alpha)
        self.root.configure(bg='black')
        self.root.overrideredirect(True) 

        # 顶部工具栏框架
        self.frame_top = tk.Frame(self.root, bg="black")
        self.frame_top.pack(side="top", fill="x")

        # 齿轮设置按钮
        self.btn_cfg = tk.Label(self.frame_top, text="⚙️", font=("Arial", 12), fg="gray", bg="black", cursor="hand2")
        self.btn_cfg.pack(side="right", padx=5, pady=2)
        self.btn_cfg.bind("<Button-1>", self.open_settings)
        
        # 拖动句柄
        self.lbl_drag = tk.Label(self.frame_top, text=" :: 拖动 :: ", font=("Arial", 8), fg="gray", bg="black", cursor="fleur")
        self.lbl_drag.pack(side="left", padx=5)
        self.lbl_drag.bind("<Button-1>", self.start_move)
        self.lbl_drag.bind("<B1-Motion>", self.on_motion)

        # 字幕显示区域
        self.lbl_src = tk.Label(self.root, text="Initializing...", font=("Arial", 14), fg="#ffff00", bg="black", wraplength=780)
        self.lbl_src.pack(side="top", fill="both", expand=True)
        
        self.lbl_zh = tk.Label(self.root, text="正在加载模型...", font=("Microsoft YaHei", 16, "bold"), fg="white", bg="black", wraplength=780)
        self.lbl_zh.pack(side="bottom", fill="both", expand=True)

    def start_move(self, event):
        self.x = event.x
        self.y = event.y

    def on_motion(self, event):
        deltax = event.x - self.x
        deltay = event.y - self.y
        x = self.root.winfo_x() + deltax
        y = self.root.winfo_y() + deltay
        self.root.geometry(f"+{x}+{y}")

    def update_text(self, src, zh):
        self.lbl_src.config(text=src)
        self.lbl_zh.config(text=zh)
        self.root.update()

    def open_settings(self, event):
        win = tk.Toplevel(self.root)
        win.title("设置")
        win.geometry("300x250")
        win.attributes("-topmost", True)
        
        tk.Label(win, text="透明度:").pack(pady=5)
        scale = tk.Scale(win, from_=0.1, to=1.0, resolution=0.1, orient="horizontal", command=self.set_alpha)
        scale.set(state.alpha)
        scale.pack(fill="x", padx=20)

        tk.Label(win, text="源语言 (自动下载模型):").pack(pady=5)
        combo = ttk.Combobox(win, values=list(LANG_MAP.keys()), state="readonly")
        # 设置当前选中项
        current_name = next(k for k, v in LANG_MAP.items() if v == state.src_lang)
        combo.set(current_name)
        combo.pack(pady=5)

        def apply_settings():
            sel_lang_code = LANG_MAP[combo.get()]
            if sel_lang_code != state.src_lang:
                if messagebox.askyesno("确认", f"切换语言到 {combo.get()} 需要下载新模型，可能会卡顿几分钟，确定吗？"):
                    state.src_lang = sel_lang_code
                    # 在后台线程下载模型
                    threading.Thread(target=prepare_translation_models, args=(state.src_lang,)).start()
                    self.lbl_zh.config(text=f"正在下载 {combo.get()} 翻译模型...")
            win.destroy()

        tk.Button(win, text="应用", command=apply_settings).pack(pady=20)

    def set_alpha(self, val):
        state.alpha = float(val)
        self.root.wm_attributes("-alpha", state.alpha)

# --- 音频处理 ---
def audio_callback(indata, frames, time, status):
    if status: print(status, file=sys.stderr)
    q.put(indata.copy())

def process_audio(overlay):
    print(f"正在加载 Whisper 模型 ({MODEL_SIZE}) ...")
    # 注意：这里去掉了 .en 后缀，因为我们需要多语言支持
    # 第一次运行会下载约 1GB 的 small model (multilingual)
    model = WhisperModel(MODEL_SIZE, device="cuda", compute_type=COMPUTE_TYPE)
    state.model_ready = True
    print("Whisper 模型加载完毕")
    
    # 预先准备默认语言 (en->zh)
    prepare_translation_models(state.src_lang)
    
    samplerate = 16000
    buffer = np.array([], dtype=np.float32)
    
    with sd.InputStream(samplerate=samplerate, blocksize=4000, channels=1, callback=audio_callback):
        while state.running:
            while not q.empty():
                buffer = np.concatenate((buffer, q.get().flatten()))
            
            if len(buffer) >= samplerate * 2.5: # 2.5秒切片
                # 传入当前的源语言
                segments, info = model.transcribe(buffer, beam_size=1, language=state.src_lang, vad_filter=True)
                
                full_text = ""
                for segment in segments:
                    full_text += segment.text + " "
                
                full_text = full_text.strip()
                if full_text:
                    trans_text = translate_text(full_text, state.src_lang)
                    print(f"[{state.src_lang}] {full_text} -> {trans_text}")
                    overlay.update_text(full_text, trans_text)
                
                buffer = np.array([], dtype=np.float32)

if __name__ == "__main__":
    overlay = SubtitleOverlay()
    
    t = threading.Thread(target=process_audio, args=(overlay,))
    t.daemon = True
    t.start()
    
    try:
        overlay.root.mainloop()
    except KeyboardInterrupt:
        state.running = False
