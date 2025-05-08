import tkinter as tk
from tkinter import filedialog, messagebox, font as tkFont
import os

# Mock NESSystem class (in a real emulator, this would be super complex, nya!)
class NESSystem:
    def __init__(self, rom_path):
        self.rom_path = rom_path
        self.is_running = False # Changed from self.running to avoid confusion
        print(f"NESSystem: Initialized with ROM: {os.path.basename(self.rom_path)}, meow!")

    def start(self):
        self.is_running = True
        print("NESSystem: Started, let's purr-lay!")

    def stop(self):
        self.is_running = False
        print("NESSystem: Stopped, nap time~")

    def reset(self):
        print("NESSystem: Resetting the purr-gram!")
        # In a real system, this would reload ROM data, reset CPU/PPU state, etc.

class NesticleTkApp:
    def __init__(self, master_window):
        self.master = master_window
        self.master.title("NESTICLE-TK ✨ Meow Version!")
        self.master.geometry("600x400")
        self.master.configure(bg="#2c2c2c") # A nice dark kitty grey
        self.master.resizable(False, False) # Classic fixed size, nya!

        self.current_rom_path = None
        self.nes_system = None
        self.emulation_running = False # Tracks if the emulation *should* be running

        # --- Cute UI Elements ---

        # Controls Frame - for all the clicky buttons!
        self.controls_frame = tk.Frame(self.master, bg="#3e3e3e", pady=7)
        self.controls_frame.pack(side=tk.TOP, fill=tk.X)

        common_button_style = {
            "bg": "#5a5a5a", 
            "fg": "#e0e0e0", 
            "relief": tk.RAISED, 
            "bd": 2, 
            "padx": 5, 
            "pady": 2,
            "font": ("Segoe UI", 9, "bold") # A slightly more modern but clean font
        }

        self.load_btn = tk.Button(self.controls_frame, text="🐾 Load ROM", command=self.load_rom_action, **common_button_style)
        self.load_btn.pack(side=tk.LEFT, padx=(10,5), pady=5) # Extra left padding for the first button

        self.start_btn = tk.Button(self.controls_frame, text="▶ Start", command=self.toggle_emulation_action, state=tk.DISABLED, **common_button_style)
        self.start_btn.pack(side=tk.LEFT, padx=5, pady=5)

        self.reset_btn = tk.Button(self.controls_frame, text="🔄 Reset", command=self.reset_rom_action, state=tk.DISABLED, **common_button_style)
        self.reset_btn.pack(side=tk.LEFT, padx=5, pady=5)

        # Game Display Canvas Frame - to keep our game screen cozy and centered!
        # NES resolution: 256x240. Let's use this directly for that retro feel.
        self.game_canvas_width = 256
        self.game_canvas_height = 240
        
        canvas_outer_frame = tk.Frame(self.master, bg="#2c2c2c") # Match master bg
        canvas_outer_frame.pack(expand=True) # This centers the frame vertically and horizontally

        self.game_canvas = tk.Canvas(canvas_outer_frame, width=self.game_canvas_width, height=self.game_canvas_height, bg="black", highlightthickness=1, highlightbackground="#1a1a1a")
        self.game_canvas.pack(padx=10, pady=10) # Padding around the canvas itself
        
        # Try to use a pixel-y font if available!
        self.retro_font_family = "Fixedsys" if "Fixedsys" in tkFont.families() else "Courier"
        self.update_canvas_message("Load a ROM to purr-lay, nya!")

        # Status Bar - for important kitty messages!
        self.status_label = tk.Label(self.master, text="No ROM loaded. Meow. 🐾", bd=1, relief=tk.SUNKEN, anchor=tk.W, bg="#1e1e1e", fg="lime green", padx=5, font=(self.retro_font_family, 10))
        self.status_label.pack(side=tk.BOTTOM, fill=tk.X)
        
        self.apply_initial_button_states() # Set buttons to their starting purr-sitions!

    def apply_initial_button_states(self):
        self.start_btn.config(state=tk.DISABLED, text="▶ Start")
        self.reset_btn.config(state=tk.DISABLED)
        self.load_btn.config(state=tk.NORMAL)
        if hasattr(self, 'emulation_loop_id'): # Cancel any lingering game loop if app is reset
            self.master.after_cancel(self.emulation_loop_id)
        self.emulation_running = False


    def update_canvas_message(self, message_text, color="lime green"):
        self.game_canvas.delete("all")
        text_x = self.game_canvas_width / 2
        text_y = self.game_canvas_height / 2
        self.game_canvas.create_text(
            text_x, text_y,
            text=message_text,
            fill=color,
            font=(self.retro_font_family, 12, "bold" if self.retro_font_family == "Courier" else "normal"),
            anchor=tk.CENTER,
            justify=tk.CENTER, # For multi-line text
            width=self.game_canvas_width - 20 # Wrap text within canvas
        )

    def load_rom_action(self):
        if self.emulation_running: # If a game is running, let's pause it first!
            self.toggle_emulation_action()

        rom_path_selected = filedialog.askopenfilename(
            title="Select a Meow-tastic NES ROM ✨",
            filetypes=(("NES ROMs", "*.nes"), ("All files", "*.*"))
        )
        if rom_path_selected:
            try:
                self.current_rom_path = rom_path_selected
                self.nes_system = NESSystem(self.current_rom_path) # Make a new kitty NES system!
                rom_filename = os.path.basename(self.current_rom_path)
                self.status_label.config(text=f"Purrfect! ROM: {rom_filename}")
                self.update_canvas_message("Ready to purr-lay, nya!")
                self.start_btn.config(state=tk.NORMAL, text="▶ Start")
                self.reset_btn.config(state=tk.DISABLED) # Can only reset after starting or when paused
                self.master.title(f"NESTICLE-TK ✨ - {rom_filename}")
            except Exception as e:
                messagebox.showerror("Hiss! Error 🙀", f"Failed to load ROM: {e}")
                self.status_label.config(text="Error loading ROM. Sad meow. 😿")
                self.current_rom_path = None
                self.nes_system = None
                self.apply_initial_button_states()
                self.update_canvas_message("Failed to load ROM.\nTry another, purrhaps?", color="red")
                self.master.title("NESTICLE-TK ✨ Meow Version!")
        else:
            if not self.current_rom_path: # Only say cancelled if no ROM was previously loaded or active
                self.status_label.config(text="ROM loading cancelled. Aww. 😿")

    def toggle_emulation_action(self):
        if not self.current_rom_path or not self.nes_system:
            messagebox.showwarning("Hold your paws! 🐾", "Please load a ROM first, silly kitty!")
            return

        if self.emulation_running: # If running, then we PAUSE
            self.emulation_running = False
            if self.nes_system: self.nes_system.stop()
            self.start_btn.config(text="▶ Start") # Change to "Start" indicating it's paused
            self.reset_btn.config(state=tk.NORMAL) 
            self.load_btn.config(state=tk.NORMAL)   
            rom_filename = os.path.basename(self.current_rom_path)
            self.status_label.config(text=f"Paused. ROM: {rom_filename}. Take a kitty break!")
            self.update_canvas_message("Paused. Press Start\nto resume purr-laying!")
            if hasattr(self, 'emulation_loop_id'): # Stop the game loop, nya!
                self.master.after_cancel(self.emulation_loop_id)
        else: # If not running, then we START
            self.emulation_running = True
            if self.nes_system: self.nes_system.start()
            self.start_btn.config(text="❚❚ Pause") # Change to "Pause" indicating it's running
            self.reset_btn.config(state=tk.NORMAL) 
            self.load_btn.config(state=tk.DISABLED) # No new ROMs while playing, silly!
            rom_filename = os.path.basename(self.current_rom_path)
            self.status_label.config(text=f"Purr-laying! ROM: {rom_filename}. Go, kitty, go!")
            # self.game_loop_tick() # Start the game loop!

            # For this mock, just display a message. In a real emu, this starts screen updates.
            self.update_canvas_message("Emulation Running!\nニャー (Nya~!)")


    # Placeholder for actual game loop ticks
    # def game_loop_tick(self):
    #     if self.emulation_running and self.nes_system:
    #         # Real emulation would happen here:
    #         # self.nes_system.execute_cycle()
    #         # frame_data = self.nes_system.get_ppu_frame_buffer()
    #         # self.draw_frame_on_canvas(frame_data)
    #         
    #         # For now, let's just imagine~
    #         # self.update_canvas_message(f"Purr-tending to play...\nFrame: {self.frames_rendered}")
    #         # self.frames_rendered += 1
    #         self.emulation_loop_id = self.master.after(16, self.game_loop_tick) # ~60 FPS of purr-fection!


    def reset_rom_action(self):
        # Using your cute logic here, nya!
        self.emulation_running = False # Stop any ongoing emulation (important first step!)
        if hasattr(self, 'emulation_loop_id'): # Stop the game loop if it was running
            self.master.after_cancel(self.emulation_loop_id)

        if self.current_rom_path:
            try:
                rom_filename = os.path.basename(self.current_rom_path) # Get the cute ROM name
                # Re-initialize or reset NESSystem
                if self.nes_system:
                    self.nes_system.reset() # Tell the system to reset its tiny kitty brain
                else: # This case should be rare if buttons are managed well
                    self.nes_system = NESSystem(self.current_rom_path)

                self.status_label.config(text=f"Reset! ROM: {rom_filename}. Fresh start, meow!")
                self.update_canvas_message("Ready to purr-lay again!\nRefreshed and fluffy!")
                self.start_btn.config(text="▶ Start", state=tk.NORMAL) # Ready to start again
                self.reset_btn.config(state=tk.DISABLED) # Disable reset immediately after reset (as you wanted!)
                self.load_btn.config(state=tk.NORMAL) # Can load a new ROM
            except Exception as e:
                messagebox.showerror("Uh oh, kitty tripped! 🙀", f"Failed to reset ROM: {e}")
                self.status_label.config(text="Error resetting ROM. Sad meow. 😿")
                # If reset fails critically, the ROM might be considered problematic
                self.current_rom_path = None 
                self.nes_system = None
                self.apply_initial_button_states() # Go to a safe state
                self.master.title("NESTICLE-TK ✨ Meow Version!")
                self.update_canvas_message("Reset failed critically.\nPlease load a new ROM.", color="red")
        else:
            # This should ideally not be reached if reset_btn is properly managed
            messagebox.showwarning("No ROM, no reset! 😿", "No ROM loaded to reset, purr-lease load one first!")
            self.apply_initial_button_states() # Go back to initial state if no ROM
            self.update_canvas_message("Load a ROM first to reset it, silly!")


# Main application execution for this cute little app, nya!
def run_nesticle_tk_app():
    main_window = tk.Tk()
    app_instance = NesticleTkApp(main_window)
    main_window.mainloop()

# Let's run this kitty!
run_nesticle_tk_app()
