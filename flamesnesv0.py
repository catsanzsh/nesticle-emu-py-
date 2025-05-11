import tkinter as tk
from tkinter import filedialog, messagebox, font as tkFont
import os
import numpy as np
from PIL import Image, ImageTk
import nes_py

class NESSystem:
    def __init__(self, rom_path):
        self.rom_path = rom_path
        self.is_running = False
        self.env = None

        # Check if ROM file exists
        if not os.path.exists(self.rom_path):
            raise FileNotFoundError(f"ROM file not found: {self.rom_path}")

        # Validate ROM size based on iNES header
        with open(self.rom_path, 'rb') as f:
            header = f.read(16)
            if len(header) != 16 or header[:4] != b'NES\x1a':
                raise ValueError("Invalid NES ROM header. Must start with 'NES\\x1a'.")
            prg_banks = header[4]  # Number of 16KB PRG banks
            chr_banks = header[5]  # Number of 8KB CHR banks
            if prg_banks == 0:
                raise ValueError("Invalid ROM: Number of PRG banks is zero.")
            # Check for trainer (512 bytes) if bit 2 of header[6] is set
            has_trainer = header[6] & 0x04
            expected_size = 16 + (512 if has_trainer else 0) + (prg_banks * 16384) + (chr_banks * 8192)
            actual_size = os.path.getsize(self.rom_path)
            if actual_size != expected_size:
                raise ValueError(f"Invalid ROM size. Expected {expected_size} bytes, got {actual_size} bytes.")

        # Initialize nes_py environment
        try:
            self.env = nes_py.NESEnv(self.rom_path)
            self.env.reset()
            print(f"NESSystem: Initialized with ROM: {os.path.basename(self.rom_path)}, meow!")
        except Exception as e:
            print(f"NESSystem: Error initializing nes-py environment: {e}")
            raise

    def start(self):
        self.is_running = True
        print("NESSystem: Started, let's purr-lay!")

    def stop(self):
        self.is_running = False
        print("NESSystem: Stopped, nap time~")

    def reset(self):
        if self.env:
            self.env.reset()
            print("NESSystem: Resetting the purr-gram!")

    def step(self, action=0):
        if not self.env or not self.is_running:
            return None, 0, False, False, {}
        state, reward, terminated, truncated, info = self.env.step(action)
        done = terminated or truncated
        if done:
            print(f"NESSystem: Step returned done (terminated={terminated}, truncated={truncated}).")
        return state, reward, terminated, truncated, info

    def get_current_frame(self):
        if self.env:
            return self.env.screen
        return None

    def close(self):
        if self.env:
            self.env.close()
            self.env = None
            print("NESSystem: nes-py environment closed, purr-bye!")

class NesticleTkApp:
    def __init__(self, master_window):
        self.master = master_window
        self.master.title("NESTICLE-TK ✨ Meow Version!")
        self.master.geometry("600x450")
        self.master.configure(bg="#2c2c2c")
        self.master.resizable(False, False)

        self.current_rom_path = None
        self.nes_system = None
        self.emulation_running = False
        self.emulation_loop_id = None
        self.game_canvas_width = 256
        self.game_canvas_height = 240

        # Input state dictionary for NES controller
        self.input_state = {
            'right': False, 'left': False, 'up': False, 'down': False,
            'a': False, 'b': False, 'start': False, 'select': False
        }

        # UI setup
        self.controls_frame = tk.Frame(self.master, bg="#3e3e3e", pady=7)
        self.controls_frame.pack(side=tk.TOP, fill=tk.X)
        
        button_style = {"bg": "#5a5a5a", "fg": "#e0e0e0", "relief": tk.RAISED, "bd": 2, "padx": 5, "pady": 2, "font": ("Segoe UI", 9, "bold")}
        
        self.load_btn = tk.Button(self.controls_frame, text="🐾 Load ROM", command=self.load_rom_action, **button_style)
        self.load_btn.pack(side=tk.LEFT, padx=(10,5), pady=5)
        
        self.start_btn = tk.Button(self.controls_frame, text="▶ Start", command=self.toggle_emulation_action, state=tk.DISABLED, **button_style)
        self.start_btn.pack(side=tk.LEFT, padx=5, pady=5)
        
        self.reset_btn = tk.Button(self.controls_frame, text="🔄 Reset", command=self.reset_rom_action, state=tk.DISABLED, **button_style)
        self.reset_btn.pack(side=tk.LEFT, padx=5, pady=5)
        
        canvas_outer_frame = tk.Frame(self.master, bg="#2c2c2c")
        canvas_outer_frame.pack(expand=True)
        
        self.game_canvas = tk.Canvas(canvas_outer_frame, width=self.game_canvas_width, height=self.game_canvas_height, bg="black", highlightthickness=1, highlightbackground="#1a1a1a")
        self.game_canvas.pack(padx=10, pady=10)
        self.tk_image = None
        
        self.retro_font_family = "Fixedsys" if "Fixedsys" in tkFont.families() else "Courier"
        self.update_canvas_message("Load a ROM to purr-lay, nya!")
        
        self.status_label = tk.Label(self.master, text="No ROM loaded. Meow. 🐾", bd=1, relief=tk.SUNKEN, anchor=tk.W, bg="#1e1e1e", fg="lime green", padx=5, font=(self.retro_font_family, 10))
        self.status_label.pack(side=tk.BOTTOM, fill=tk.X)

        # Bind keyboard events
        self.master.bind('<KeyPress>', self.key_press)
        self.master.bind('<KeyRelease>', self.key_release)

        self.apply_initial_button_states()
        self.master.protocol("WM_DELETE_WINDOW", self.on_closing_application)

    def get_action(self):
        action = 0
        if self.input_state['a']:      action |= 1 << 0  # A
        if self.input_state['b']:      action |= 1 << 1  # B
        if self.input_state['select']: action |= 1 << 2  # Select
        if self.input_state['start']:  action |= 1 << 3  # Start
        if self.input_state['up']:     action |= 1 << 4  # Up
        if self.input_state['down']:   action |= 1 << 5  # Down
        if self.input_state['left']:   action |= 1 << 6  # Left
        if self.input_state['right']:  action |= 1 << 7  # Right
        return action

    def key_press(self, event):
        key = event.keysym.lower()
        mapping = {
            'right': 'right', 'left': 'left', 'up': 'up', 'down': 'down',
            'z': 'a', 'x': 'b', 'return': 'start', 'shift': 'select'
        }
        if key in mapping and self.emulation_running:
            self.input_state[mapping[key]] = True

    def key_release(self, event):
        key = event.keysym.lower()
        mapping = {
            'right': 'right', 'left': 'left', 'up': 'up', 'down': 'down',
            'z': 'a', 'x': 'b', 'return': 'start', 'shift': 'select'
        }
        if key in mapping:
            self.input_state[mapping[key]] = False

    def game_loop_tick(self):
        if not self.emulation_running or not self.nes_system or not self.nes_system.env:
            self.emulation_running = False
            if self.emulation_loop_id:
                self.master.after_cancel(self.emulation_loop_id)
                self.emulation_loop_id = None
            return

        try:
            action = self.get_action()
            state, reward, terminated, truncated, info = self.nes_system.step(action)
            done = terminated or truncated

            if state is not None:
                self.draw_frame_on_canvas(state)
            else:
                print("Game loop: No state returned. Stopping emulation.")
                self.update_canvas_message("Emulation hiccup!\nFrame data missing.", "orange")
                self.toggle_emulation_action()
                return

            if done:
                print(f"Game loop: 'done' reported. Emulation continues until user action.")

            if self.emulation_running:
                self.emulation_loop_id = self.master.after(16, self.game_loop_tick)
        except Exception as e:
            print(f"Error in game loop: {e}")
            messagebox.showerror("Runtime Purr-oblem 🙀", f"Error during emulation: {e}")
            self.emulation_running = False
            if self.nes_system: self.nes_system.stop()
            if self.emulation_loop_id:
                self.master.after_cancel(self.emulation_loop_id)
                self.emulation_loop_id = None
            self.start_btn.config(text="▶ Start")
            self.reset_btn.config(state=tk.NORMAL if self.current_rom_path else tk.DISABLED)
            self.load_btn.config(state=tk.NORMAL)
            self.status_label.config(text="Emulation error. Sad meow. 😿")
            self.update_canvas_message("Emulation stopped\ndue to an error.", color="red")

    def apply_initial_button_states(self):
        self.start_btn.config(state=tk.DISABLED, text="▶ Start")
        self.reset_btn.config(state=tk.DISABLED)
        self.load_btn.config(state=tk.NORMAL)
        if self.emulation_loop_id:
            self.master.after_cancel(self.emulation_loop_id)
            self.emulation_loop_id = None
        self.emulation_running = False

    def update_canvas_message(self, message_text, color="lime green"):
        self.game_canvas.delete("all")
        text_x = self.game_canvas_width / 2
        text_y = self.game_canvas_height / 2
        self.game_canvas.create_text(
            text_x, text_y, text=message_text, fill=color,
            font=(self.retro_font_family, 12, "bold" if self.retro_font_family == "Courier" else "normal"),
            anchor=tk.CENTER, justify=tk.CENTER, width=self.game_canvas_width - 20
        )
        self.tk_image = None

    def draw_frame_on_canvas(self, frame_data_np):
        if frame_data_np is None:
            print("draw_frame_on_canvas: Received None for frame_data_np.")
            return
        try:
            image = Image.fromarray(frame_data_np.astype(np.uint8), 'RGB')
            self.tk_image = ImageTk.PhotoImage(image=image)
            self.game_canvas.delete("all")
            self.game_canvas.create_image(0, 0, anchor=tk.NW, image=self.tk_image)
        except Exception as e:
            print(f"Error drawing frame: {e}")
            self.update_canvas_message(f"Frame display error!\n{e}", "red")
            if self.emulation_running:
                self.toggle_emulation_action()

    def load_rom_action(self):
        if self.emulation_running:
            self.toggle_emulation_action()
        if self.nes_system:
            self.nes_system.close()
            self.nes_system = None
            self.tk_image = None
        rom_path_selected = filedialog.askopenfilename(
            title="Select a Meow-tastic NES ROM ✨",
            filetypes=(("NES ROMs", "*.nes"), ("All files", "*.*"))
        )
        if rom_path_selected:
            try:
                self.current_rom_path = rom_path_selected
                self.nes_system = NESSystem(self.current_rom_path)
                rom_filename = os.path.basename(self.current_rom_path)
                self.status_label.config(text=f"Purrfect! ROM: {rom_filename}")
                initial_frame = self.nes_system.get_current_frame()
                if initial_frame is not None:
                    self.draw_frame_on_canvas(initial_frame)
                else:
                    self.update_canvas_message("Ready to purr-lay, nya!")
                self.start_btn.config(state=tk.NORMAL, text="▶ Start")
                self.reset_btn.config(state=tk.DISABLED)
                self.master.title(f"NESTICLE-TK ✨ - {rom_filename}")
                self.emulation_running = False
            except Exception as e:
                messagebox.showerror("Hiss! Error 🙀", f"Failed to load ROM: {e}")
                self.status_label.config(text="Error loading ROM. Sad meow. 😿")
                if self.nes_system: self.nes_system.close()
                self.current_rom_path = None
                self.nes_system = None
                self.apply_initial_button_states()
                self.update_canvas_message("Failed to load ROM.\nTry another, purrhaps?", color="red")
                self.master.title("NESTICLE-TK ✨ Meow Version!")

    def toggle_emulation_action(self):
        if not self.current_rom_path or not self.nes_system:
            messagebox.showwarning("Hold your paws! 🐾", "Please load a ROM first, silly kitty!")
            return
        if self.emulation_running:  # Pause
            self.emulation_running = False
            if self.nes_system: self.nes_system.stop()
            if self.emulation_loop_id:
                self.master.after_cancel(self.emulation_loop_id)
                self.emulation_loop_id = None
            self.start_btn.config(text="▶ Start")
            self.reset_btn.config(state=tk.NORMAL)
            self.load_btn.config(state=tk.NORMAL)
            rom_filename = os.path.basename(self.current_rom_path)
            self.status_label.config(text=f"Paused. ROM: {rom_filename}. Take a kitty break!")
            self.update_canvas_message("Paused. Press Start\nto resume purr-laying!")
        else:  # Start/Resume
            self.emulation_running = True
            if self.nes_system: self.nes_system.start()
            self.start_btn.config(text="❚❚ Pause")
            self.reset_btn.config(state=tk.NORMAL)
            self.load_btn.config(state=tk.DISABLED)
            rom_filename = os.path.basename(self.current_rom_path)
            self.status_label.config(text=f"Purr-laying! ROM: {rom_filename}. Go, kitty, go!")
            self.game_canvas.delete("all")
            self.game_loop_tick()

    def reset_rom_action(self):
        was_running = self.emulation_running
        if self.emulation_running:
            self.emulation_running = False
            if self.emulation_loop_id:
                self.master.after_cancel(self.emulation_loop_id)
                self.emulation_loop_id = None
            if self.nes_system: self.nes_system.stop()
        if self.current_rom_path and self.nes_system:
            try:
                rom_filename = os.path.basename(self.current_rom_path)
                self.nes_system.reset()
                frame_after_reset = self.nes_system.get_current_frame()
                if frame_after_reset is not None:
                    self.draw_frame_on_canvas(frame_after_reset)
                else:
                    self.update_canvas_message("Ready to purr-lay again!\nRefreshed and fluffy!")
                self.status_label.config(text=f"Reset! ROM: {rom_filename}. Fresh start, meow!")
                self.start_btn.config(text="▶ Start", state=tk.NORMAL)
                self.reset_btn.config(state=tk.DISABLED)
                self.load_btn.config(state=tk.NORMAL)
                self.emulation_running = False
            except Exception as e:
                messagebox.showerror("Uh oh, kitty tripped! 🙀", f"Failed to reset ROM: {e}")
                self.status_label.config(text="Error resetting ROM. Sad meow. 😿")
                if self.nes_system: self.nes_system.close()
                self.current_rom_path = None
                self.nes_system = None
                self.apply_initial_button_states()
                self.update_canvas_message("Reset failed.\nPlease load a new ROM.", color="red")
                self.master.title("NESTICLE-TK ✨ Meow Version!")

    def on_closing_application(self):
        print("Closing application, meow...")
        if self.emulation_running:
            self.emulation_running = False
            if self.emulation_loop_id:
                self.master.after_cancel(self.emulation_loop_id)
        if self.nes_system:
            self.nes_system.close()
        self.master.destroy()

def run_nesticle_tk_app():
    try:
        import nes_py
        from PIL import Image, ImageTk
        import numpy
    except ImportError as e:
        root_check = tk.Tk()
        root_check.withdraw()
        messagebox.showerror("Dependency Error", f"Missing critical library: {e}.\nPlease install nes-py, Pillow, and numpy.\n\nExample: pip install nes-py Pillow numpy")
        root_check.destroy()
        return
    main_window = tk.Tk()
    app_instance = NesticleTkApp(main_window)
    main_window.mainloop()

if __name__ == "__main__":
    run_nesticle_tk_app()
