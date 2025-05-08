import asyncio
import platform
import pygame
import numpy as np

# ROM Class for loading and parsing NES ROMs
class ROM:
    def __init__(self, data):
        self.data = bytearray(data)
        self.header = self.data[:16]
        if self.header[:4] != b"NES\x1a":
            raise ValueError("Invalid iNES file - missing header")
        self.prg_banks = self.header[4]
        self.chr_banks = self.header[5]
        self.mapper_num = (self.header[6] >> 4) | (self.header[7] & 0xF0) # Corrected mapper number extraction
        self.mirroring = self.header[6] & 0x01 # 0 for horizontal, 1 for vertical
        self.four_screen_mode = bool(self.header[6] & 0x08) # Added four-screen mode flag
        self.battery = bool(self.header[6] & 0x02)
        self.trainer_present = bool(self.header[6] & 0x04) # Renamed for clarity
        
        prg_rom_start = 16 + (512 if self.trainer_present else 0)
        prg_rom_size = 16384 * self.prg_banks
        prg_rom_end = prg_rom_start + prg_rom_size
        self.prg_rom = self.data[prg_rom_start:prg_rom_end]

        chr_rom_size = 8192 * self.chr_banks
        # If chr_banks is 0, it means CHR RAM is used, typically 8KB.
        # The ROM class itself doesn't hold CHR RAM, the PPU or Mapper will manage it.
        if self.chr_banks > 0:
            self.chr_rom = self.data[prg_rom_end : prg_rom_end + chr_rom_size]
        else:
            # This bytearray will be used by the PPU if chr_banks is 0, acting as CHR-RAM
            self.chr_rom = bytearray(8192) # Placeholder for CHR RAM data if needed by mapper/PPU

# Mapper Base Class with NROM (Mapper 0) Implementation
class Mapper:
    def __init__(self, rom):
        self.rom = rom
        self.prg_rom = rom.prg_rom
        # CHR data is directly from ROM if CHR banks > 0.
        # If CHR banks == 0, rom.chr_rom is an 8KB bytearray that can act as CHR-RAM.
        self.chr_mem = rom.chr_rom

    def cpu_read(self, addr):
        # Mapper 0 (NROM) specific logic
        if 0x8000 <= addr <= 0xFFFF:
            # If 1 PRG bank (16KB), it's mirrored in 0xC000-0xFFFF
            # If 2 PRG banks (32KB), 0x8000-0xFFFF maps directly
            offset = addr - 0x8000
            if self.rom.prg_banks == 1: # 16KB PRG ROM
                return self.prg_rom[offset % 0x4000]
            else: # 32KB PRG ROM (or more, though NROM typically doesn't exceed this)
                return self.prg_rom[offset % len(self.prg_rom)] # General case
        return 0 # Open bus or unhandled by mapper

    def cpu_write(self, addr, value):
        # NROM generally doesn't have CPU-writable registers in PRG ROM space
        # Some complex mappers would handle writes here for bank switching etc.
        # For CHR-RAM, writes would go through PPU bus, potentially handled by mapper
        pass

    def ppu_read(self, addr):
        # For PPU addresses 0x0000-0x1FFF (Pattern Tables)
        if 0x0000 <= addr <= 0x1FFF:
            return self.chr_mem[addr]
        return 0

    def ppu_write(self, addr, value):
        # For PPU addresses 0x0000-0x1FFF (Pattern Tables)
        # This is only effective if chr_mem is CHR-RAM (rom.chr_banks == 0)
        if 0x0000 <= addr <= 0x1FFF and self.rom.chr_banks == 0:
            self.chr_mem[addr] = value

# CPU Class with Full 6502 Opcode Support (Simplified)
class CPU:
    def __init__(self, nes_system): # nes_system provides access to PPU, APU, Mapper
        self.nes = nes_system
        self.ram = bytearray(0x0800) # 2KB CPU RAM
        self.cycles = 0
        self.reset()

    def reset(self):
        # Read reset vector from $FFFC-$FFFD
        self.pc = self.read_word(0xFFFC)
        self.sp = 0xFD # Stack pointer initialized
        self.acc = 0 # Accumulator
        self.x = 0   # X register
        self.y = 0   # Y register
        self.status = 0x24 # Status register (IRQ disabled, B flag set, Unused bit 5 always 1)
        self.cycles = 7 # Cycles for reset sequence

    def set_flag(self, flag, value):
        if value:
            self.status |= flag
        else:
            self.status &= ~flag

    def get_flag(self, flag):
        return bool(self.status & flag)

    # Status Register Flags
    C_FLAG = 0x01  # Carry
    Z_FLAG = 0x02  # Zero
    I_FLAG = 0x04  # Interrupt Disable
    D_FLAG = 0x08  # Decimal Mode (not used in NES)
    B_FLAG = 0x10  # Break Command
    U_FLAG = 0x20  # Unused (always 1)
    V_FLAG = 0x40  # Overflow
    N_FLAG = 0x80  # Negative

    def set_zero_negative_flags(self, value):
        self.set_flag(self.Z_FLAG, value == 0)
        self.set_flag(self.N_FLAG, value & 0x80)

    def read(self, addr):
        addr &= 0xFFFF # Ensure 16-bit address
        if 0x0000 <= addr < 0x2000: # CPU RAM (0x0000-0x07FF mirrored up to 0x1FFF)
            return self.ram[addr % 0x0800]
        elif 0x2000 <= addr < 0x4000: # PPU Registers (mirrored every 8 bytes)
            return self.nes.ppu.cpu_read_register(addr % 8)
        elif addr == 0x4016: # Controller 1 Data
            return self.nes.controller1.read()
        elif addr == 0x4017: # Controller 2 Data (not implemented in this example)
            return 0 # Open bus
        # TODO: APU registers 0x4000 - 0x4013, 0x4015
        elif 0x8000 <= addr <= 0xFFFF: # ROM/Mapper space
            return self.nes.mapper.cpu_read(addr)
        return 0 # Open bus for unmapped addresses

    def write(self, addr, value):
        addr &= 0xFFFF
        value &= 0xFF
        if 0x0000 <= addr < 0x2000: # CPU RAM
            self.ram[addr % 0x0800] = value
        elif 0x2000 <= addr < 0x4000: # PPU Registers
            self.nes.ppu.cpu_write_register(addr % 8, value)
        elif addr == 0x4014: # OAM DMA
            self.nes.ppu.oam_dma(value)
        elif addr == 0x4016: # Controller Strobe
            self.nes.controller1.write(value)
        # TODO: APU registers
        elif 0x8000 <= addr <= 0xFFFF: # ROM/Mapper space (usually for mapper control)
            self.nes.mapper.cpu_write(addr, value)

    def read_word(self, addr):
        low = self.read(addr)
        high = self.read(addr + 1)
        return (high << 8) | low

    def push(self, value):
        self.write(0x0100 + self.sp, value & 0xFF)
        self.sp = (self.sp - 1) & 0xFF

    def push_word(self, value):
        self.push((value >> 8) & 0xFF) # High byte
        self.push(value & 0xFF)      # Low byte

    def pop(self):
        self.sp = (self.sp + 1) & 0xFF
        return self.read(0x0100 + self.sp)

    def pop_word(self):
        low = self.pop()
        high = self.pop()
        return (high << 8) | low

    def step(self):
        if self.nes.ppu.nmi_pending:
            self.nes.ppu.nmi_pending = False
            self.nmi()

        opcode = self.read(self.pc)
        self.pc = (self.pc + 1) & 0xFFFF
        cycles_taken = 2 # Default, will be overridden

        # Simplified Opcode Implementations (add more as needed)
        if opcode == 0xA9:  # LDA Immediate
            value = self.read(self.pc)
            self.pc = (self.pc + 1) & 0xFFFF
            self.acc = value
            self.set_zero_negative_flags(self.acc)
            cycles_taken = 2
        elif opcode == 0xAD:  # LDA Absolute
            addr = self.read_word(self.pc)
            self.pc = (self.pc + 2) & 0xFFFF
            self.acc = self.read(addr)
            self.set_zero_negative_flags(self.acc)
            cycles_taken = 4
        elif opcode == 0x8D:  # STA Absolute
            addr = self.read_word(self.pc)
            self.pc = (self.pc + 2) & 0xFFFF
            self.write(addr, self.acc)
            cycles_taken = 4
        elif opcode == 0x20: # JSR Absolute
            addr = self.read_word(self.pc)
            # self.pc is already advanced past the operand by the time JSR is decoded
            # So, push PC-1 (address of the last byte of JSR instruction)
            self.push_word(self.pc + 1) # Push return address (PC after operand) -1
            self.pc = addr
            cycles_taken = 6
        elif opcode == 0x60: # RTS
            self.pc = (self.pop_word() + 1) & 0xFFFF
            cycles_taken = 6
        elif opcode == 0x4C:  # JMP Absolute
            self.pc = self.read_word(self.pc)
            cycles_taken = 3
        elif opcode == 0x00:  # BRK
            self.pc = (self.pc + 1) & 0xFFFF # BRK has a padding byte
            self.push_word(self.pc)
            self.push(self.status | self.B_FLAG | self.U_FLAG) # B flag set, U flag set
            self.set_flag(self.I_FLAG, True)
            self.pc = self.read_word(0xFFFE) # IRQ/BRK vector
            cycles_taken = 7
        elif opcode == 0xEA: # NOP
            cycles_taken = 2
        elif opcode == 0xA2: # LDX Immediate
            self.x = self.read(self.pc)
            self.pc = (self.pc + 1) & 0xFFFF
            self.set_zero_negative_flags(self.x)
            cycles_taken = 2
        elif opcode == 0xCA: # DEX
            self.x = (self.x - 1) & 0xFF
            self.set_zero_negative_flags(self.x)
            cycles_taken = 2
        elif opcode == 0xD0: # BNE Relative
            offset = self.read(self.pc)
            self.pc = (self.pc + 1) & 0xFFFF
            cycles_taken = 2 # Base cycles
            if not self.get_flag(self.Z_FLAG):
                cycles_taken += 1 # Add 1 if branch taken
                prev_pc_page = (self.pc >> 8)
                self.pc = (self.pc + np.int8(offset)) & 0xFFFF # Handle signed offset
                if (self.pc >> 8) != prev_pc_page:
                    cycles_taken +=1 # Add 1 if page boundary crossed
        elif opcode == 0x9A: # TXS
            self.sp = self.x
            cycles_taken = 2
        elif opcode == 0x78: # SEI
            self.set_flag(self.I_FLAG, True)
            cycles_taken = 2
        elif opcode == 0xA0: # LDY Immediate
            self.y = self.read(self.pc)
            self.pc = (self.pc + 1) & 0xFFFF
            self.set_zero_negative_flags(self.y)
            cycles_taken = 2
        elif opcode == 0x8C: # STY Absolute
            addr = self.read_word(self.pc)
            self.pc = (self.pc + 2) & 0xFFFF
            self.write(addr, self.y)
            cycles_taken = 4
        elif opcode == 0x8E: # STX Absolute
            addr = self.read_word(self.pc)
            self.pc = (self.pc + 2) & 0xFFFF
            self.write(addr, self.x)
            cycles_taken = 4
        # Add more opcodes here...
        else:
            print(f"Unknown opcode {opcode:02X} at PC={self.pc-1:04X}")
            # For now, treat unknown as NOP to avoid crashing, but this is not accurate
            cycles_taken = 2


        self.cycles += cycles_taken
        return cycles_taken

    def nmi(self):
        self.push_word(self.pc)
        self.push(self.status & ~self.B_FLAG | self.U_FLAG) # Clear B flag, set U
        self.set_flag(self.I_FLAG, True) # Disable further interrupts
        self.pc = self.read_word(0xFFFA) # NMI vector
        self.cycles += 7


# PPU Class with Enhanced Rendering
class PPU:
    def __init__(self, nes_system):
        self.nes = nes_system
        pygame.init() # Should be called once globally
        pygame.display.set_caption("NES Emulator")
        self.screen_width = 256
        self.screen_height = 240
        self.screen = pygame.display.set_mode((self.screen_width, self.screen_height))
        self.framebuffer = pygame.Surface((self.screen_width, self.screen_height))
        
        self.vram = bytearray(0x800)  # 2KB VRAM for Nametables (two 1KB tables)
        self.palette_ram = bytearray(32) # Palette RAM
        self.oam = bytearray(256) # Object Attribute Memory (for sprites)

        # PPU Registers (internal state)
        self.ppuctrl = 0x00    # $2000
        self.ppumask = 0x00    # $2001
        self.ppustatus = 0xA0  # $2002 (VBlank, Sprite 0 Hit, Sprite Overflow) - Initial: VBlank, U=1
        self.oamaddr = 0x00    # $2003
        # self.oamdata ($2004) is direct access to self.oam[self.oamaddr]
        self.ppuscroll = 0x00  # $2005 (written twice for X and Y)
        self.ppuaddr = 0x00    # $2006 (written twice for high and low byte)
        # self.ppudata ($2007) is data read/written from/to VRAM via ppuaddr

        self.vram_addr_latch = False # For PPUADDR and PPUSCROLL
        self.current_vram_addr = 0   # Internal VRAM address register (v)
        self.temp_vram_addr = 0      # Temporary VRAM address register (t)
        self.fine_x_scroll = 0       # Fine X scroll (3 bits)

        self.ppu_data_buffer = 0 # For PPUDATA reads

        self.scanline = 0
        self.cycle = 0
        self.nmi_pending = False
        self.frame_odd = False # For NTSC scanline skipping

        self.nes_colors = [
            (84, 84, 84), (0, 30, 116), (8, 16, 144), (48, 0, 136), (68, 0, 100), (92, 0, 48),
            (84, 4, 0), (60, 24, 0), (32, 42, 0), (8, 58, 0), (0, 64, 0), (0, 60, 0),
            (0, 50, 76), (0, 0, 0), (0, 0, 0), (0, 0, 0), (152, 150, 152), (8, 76, 196),
            (48, 50, 236), (92, 30, 228), (136, 20, 176), (160, 20, 100), (152, 34, 32),
            (120, 60, 0), (84, 90, 0), (40, 114, 0), (8, 124, 0), (0, 118, 40), (0, 102, 120),
            (0, 0, 0), (0, 0, 0), (0, 0, 0), (236, 238, 236), (76, 154, 236), (120, 124, 236),
            (176, 98, 236), (228, 84, 236), (236, 88, 180), (236, 106, 100), (212, 136, 32),
            (160, 170, 0), (116, 196, 0), (76, 208, 32), (56, 204, 108), (56, 180, 204),
            (60, 60, 60), (0, 0, 0), (0, 0, 0), (236, 238, 236), (168, 204, 236), (188, 188, 236),
            (212, 178, 236), (236, 174, 236), (236, 174, 212), (236, 180, 176), (228, 196, 144),
            (204, 210, 120), (180, 222, 120), (168, 226, 144), (152, 226, 180), (160, 214, 228),
            (160, 162, 160), (0, 0, 0), (0, 0, 0)
        ]
    
    def _get_mirrored_vram_addr(self, addr):
        addr &= 0x0FFF # Nametable addresses are 0x2000-0x2FFF, mirrored from 0x30
