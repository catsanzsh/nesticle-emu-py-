import tkinter as tk
from tkinter import filedialog, messagebox, font as tkFont
import os
import numpy as np # For nes-py frame data
from PIL import Image, ImageTk # For displaying nes-py frames in Tkinter
import nes_py # For the NES emulation core

# --- NESSystem Class (Integrated with nes-py) ---
class NESSystem:
    def __init__(self, rom_path):
        self.rom_path = rom_path
        self.is_running = False # Reflects if the system *should* be stepping
        self.env = None # Initialize env as None
        try:
            self.env = nes_py.NESEnv(self.rom_path)
            self.env.reset() # Initial reset to get the first frame
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
            # self.is_running = False # Resetting often implies a stopped state until user starts again
            print("NESSystem: Resetting the purr-gram!")
        else:
            print("NESSystem: Cannot reset, environment not initialized.")

    def step(self, action=0): # action=0 is typically 'NOOP'
        if not self.env or not self.is_running: # Check internal flag
            return None, 0, False, False, {}

        state, reward, terminated, truncated, info = self.env.step(action=action)
        done = terminated or truncated
        
        if done:
            print(f"NESSystem: Step returned done (terminated={terminated}, truncated={truncated}). ROM: {os.path.basename(self.rom_path)}")
            # self.is_running = False # Optional: auto-stop on game over

        return state, reward, terminated, truncated, info

    def get_current_frame(self):
        if self.env:
            return self.env.screen # NumPy array (240, 256, 3)
        return None

    def close(self):
        if self.env:
            self.env.close()
            self.env = None
            self.is_running = False
            print("NESSystem: nes-py environment closed, purr-bye!")

# --- Tkinter Application Class ---
class NesticleTkApp:
    def __init__(self, master_window):
        self.master = master_window
        self.master.title("NESTICLE-TK ✨ Meow Version!")
        self.master.geometry("600x450")
        self.master.configure(bg="#2c2c2c")
        self.master.resizable(False, False)

        self.current_rom_path = None
        self.nes_system = None
        self.emulation_running = False # Drives the Tkinter UI loop
        self.emulation_loop_id = None

        self.game_canvas_width = 256
        self.game_canvas_height = 240

        self.controls_frame = tk.Frame(self.master, bg="#3e3e3e", pady=7)
        self.controls_frame.pack(side=tk.TOP, fill=tk.X)

        common_button_style = {
            "bg": "#5a5a5a", "fg": "#e0e0e0",
            "relief": tk.RAISED, "bd": 2, "padx": 5, "pady": 2,
            "font": ("Segoe UI", 9, "bold")
        }

        self.load_btn = tk.Button(self.controls_frame, text="🐾 Load ROM", command=self.load_rom_action, **common_button_style)
        self.load_btn.pack(side=tk.LEFT, padx=(10,5), pady=5)

        self.start_btn = tk.Button(self.controls_frame, text="▶ Start", command=self.toggle_emulation_action, state=tk.DISABLED, **common_button_style)
        self.start_btn.pack(side=tk.LEFT, padx=5, pady=5)

        self.reset_btn = tk.Button(self.controls_frame, text="🔄 Reset", command=self.reset_rom_action, state=tk.DISABLED, **common_button_style)
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

        self.apply_initial_button_states()
        self.master.protocol("WM_DELETE_WINDOW", self.on_closing_application)

    def apply_initial_button_states(self):
        self.start_btn.config(state=tk.DISABLED, text="▶ Start")
        self.reset_btn.config(state=tk.DISABLED) # Correct: No ROM, no reset
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
            text_x, text_y,
            text=message_text, fill=color,
            font=(self.retro_font_family, 12, "bold" if self.retro_font_family == "Courier" else "normal"),
            anchor=tk.CENTER, justify=tk.CENTER, width=self.game_canvas_width - 20
        )
        self.tk_image = None # Clear any lingering PhotoImage

    def draw_frame_on_canvas(self, frame_data_np):
        if frame_data_np is None:
            print("draw_frame_on_canvas: Received None for frame_data_np.")
            # Optionally, show a message, but be careful about flickering if it's transient
            # self.update_canvas_message("No frame data to show, meow?", "orange")
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
                self.toggle_emulation_action() # Stop emulation

    def load_rom_action(self):
        if self.emulation_running:
            self.toggle_emulation_action() # Pause if running

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
                # --- FIX 1 Start ---
                self.reset_btn.config(state=tk.NORMAL) # Enable reset once ROM is loaded
                # --- FIX 1 End ---
                self.load_btn.config(state=tk.NORMAL) # Keep load enabled
                self.master.title(f"NESTICLE-TK ✨ - {rom_filename}")
                self.emulation_running = False
            except Exception as e:
                messagebox.showerror("Hiss! Error 🙀", f"Failed to load ROM with nes-py: {e}")
                self.status_label.config(text="Error loading ROM. Sad meow. 😿")
                if self.nes_system: self.nes_system.close()
                self.current_rom_path = None
                self.nes_system = None
                self.apply_initial_button_states()
                self.update_canvas_message("Failed to load ROM.\nTry another, purrhaps?", color="red")
                self.master.title("NESTICLE-TK ✨ Meow Version!")
        else:
            if not self.current_rom_path:
                self.status_label.config(text="ROM loading cancelled. Aww. 😿")
                self.update_canvas_message("Load a ROM to purr-lay, nya!") # Reset canvas message


    def game_loop_tick(self):
        if not self.emulation_running or not self.nes_system or not self.nes_system.env:
            self.emulation_running = False 
            if self.emulation_loop_id:
                self.master.after_cancel(self.emulation_loop_id)
                self.emulation_loop_id = None
            # Update UI to reflect that emulation is no longer truly running if it gets here unexpectedly
            if not self.current_rom_path: # If ROM was somehow lost
                 self.apply_initial_button_states()
            else: # If ROM exists but loop stopped, go to a paused-like state
                 self.start_btn.config(text="▶ Start", state=tk.NORMAL)
                 self.reset_btn.config(state=tk.NORMAL)
                 self.load_btn.config(state=tk.NORMAL)
            return

        try:
            action = 0 
            state, reward, terminated, truncated, info = self.nes_system.step(action)
            done = terminated or truncated

            if state is not None:
                self.draw_frame_on_canvas(state)
            else:
                print("Game loop: No state (frame) returned from nes_system.step. Assuming env closed or error.")
                self.update_canvas_message("Emulation hiccup!\nFrame data missing.", "orange")
                self.toggle_emulation_action() # This will set emulation_running to False and update buttons
                return

            if done:
                print(f"Game loop: nes-py reported 'done' for {os.path.basename(self.current_rom_path)}. Emulation continues (displaying last frame).")
                # Consider auto-pausing or specific UI feedback for "game over"
                # For now, it just stops stepping if nes_system.step internally sets self.nes_system.is_running to False.
                # If nes_py automatically stops providing new frames or behavior changes on 'done',
                # this loop might effectively pause.
                # If the game itself handles 'done' by showing a screen and waiting, it will continue.

            if self.emulation_running: # Re-check, as 'done' or an error in step might change state
                self.emulation_loop_id = self.master.after(16, self.game_loop_tick) # ~60 FPS
            else: # If self.emulation_running became false during the step (e.g. from an error handler or 'done' logic)
                if self.emulation_loop_id:
                    self.master.after_cancel(self.emulation_loop_id)
                    self.emulation_loop_id = None
                # Update UI to reflect actual paused state
                self.start_btn.config(text="▶ Start", state=tk.NORMAL)
                self.reset_btn.config(state=tk.NORMAL) # Should be normal if ROM loaded
                self.load_btn.config(state=tk.NORMAL)
                rom_filename = os.path.basename(self.current_rom_path) if self.current_rom_path else "No ROM"
                self.status_label.config(text=f"Paused. ROM: {rom_filename}")


        except Exception as e:
            print(f"Error in game loop: {e}")
            messagebox.showerror("Runtime Purr-oblem 🙀", f"Error during emulation: {e}")
            self.emulation_running = False
            if self.nes_system: self.nes_system.stop()
            
            if self.emulation_loop_id:
                self.master.after_cancel(self.emulation_loop_id)
                self.emulation_loop_id = None

            self.start_btn.config(text="▶ Start", state=tk.NORMAL if self.current_rom_path else tk.DISABLED)
            self.reset_btn.config(state=tk.NORMAL if self.current_rom_path else tk.DISABLED)
            self.load_btn.config(state=tk.NORMAL)
            self.status_label.config(text="Emulation error. Sad meow. 😿")
            self.update_canvas_message("Emulation stopped\ndue to an error.", color="red")

    def toggle_emulation_action(self):
        if not self.current_rom_path or not self.nes_system:
            messagebox.showwarning("Hold your paws! 🐾", "Please load a ROM first, silly kitty!")
            return

        if self.emulation_running: # PAUSE action
            self.emulation_running = False
            if self.nes_system: self.nes_system.stop() # Signal nes_system to stop stepping
            if self.emulation_loop_id:
                self.master.after_cancel(self.emulation_loop_id)
                self.emulation_loop_id = None

            self.start_btn.config(text="▶ Start")
            self.reset_btn.config(state=tk.NORMAL) # Reset is fine when paused
            self.load_btn.config(state=tk.NORMAL) # Load is fine when paused
            rom_filename = os.path.basename(self.current_rom_path)
            self.status_label.config(text=f"Paused. ROM: {rom_filename}. Take a kitty break!")
            # --- FIX 2 Start (Removed update_canvas_message) ---
            # Canvas will retain the last frame.
            # --- FIX 2 End ---

        else: # START / RESUME action
            self.emulation_running = True
            if self.nes_system: self.nes_system.start() # Signal nes_system to start stepping

            self.start_btn.config(text="❚❚ Pause")
            self.reset_btn.config(state=tk.NORMAL) # Reset is fine when running (it will pause then reset)
            self.load_btn.config(state=tk.DISABLED) # Don't load while actively running
            rom_filename = os.path.basename(self.current_rom_path)
            self.status_label.config(text=f"Purr-laying! ROM: {rom_filename}. Go, kitty, go!")
            
            self.game_canvas.delete("all") # Clear any "Paused", "Error", or initial messages

            # --- FIX 4 Start (Robustness) ---
            if self.emulation_loop_id: # Ensure no old loop is lurking
                self.master.after_cancel(self.emulation_loop_id)
                self.emulation_loop_id = None
            # --- FIX 4 End ---
            self.game_loop_tick()


    def reset_rom_action(self):
        # Stop emulation if it's running
        if self.emulation_running:
            self.emulation_running = False 
            if self.emulation_loop_id:
                self.master.after_cancel(self.emulation_loop_id)
                self.emulation_loop_id = None
            if self.nes_system: self.nes_system.stop() # Signal internal NES system to stop

        if self.current_rom_path and self.nes_system:
            try:
                rom_filename = os.path.basename(self.current_rom_path)
                self.nes_system.reset() # This calls env.reset()

                frame_after_reset = self.nes_system.get_current_frame()
                if frame_after_reset is not None:
                    self.draw_frame_on_canvas(frame_after_reset)
                else:
                    self.update_canvas_message("Ready to purr-lay again!\nRefreshed and fluffy!")

                self.status_label.config(text=f"Reset! ROM: {rom_filename}. Fresh start, meow!")
                self.start_btn.config(text="▶ Start", state=tk.NORMAL)
                # --- FIX 1 Start ---
                self.reset_btn.config(state=tk.NORMAL) # Keep reset enabled
                # --- FIX 1 End ---
                self.load_btn.config(state=tk.NORMAL)
                self.emulation_running = False # Ensure state is not running after reset

            except Exception as e:
                messagebox.showerror("Uh oh, kitty tripped! 🙀", f"Failed to reset ROM: {e}")
                self.status_label.config(text="Error resetting ROM. Sad meow. 😿")
                if self.nes_system: self.nes_system.close()
                self.current_rom_path = None
                self.nes_system = None
                self.apply_initial_button_states()
                self.master.title("NESTICLE-TK ✨ Meow Version!")
                self.update_canvas_message("Reset failed.\nPlease load a new ROM.", color="red")
        else:
            messagebox.showwarning("No ROM, no reset! 😿", "No ROM loaded to reset, purr-lease load one first!")
            self.apply_initial_button_states()
            self.update_canvas_message("Load a ROM first to reset it, silly!")


    def on_closing_application(self):
        print("Closing application, meow...")
        if self.emulation_running:
            self.emulation_running = False
            if self.emulation_loop_id:
                self.master.after_cancel(self.emulation_loop_id)
                self.emulation_loop_id = None # Good practice
        if self.nes_system:
            self.nes_system.close()
        self.master.destroy()

# Main application execution
def run_nesticle_tk_app():
    try:
        # Check for critical imports early
        import nes_py
        from PIL import Image, ImageTk
        import numpy
    except ImportError as e:
        try:
            root_check = tk.Tk()
            root_check.withdraw()
            messagebox.showerror("Dependency Error", f"Missing critical library: {e}.\nPlease install nes-py, Pillow, and numpy.\n\nExample: pip install nes-py Pillow numpy")
            root_check.destroy()
        except tk.TclError:
            print(f"CRITICAL ERROR: Missing critical library: {e}.")
            print("Please install required libraries: nes-py, Pillow, numpy.")
            print("You can typically install them using: pip install nes-py Pillow numpy")
        return

    main_window = tk.Tk()
    app_instance = NesticleTkApp(main_window) # noqa: F841 (app_instance is used by mainloop)
    main_window.mainloop()

if __name__ == "__main__":
    run_nesticle_tk_app()
