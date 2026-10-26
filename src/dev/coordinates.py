import io
import queue
import threading
import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageTk
from src.api.config import adb, reconnect, DEVICE
from src.api.display import resolve_game_display, game_region
from src.api.common.layout import to_reference

PNG = b'\x89PNG\r\n\x1a\n'

def screenshot(display_id):
    flag = [] if str(display_id) in ('', '0', 'None') else ['-d', str(display_id)]
    result = adb('exec-out', 'screencap', *flag, '-p', timeout=25)
    start = result.stdout.find(PNG)
    if result.returncode or start < 0:
        raise RuntimeError('Screenshot failed: ' + result.stderr.decode(errors='replace')[:200])
    with Image.open(io.BytesIO(result.stdout[start:])) as image:
        return image.convert('RGB')

def crop(image, region):
    left, top, width, height = region
    if (left, top, width, height) == (0, 0, image.width, image.height) or (image.width, image.height) != SCREEN.get('size'):
        return image
    return image.crop((left, top, left + width, top + height))

SCREEN = {}

def resolve():
    selected = resolve_game_display()
    image = screenshot(selected.physical_id)
    SCREEN['size'] = image.size
    region, source = game_region(selected.frame, selected.size, image.width, image.height)
    print(f'[GAME] {DEVICE} input={selected.logical_id} screenshot={selected.physical_id} '
          f'port={selected.port} screen={image.width}x{image.height} '
          f'game area={region[2]}x{region[3]} at ({region[0]}, {region[1]}) [{source}]', flush=True)
    return selected.logical_id, selected.physical_id, crop(image, region), region

class Picker:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title('Blazing Dev - Automatic Display Coordinate Picker')
        self.root.geometry('700x1000')
        self.events = queue.Queue()
        self.logical = None
        self.physical = None
        self.image = None
        self.tk_image = None
        self.rect = (0, 0, 1, 1)
        self.region = (0, 0, 1, 1)
        self.running = True
        self.busy = False
        self.taps = tk.BooleanVar(value=False)
        self.status = tk.StringVar(value='Connecting to game...')
        self.coords = tk.StringVar(value='Click the game to get coordinates')
        bar = ttk.Frame(self.root, padding=8)
        bar.pack(fill='x')
        ttk.Checkbutton(bar, text='Send taps to game', variable=self.taps).pack(side='left')
        ttk.Button(bar, text='Redetect', command=self.redetect).pack(side='left', padx=8)
        ttk.Label(self.root, textvariable=self.status, padding=(8, 0)).pack(fill='x')
        ttk.Label(self.root, textvariable=self.coords, padding=(8, 4)).pack(fill='x')
        self.canvas = tk.Canvas(self.root, bg='#171717', highlightthickness=0)
        self.canvas.pack(fill='both', expand=True, padx=8, pady=8)
        self.canvas.bind('<Button-1>', self.click)
        self.root.bind('<Escape>', lambda e: self.root.destroy())
        self.root.protocol('WM_DELETE_WINDOW', self.close)
        self.root.after(80, self.poll)
        self.redetect()

    def close(self):
        self.running = False
        self.root.destroy()

    def redetect(self):
        if self.busy:
            return
        self.logical = None
        self.physical = None
        self.status.set('Detecting Blazing Online window and screenshot display...')
        self.start_worker(True)

    def start_worker(self, detect=False):
        if self.busy:
            return
        self.busy = True
        threading.Thread(target=self.worker, args=(detect,), daemon=True).start()

    def worker(self, detect):
        try:
            if detect:
                reconnect()
                logical, physical, image, region = resolve()
                self.events.put(('detected', logical, physical, image, region))
            else:
                self.events.put(('frame', crop(screenshot(self.physical), self.region)))
        except Exception as exc:
            self.events.put(('error', str(exc)))
        finally:
            self.events.put(('ready',))

    def poll(self):
        try:
            while True:
                event = self.events.get_nowait()
                kind = event[0]
                if kind == 'detected':
                    _, self.logical, self.physical, self.image, self.region = event
                    self.status.set(f'Input display {self.logical} | Capture {self.physical} | game area {self.image.width}x{self.image.height} at ({self.region[0]}, {self.region[1]})')
                    self.draw()
                elif kind == 'frame':
                    self.image = event[1]
                    self.draw()
                elif kind == 'error':
                    self.status.set('Error: ' + event[1])
                    print('[ERROR]', event[1], flush=True)
                elif kind == 'ready':
                    self.busy = False
        except queue.Empty:
            pass
        if self.running:
            if self.physical is not None and not self.busy:
                self.start_worker(False)
            self.root.after(500, self.poll)

    def draw(self):
        if self.image is None:
            return
        self.root.update_idletasks()
        cw, ch = max(self.canvas.winfo_width(), 100), max(self.canvas.winfo_height(), 100)
        scale = min(cw / self.image.width, ch / self.image.height)
        w, h = max(1, round(self.image.width * scale)), max(1, round(self.image.height * scale))
        x, y = (cw - w) // 2, (ch - h) // 2
        self.tk_image = ImageTk.PhotoImage(self.image.resize((w, h), Image.Resampling.BILINEAR))
        self.canvas.delete('all')
        self.canvas.create_image(x, y, anchor='nw', image=self.tk_image)
        self.rect = x, y, w, h

    def click(self, event):
        if self.image is None or self.logical is None:
            return
        left, top, w, h = self.rect
        if not (left <= event.x < left + w and top <= event.y < top + h):
            return
        x = min(self.image.width - 1, round((event.x - left) * self.image.width / w))
        y = min(self.image.height - 1, round((event.y - top) * self.image.height / h))
        rx, ry = (round(v) for v in to_reference(x, y, self.image.width, self.image.height))
        line = f'Device ({x}, {y}) | Project reference ({rx}, {ry})'
        self.coords.set(line)
        print(f'[COORD] {line} | "point_name": ({rx}, {ry}),', flush=True)
        if self.taps.get():
            logical = self.logical
            def send():
                sx, sy = x + self.region[0], y + self.region[1]
                flag = [] if str(logical) in ('', '0', 'None') else ['-d', str(logical)]
                result = adb('shell', 'input', *flag, 'tap', str(sx), str(sy))
                if result.returncode:
                    print('[TAP ERROR]', result.stderr.decode(errors='replace'), flush=True)
                else:
                    print(f'[TAP] display={logical} x={sx} y={sy}', flush=True)
            threading.Thread(target=send, daemon=True).start()

    def run(self):
        self.root.mainloop()

if __name__ == '__main__':
    Picker().run()
