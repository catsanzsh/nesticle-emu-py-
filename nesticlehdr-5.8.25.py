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
        self.is_running = False
        self.env = None # Initialize env as None
        try:
            # Forcing the environment to provide full frames without skipping
            # Some games might require specific render modes or options if available in your nes-py version
            self.env = nes_py.NESEnv(self.rom_path)
            # The environment automatically loads the ROM.
            # We reset it to get the initial frame.
            self.env.reset()
            print(f"NESSystem: Initialized with ROM: {os.path.basename(self.rom_path)}, meow!")
        except Exception as e:
            print(f"NESSystem: Error initializing nes-py environment: {e}")
            raise # Re-raise the exception to be caught by the UI

    def start(self):
        self.is_running = True
        # No specific nes-py action needed here, game loop handles stepping
        print("NESSystem: Started, let's purr-lay!")

    def stop(self):
        self.is_running = False
        # No specific nes-py action needed here, game loop handles stopping
        print("NESSystem: Stopped, nap time~")

    def reset(self):
        if self.env:
            self.env.reset()
            print("NESSystem: Resetting the purr-gram!")
        else:
            print("NESSystem: Cannot reset, environment not initialized.")


    def step(self, action=0): # action=0 is typically 'NOOP'
        """Executes one frame of the NES emulation."""
        if not self.env or not self.is_running:
            # Return a structure similar to env.step() but with None for state
            return None, 0, False, False, {}

        # The action space for nes-py is typically a discrete number.
        # 0 is often NOOP.
        # For demonstration, action 0 (NOOP) is used.
        # To implement controls, you'd map keyboard events to different action values.
        # state is the screen (numpy array), reward, terminated, truncated, info
        state, reward, terminated, truncated, info = self.env.step(action=action)
        
        done = terminated or truncated # Combine terminated and truncated flags
        
        # For an emulator, "done" might mean the game ended or an RL episode finished.
        # We'll print it but not automatically stop/reset the game loop here.
        if done:
             print(f"NESSystem: Step returned done (terminated={terminated}, truncated={truncated}). ROM: {os.path.basename(self.rom_path)}")

        return state, reward, terminated, truncated, info

    def get_current_frame(self):
        """Returns the current video frame from the PPU."""
        if self.env:
            # Ensure the frame is what we expect (e.g. after a reset or initial load)
            # self.env.screen directly gives the last rendered screen
            return self.env.screen # This is a NumPy array (240, 256, 3)
        return None

    def close(self):
        """Closes the nes-py environment."""
        if self.env:
            self.env.close()
            self.env = None
            print("NESSystem: nes-py environment closed, purr-bye!")

# --- Tkinter Application Class ---
class NesticleTkApp:
    def __init__(self, master_window):
        self.master = master_window
        self.master.title("NESTICLE-TK ✨ Meow Version!")
        # Adjusted geometry slightly if needed
        self.master.geometry("600x450") # WidthxHeight
        self.master.configure(bg="#2c2c2c")
        self.master.resizable(False, False)

        self.current_rom_path = None
        self.nes_system = None
        self.emulation_running = False
        self.emulation_loop_id = None # To store the 'after' job ID

        # NES resolution: 240 rows, 256 columns.
        self.game_canvas_width = 256
        self.game_canvas_height = 240

        # --- UI Elements ---
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
        canvas_outer_frame.pack(expand=True) # Centers the canvas

        self.game_canvas = tk.Canvas(canvas_outer_frame, width=self.game_canvas_width, height=self.game_canvas_height, bg="black", highlightthickness=1, highlightbackground="#1a1a1a")
        self.game_canvas.pack(padx=10, pady=10)
        self.tk_image = None # To hold the PhotoImage and prevent garbage collection

        self.retro_font_family = "Fixedsys" if "Fixedsys" in tkFont.families() else "Courier"
        self.update_canvas_message("Load a ROM to purr-lay, nya!")

        self.status_label = tk.Label(self.master, text="No ROM loaded. Meow. 🐾", bd=1, relief=tk.SUNKEN, anchor=tk.W, bg="#1e1e1e", fg="lime green", padx=5, font=(self.retro_font_family, 10))
        self.status_label.pack(side=tk.BOTTOM, fill=tk.X)

        self.apply_initial_button_states()
        self.master.protocol("WM_DELETE_WINDOW", self.on_closing_application)

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
            text_x, text_y,
            text=message_text, fill=color,
            font=(self.retro_font_family, 12, "bold" if self.retro_font_family == "Courier" else "normal"),
            anchor=tk.CENTER, justify=tk.CENTER, width=self.game_canvas_width - 20
        )
        self.tk_image = None

    def draw_frame_on_canvas(self, frame_data_np):
        if frame_data_np is None:
            # This case might occur if nes_system.step() returns None for the state
            # or if get_current_frame returns None.
            # self.update_canvas_message("No frame data, meow?", "orange") # Avoid flickering if transient
            print("draw_frame_on_canvas: Received None for frame_data_np.")
            return

        try:
            image = Image.fromarray(frame_data_np.astype(np.uint8), 'RGB')
            self.tk_image = ImageTk.PhotoImage(image=image) # Keep a reference!

            self.game_canvas.delete("all")
            self.game_canvas.create_image(0, 0, anchor=tk.NW, image=self.tk_image)
        except Exception as e:
            print(f"Error drawing frame: {e}")
            self.update_canvas_message(f"Frame display error!\n{e}", "red")
            if self.emulation_running: # Stop emulation if critical drawing error
                self.toggle_emulation_action()


    def load_rom_action(self):
        if self.emulation_running:
            self.toggle_emulation_action() # Pause if running

        if self.nes_system:
            self.nes_system.close()
            self.nes_system = None
            self.tk_image = None # Clear old image reference

        rom_path_selected = filedialog.askopenfilename(
            title="Select a Meow-tastic NES ROM ✨",
            filetypes=(("NES ROMs", "*.nes"), ("All files", "*.*"))
        )
        if rom_path_selected:
            try:
                self.current_rom_path = rom_path_selected
                self.nes_system = NESSystem(self.current_rom_path) # This also calls env.reset()
                rom_filename = os.path.basename(self.current_rom_path)
                self.status_label.config(text=f"Purrfect! ROM: {rom_filename}")

                initial_frame = self.nes_system.get_current_frame()
                if initial_frame is not None:
                    self.draw_frame_on_canvas(initial_frame)
                else: # Fallback if frame is None
                    self.update_canvas_message("Ready to purr-lay, nya!")

                self.start_btn.config(state=tk.NORMAL, text="▶ Start")
                self.reset_btn.config(state=tk.DISABLED) # Reset only active when running or paused
                self.master.title(f"NESTICLE-TK ✨ - {rom_filename}")
                self.emulation_running = False # Not running until Start is pressed
            except Exception as e:
                messagebox.showerror("Hiss! Error 🙀", f"Failed to load ROM with nes-py: {e}")
                self.status_label.config(text="Error loading ROM. Sad meow. 😿")
                if self.nes_system: self.nes_system.close() # Ensure cleanup
                self.current_rom_path = None
                self.nes_system = None
                self.apply_initial_button_states()
                self.update_canvas_message("Failed to load ROM.\nTry another, purrhaps?", color="red")
                self.master.title("NESTICLE-TK ✨ Meow Version!")
        else:
            if not self.current_rom_path: # Only show if no ROM was ever loaded
                self.status_label.config(text="ROM loading cancelled. Aww. 😿")


    def game_loop_tick(self):
        if not self.emulation_running or not self.nes_system or not self.nes_system.env:
            self.emulation_running = False # Ensure flag is correct
            # Cancel any pending loop if conditions are not met.
            if self.emulation_loop_id:
                self.master.after_cancel(self.emulation_loop_id)
                self.emulation_loop_id = None
            return

        try:
            action = 0 # Default NOOP action. Implement actual input handling for gameplay.
            
            # state is the new frame
            state, reward, terminated, truncated, info = self.nes_system.step(action)
            done = terminated or truncated

            if state is not None:
                self.draw_frame_on_canvas(state)
            else:
                # This condition means nes_py.step might have had an issue or env closed.
                print("Game loop: No state (frame) returned from nes_system.step. Stopping emulation.")
                self.update_canvas_message("Emulation hiccup!\nFrame data missing.", "orange")
                self.toggle_emulation_action() # Pause/stop the emulation
                return # Stop further processing in this tick

            # If 'done' is true, the game (or current RL episode) has ended.
            # For an emulator, we usually let the user decide to reset or load another game.
            # Some games might show a "Game Over" screen and wait for input.
            if done:
                print(f"Game loop: nes-py reported 'done' for {os.path.basename(self.current_rom_path)}. Emulation continues until user stops/resets.")
                # You could choose to auto-pause here if desired:
                # self.toggle_emulation_action()
                # self.update_canvas_message("Game Over or Cleared!\nPress Reset or Load.", "yellow")


            # Schedule the next tick only if still running
            if self.emulation_running:
                 self.emulation_loop_id = self.master.after(16, self.game_loop_tick) # ~60 FPS

        except Exception as e:
            print(f"Error in game loop: {e}")
            messagebox.showerror("Runtime Purr-oblem 🙀", f"Error during emulation: {e}")
            # Safely stop emulation
            self.emulation_running = False
            if self.nes_system: self.nes_system.stop() # Conceptual stop
            
            if self.emulation_loop_id:
                self.master.after_cancel(self.emulation_loop_id)
                self.emulation_loop_id = None

            self.start_btn.config(text="▶ Start") # UI update
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
            if self.nes_system: self.nes_system.stop() # Mark system as not actively running steps
            if self.emulation_loop_id:
                self.master.after_cancel(self.emulation_loop_id)
                self.emulation_loop_id = None

            self.start_btn.config(text="▶ Start")
            self.reset_btn.config(state=tk.NORMAL)
            self.load_btn.config(state=tk.NORMAL)
            rom_filename = os.path.basename(self.current_rom_path)
            self.status_label.config(text=f"Paused. ROM: {rom_filename}. Take a kitty break!")
            # Keep current frame on canvas, or show a "Paused" message if frame is unavailable
            # current_frame_on_pause = self.nes_system.get_current_frame() # Frame might be stale
            # if current_frame_on_pause is not None:
            #     self.draw_frame_on_canvas(current_frame_on_pause)
            # else:
            self.update_canvas_message("Paused. Press Start\nto resume purr-laying!")

        else: # START / RESUME action
            self.emulation_running = True
            if self.nes_system: self.nes_system.start() # Mark system as ready to run steps

            self.start_btn.config(text="❚❚ Pause")
            self.reset_btn.config(state=tk.NORMAL)
            self.load_btn.config(state=tk.DISABLED) # Don't load while actively running
            rom_filename = os.path.basename(self.current_rom_path)
            self.status_label.config(text=f"Purr-laying! ROM: {rom_filename}. Go, kitty, go!")

            self.game_canvas.delete("all") # Clear any "Paused" or old messages
            self.game_loop_tick()


    def reset_rom_action(self):
        # Stop emulation if it's running
        was_running = self.emulation_running
        if self.emulation_running:
            self.emulation_running = False # Stop the loop flag first
            if self.emulation_loop_id:
                self.master.after_cancel(self.emulation_loop_id)
                self.emulation_loop_id = None
            if self.nes_system: self.nes_system.stop()

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
                # Reset button becomes disabled after a reset, until game is started/paused again
                self.reset_btn.config(state=tk.DISABLED)
                self.load_btn.config(state=tk.NORMAL)
                self.emulation_running = False # Ensure state is not running

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
            self.apply_initial_button_states() # Go to initial state
            self.update_canvas_message("Load a ROM first to reset it, silly!")


    def on_closing_application(self):
        print("Closing application, meow...")
        if self.emulation_running:
            self.emulation_running = False
            if self.emulation_loop_id:
                self.master.after_cancel(self.emulation_loop_id)
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
        # If Tkinter is available, show an error dialog. Otherwise, print to console.
        try:
            root_check = tk.Tk()
            root_check.withdraw() # Hide the empty root window
            messagebox.showerror("Dependency Error", f"Missing critical library: {e}.\nPlease install nes-py, Pillow, and numpy.\n\nExample: pip install nes-py Pillow numpy")
            root_check.destroy()
        except tk.TclError: # If Tkinter itself is not available or fails to initialize
            print(f"CRITICAL ERROR: Missing critical library: {e}.")
            print("Please install required libraries: nes-py, Pillow, numpy.")
            print("You can typically install them using: pip install nes-py Pillow numpy")
        return # Exit if dependencies are missing

    main_window = tk.Tk()
    app_instance = NesticleTkApp(main_window)
    main_window.mainloop()

# Let's run this kitty!
if __name__ == "__main__":
    run_nesticle_tk_app()
