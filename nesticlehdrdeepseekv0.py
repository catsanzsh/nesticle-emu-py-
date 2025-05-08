import tkinter as tk
from tkinter import filedialog
import pygame
import asyncio
import platform
from PIL import Image, ImageTk
import numpy as np

class NESGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("NESTicle Emulator")
        self.root.geometry("600x400")
        
        # Setup GUI components
        self.create_widgets()
        
        # Pygame initialization
        self.pygame_frame = tk.Frame(self.root, width=256, height=240)
        self.pygame_frame.pack(side=tk.LEFT, padx=10, pady=10)
        
        # Emulation system
        self.nes = None
        self.running = False
        self.current_rom = None
        
        # Pygame surface for Tkinter
        self.pygame_surface = None
        self.tk_image = None

    def create_widgets(self):
        control_frame = tk.Frame(self.root)
        control_frame.pack(side=tk.RIGHT, padx=10, pady=10)
        
        self.load_btn = tk.Button(control_frame, text="Load ROM", command=self.load_rom)
        self.load_btn.pack(pady=5)
        
        self.start_btn = tk.Button(control_frame, text="Start", command=self.start_emulation)
        self.start_btn.pack(pady=5)
        
        self.reset_btn = tk.Button(control_frame, text="Reset", command=self.reset_emulation)
        self.reset_btn.pack(pady=5)
        
        self.status_label = tk.Label(control_frame, text="Status: Stopped")
        self.status_label.pack(pady=5)
        
        # Pygame display area
        self.canvas = tk.Canvas(self.pygame_frame, width=256, height=240)
        self.canvas.pack()

    def load_rom(self):
        file_path = filedialog.askopenfilename(filetypes=[("NES ROMs", "*.nes")])
        if file_path:
            self.current_rom = file_path
            self.status_label.config(text=f"Loaded: {file_path.split('/')[-1]}")

    def start_emulation(self):
        if self.current_rom and not self.running:
            with open(self.current_rom, "rb") as f:
                rom_data = f.read()
            self.nes = NESSystem(rom_data)
            self.running = True
            self.status_label.config(text="Status: Running")
            self.root.after(10, self.update_display)
            asyncio.ensure_future(self.run_emulation())

    async def run_emulation(self):
        while self.running:
            # Process Pygame events
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.running = False
            
            # Run emulation cycle
            if self.nes:
                cpu_cycles = self.nes.cpu.step()
                self.nes.ppu.step(cpu_cycles)
            
            # Maintain 60 FPS
            await asyncio.sleep(1/60)

    def update_display(self):
        if self.nes and self.running:
            # Convert Pygame surface to Tkinter PhotoImage
            img_str = pygame.image.tostring(self.nes.ppu.framebuffer, 'RGB')
            img = Image.frombytes('RGB', (256, 240), img_str)
            self.tk_image = ImageTk.PhotoImage(img)
            
            # Update canvas
            self.canvas.create_image(0, 0, anchor=tk.NW, image=self.tk_image)
            
            # Schedule next update
            self.root.after(16, self.update_display)

    def reset_emulation(self):
        self.running = False
        self.nes = None
        self.status_label.config(text="Status: Stopped")
        self.canvas.delete("all")

# Include all previous NES emulation classes (ROM, Mapper, CPU, PPU, etc.) here
# ...

if __name__ == "__main__":
    root = tk.Tk()
    app = NESGUI(root)
    
    if platform.system() == 'Windows':
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    
    loop = asyncio.get_event_loop()
    loop.run_forever()
