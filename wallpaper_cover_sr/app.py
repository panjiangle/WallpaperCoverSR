"""Small settings window + notification-area icon; no browser or web server."""
import argparse
import ctypes
import logging
from logging.handlers import RotatingFileHandler
import os
import queue
import threading
import tkinter as tk
from tkinter import ttk, messagebox

from PIL import Image, ImageDraw
import pystray

from . import __version__
from .media_policy import APP_ID
from .config import Settings, DATA, startup_enabled, set_startup
from .worker import Worker


def tray_image():
    image = Image.new('RGBA', (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((3, 3, 61, 61), radius=14, fill='#3665d8')
    draw.rectangle((15, 19, 45, 48), outline='white', width=3)
    draw.line((20, 41, 28, 32, 35, 39, 41, 30), fill='white', width=3)
    draw.line((45, 9, 45, 25), fill='#b6e8ff', width=4)
    draw.line((37, 17, 53, 17), fill='#b6e8ff', width=4)
    return image


class Application:
    def __init__(self, background, show_event):
        self.settings = Settings()
        self.worker = Worker(self.settings)
        self.show_event = show_event
        self.messages = queue.Queue()
        self.closing = False
        self.root = tk.Tk()
        self.root.title('Wallpaper Cover SR')
        self.root.geometry('560x490')
        self.root.resizable(False, False)
        self.root.protocol('WM_DELETE_WINDOW', self.root.withdraw)
        style = ttk.Style()
        if 'vista' in style.theme_names():
            style.theme_use('vista')
        style.configure('TLabel', font=('Microsoft YaHei UI', 10))
        style.configure('TButton', font=('Microsoft YaHei UI', 9), padding=(10, 5))
        style.configure('TCheckbutton', font=('Microsoft YaHei UI', 10))
        frame = ttk.Frame(self.root, padding=24)
        frame.pack(fill='both', expand=True)
        ttk.Label(frame, text='让歌曲封面清楚一点', font=('Microsoft YaHei UI', 18, 'bold')).pack(anchor='w')
        ttk.Label(frame, text='高清原封面优先 · 换壁纸自动生效', foreground='#666666').pack(anchor='w', pady=(5, 20))
        settings = self.settings.get()
        self.enabled = tk.BooleanVar(value=settings['enabled'])
        ttk.Checkbutton(frame, text='启用封面增强', variable=self.enabled, command=self.toggle).pack(anchor='w')
        self.prefer_hd = tk.BooleanVar(value=settings['prefer_hd'])
        ttk.Checkbutton(frame, text='优先使用网易云高清原封面（联网）', variable=self.prefer_hd, command=self.change_source).pack(anchor='w', pady=(8, 0))
        ttk.Label(frame, text='高清原图直接显示；获取失败时使用下方超分倍率。', foreground='#666666', font=('Microsoft YaHei UI', 9)).pack(anchor='w', pady=(4, 0))
        row = ttk.Frame(frame)
        row.pack(fill='x', pady=12)
        ttk.Label(row, text='回退超分倍率').pack(side='left')
        self.scale = tk.StringVar(value=f'{settings["scale"]}×')
        dropdown = ttk.Combobox(row, textvariable=self.scale, values=['2×', '3×', '4×'], state='readonly', width=7)
        dropdown.pack(side='left', padx=(16, 0))
        dropdown.bind('<<ComboboxSelected>>', self.change_scale)
        self.autorun = tk.BooleanVar(value=startup_enabled())
        ttk.Checkbutton(frame, text='登录 Windows 时在后台启动', variable=self.autorun, command=self.autostart).pack(anchor='w', pady=(0, 15))
        ttk.Separator(frame).pack(fill='x', pady=(0, 12))
        self.song = tk.StringVar(value='等待歌曲…')
        self.status = tk.StringVar(value='正在启动…')
        ttk.Label(frame, textvariable=self.song, wraplength=485).pack(anchor='w')
        ttk.Label(frame, textvariable=self.status, foreground='#666666', wraplength=485).pack(anchor='w', pady=(5, 12))
        buttons = ttk.Frame(frame)
        buttons.pack(fill='x')
        ttk.Button(buttons, text='恢复播放器封面', command=self.restore).pack(side='left')
        ttk.Button(buttons, text='退出程序', command=self.exit).pack(side='left', padx=8)
        ttk.Button(buttons, text='收起到托盘', command=self.root.withdraw).pack(side='right')
        ttk.Label(frame, text=f'v{__version__} · 支持读取 Windows 媒体封面的壁纸；关闭窗口仍会运行。', foreground='#888888', font=('Microsoft YaHei UI', 9)).pack(anchor='w', pady=(12, 0))
        self.tray = pystray.Icon('WallpaperCoverSR', tray_image(), 'Wallpaper Cover SR', menu=pystray.Menu(
            pystray.MenuItem('打开设置', lambda *_: self.messages.put(('show', None)), default=True),
            pystray.MenuItem('启用封面增强', lambda *_: self.messages.put(('toggle', None)),
                             checked=lambda _: self.settings.get()['enabled']),
            pystray.MenuItem('打开日志文件夹', lambda *_: os.startfile(DATA)),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem('退出', lambda *_: self.messages.put(('quit', None))),
        ))
        threading.Thread(target=self.tray.run, daemon=True, name='Tray').start()
        if background:
            self.root.withdraw()
        self.worker.thread.start()
        self.root.after(500, self.tick)

    def toggle(self):
        self.settings.save(enabled=bool(self.enabled.get()))
        self.worker.poke()
        self.tray.update_menu()

    def change_scale(self, *_):
        self.settings.save(scale=int(self.scale.get()[0]))
        self.worker.poke()

    def change_source(self):
        self.settings.save(prefer_hd=bool(self.prefer_hd.get()))
        self.worker.poke()

    def autostart(self):
        try:
            set_startup(self.autorun.get())
        except OSError as exc:
            self.autorun.set(startup_enabled())
            messagebox.showerror('开机启动设置失败', str(exc), parent=self.root)

    def restore(self):
        self.enabled.set(False)
        self.toggle()

    def show(self):
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

    def tick(self):
        if self.closing:
            return
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
        if kernel.WaitForSingleObject(self.show_event, 0) == 0:
            self.show()
        while not self.messages.empty():
            kind, value = self.messages.get_nowait()
            if kind == 'show':
                self.show()
            elif kind == 'toggle':
                self.enabled.set(not self.settings.get()['enabled'])
                self.toggle()
            elif kind == 'quit':
                self.exit()
                return
        info = self.worker.get_info()
        self.status.set(info.get('message', ''))
        if info.get('title'):
            song = info['title'] + ('  /  ' + info['artist'] if info.get('artist') else '')
            self.song.set(song)
        elif info.get('state') in ('waiting', 'setup'):
            self.song.set('等待歌曲…')
        self.root.after(500, self.tick)

    def exit(self):
        self.closing = True
        self.worker.stop()
        self.status.set('正在退出并恢复播放器的原始封面…')
        def finish():
            if self.worker.thread.is_alive():
                self.root.after(100, finish)
            else:
                self.tray.stop()
                self.root.destroy()
        self.root.after(100, finish)


def main():
    parser = argparse.ArgumentParser(description='Wallpaper Cover SR')
    parser.add_argument('--background', action='store_true', help='只显示托盘图标')
    parser.add_argument('--quit', action='store_true', help='退出已经运行的实例')
    args = parser.parse_args()
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)
    handler = RotatingFileHandler(DATA / 'app.log', maxBytes=524288, backupCount=2, encoding='utf-8')
    logging.basicConfig(level=logging.INFO, handlers=[handler])
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p]
    kernel.CreateMutexW.restype = ctypes.c_void_p
    kernel.CreateEventW.argtypes = [ctypes.c_void_p, ctypes.c_bool, ctypes.c_bool, ctypes.c_wchar_p]
    kernel.CreateEventW.restype = ctypes.c_void_p
    kernel.SetEvent.argtypes = [ctypes.c_void_p]
    kernel.CloseHandle.argtypes = [ctypes.c_void_p]
    show = kernel.CreateEventW(None, False, False, 'Local\\WallpaperCoverSR-Show')
    quit_event = kernel.CreateEventW(None, False, False, 'Local\\WallpaperCoverSR-Quit')
    mutex = kernel.CreateMutexW(None, False, 'Local\\WallpaperCoverSR-SingleInstance')
    if not mutex or not show or not quit_event:
        raise ctypes.WinError(ctypes.get_last_error())
    exists = ctypes.get_last_error() == 183
    try:
        if args.quit:
            kernel.SetEvent(quit_event)
            return
        if exists:
            if not args.background:
                kernel.SetEvent(show)
            return
        app = Application(args.background, show)
        def check_quit():
            kernel.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
            if not app.closing:
                if kernel.WaitForSingleObject(quit_event, 0) == 0:
                    app.exit()
                else:
                    app.root.after(500, check_quit)
        app.root.after(500, check_quit)
        app.root.mainloop()
    except Exception:
        logging.exception('Application startup failed')
        ctypes.windll.user32.MessageBoxW(None, f'启动失败，请查看 {DATA / "app.log"}', 'Wallpaper Cover SR', 0x10)
        raise
    finally:
        for handle in (show, quit_event, mutex):
            kernel.CloseHandle(handle)
