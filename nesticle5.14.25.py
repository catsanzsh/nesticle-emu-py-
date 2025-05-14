import tkinter as tk
from tkinter import filedialog, messagebox, font as tkFont
import os

# NESSystem class manages the ROM and emulation state (Optimized)
class NESSystem:
    def __init__(self, rom_path):
        """
        Initializes the NES system with the given ROM path.
        Attempts to load the ROM and initialize placeholder components.
        Raises an exception if ROM loading fails.
        """
        self.rom_path = rom_path
        self.rom_data = None  # Placeholder for actual ROM data/header info
        self.is_running = False
        self.cpu = None  # Placeholder for CPU state/object
        self.ppu = None  # Placeholder for PPU state/object
        self.apu = None  # Placeholder for APU state/object
        self.memory = None  # Placeholder for Memory state/object
        self.error_message = None # Stores any error message from loading

        try:
            self._load_rom()
            self._initialize_components() # Initialize components only if ROM loads
            print(f"NESSystem: Initialized successfully with ROM: {os.path.basename(self.rom_path)}")
        except Exception as e:
            self.error_message = str(e)
            # Re-raise the exception so the calling code (GUI) can catch it
            # and display an appropriate error message to the user.
            print(f"NESSystem: Error during initialization: {self.error_message}")
            raise

    def _load_rom(self):
        """
        Private method to attempt loading and basic validation of the ROM file.
        In a real emulator, this would parse the iNES header and load PRG/CHR ROM banks.
        Raises FileNotFoundError or IOError if the ROM cannot be accessed or read.
        """
        if not os.path.exists(self.rom_path):
            raise FileNotFoundError(f"ROM file not found: {self.rom_path}")
        if not os.access(self.rom_path, os.R_OK):
            # This checks if the file is readable.
            raise IOError(f"ROM file is not readable (check permissions): {self.rom_path}")
        
        try:
            # Placeholder for actual ROM loading and parsing.
            # For now, we'll just "load" it by checking its size.
            # A real implementation would read bytes, parse iNES header, etc.
            rom_file_size = os.path.getsize(self.rom_path)
            if rom_file_size == 0:
                raise IOError(f"ROM file is empty: {self.rom_path}")

            self.rom_data = {"size": rom_file_size, "filename": os.path.basename(self.rom_path)} 
            print(f"NESSystem: Successfully opened ROM: {self.rom_data['filename']}, Size: {self.rom_data['size']} bytes.")
            # Future steps: Parse iNES header, map PRG ROM, map CHR ROM, setup mappers.
        except Exception as e:
            # Catch any other exceptions during the "loading" process.
            raise IOError(f"Error processing ROM file {os.path.basename(self.rom_path)}: {e}")

    def _initialize_components(self):
        """
        Initializes placeholder NES components.
        In a real emulator, these would be complex objects representing CPU, PPU, APU, and memory.
        """
        self.cpu = {"registers": {"A": 0, "X": 0, "Y": 0, "SP": 0xFD, "PC": 0}, "status_flags": {}} 
        self.ppu = {"registers": {}, "vram": bytearray(0x800), "oam": bytearray(0x100)} 
        self.apu = {"registers": {}}
        self.memory = {"ram": bytearray(0x800)} # 2KB internal RAM
        print("NESSystem: CPU, PPU, APU, and Memory components initialized (stubs).")

    def start(self):
        """Starts or resumes emulation."""
        if self.error_message:
            print(f"NESSystem: Cannot start due to system error: {self.error_message}")
            return False # Indicate failure to start
        if not self.rom_data:
            print("NESSystem: Cannot start. No ROM data loaded or ROM load failed.")
            return False # Indicate failure to start
            
        self.is_running = True
        print(f"NESSystem: Started emulation for {self.rom_data.get('filename', 'Unknown ROM')}.")
        # In a real emulator, this is where the main emulation loop (CPU/PPU cycles) would begin or resume.
        # For example: self.cpu.run_cycles(CYCLES_PER_FRAME)
        return True # Indicate success

    def stop(self):
        """Stops or pauses emulation."""
        if not self.is_running:
            print("NESSystem: Emulation is not running, no need to stop.")
            return

        self.is_running = False
        rom_name = self.rom_data.get('filename', 'current ROM') if self.rom_data else 'current ROM'
        print(f"NESSystem: Stopped emulation for {rom_name}.")
        # In a real emulator, this would halt the emulation loop.
        # Potentially save state if implementing save states.

    def reset(self):
        """Resets the emulation to its initial state for the currently loaded ROM."""
        if self.error_message:
            print(f"NESSystem: Cannot reset due to system error during load: {self.error_message}")
            # If the system had an error on load, reset might not be possible without a successful reload.
            return False
        if not self.rom_data:
            print("NESSystem: Cannot reset. No ROM data loaded.")
            return False

        print(f"NESSystem: Resetting emulation for {self.rom_data.get('filename', 'Unknown ROM')}.")
        
        # Stop emulation if it's running
        if self.is_running:
            self.stop()
            
        # Re-initialize NES components to their power-on state
        self._initialize_components() 
        
        # Set program counter to reset vector (placeholder, actual address depends on mapper and ROM)
        # self.cpu['registers']['PC'] = self._read_reset_vector() # Example
        
        self.is_running = False # Emulation is reset, not automatically started.
        print("NESSystem: System reset to initial state. Ready to start.")
        return True

# NesticleTkApp class handles the GUI (largely unchanged, but interacts with optimized NESSystem)
class NesticleTkApp:
    def __init__(self, master_window):
        self.master = master_window
        self.master.title("Nesticle-TK - A NES Emulator")
        self.master.geometry("700x450")
        self.master.configure(bg="#2a0000")
        self.master.resizable(False, False)

        self.current_rom_path = None
        self.nes_system = None # This will be an instance of NESSystem
        self.emulation_running = False # Tracks GUI state of emulation

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
        self.game_canvas_width = 256 * 2 # Standard NES resolution, scaled up
        self.game_canvas_height = 240 * 2

        canvas_outer_frame = tk.Frame(self.master, bg="#2a0000") # Match master background
        canvas_outer_frame.pack(expand=True) # Allow canvas to center

        self.game_canvas = tk.Canvas(canvas_outer_frame, width=self.game_canvas_width, height=self.game_canvas_height, bg="black", highlightthickness=2, highlightbackground="#FF0000")
        self.game_canvas.pack(padx=10, pady=10)
        self.game_canvas.config(cursor="pirate") # Custom cursor for the game area

        # Determine a suitable retro font
        self.retro_font_family = "Fixedsys" if "Fixedsys" in tkFont.families() else "Courier"
        self.update_canvas_message("Please load a ROM to start playing!", color="#FF0000")

        # Status Bar
        self.status_label = tk.Label(self.master, text="No ROM loaded. Please load one to start!", bd=2, relief=tk.SUNKEN, anchor=tk.W, bg="#111111", fg="#00FF00", padx=5, font=(self.retro_font_family, 11, "bold"))
        self.status_label.pack(side=tk.BOTTOM, fill=tk.X)

        self.apply_initial_button_states()

    def apply_initial_button_states(self):
        """Resets buttons and emulation state to initial (no ROM loaded)"""
        self.start_btn.config(state=tk.DISABLED, text="Start")
        self.reset_btn.config(state=tk.DISABLED)
        self.load_btn.config(state=tk.NORMAL)
        
        # If there's an active emulation loop (not implemented yet, but good for future)
        if hasattr(self, 'emulation_loop_id') and self.emulation_loop_id:
            self.master.after_cancel(self.emulation_loop_id)
            self.emulation_loop_id = None
        self.emulation_running = False # GUI flag for emulation state

    def update_canvas_message(self, message_text, color="#00FF00"):
        """Clears the canvas and displays a message."""
        self.game_canvas.delete("all") # Clear previous drawings/messages
        text_x = self.game_canvas_width / 2
        text_y = self.game_canvas_height / 2
        self.game_canvas.create_text(
            text_x, text_y,
            text=message_text,
            fill=color,
            font=(self.retro_font_family, 14, "bold"),
            anchor=tk.CENTER,
            justify=tk.CENTER,
            width=self.game_canvas_width - 40 # Ensure text wraps
        )

    def load_rom_action(self):
        """Handles the Load ROM button action."""
        # If emulation is running, stop it before loading a new ROM
        if self.emulation_running:
            self.toggle_emulation_action() # This will call nes_system.stop()

        rom_path_selected = filedialog.askopenfilename(
            title="Select a NES ROM",
            filetypes=(("NES Files", "*.nes"), ("All Files", "*.*"))
        )
        if rom_path_selected:
            try:
                # Attempt to initialize NESSystem with the selected ROM
                # This will raise an exception if NESSystem.__init__ fails (e.g., ROM not found)
                self.nes_system = NESSystem(rom_path_selected)
                self.current_rom_path = rom_path_selected # Store path only on successful load
                
                rom_filename = os.path.basename(self.current_rom_path)
                self.status_label.config(text=f"ROM loaded: {rom_filename}. Ready to play!")
                self.update_canvas_message(f"ROM '{rom_filename}' loaded!\nPress Start to begin!", color="#00FF00")
                self.start_btn.config(state=tk.NORMAL, text="Start")
                self.reset_btn.config(state=tk.DISABLED) # Reset is enabled once game starts or is paused
                self.load_btn.config(state=tk.NORMAL) # Allow loading another ROM
                self.master.title(f"Nesticle-TK - {rom_filename}")
                self.emulation_running = False # Reset emulation state for new ROM

            except Exception as e:
                # Catch errors from NESSystem.__init__ (e.g., FileNotFoundError, IOError)
                messagebox.showerror("Error Loading ROM", f"Failed to load ROM: {e}")
                self.status_label.config(text="Failed to load ROM. Please try again.")
                self.current_rom_path = None
                self.nes_system = None
                self.apply_initial_button_states() # Reset buttons to initial state
                self.update_canvas_message("Failed to load ROM.\nPlease try another one.", color="#FF0000")
                self.master.title("Nesticle-TK - A NES Emulator")
        else:
            # User cancelled the file dialog
            if not self.current_rom_path: # Only update status if no ROM was previously loaded
                self.status_label.config(text="No ROM loaded. Load cancelled.")

    def toggle_emulation_action(self):
        """Handles the Start/Pause button action."""
        if not self.nes_system or not self.current_rom_path:
            messagebox.showwarning("Warning", "Please load a ROM first!")
            return

        if self.emulation_running: # If running, then pause
            if self.nes_system: self.nes_system.stop()
            self.emulation_running = False
            self.start_btn.config(text="Start")
            self.reset_btn.config(state=tk.NORMAL) # Allow reset when paused
            self.load_btn.config(state=tk.NORMAL) # Allow loading new ROM when paused
            rom_filename = os.path.basename(self.current_rom_path)
            self.status_label.config(text=f"Paused. ROM: {rom_filename}.")
            self.update_canvas_message("Paused. Press Start to resume!", color="#FFFF00")
            # Cancel the emulation loop (if one exists)
            if hasattr(self, 'emulation_loop_id') and self.emulation_loop_id:
                self.master.after_cancel(self.emulation_loop_id)
                self.emulation_loop_id = None
        else: # If not running (paused or freshly loaded), then start
            if self.nes_system and self.nes_system.start(): # nes_system.start() now returns True on success
                self.emulation_running = True
                self.start_btn.config(text="Pause")
                self.reset_btn.config(state=tk.NORMAL) # Allow reset when running
                self.load_btn.config(state=tk.DISABLED) # Disable ROM loading while running
                rom_filename = os.path.basename(self.current_rom_path)
                self.status_label.config(text=f"Playing ROM: {rom_filename}.")
                self.update_canvas_message(f"Playing '{rom_filename}'!\n(Emulation visuals not yet implemented)", color="#00FF00")
                # Start the emulation loop (placeholder for actual game loop)
                # self.run_emulation_frame() 
            else:
                # This case might occur if nes_system.start() failed for some reason
                messagebox.showerror("Error", "Could not start emulation. System may not be ready.")
                self.status_label.config(text="Error starting emulation.")


    def reset_rom_action(self):
        """Handles the Reset button action."""
        if not self.current_rom_path: # Check if a ROM path is known
            messagebox.showwarning("Warning", "No ROM loaded to reset!")
            self.apply_initial_button_states()
            self.update_canvas_message("Please load a ROM first to reset it.", color="orange")
            return

        # If emulation is running, stop it first
        if self.emulation_running:
            if self.nes_system: self.nes_system.stop()
            self.emulation_running = False
            if hasattr(self, 'emulation_loop_id') and self.emulation_loop_id:
                self.master.after_cancel(self.emulation_loop_id)
                self.emulation_loop_id = None
        
        try:
            if self.nes_system:
                if not self.nes_system.reset(): # nes_system.reset() now returns True/False
                    messagebox.showerror("Error", "Failed to reset the NES system.")
                    # Keep current state, or revert to a "no ROM" state?
                    # For now, assume reset failed but ROM might still be "loaded" conceptually
                    self.status_label.config(text="Failed to reset system.")
                    return 
            else:
                # This case could happen if nes_system was None, but current_rom_path exists
                # (e.g. after a load failure that didn't clear current_rom_path, though current logic clears it)
                # Attempt to re-initialize.
                print("NESSystem was None during reset, attempting re-initialization.")
                self.nes_system = NESSystem(self.current_rom_path) # This will also reset it.
                                                                  # Error here will be caught by the except block.

            # If reset was successful (or re-initialization was successful)
            rom_filename = os.path.basename(self.current_rom_path)
            self.status_label.config(text=f"Reset complete. ROM: {rom_filename}. Ready to play!")
            self.update_canvas_message(f"'{rom_filename}' reset and ready!\nPress Start to begin!", color="#00FFFF")
            self.start_btn.config(text="Start", state=tk.NORMAL)
            self.reset_btn.config(state=tk.DISABLED) # Disable reset until game starts/pauses again
            self.load_btn.config(state=tk.NORMAL) # Allow loading another ROM

        except Exception as e:
            # This catches errors from NESSystem(self.current_rom_path) if nes_system was None
            messagebox.showerror("Error Resetting ROM", f"Failed to reset/re-initialize ROM: {e}")
            self.status_label.config(text="Failed to reset ROM. Please try re-loading.")
            # Consider full clear if re-initialization fails badly
            self.current_rom_path = None 
            self.nes_system = None
            self.apply_initial_button_states()
            self.master.title("Nesticle-TK - A NES Emulator")
            self.update_canvas_message("Failed to reset ROM.\nPlease load another one.", color="#FF0000")


# Main function to run the application
def run_nesticle_tk_app():
    main_window = tk.Tk()
    app_instance = NesticleTkApp(main_window)
    main_window.mainloop()

# Entry point of the script
if __name__ == "__main__":
    run_nesticle_tk_app()
