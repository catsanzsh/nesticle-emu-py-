import tkinter as tk
from tkinter import filedialog, messagebox, font as tkFont
import os
from nes_py import NesEnv
from PIL import Image, ImageTk

# NesticleTkApp class handles the GUI and emulation
class NesticleTkApp:
    def __init__(self, master_window):
        self.master = master_window
        self.master.title("Nesticle-TK - A NES Emulator")
        self.master.geometry("700x450")
        self.master.configure(bg="#2a0000")
        self.master.resizable(False, False)

        self.current_rom_path = None
        self.env = None
        self.emulation_running = False
        self.pressed_buttons = set()
        
        # Key mappings for NES controller
        self.key_to_button = {
            'Up': 'UP',
            'Down': 'DOWN',
            'Left': 'LEFT',
            'Right': 'RIGHT',
            'z': 'A',
            'x': 'B',
            'Return': 'START',
            'space': 'SELECT',
        }
        self.master.bind('<KeyPress>', self.on_key_press)
        self.master.bind('<KeyRelease>', self.on_key_release)
        self.master.protocol("WM_DELETE_WINDOW", self.on_close)

        # Controls Frame for buttons
        self.controls_frame = tk.Frame(self.master, bg="#333333", pady=7)
        self.controls_frame.pack(side=tk.TOP, fill=tk.X)

        # Cursor label
        self.cursor_label = tk.Label(self.controls_frame, text="Cursor: Custom", bg="#FFFF00", fg="black", font=("Courier", 9, "bold"))
        self.cursor_label.pack(side=tk.LEFT, padx=(5,5), pady=5)

        common_button_style = {
            "bg": "#770000",
            "fg": "#FFFF00",
            "relief": tk.RAISED,
            "bd": 3,
            "padx": 7,
            "pady": 3,
            "font": ("Courier", 10, "bold")
        }

        # Buttons for loading, starting, and resetting
        self.load_btn = tk.Button(self.controls_frame, text="Load ROM", command=self.load_rom_action, **common_button_style)
        self.load_btn.pack(side=tk.LEFT, padx=(10,5), pady=5)

        self.start_btn = tk.Button(self.controls_frame, text="Start", command=self.toggle_emulation_action, state=tk.DISABLED, **common_button_style)
        self.start_btn.pack(side=tk.LEFT, padx=5, pady=5)

        self.reset_btn = tk.Button(self.controls_frame, text="Reset", command=self.reset_rom_action, state=tk.DISABLED, **common_button_style)
        self.reset_btn.pack(side=tk.LEFT, padx=5, pady=5)

        # Game Display Canvas Frame
        self.game_canvas_width = 256 * 2
        self.game_canvas_height = 240 * 2

        canvas_outer_frame = tk.Frame(self.master, bg="#2a0000")
        canvas_outer_frame.pack(expand=True)

        self.game_canvas = tk.Canvas(canvas_outer_frame, width=self.game_canvas_width, height=self.game_canvas_height, bg="black", highlightthickness=2, highlightbackground="#FF0000")
        self.game_canvas.pack(padx=10, pady=10)
        self.game_canvas.config(cursor="pirate")

        self.retro_font_family = "Fixedsys" if "Fixedsys" in tkFont.families() else "Courier"
        self.update_canvas_message("Please load a ROM to start playing!", color="#FF0000")

        # Status Bar
        self.status_label = tk.Label(self.master, text="No ROM loaded. Please load one to start!", bd=2, relief=tk.SUNKEN, anchor=tk.W, bg="#111111", fg="#00FF00", padx=5, font=(self.retro_font_family, 11, "bold"))
        self.status_label.pack(side=tk.BOTTOM, fill=tk.X)

        self.apply_initial_button_states()

    def apply_initial_button_states(self):
        self.start_btn.config(state=tk.DISABLED, text="Start")
        self.reset_btn.config(state=tk.DISABLED)
        self.load_btn.config(state=tk.NORMAL)
        if hasattr(self, 'emulation_loop_id'):
            self.master.after_cancel(self.emulation_loop_id)
        self.emulation_running = False

    def update_canvas_message(self, message_text, color="#00FF00"):
        self.game_canvas.delete("all")
        text_x = self.game_canvas_width / 2
        text_y = self.game_canvas_height / 2
        self.game_canvas.create_text(
            text_x, text_y,
            text=message_text,
            fill=color,
            font=(self.retro_font_family, 14, "bold"),
            anchor=tk.CENTER,
            justify=tk.CENTER,
            width=self.game_canvas_width - 40
        )

    def update_canvas_with_frame(self, observation):
        image = Image.fromarray(observation)
        image = image.resize((self.game_canvas_width, self.game_canvas_height), Image.NEAREST)
        self.current_image = ImageTk.PhotoImage(image)
        self.game_canvas.delete("all")
        self.game_canvas.create_image(0, 0, image=self.current_image, anchor=tk.NW)

    def load_rom_action(self):
        if self.emulation_running:
            self.toggle_emulation_action()

        rom_path_selected = filedialog.askopenfilename(
            title="Select a NES ROM",
            filetypes=(("NES Files", "*.nes"), ("All Files", "*.*"))
        )
        if rom_path_selected:
            try:
                self.current_rom_path = rom_path_selected
                if hasattr(self, 'env'):
                    self.env.close()
                self.env = NesEnv(rom_path=self.current_rom_path)
                observation = self.env.reset()
                self.update_canvas_with_frame(observation)
                rom_filename = os.path.basename(self.current_rom_path)
                self.status_label.config(text=f"ROM loaded: {rom_filename}. Ready to play!")
                self.start_btn.config(state=tk.NORMAL, text="Start")
                self.reset_btn.config(state=tk.DISABLED)
                self.master.title(f"Nesticle-TK - {rom_filename}")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to load ROM: {e}")
                self.status_label.config(text="Failed to load ROM. Please try again.")
                self.current_rom_path = None
                self.env = None
                self.apply_initial_button_states()
                self.update_canvas_message("Failed to load ROM.\nPlease try another one.", color="#FF0000")
                self.master.title("Nesticle-TK - A NES Emulator")
        else:
            if not self.current_rom_path:
                self.status_label.config(text="No ROM loaded. Please load one to start!")

    def toggle_emulation_action(self):
        if not self.current_rom_path or not self.env:
            messagebox.showwarning("Warning", "Please load a ROM first!")
            return

        if self.emulation_running:
            self.emulation_running = False
            self.start_btn.config(text="Start")
            self.reset_btn.config(state=tk.NORMAL)
            self.load_btn.config(state=tk.NORMAL)
            rom_filename = os.path.basename(self.current_rom_path)
            self.status_label.config(text=f"Paused. ROM: {rom_filename}.")
            self.update_canvas_message("Paused. Press Start to resume!", color="#FFFF00")
            if hasattr(self, 'emulation_loop_id'):
                self.master.after_cancel(self.emulation_loop_id)
        else:
            self.emulation_running = True
            self.start_btn.config(text="Pause")
            self.reset_btn.config(state=tk.NORMAL)
            self.load_btn.config(state=tk.DISABLED)
            rom_filename = os.path.basename(self.current_rom_path)
            self.status_label.config(text=f"Playing ROM: {rom_filename}.")
            self.emulation_step()

    def emulation_step(self):
        if self.emulation_running:
            action = list(self.pressed_buttons)
            observation, reward, done, info = self.env.step(action)
            self.update_canvas_with_frame(observation)
            self.emulation_loop_id = self.master.after(16, self.emulation_step)

    def reset_rom_action(self):
        self.emulation_running = False
        if hasattr(self, 'emulation_loop_id'):
            self.master.after_cancel(self.emulation_loop_id)

        if self.current_rom_path:
            try:
                rom_filename = os.path.basename(self.current_rom_path)
                if self.env:
                    observation = self.env.reset()
                    self.update_canvas_with_frame(observation)
                else:
                    self.env = NesEnv(rom_path=self.current_rom_path)
                    observation = self.env.reset()
                    self.update_canvas_with_frame(observation)

                self.status_label.config(text=f"Reset complete. ROM: {rom_filename}. Ready to play!")
                self.start_btn.config(text="Start", state=tk.NORMAL)
                self.reset_btn.config(state=tk.DISABLED)
                self.load_btn.config(state=tk.NORMAL)
            except Exception as e:
                messagebox.showerror("Error", f"Failed to reset ROM: {e}")
                self.status_label.config(text="Failed to reset ROM. Please try again.")
                self.current_rom_path = None
                self.env = None
                self.apply_initial_button_states()
                self.master.title("Nesticle-TK - A NES Emulator")
                self.update_canvas_message("Failed to reset ROM.\nPlease load another one.", color="#FF0000")
        else:
            messagebox.showwarning("Warning", "No ROM loaded to reset!")
            self.apply_initial_button_states()
            self.update_canvas_message("Please load a ROM first to reset it.", color="orange")

    def on_key_press(self, event):
        button = self.key_to_button.get(event.keysym)
        if button and button not in self.pressed_buttons:
            self.pressed_buttons.add(button)

    def on_key_release(self, event):
        button = self.key_to_button.get(event.keysym)
        if button in self.pressed_buttons:
            self.pressed_buttons.remove(button)

    def on_close(self):
        if hasattr(self, 'env'):
            self.env.close()
        self.master.destroy()

def run_nesticle_tk_app():
    main_window = tk.Tk()
    app_instance = NesticleTkApp(main_window)
    main_window.mainloop()

run_nesticle_tk_app()
