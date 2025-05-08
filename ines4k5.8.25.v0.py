#!/usr/bin/env python3
"""
NES Emulator GUI - A simple interface for NES emulation
This module provides a basic GUI for loading and emulating NES ROMs
using Tkinter for all UI and rendering.
"""

import tkinter as tk
from tkinter import filedialog
from PIL import Image, ImageTk # Pillow is used for image manipulation

class NESGUI:
    """
    Main GUI class for the NES emulator.
    Handles the user interface and emulation loop management.
    """
    def __init__(self, root_window):
        """
        Initialize the NES emulator GUI.

        Args:
            root_window: Tkinter root window
        """
        # Set up the main window
        self.root = root_window
        self.root.title("NES Emulator (Tkinter only)")
        self.root.geometry("600x450") # Adjusted height slightly for clarity

        # Frame for the emulation display (NES resolution: 256x240)
        self.display_frame = tk.Frame(self.root, width=256, height=240, bg="black")
        self.display_frame.pack(side=tk.LEFT, padx=10, pady=10)
        self.display_frame.pack_propagate(False) # Prevent frame from shrinking to canvas size initially

        # Canvas for displaying the emulation output
        self.canvas = tk.Canvas(self.display_frame, width=256, height=240, bg="black", highlightthickness=0)
        self.canvas.pack()

        # Create the UI widgets
        self.create_widgets()

        # Initialize emulation variables
        self.nes = None  # Will hold the NES system instance
        self.running = False  # Emulation state
        self.current_rom = None  # Currently loaded ROM path
        self.tk_image = None  # Will hold the PhotoImage for Tkinter canvas

    def create_widgets(self):
        """Create and arrange all GUI elements."""
        # Control panel frame
        control_frame = tk.Frame(self.root)
        control_frame.pack(side=tk.RIGHT, padx=10, pady=10, fill=tk.Y, expand=False)

        # ROM loading button
        self.load_btn = tk.Button(control_frame, text="Load ROM", command=self.load_rom)
        self.load_btn.pack(pady=5, fill=tk.X)

        # Start emulation button
        self.start_btn = tk.Button(control_frame, text="Start", command=self.start_emulation)
        self.start_btn.pack(pady=5, fill=tk.X)

        # Reset emulation button
        self.reset_btn = tk.Button(control_frame, text="Reset", command=self.reset_emulation)
        self.reset_btn.pack(pady=5, fill=tk.X)

        # Status display label
        self.status_label = tk.Label(control_frame, text="Status: Idle", wraplength=180) # Wraplength for long messages
        self.status_label.pack(pady=10)

    def load_rom(self):
        """Open file dialog to select and load a ROM file."""
        file_path = filedialog.askopenfilename(
            title="Select NES ROM",
            filetypes=[("NES ROMs", "*.nes"), ("All files", "*.*")]
        )
        if file_path:
            self.current_rom = file_path
            # Extract filename for display
            rom_name = file_path.split('/')[-1].split('\\')[-1]
            self.status_label.config(text=f"Loaded: {rom_name}")
            self.reset_emulation() # Reset if a new ROM is loaded

    def start_emulation(self):
        """Start the emulation process if a ROM is loaded."""
        if self.current_rom and not self.running:
            try:
                # Read the ROM data (placeholder - actual parsing needed)
                with open(self.current_rom, "rb") as f:
                    rom_data = f.read()

                # Initialize the NES system
                self.nes = NESSystem(rom_data) # PPU no longer needs a direct screen reference here
                self.running = True
                self.status_label.config(text="Status: Running")

                # Start the emulation loop
                self.root.after(16, self.emulate_frame)  # Target ~60fps (1000ms / 60fps ~= 16ms)
            except Exception as e:
                self.status_label.config(text=f"Error starting: {str(e)}")
                print(f"Error starting emulation: {e}")
                import traceback
                traceback.print_exc()
                self.running = False
        elif not self.current_rom:
            self.status_label.config(text="Status: No ROM loaded!")
        elif self.running:
            self.status_label.config(text="Status: Already running.")


    def emulate_frame(self):
        """Run one frame of emulation."""
        if not self.running or not self.nes:
            return # Stop if not running or NES not initialized

        try:
            # --- Core Emulation Logic (Simplified) ---
            # In a real emulator, this involves:
            # 1. Handling controller input
            # 2. Executing CPU cycles for one frame
            # 3. Executing PPU cycles corresponding to the CPU cycles
            # 4. Handling APU (Audio Processing Unit) cycles
            # 5. Synchronization between components

            # Placeholder: Simulate CPU and PPU work
            cycles_this_frame = 0
            target_cycles_per_frame = 29780 # Approximate for NTSC NES

            while cycles_this_frame < target_cycles_per_frame:
                # cpu_step_cycles = self.nes.cpu.step() # Execute one CPU instruction
                # self.nes.ppu.step(cpu_step_cycles * 3) # PPU runs 3x faster
                # cycles_this_frame += cpu_step_cycles
                # For this placeholder, we'll just simulate a block of work
                cpu_step_cycles = self.nes.cpu.step()
                self.nes.ppu.step(cpu_step_cycles * 3) # Pass arbitrary PPU cycles
                cycles_this_frame += cpu_step_cycles
                if cycles_this_frame >= target_cycles_per_frame: # Ensure we don't massively overshoot
                    break


            # Update the display with the PPU's output
            self.update_display()

            # Schedule the next frame
            if self.running:
                self.root.after(16, self.emulate_frame) # ~16ms for 60 FPS

        except Exception as e:
            self.status_label.config(text=f"Runtime Error: {str(e)}")
            print(f"Runtime error during emulation: {e}")
            import traceback
            traceback.print_exc()
            self.running = False


    def update_display(self):
        """Convert and display the current frame from PPU to tkinter canvas."""
        if self.nes and self.nes.ppu and self.running:
            try:
                # Get the frame data (as a PIL Image) from the PPU
                pil_image = self.nes.ppu.get_frame_data()

                if pil_image:
                    # Convert PIL Image to PhotoImage for Tkinter
                    # Keep a reference to self.tk_image to prevent garbage collection!
                    self.tk_image = ImageTk.PhotoImage(image=pil_image)

                    # Clear the canvas and draw the new image
                    self.canvas.delete("all")
                    self.canvas.create_image(0, 0, anchor=tk.NW, image=self.tk_image)
                else:
                    # Fallback if PPU doesn't return an image (e.g., during init)
                    self.canvas.delete("all")
                    self.canvas.create_text(128, 120, text="No PPU Data", fill="grey")

            except Exception as e:
                print(f"Display update error: {e}")
                import traceback
                traceback.print_exc()
                self.status_label.config(text=f"Display Error: {str(e)}")
                self.running = False # Stop emulation on display error


    def reset_emulation(self):
        """Stop emulation and reset the system state."""
        self.running = False
        # self.nes = None # Re-initialize NESSystem if ROM is still loaded
        if self.current_rom:
            # Optionally, you might want to re-initialize parts of the NES
            # or just clear the screen and wait for 'Start' again.
            # For now, just stop and clear.
            try:
                # Re-initialize the NES system with the current ROM
                with open(self.current_rom, "rb") as f:
                    rom_data = f.read()
                self.nes = NESSystem(rom_data) # Reset NES state
                self.status_label.config(text=f"Reset. ROM: {self.current_rom.split('/')[-1]}")
            except Exception as e:
                self.status_label.config(text=f"Error resetting: {e}")
                self.nes = None # Ensure nes is None if reset fails
        else:
            self.nes = None
            self.status_label.config(text="Status: Idle")

        # Clear the canvas
        self.canvas.delete("all")
        # Optionally, draw a default screen
        default_img = Image.new('RGB', (256, 240), color = 'black')
        self.tk_image = ImageTk.PhotoImage(image=default_img)
        self.canvas.create_image(0,0, anchor=tk.NW, image=self.tk_image)
        self.canvas.create_text(128, 120, text="Press 'Load ROM'", fill="darkgrey")


class NESSystem:
    """
    Main NES system class that connects all components.
    This is a simplified placeholder implementation.
    """
    def __init__(self, rom_data):
        """
        Initialize the NES system with ROM data.

        Args:
            rom_data: Binary ROM data
        """
        self.rom = ROM(rom_data)
        self.mapper = Mapper(self.rom) # Placeholder
        self.ppu = PPU(self) # PPU is part of the NES system
        self.cpu = CPU(self) # CPU is part of the NES system
        self.controller1 = Controller() # Placeholder
        self.controller2 = Controller() # Placeholder
        # In a real emulator, components (CPU, PPU, APU, Mapper) would have
        # complex interactions and share memory/buses.


# --- Placeholder component classes ---
# In a real implementation, these would have full NES functionality.

class ROM:
    """Handles ROM data and header parsing (placeholder)."""
    def __init__(self, rom_data):
        self.data = rom_data
        # In a real implementation: parse iNES header, extract PRG-ROM, CHR-ROM/RAM,
        # mapper type, mirroring, etc.
        print(f"ROM loaded: {len(rom_data)} bytes.")
        if not rom_data:
            raise ValueError("ROM data cannot be empty.")


class Mapper:
    """Handles memory mapping between CPU/PPU and ROM (placeholder)."""
    def __init__(self, rom):
        self.rom = rom
        # In a real implementation, this class would implement logic for a specific
        # NES memory mapper (e.g., NROM, UxROM, MMC1, MMC3, etc.) based on ROM header.
        # It would control how CPU/PPU addresses are translated to ROM/RAM locations.


class CPU:
    """Emulates the Ricoh 2A03 CPU (based on 6502) (placeholder)."""
    def __init__(self, nes_system):
        self.nes = nes_system # Reference to the main NES system for bus access
        # In a real implementation: initialize registers (A, X, Y, SP, PC, P),
        # memory (internal RAM), and prepare for instruction fetching/decoding.
        self.cycle_count = 0

    def step(self):
        """
        Execute one CPU instruction and return the number of cycles it took.
        Placeholder: returns a fixed number of cycles.
        """
        # In a real implementation: fetch opcode from memory (via mapper),
        # decode instruction, execute it (modifying registers/memory),
        # and return the actual number of CPU cycles consumed.
        self.cycle_count += 4 # Simulate a simple instruction
        return 4  # Average 6502 instruction might take 2-7 cycles


class PPU:
    """
    Emulates the Picture Processing Unit (placeholder).
    This PPU directly generates a PIL Image for display.
    """
    def __init__(self, nes_system):
        self.nes = nes_system # Reference to the main NES system
        self.frame_counter = 0
        self.width = 256 # NES horizontal resolution
        self.height = 240 # NES vertical resolution

        # Simple color palette for placeholder graphics
        self.colors = [
            (0, 0, 0), (0, 0, 170), (170, 0, 0), (170, 0, 170),
            (0, 170, 0), (0, 170, 170), (170, 85, 0), (170, 170, 170),
            (85, 85, 85), (85, 85, 255), (255, 85, 85), (255, 85, 255),
            (85, 255, 85), (85, 255, 255), (255, 255, 85), (255, 255, 255)
        ]


    def step(self, ppu_cycles):
        """
        Run the PPU for a specified number of PPU cycles.
        Placeholder: simply increments a frame counter to change visuals.
        """
        # In a real PPU:
        # - Process scanlines and pixels based on PPU registers, VRAM, OAM, pattern tables.
        # - Handle NMI (Non-Maskable Interrupt) for VBlank.
        # - Render background and sprites.
        # - Manage scrolling.
        # This method would be called multiple times per frame.
        # For this placeholder, we just advance a counter to make the image change.
        # We assume `get_frame_data` is called once per visual frame.
        self.frame_counter += 1


    def get_frame_data(self):
        """
        Generate and return the current PPU frame as a PIL Image.
        Placeholder: creates a simple dynamic image.
        """
        # Create a new image for the current frame
        image = Image.new('RGB', (self.width, self.height), color='black')
        pixels = image.load() # Get access to pixel data

        # --- Placeholder rendering logic ---
        # Draw something simple that changes over time
        # Example: A moving color band
        band_height = 20
        band_color_index = (self.frame_counter // 10) % len(self.colors) # Change color every 10 "PPU steps"
        band_color = self.colors[band_color_index]
        band_y_position = (self.frame_counter % (self.height - band_height))

        for y in range(band_y_position, band_y_position + band_height):
            for x in range(self.width):
                if 0 <= y < self.height: # Boundary check
                    pixels[x, y] = band_color

        # Example: A flashing rectangle
        if (self.frame_counter // 30) % 2 == 0: # Flash every 30 "PPU steps"
            rect_color = self.colors[5] # Green
            for y_rect in range(50, 100):
                for x_rect in range(50, 100):
                    pixels[x_rect, y_rect] = rect_color
        # --- End placeholder rendering ---

        # In a real PPU, `pixels` would be filled based on the complex rendering of
        # pattern tables, nametables, attribute tables, and Object Attribute Memory (OAM for sprites).

        return image


class Controller:
    """Handles controller input (placeholder)."""
    def __init__(self):
        self.buttons = [False] * 8  # A, B, Select, Start, Up, Down, Left, Right
        # In a real implementation:
        # - Map keyboard keys to these buttons.
        # - Handle reading and latching of controller state for the CPU.

    def read_button_state(self, button_index):
        """Read the state of a specific button."""
        if 0 <= button_index < 8:
            return self.buttons[button_index]
        return False

    def set_button_state(self, button_index, pressed):
        """Set the state of a specific button (e.g., from keyboard input)."""
        if 0 <= button_index < 8:
            self.buttons[button_index] = pressed


if __name__ == "__main__":
    # Entry point of the application
    try:
        main_window = tk.Tk()
        app = NESGUI(main_window)
        main_window.mainloop()
    except Exception as e:
        # Print any errors that occur during startup
        print(f"Critical Startup Error: {e}")
        import traceback
        traceback.print_exc()
