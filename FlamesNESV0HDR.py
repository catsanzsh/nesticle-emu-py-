import asyncio
import platform
import pygame
import numpy as np

# --- Constants ---
SCREEN_WIDTH, SCREEN_HEIGHT = 256, 240
PPU_CYCLES_PER_SCANLINE = 341
SCANLINES_PER_FRAME = 262
VISIBLE_SCANLINES = 240
VBLANK_SCANLINE = 241

# NES Color Palette (accurate)
NES_PALETTE = [
    (0x7C, 0x7C, 0x7C), (0x00, 0x00, 0xFC), (0x00, 0x00, 0xBC), (0x44, 0x28, 0xBC),
    (0x94, 0x00, 0x84), (0xA8, 0x00, 0x20), (0xA8, 0x10, 0x00), (0x88, 0x14, 0x00),
    (0x50, 0x30, 0x00), (0x00, 0x78, 0x00), (0x00, 0x68, 0x00), (0x00, 0x58, 0x00),
    (0x00, 0x40, 0x58), (0x00, 0x00, 0x00), (0x00, 0x00, 0x00), (0x00, 0x00, 0x00),
    (0xBC, 0xBC, 0xBC), (0x00, 0x78, 0xF8), (0x00, 0x58, 0xF8), (0x68, 0x44, 0xFC),
    (0xD8, 0x00, 0xCC), (0xE4, 0x00, 0x58), (0xF8, 0x38, 0x00), (0xE4, 0x5C, 0x10),
    (0xAC, 0x7C, 0x00), (0x00, 0xB8, 0x00), (0x00, 0xA8, 0x00), (0x00, 0xA8, 0x44),
    (0x00, 0x88, 0x88), (0x00, 0x00, 0x00), (0x00, 0x00, 0x00), (0x00, 0x00, 0x00),
    (0xF8, 0xF8, 0xF8), (0x3C, 0xBC, 0xFC), (0x68, 0x88, 0xFC), (0x98, 0x78, 0xF8),
    (0xF8, 0x78, 0xF8), (0xF8, 0x58, 0x98), (0xF8, 0x78, 0x00), (0xFC, 0xA0, 0x44),
    (0xF8, 0xB8, 0x00), (0xB8, 0xF8, 0x18), (0x58, 0xD8, 0x54), (0x58, 0xF8, 0x98),
    (0x00, 0xE8, 0xD8), (0x78, 0x78, 0x78), (0x00, 0x00, 0x00), (0x00, 0x00, 0x00),
    (0xFC, 0xFC, 0xFC), (0xA4, 0xE4, 0xFC), (0xB8, 0xB8, 0xF8), (0xD8, 0xB8, 0xF8),
    (0xF8, 0xB8, 0xF8), (0xF8, 0xA4, 0xC0), (0xF0, 0xD0, 0xB0), (0xFC, 0xE0, 0xA8),
    (0xF8, 0xD8, 0x78), (0xD8, 0xF8, 0x78), (0xB8, 0xF8, 0xB8), (0xB8, 0xF8, 0xD8),
    (0x00, 0xFC, 0xFC), (0xF8, 0xD8, 0xF8), (0x00, 0x00, 0x00), (0x00, 0x00, 0x00),
]

# --- ROM Class ---
class ROM:
    def __init__(self, data):
        self.data = bytearray(data)
        if self.data[:4] != b"NES\x1a":
            raise ValueError("Invalid iNES file - missing header")
        self.header = self.data[:16]
        self.prg_banks = self.header[4]
        self.chr_banks = self.header[5]
        self.mapper = (self.header[6] >> 4) | (self.header[7] & 0xF0)
        self.mirroring = self.header[6] & 0x01  # 0: Vertical, 1: Horizontal
        self.has_battery_ram = bool(self.header[6] & 0x02)
        self.has_trainer = bool(self.header[6] & 0x04)
        
        prg_start = 16 + (512 if self.has_trainer else 0)
        prg_end = prg_start + 16384 * self.prg_banks
        self.prg_rom = self.data[prg_start:prg_end]
        
        chr_start = prg_end
        chr_end = chr_start + 8192 * self.chr_banks
        if self.chr_banks == 0: # CHR RAM
            self.chr_mem = bytearray(8192)
            self.is_chr_ram = True
        else:
            self.chr_mem = self.data[chr_start:chr_end]
            self.is_chr_ram = False
        
        print(f"ROM Loaded: PRG Banks: {self.prg_banks}, CHR Banks: {self.chr_banks}, Mapper: {self.mapper}, Mirroring: {'Horizontal' if self.mirroring else 'Vertical'}")
        if self.is_chr_ram:
            print("Using CHR RAM (8KB)")

# --- CPU Status Flags ---
class StatusFlags:
    C = (1 << 0)  # Carry
    Z = (1 << 1)  # Zero
    I = (1 << 2)  # Interrupt Disable
    D = (1 << 3)  # Decimal Mode (unused)
    B = (1 << 4)  # Break Command
    U = (1 << 5)  # Unused (always 1)
    V = (1 << 6)  # Overflow
    N = (1 << 7)  # Negative

# --- CPU Class (Expanded) ---
class CPU:
    def __init__(self, nes):
        self.nes = nes
        self.ram = bytearray(0x0800)  # 2KB Work RAM
        self.reset()

        # Lookup table for opcodes (name, addressing_mode_func, operation_func, cycles)
        self.opcodes = {
            0x00: ("BRK", self.IMP, self.brk, 7), 0xEA: ("NOP", self.IMP, self.nop, 2),
            0xA9: ("LDA", self.IMM, self.lda, 2), 0xA5: ("LDA", self.ZP0, self.lda, 3),
            0xB5: ("LDA", self.ZPX, self.lda, 4), 0xAD: ("LDA", self.ABS, self.lda, 4),
            0xBD: ("LDA", self.ABX, self.lda, 4), 0xB9: ("LDA", self.ABY, self.lda, 4), # Add page cross penalty
            0xA1: ("LDA", self.IZX, self.lda, 6), 0xB1: ("LDA", self.IZY, self.lda, 5), # Add page cross penalty
            0xA2: ("LDX", self.IMM, self.ldx, 2), 0xA6: ("LDX", self.ZP0, self.ldx, 3),
            0xB6: ("LDX", self.ZPY, self.ldx, 4), 0xAE: ("LDX", self.ABS, self.ldx, 4),
            0xBE: ("LDX", self.ABY, self.ldx, 4), # Add page cross penalty
            0xA0: ("LDY", self.IMM, self.ldy, 2), 0xA4: ("LDY", self.ZP0, self.ldy, 3),
            0xB4: ("LDY", self.ZPX, self.ldy, 4), 0xAC: ("LDY", self.ABS, self.ldy, 4),
            0xBC: ("LDY", self.ABX, self.ldy, 4), # Add page cross penalty
            0x8D: ("STA", self.ABS, self.sta, 4), 0x85: ("STA", self.ZP0, self.sta, 3),
            0x95: ("STA", self.ZPX, self.sta, 4), 0x9D: ("STA", self.ABX, self.sta, 5),
            0x99: ("STA", self.ABY, self.sta, 5), 0x81: ("STA", self.IZX, self.sta, 6),
            0x91: ("STA", self.IZY, self.sta, 6),
            0x8E: ("STX", self.ABS, self.stx, 4), 0x86: ("STX", self.ZP0, self.stx, 3),
            0x96: ("STX", self.ZPY, self.stx, 4),
            0x8C: ("STY", self.ABS, self.sty, 4), 0x84: ("STY", self.ZP0, self.sty, 3),
            0x94: ("STY", self.ZPX, self.sty, 4),
            0xAA: ("TAX", self.IMP, self.tax, 2), 0xA8: ("TAY", self.IMP, self.tay, 2),
            0xBA: ("TSX", self.IMP, self.tsx, 2), 0x8A: ("TXA", self.IMP, self.txa, 2),
            0x9A: ("TXS", self.IMP, self.txs, 2), 0x98: ("TYA", self.IMP, self.tya, 2),
            0x48: ("PHA", self.IMP, self.pha, 3), 0x68: ("PLA", self.IMP, self.pla, 4),
            0x08: ("PHP", self.IMP, self.php, 3), 0x28: ("PLP", self.IMP, self.plp, 4),
            0x29: ("AND", self.IMM, self.and_op, 2),0x25: ("AND", self.ZP0, self.and_op, 3),
            0x35: ("AND", self.ZPX, self.and_op, 4),0x2D: ("AND", self.ABS, self.and_op, 4),
            0x3D: ("AND", self.ABX, self.and_op, 4),0x39: ("AND", self.ABY, self.and_op, 4),
            0x21: ("AND", self.IZX, self.and_op, 6),0x31: ("AND", self.IZY, self.and_op, 5),
            0x49: ("EOR", self.IMM, self.eor_op, 2),0x45: ("EOR", self.ZP0, self.eor_op, 3),
            0x55: ("EOR", self.ZPX, self.eor_op, 4),0x4D: ("EOR", self.ABS, self.eor_op, 4),
            0x5D: ("EOR", self.ABX, self.eor_op, 4),0x59: ("EOR", self.ABY, self.eor_op, 4),
            0x41: ("EOR", self.IZX, self.eor_op, 6),0x51: ("EOR", self.IZY, self.eor_op, 5),
            0x09: ("ORA", self.IMM, self.ora_op, 2),0x05: ("ORA", self.ZP0, self.ora_op, 3),
            0x15: ("ORA", self.ZPX, self.ora_op, 4),0x0D: ("ORA", self.ABS, self.ora_op, 4),
            0x1D: ("ORA", self.ABX, self.ora_op, 4),0x19: ("ORA", self.ABY, self.ora_op, 4),
            0x01: ("ORA", self.IZX, self.ora_op, 6),0x11: ("ORA", self.IZY, self.ora_op, 5),
            0x24: ("BIT", self.ZP0, self.bit, 3), 0x2C: ("BIT", self.ABS, self.bit, 4),
            0x10: ("BPL", self.REL, self.bpl, 2), 0x30: ("BMI", self.REL, self.bmi, 2),
            0x50: ("BVC", self.REL, self.bvc, 2), 0x70: ("BVS", self.REL, self.bvs, 2),
            0x90: ("BCC", self.REL, self.bcc, 2), 0xB0: ("BCS", self.REL, self.bcs, 2),
            0xD0: ("BNE", self.REL, self.bne, 2), 0xF0: ("BEQ", self.REL, self.beq, 2),
            0xC9: ("CMP", self.IMM, self.cmp, 2), 0xC5: ("CMP", self.ZP0, self.cmp, 3),
            0xD5: ("CMP", self.ZPX, self.cmp, 4), 0xCD: ("CMP", self.ABS, self.cmp, 4),
            0xDD: ("CMP", self.ABX, self.cmp, 4), 0xD9: ("CMP", self.ABY, self.cmp, 4),
            0xC1: ("CMP", self.IZX, self.cmp, 6), 0xD1: ("CMP", self.IZY, self.cmp, 5),
            0xE0: ("CPX", self.IMM, self.cpx, 2), 0xE4: ("CPX", self.ZP0, self.cpx, 3),
            0xEC: ("CPX", self.ABS, self.cpx, 4),
            0xC0: ("CPY", self.IMM, self.cpy, 2), 0xC4: ("CPY", self.ZP0, self.cpy, 3),
            0xCC: ("CPY", self.ABS, self.cpy, 4),
            0xE6: ("INC", self.ZP0, self.inc, 5), 0xF6: ("INC", self.ZPX, self.inc, 6),
            0xEE: ("INC", self.ABS, self.inc, 6), 0xFE: ("INC", self.ABX, self.inc, 7),
            0xC6: ("DEC", self.ZP0, self.dec, 5), 0xD6: ("DEC", self.ZPX, self.dec, 6),
            0xCE: ("DEC", self.ABS, self.dec, 6), 0xDE: ("DEC", self.ABX, self.dec, 7),
            0xE8: ("INX", self.IMP, self.inx, 2), 0xCA: ("DEX", self.IMP, self.dex, 2),
            0xC8: ("INY", self.IMP, self.iny, 2), 0x88: ("DEY", self.IMP, self.dey, 2),
            0x0A: ("ASL", self.ACC, self.asl_acc, 2), 0x06: ("ASL", self.ZP0, self.asl_mem, 5),
            0x16: ("ASL", self.ZPX, self.asl_mem, 6), 0x0E: ("ASL", self.ABS, self.asl_mem, 6),
            0x1E: ("ASL", self.ABX, self.asl_mem, 7),
            0x4A: ("LSR", self.ACC, self.lsr_acc, 2), 0x46: ("LSR", self.ZP0, self.lsr_mem, 5),
            0x56: ("LSR", self.ZPX, self.lsr_mem, 6), 0x4E: ("LSR", self.ABS, self.lsr_mem, 6),
            0x5E: ("LSR", self.ABX, self.lsr_mem, 7),
            0x2A: ("ROL", self.ACC, self.rol_acc, 2), 0x26: ("ROL", self.ZP0, self.rol_mem, 5),
            0x36: ("ROL", self.ZPX, self.rol_mem, 6), 0x2E: ("ROL", self.ABS, self.rol_mem, 6),
            0x3E: ("ROL", self.ABX, self.rol_mem, 7),
            0x6A: ("ROR", self.ACC, self.ror_acc, 2), 0x66: ("ROR", self.ZP0, self.ror_mem, 5),
            0x76: ("ROR", self.ZPX, self.ror_mem, 6), 0x6E: ("ROR", self.ABS, self.ror_mem, 6),
            0x7E: ("ROR", self.ABX, self.ror_mem, 7),
            0x4C: ("JMP", self.ABS_JMP, self.jmp, 3), 0x6C: ("JMP", self.IND_JMP, self.jmp, 5),
            0x20: ("JSR", self.ABS_JMP, self.jsr, 6),0x60: ("RTS", self.IMP, self.rts, 6),
            0x40: ("RTI", self.IMP, self.rti, 6),
            0x18: ("CLC", self.IMP, self.clc, 2), 0x38: ("SEC", self.IMP, self.sec, 2),
            0x58: ("CLI", self.IMP, self.cli, 2), 0x78: ("SEI", self.IMP, self.sei, 2),
            0xB8: ("CLV", self.IMP, self.clv, 2), 0xD8: ("CLD", self.IMP, self.cld, 2),
            0xF8: ("SED", self.IMP, self.sed, 2),
        }
        # Add more opcodes...
        self.cycles_remaining = 0
        self.total_cycles = 0


    def reset(self):
        self.pc = self.read_word(0xFFFC)
        self.sp = 0xFD
        self.acc = 0
        self.x = 0
        self.y = 0
        self.status = StatusFlags.U | StatusFlags.I # Start with Unused and Interrupt Disable set
        self.cycles_remaining = 8 # Reset takes 8 cycles
        self.total_cycles = 0
        print(f"CPU Reset: PC set to ${self.pc:04X}")

    def nmi(self):
        self.push_word(self.pc)
        self.push(self.status | StatusFlags.U) # B flag is not set by NMI
        self.status |= StatusFlags.I # Disable further interrupts
        self.pc = self.read_word(0xFFFA)
        self.cycles_remaining += 7
        print(f"NMI: PC set to ${self.pc:04X}")
        
    def irq(self):
        if not (self.status & StatusFlags.I):
            self.push_word(self.pc)
            self.push(self.status | StatusFlags.U) # B flag is not set
            self.status |= StatusFlags.I
            self.pc = self.read_word(0xFFFE)
            self.cycles_remaining += 7
            print(f"IRQ: PC set to ${self.pc:04X}")


    def set_flag(self, flag, value):
        if value: self.status |= flag
        else: self.status &= ~flag

    def get_flag(self, flag):
        return bool(self.status & flag)

    def set_zn_flags(self, value):
        self.set_flag(StatusFlags.Z, value == 0)
        self.set_flag(StatusFlags.N, bool(value & 0x80))

    def read(self, addr):
        addr &= 0xFFFF # Ensure 16-bit address
        if 0x0000 <= addr < 0x2000: # RAM
            return self.ram[addr % 0x0800]
        elif 0x2000 <= addr < 0x4000: # PPU Registers
            return self.nes.ppu.read_register(addr % 8)
        elif 0x4000 <= addr < 0x4018: # APU/IO Registers
            if addr == 0x4016: # Controller 1
                return self.nes.controller1.read()
            elif addr == 0x4017: # Controller 2
                return self.nes.controller2.read()
            # Other APU/IO regs...
            return 0 # Placeholder
        elif 0x4020 <= addr < 0x6000: # Expansion ROM (often unused)
            return 0 # Placeholder
        elif 0x6000 <= addr < 0x8000: # Battery Backed RAM (SRAM)
             # For now, assume no SRAM or handled by mapper
            return 0
        elif 0x8000 <= addr <= 0xFFFF: # PRG ROM
            # Mapper 0 logic (NROM)
            if self.nes.rom.prg_banks == 1: # 16KB ROM
                return self.nes.rom.prg_rom[(addr - 0x8000) % 0x4000]
            else: # 32KB ROM
                return self.nes.rom.prg_rom[addr - 0x8000]
        return 0 # Should not happen with proper mapping

    def write(self, addr, value):
        addr &= 0xFFFF
        value &= 0xFF
        if 0x0000 <= addr < 0x2000: # RAM
            self.ram[addr % 0x0800] = value
        elif 0x2000 <= addr < 0x4000: # PPU Registers
            self.nes.ppu.write_register(addr % 8, value)
        elif 0x4000 <= addr < 0x4018: # APU/IO Registers
            if addr == 0x4014: # OAM DMA
                self.nes.ppu.oam_dma(value)
            elif addr == 0x4016: # Controller Strobe
                self.nes.controller1.write(value)
                self.nes.controller2.write(value)
            # Other APU/IO regs...
        elif 0x6000 <= addr < 0x8000: # SRAM
            pass # Handle SRAM writes if mapper supports it
        elif 0x8000 <= addr <= 0xFFFF: # PRG ROM (writes usually for mappers)
            # Handle mapper writes here if applicable
            # print(f"Warning: Write to PRG-ROM space ${addr:04X} = ${value:02X} (Mapper may handle this)")
            pass


    def read_word(self, addr):
        low = self.read(addr)
        high = self.read(addr + 1)
        return (high << 8) | low
    
    def read_word_bug(self, addr): # For JMP (indirect) bug
        low = self.read(addr)
        # If addr LSB is 0xFF, the high byte is read from addr & 0xFF00, not addr + 1
        if (addr & 0x00FF) == 0x00FF:
            high = self.read(addr & 0xFF00)
        else:
            high = self.read(addr + 1)
        return (high << 8) | low

    def push(self, value):
        self.write(0x0100 + self.sp, value)
        self.sp = (self.sp - 1) & 0xFF

    def pop(self):
        self.sp = (self.sp + 1) & 0xFF
        return self.read(0x0100 + self.sp)

    def push_word(self, value):
        self.push((value >> 8) & 0xFF) # High byte
        self.push(value & 0xFF)        # Low byte

    def pop_word(self):
        low = self.pop()
        high = self.pop()
        return (high << 8) | low
    
    # --- Addressing Modes ---
    # Each returns the effective address or value, and if a page boundary was crossed (for cycle penalty)
    def IMM(self): self.pc += 1; return self.pc - 1, False # Returns address of immediate value
    def ZP0(self): self.pc += 1; return self.read(self.pc -1) & 0xFF, False
    def ZPX(self): self.pc += 1; return (self.read(self.pc -1) + self.x) & 0xFF, False
    def ZPY(self): self.pc += 1; return (self.read(self.pc -1) + self.y) & 0xFF, False # Only for LDX, STX
    def ABS(self): self.pc += 2; return self.read_word(self.pc - 2), False
    def ABX(self): 
        self.pc += 2
        base_addr = self.read_word(self.pc - 2)
        eff_addr = (base_addr + self.x) & 0xFFFF
        return eff_addr, (base_addr & 0xFF00) != (eff_addr & 0xFF00)
    def ABY(self): 
        self.pc += 2
        base_addr = self.read_word(self.pc - 2)
        eff_addr = (base_addr + self.y) & 0xFFFF
        return eff_addr, (base_addr & 0xFF00) != (eff_addr & 0xFF00)
    def IZX(self): # (Indirect, X)
        self.pc += 1
        zp_addr = (self.read(self.pc-1) + self.x) & 0xFF
        eff_addr = self.read_word_bug(zp_addr) # Uses page wrap bug for address read
        return eff_addr, False
    def IZY(self): # (Indirect), Y
        self.pc += 1
        zp_addr = self.read(self.pc-1)
        base_addr = self.read_word_bug(zp_addr) # Uses page wrap bug for address read
        eff_addr = (base_addr + self.y) & 0xFFFF
        return eff_addr, (base_addr & 0xFF00) != (eff_addr & 0xFF00)
    def IMP(self): return 0, False # Implied, no operand needed
    def REL(self): # Relative for branches
        self.pc += 1
        offset = self.read(self.pc - 1)
        if offset & 0x80: offset -= 0x100 # Sign extend
        return (self.pc + offset) & 0xFFFF, False
    def ACC(self): return 0, False # Accumulator addressing
    def ABS_JMP(self): self.pc +=2; return self.read_word(self.pc - 2), False # For JMP ABS
    def IND_JMP(self): self.pc +=2; return self.read_word_bug(self.read_word(self.pc-2)), False # For JMP IND

    # --- Opcodes Implementation ---
    def lda(self, addr, page_crossed):
        value = self.read(addr) if addr is not None else self.acc # Handle ACC mode if added
        self.acc = value
        self.set_zn_flags(self.acc)
        return 1 if page_crossed and self.opcodes[self.current_opcode][1] in [self.ABX, self.ABY, self.IZY] else 0
    
    def ldx(self, addr, page_crossed):
        value = self.read(addr)
        self.x = value
        self.set_zn_flags(self.x)
        return 1 if page_crossed and self.opcodes[self.current_opcode][1] == self.ABY else 0 # LDX, ABY

    def ldy(self, addr, page_crossed):
        value = self.read(addr)
        self.y = value
        self.set_zn_flags(self.y)
        return 1 if page_crossed and self.opcodes[self.current_opcode][1] == self.ABX else 0 # LDY, ABX

    def sta(self, addr, page_crossed): self.write(addr, self.acc); return 0
    def stx(self, addr, page_crossed): self.write(addr, self.x); return 0
    def sty(self, addr, page_crossed): self.write(addr, self.y); return 0

    def tax(self, addr, page_crossed): self.x = self.acc; self.set_zn_flags(self.x); return 0
    def tay(self, addr, page_crossed): self.y = self.acc; self.set_zn_flags(self.y); return 0
    def tsx(self, addr, page_crossed): self.x = self.sp; self.set_zn_flags(self.x); return 0
    def txa(self, addr, page_crossed): self.acc = self.x; self.set_zn_flags(self.acc); return 0
    def txs(self, addr, page_crossed): self.sp = self.x; return 0 # No flags
    def tya(self, addr, page_crossed): self.acc = self.y; self.set_zn_flags(self.acc); return 0

    def pha(self, addr, page_crossed): self.push(self.acc); return 0
    def pla(self, addr, page_crossed): self.acc = self.pop(); self.set_zn_flags(self.acc); return 0
    def php(self, addr, page_crossed): self.push(self.status | StatusFlags.B | StatusFlags.U); return 0 # B and U are set on stack
    def plp(self, addr, page_crossed): self.status = (self.pop() & ~StatusFlags.B) | StatusFlags.U; return 0 # B is not restored, U is always set

    def _branch(self, condition, target_addr):
        if condition:
            self.cycles_remaining += 1 # Branch taken
            if (self.pc & 0xFF00) != (target_addr & 0xFF00):
                self.cycles_remaining += 1 # Page crossed
            self.pc = target_addr
        return 0 # Base cycles already counted

    def bpl(self, addr, page_crossed): return self._branch(not self.get_flag(StatusFlags.N), addr)
    def bmi(self, addr, page_crossed): return self._branch(self.get_flag(StatusFlags.N), addr)
    def bvc(self, addr, page_crossed): return self._branch(not self.get_flag(StatusFlags.V), addr)
    def bvs(self, addr, page_crossed): return self._branch(self.get_flag(StatusFlags.V), addr)
    def bcc(self, addr, page_crossed): return self._branch(not self.get_flag(StatusFlags.C), addr)
    def bcs(self, addr, page_crossed): return self._branch(self.get_flag(StatusFlags.C), addr)
    def bne(self, addr, page_crossed): return self._branch(not self.get_flag(StatusFlags.Z), addr)
    def beq(self, addr, page_crossed): return self._branch(self.get_flag(StatusFlags.Z), addr)

    def bit(self, addr, page_crossed):
        value = self.read(addr)
        self.set_flag(StatusFlags.Z, (self.acc & value) == 0)
        self.set_flag(StatusFlags.N, bool(value & 0x80))
        self.set_flag(StatusFlags.V, bool(value & 0x40))
        return 0
    
    def _compare(self, reg_val, mem_val):
        result = reg_val - mem_val
        self.set_flag(StatusFlags.C, result >= 0)
        self.set_zn_flags(result & 0xFF)

    def cmp(self, addr, page_crossed): self._compare(self.acc, self.read(addr)); return 1 if page_crossed else 0
    def cpx(self, addr, page_crossed): self._compare(self.x, self.read(addr)); return 0 # No page cross penalty for CPX/CPY IMM
    def cpy(self, addr, page_crossed): self._compare(self.y, self.read(addr)); return 0

    def _logical_op(self, op_func, addr, page_crossed):
        self.acc = op_func(self.acc, self.read(addr))
        self.set_zn_flags(self.acc)
        return 1 if page_crossed else 0

    def and_op(self, addr, page_crossed): return self._logical_op(lambda a, b: a & b, addr, page_crossed)
    def eor_op(self, addr, page_crossed): return self._logical_op(lambda a, b: a ^ b, addr, page_crossed)
    def ora_op(self, addr, page_crossed): return self._logical_op(lambda a, b: a | b, addr, page_crossed)

    def inc(self, addr, page_crossed): value = (self.read(addr) + 1) & 0xFF; self.write(addr, value); self.set_zn_flags(value); return 0
    def dec(self, addr, page_crossed): value = (self.read(addr) - 1) & 0xFF; self.write(addr, value); self.set_zn_flags(value); return 0
    def inx(self, addr, page_crossed): self.x = (self.x + 1) & 0xFF; self.set_zn_flags(self.x); return 0
    def dex(self, addr, page_crossed): self.x = (self.x - 1) & 0xFF; self.set_zn_flags(self.x); return 0
    def iny(self, addr, page_crossed): self.y = (self.y + 1) & 0xFF; self.set_zn_flags(self.y); return 0
    def dey(self, addr, page_crossed): self.y = (self.y - 1) & 0xFF; self.set_zn_flags(self.y); return 0
    
    def _shift_op_acc(self, shift_func):
        self.acc = shift_func(self.acc)
        self.set_zn_flags(self.acc)
        return 0
    
    def _shift_op_mem(self, shift_func, addr):
        value = self.read(addr)
        result = shift_func(value)
        self.write(addr, result)
        self.set_zn_flags(result)
        return 0

    def asl_acc(self, addr, page_crossed): return self._shift_op_acc(lambda val: (self.set_flag(StatusFlags.C, bool(val & 0x80)), (val << 1) & 0xFF)[1])
    def asl_mem(self, addr, page_crossed): return self._shift_op_mem(lambda val: (self.set_flag(StatusFlags.C, bool(val & 0x80)), (val << 1) & 0xFF)[1], addr)
    def lsr_acc(self, addr, page_crossed): return self._shift_op_acc(lambda val: (self.set_flag(StatusFlags.C, bool(val & 0x01)), val >> 1)[1])
    def lsr_mem(self, addr, page_crossed): return self._shift_op_mem(lambda val: (self.set_flag(StatusFlags.C, bool(val & 0x01)), val >> 1)[1], addr)
    def rol_acc(self, addr, page_crossed): return self._shift_op_acc(lambda val: (old_c = self.get_flag(StatusFlags.C), self.set_flag(StatusFlags.C, bool(val & 0x80)), ((val << 1) | old_c) & 0xFF)[2])
    def rol_mem(self, addr, page_crossed): return self._shift_op_mem(lambda val: (old_c = self.get_flag(StatusFlags.C), self.set_flag(StatusFlags.C, bool(val & 0x80)), ((val << 1) | old_c) & 0xFF)[2], addr)
    def ror_acc(self, addr, page_crossed): return self._shift_op_acc(lambda val: (old_c = self.get_flag(StatusFlags.C), self.set_flag(StatusFlags.C, bool(val & 0x01)), (val >> 1) | (old_c << 7))[2])
    def ror_mem(self, addr, page_crossed): return self._shift_op_mem(lambda val: (old_c = self.get_flag(StatusFlags.C), self.set_flag(StatusFlags.C, bool(val & 0x01)), (val >> 1) | (old_c << 7))[2], addr)

    def jmp(self, addr, page_crossed): self.pc = addr; return 0
    def jsr(self, addr, page_crossed): self.push_word(self.pc - 1); self.pc = addr; return 0 # PC is already advanced by ABS_JMP
    def rts(self, addr, page_crossed): self.pc = (self.pop_word() + 1) & 0xFFFF; return 0
    def rti(self, addr, page_crossed): 
        self.status = (self.pop() & ~StatusFlags.B) | StatusFlags.U
        self.pc = self.pop_word()
        return 0
    
    def brk(self, addr, page_crossed):
        self.pc += 1 # BRK is 2 bytes, but PC already advanced by 1
        self.push_word(self.pc)
        self.push(self.status | StatusFlags.B | StatusFlags.U) # B flag set on stack
        self.status |= StatusFlags.I
        self.pc = self.read_word(0xFFFE) # IRQ vector
        return 0
    
    def nop(self, addr, page_crossed): return 0 # No operation
    
    def clc(self, addr, page_crossed): self.set_flag(StatusFlags.C, False); return 0
    def sec(self, addr, page_crossed): self.set_flag(StatusFlags.C, True); return 0
    def cli(self, addr, page_crossed): self.set_flag(StatusFlags.I, False); return 0
    def sei(self, addr, page_crossed): self.set_flag(StatusFlags.I, True); return 0
    def clv(self, addr, page_crossed): self.set_flag(StatusFlags.V, False); return 0
    def cld(self, addr, page_crossed): self.set_flag(StatusFlags.D, False); return 0 # Decimal mode not used
    def sed(self, addr, page_crossed): self.set_flag(StatusFlags.D, True); return 0 # Decimal mode not used

    def step(self):
        if self.cycles_remaining > 0:
            self.cycles_remaining -= 1
            return 1

        self.current_opcode = self.read(self.pc)
        self.pc = (self.pc + 1) & 0xFFFF
        
        op_info = self.opcodes.get(self.current_opcode)
        if not op_info:
            print(f"Unknown opcode: ${self.current_opcode:02X} at PC: ${self.pc-1:04X}")
            # Potentially halt or raise error
            return 1 # Consume one cycle for the unknown opcode fetch

        op_name, addr_mode_func, op_func, base_cycles = op_info
        
        # For debugging:
        # if self.total_cycles > 200000 and self.total_cycles < 200100 : # Print a window of instructions
        #    print(f"PC:${self.pc-1:04X} Op:${self.current_opcode:02X}({op_name}) A:${self.acc:02X} X:${self.x:02X} Y:${self.y:02X} P:${self.status:02X} SP:${self.sp:02X} CYC:{self.total_cycles}")

        eff_addr, page_crossed = addr_mode_func()
        
        # For immediate mode, eff_addr is the address of the immediate value itself
        # For accumulator mode, op_func needs to know to use self.acc
        param_for_op = eff_addr
        if addr_mode_func == self.IMM:
            param_for_op = self.read(eff_addr) # Pass the value for IMM
        elif addr_mode_func == self.ACC:
            param_for_op = None # Op function will use self.acc

        additional_cycles = op_func(eff_addr, page_crossed) # Pass eff_addr or value based on mode
        
        self.cycles_remaining = base_cycles + additional_cycles -1 # -1 for current cycle
        self.total_cycles += base_cycles + additional_cycles
        return base_cycles + additional_cycles

# --- PPU Class (Expanded) ---
class PPU:
    def __init__(self, nes):
        self.nes = nes
        pygame.init()
        pygame.display.set_caption("NES Emulator - Nesticle Style")
        self.screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
        self.framebuffer = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT)) # Internal buffer
        self.clock = pygame.time.Clock()

        self.vram = bytearray(0x0800)  # 2KB for nametables (mirrored to 0x2000-0x2FFF)
        self.palette_ram = bytearray(0x20) # 32 bytes for palettes
        self.oam = bytearray(0x100)      # 256 bytes for Object Attribute Memory (sprites)
        
        # PPU Registers
        self.ppuctrl = 0    # $2000 Write
        self.ppumask = 0    # $2001 Write
        self.ppustatus = 0  # $2002 Read
        self.oamaddr = 0    # $2003 Write
        # self.oamdata ($2004) is direct access to self.oam via oamaddr
        # self.ppuscroll ($2005) Write x2
        # self.ppuaddr ($2006) Write x2
        # self.ppudata ($2007) Read/Write
        
        self.vram_addr = 0  # Current VRAM address (15-bit)
        self.temp_vram_addr = 0 # Temporary VRAM address (15-bit)
        self.fine_x_scroll = 0 # 3-bit
        self.addr_latch = False # False: high byte, True: low byte for PPUADDR/PPUSCROLL

        self.data_buffer = 0 # For PPUDATA reads (buffered)
        
        self.scanline = 0
        self.cycle = 0
        self.frame_count = 0
        self.nmi_occurred = False
        self.nmi_output = False
        
        # Default palette (can be overwritten by game)
        # Example: Solid color for background color 0
        self.palette_ram[0x00] = 0x0F # Black
        self.palette_ram[0x01] = 0x01 # Dark Blue
        self.palette_ram[0x02] = 0x11 # Brighter Blue
        self.palette_ram[0x03] = 0x21 # Brightest Blue

        self.nametable_cache = [pygame.Surface((256,240)) for _ in range(4)] # Cache for nametables if needed
        self.pattern_table_cache = [pygame.Surface((128,128)) for _ in range(2)] # Cache for pattern tables


    def reset(self):
        self.ppuctrl = 0
        self.ppumask = 0
        self.ppustatus = 0 # VBlank flag cleared
        self.oamaddr = 0
        self.vram_addr = 0
        self.temp_vram_addr = 0
        self.fine_x_scroll = 0
        self.addr_latch = False
        self.data_buffer = 0
        self.scanline = 0
        self.cycle = 0
        self.nmi_occurred = False
        self.nmi_output = False
        # Clear VRAM, OAM, Palette RAM? Usually game initializes these.

    def oam_dma(self, page_addr):
        """ DMA transfer from CPU RAM to PPU OAM """
        start_addr = page_addr << 8
        for i in range(256):
            self.oam[(self.oamaddr + i) & 0xFF] = self.nes.cpu.read(start_addr + i)
        self.nes.cpu.cycles_remaining += 513 # Or 514 if on odd CPU cycle
        # print(f"OAM DMA from ${start_addr:04X}")

    def read_register(self, reg_idx):
        val = 0
        if reg_idx == 2: # PPUSTATUS ($2002)
            val = (self.ppustatus & 0xE0) | (self.data_buffer & 0x1F) # Top 3 bits + PPU open bus
            self.ppustatus &= ~0x80 # Clear VBlank flag
            self.addr_latch = False
            if self.scanline == VBLANK_SCANLINE and self.cycle == 1: # Suppress NMI if PPUSTATUS read here
                self.nmi_output = False 
            # print(f"Read PPUSTATUS: ${val:02X} (VBlank cleared)")
        elif reg_idx == 4: # OAMDATA ($2004)
            val = self.oam[self.oamaddr]
            # OAMDATA read doesn't increment OAMADDR during rendering
        elif reg_idx == 7: # PPUDATA ($2007)
            val = self.data_buffer # Return buffered value
            self.data_buffer = self.read_ppu_memory(self.vram_addr) # Update buffer with new value
            if self.vram_addr >= 0x3F00: # Palette RAM reads are immediate
                 val = self.data_buffer
            self.vram_addr += 32 if (self.ppuctrl & 0x04) else 1
            self.vram_addr &= 0x3FFF
            # print(f"Read PPUDATA: val=${val:02X}, new_buffer=${self.data_buffer:02X}, VRAM_ADDR=${self.vram_addr:04X}")
        return val

    def write_register(self, reg_idx, value):
        # self.data_buffer = value # Any PPU write updates the "open bus" decay value
        if reg_idx == 0: # PPUCTRL ($2000)
            old_nmi_enable = self.ppuctrl & 0x80
            self.ppuctrl = value
            self.temp_vram_addr = (self.temp_vram_addr & 0xF3FF) | ((value & 0x03) << 10) # Nametable select
            if not old_nmi_enable and (self.ppuctrl & 0x80) and (self.ppustatus & 0x80):
                 self.nmi_output = True # NMI can be triggered if enabled now and VBlank is set
            # print(f"Write PPUCTRL: ${value:02X}")
        elif reg_idx == 1: # PPUMASK ($2001)
            self.ppumask = value
            # print(f"Write PPUMASK: ${value:02X}")
        elif reg_idx == 3: # OAMADDR ($2003)
            self.oamaddr = value
        elif reg_idx == 4: # OAMDATA ($2004)
            self.oam[self.oamaddr] = value
            self.oamaddr = (self.oamaddr + 1) & 0xFF
        elif reg_idx == 5: # PPUSCROLL ($2005)
            if not self.addr_latch: # First write (X scroll)
                self.temp_vram_addr = (self.temp_vram_addr & 0xFFE0) | (value >> 3)
                self.fine_x_scroll = value & 0x07
            else: # Second write (Y scroll)
                self.temp_vram_addr = (self.temp_vram_addr & 0x8C1F) | ((value & 0xF8) << 2) | ((value & 0x07) << 12)
            self.addr_latch = not self.addr_latch
            # print(f"Write PPUSCROLL: ${value:02X}, latch: {self.addr_latch}, fine_x: {self.fine_x_scroll}")
        elif reg_idx == 6: # PPUADDR ($2006)
            if not self.addr_latch: # First write (High byte)
                self.temp_vram_addr = (self.temp_vram_addr & 0x00FF) | ((value & 0x3F) << 8) # Mask to 14 bits
            else: # Second write (Low byte)
                self.temp_vram_addr = (self.temp_vram_addr & 0xFF00) | value
                self.vram_addr = self.temp_vram_addr # Commit to main VRAM address
            self.addr_latch = not self.addr_latch
            # print(f"Write PPUADDR: ${value:02X}, latch: {self.addr_latch}, VRAM_ADDR=${self.vram_addr:04X}")
        elif reg_idx == 7: # PPUDATA ($2007)
            self.write_ppu_memory(self.vram_addr, value)
            self.vram_addr += 32 if (self.ppuctrl & 0x04) else 1
            self.vram_addr &= 0x3FFF # VRAM address wraps around
            # print(f"Write PPUDATA: ${value:02X} to ${self.vram_addr:04X} (before increment)")

    def _get_mirrored_vram_addr(self, addr):
        addr &= 0x3FFF # Max PPU address
        if 0x3000 <= addr <= 0x3EFF: # Mirror of 0x2000-0x2EFF
            addr -= 0x1000
        
        # Nametable mirroring
        # 0x2000-0x23FF (NT0), 0x2400-0x27FF (NT1)
        # 0x2800-0x2BFF (NT2), 0x2C00-0x2FFF (NT3)
        if 0x2000 <= addr <= 0x2FFF:
            relative_addr = addr & 0x03FF # Offset within a nametable
            if self.nes.rom.mirroring == 0: # Vertical (NT0, NT2) <-> (NT1, NT3)
                # NT0 maps to NT0 (0x2000), NT1 maps to NT1 (0x2400)
                # NT2 maps to NT0 (0x2000), NT3 maps to NT1 (0x2400)
                if (addr & 0x0800): # NT2 or NT3
                    return (addr & 0x07FF) | 0x2000 if (addr & 0x0400) else (addr & 0x07FF) | 0x2000 # This logic simplifies to:
                    # if using NT2 (0x2800-0x2BFF), maps to NT0 (0x2000-0x23FF)
                    # if using NT3 (0x2C00-0x2FFF), maps to NT1 (0x2400-0x27FF)
                    return (addr - 0x0800) 
                return addr # NT0 and NT1 are fine
            elif self.nes.rom.mirroring == 1: # Horizontal (NT0, NT1) <-> (NT2, NT3)
                # NT0 maps to NT0, NT2 maps to NT0
                # NT1 maps to NT1, NT3 maps to NT1
                if (addr & 0x0400): # NT1 or NT3
                    return (addr & 0x0BFF) if (addr & 0x0800) else addr # NT1 maps to NT1, NT3 maps to NT1
                    # if using NT1 (0x2400-0x27FF), maps to NT1
                    # if using NT3 (0x2C00-0x2FFF), maps to NT1 (0x2400)
                    return (addr - 0x0400) if (addr & 0x0800) else addr # Effectively maps 2 and 3 to 0 and 1 with mirroring on the same physical bank.
                                                                   # Simplified:
                if addr >= 0x2800: # NT2 or NT3
                    addr -= 0x0800 # Map to NT0 or NT1
                if addr >= 0x2400: # NT1 or (original NT3 mapped to NT1)
                    addr -= 0x0400 # Map to physical bank 1
                return addr | (0x2000 if (addr & 0x0400) == 0 else 0x2400) # This needs more careful thought for horizontal
                # Correct Horizontal:
                # NT0 (0x2000), NT1 (0x2400) are distinct.
                # NT2 (0x2800) mirrors NT0. NT3 (0x2C00) mirrors NT1.
                if addr >= 0x2C00: return (addr - 0x0C00) + 0x2400 # NT3 -> NT1
                if addr >= 0x2800: return (addr - 0x0800) + 0x2000 # NT2 -> NT0
                # For horizontal: (0,1) are one bank, (2,3) are another.
                # (0,2) use one physical memory, (1,3) use another.
                # if relative_addr comes from 0x2000 or 0x2800 -> use bank A
                # if relative_addr comes from 0x2400 or 0x2C00 -> use bank B
                if self.nes.rom.mirroring == 1: # Horizontal
                    if (addr & 0x0400): # Nametables 1 or 3 (0x2400-0x27FF or 0x2C00-0x2FFF)
                        return 0x0400 + relative_addr # Use second physical nametable RAM
                    else: # Nametables 0 or 2 (0x2000-0x23FF or 0x2800-0x2BFF)
                        return relative_addr # Use first physical nametable RAM
                else: # Vertical
                    if (addr & 0x0800): # Nametables 2 or 3 (0x2800-0x2FFF)
                        return 0x0400 + relative_addr # Use second physical nametable RAM
                    else: # Nametables 0 or 1 (0x2000-0x27FF)
                        return relative_addr # Use first physical nametable RAM
            # Simplified mirroring (for now):
            # Vertical: $2000-$23FF and $2800-$2BFF use one 1K bank. $2400-$27FF and $2C00-$2FFF use another.
            # Horizontal: $2000-$23FF and $2400-$27FF use one 1K bank. $2800-$2BFF and $2C00-$2FFF use another.
            # This implementation maps 0x2000-0x27FF to self.vram[0x000-0x7FF] and mirrors above.
            # return (addr & 0x07FF) if self.nes.rom.mirroring == 0 else (addr & 0x03FF) | ((addr & 0x0800) >> 1)
            # For NROM (mapper 0), often physical VRAM is just 2KB.
            # Nametable 0 at $2000, Nametable 1 at $2400.
            # Vertical: $2000 mirrors $2800, $2400 mirrors $2C00. Index into vram: addr % 0x800.
            # Horizontal: $2000 mirrors $2400, $2800 mirrors $2C00. Index into vram: (addr & 0x3FF) or (addr & 0x3FF) + 0x400
            if self.nes.rom.mirroring == 0: # Vertical
                return addr & 0x07FF # Mirrors $2000/$2800 and $2400/$2C00
            else: # Horizontal
                if addr >= 0x2800: addr -= 0x0800 # Map NT2/3 to NT0/1 space
                if addr >= 0x2400: addr -= 0x0400 # Map NT1 to NT0 space
                return addr & 0x03FF # This effectively gives two 1KB banks next to each other if not careful
                # Corrected simplified for two 1KB physical banks:
                # Horizontal: (NT0, NT1 share bank 0), (NT2, NT3 share bank 1) NO, this is wrong.
                # Horizontal: (NT0, NT2 share bank 0), (NT1, NT3 share bank 1)
                # Vertical:   (NT0, NT1 share bank 0), (NT2, NT3 share bank 1)  NO.
                # Vertical: (NT0, NT2 use one physical bank), (NT1, NT3 use other physical bank)
                # (addr & 0x3FF) is offset within a nametable.
                # Mirroring determines which 1KB physical bank is used.
                # VRAM is 2KB (0x800 bytes).
                # Bank 0: self.vram[0x000-0x3FF]
                # Bank 1: self.vram[0x400-0x7FF]

                if self.nes.rom.mirroring == 0: # Vertical
                    if (addr & 0x0800): # Nametable 2 or 3
                        return (addr & 0x03FF) # Maps to Bank 0 (like NT0)
                    else: # Nametable 0 or 1
                        return (addr & 0x03FF) + (0x0400 if (addr & 0x0400) else 0x0000) # NT0 to Bank0, NT1 to Bank1
                else: # Horizontal
                    if (addr & 0x0400): # Nametable 1 or 3
                        return (addr & 0x03FF) # Maps to Bank 0 (like NT0)
                    else: # Nametable 0 or 2
                        return (addr & 0x03FF) + (0x0400 if (addr & 0x0800) else 0x0000) # NT0 to Bank0, NT2 to Bank1
                # Let's use a common interpretation:
                # Vertical: (NT0, NT2) -> VRAM 0-0x3FF; (NT1, NT3) -> VRAM 0x400-0x7FF
                # Horizontal: (NT0, NT1) -> VRAM 0-0x3FF; (NT2, NT3) -> VRAM 0x400-0x7FF
                if self.nes.rom.mirroring == 0: # Vertical mirroring
                    if addr < 0x2800: # NT0 or NT1
                        return addr & 0x07FF # Accesses first 2KB of VRAM (0x2000-0x27FF -> 0x000-0x7FF)
                    else: # NT2 or NT3
                        return (addr & 0x07FF) # Mirrors NT0/NT1
                else: # Horizontal mirroring
                    if addr < 0x2400 or (addr >= 0x2800 and addr < 0x2C00): # NT0 or NT2
                        return addr & 0x03FF # Accesses first 1KB (0x000-0x3FF)
                    else: # NT1 or NT3
                        return (addr & 0x03FF) + 0x0400 # Accesses second 1KB (0x400-0x7FF)
        return addr # For CHR ROM/RAM and Palette

    def read_ppu_memory(self, addr):
        addr = self._get_mirrored_vram_addr(addr)
        if 0x0000 <= addr < 0x2000: # Pattern Tables (CHR ROM/RAM)
            return self.nes.rom.chr_mem[addr]
        elif 0x2000 <= addr < 0x3F00: # Nametables (actually 0x2000-0x2FFF after mirroring logic)
            return self.vram[addr & 0x07FF] # Access one of the two 1KB banks
        elif 0x3F00 <= addr < 0x4000: # Palette RAM
            addr &= 0x1F # Mirror 0x3F20-0x3FFF to 0x3F00-0x3F1F
            if addr == 0x10 or addr == 0x14 or addr == 0x18 or addr == 0x1C: # Sprite palette mirrors BG palette
                addr -= 0x10
            return self.palette_ram[addr] & (0x3F if self.ppumask & 0x01 else 0x30) # Greyscale applies here
        return 0

    def write_ppu_memory(self, addr, value):
        addr = self._get_mirrored_vram_addr(addr)
        if 0x0000 <= addr < 0x2000: # Pattern Tables
            if self.nes.rom.is_chr_ram:
                self.nes.rom.chr_mem[addr] = value
            # else: print(f"Attempt to write to CHR ROM at ${addr:04X}")
        elif 0x2000 <= addr < 0x3F00: # Nametables
            self.vram[addr & 0x07FF] = value
        elif 0x3F00 <= addr < 0x4000: # Palette RAM
            addr &= 0x1F
            if addr == 0x10 or addr == 0x14 or addr == 0x18 or addr == 0x1C:
                addr -= 0x10
            self.palette_ram[addr] = value

    def step_ppu(self):
        # Visible scanlines and pre-render scanline
        if self.scanline >= -1 and self.scanline < VISIBLE_SCANLINES: # -1 is pre-render
            if self.scanline == -1 and self.cycle == 1: # Pre-render, clear VBlank, Sprite 0, Overflow
                self.ppustatus &= ~(0x80 | 0x40 | 0x20) 
                self.nmi_occurred = False # Not nmi_output, that's for CPU signalling
                self.nmi_output = False

            # TODO: Background rendering, Sprite evaluation & rendering logic per cycle
            # This is highly simplified for now. A real PPU fetches data throughout the scanline.
            pass

        # VBlank period
        if self.scanline == VBLANK_SCANLINE and self.cycle == 1:
            if not self.nmi_occurred: # Set VBlank flag only once per frame
                self.ppustatus |= 0x80 # Set VBlank flag
                if self.ppuctrl & 0x80: # If NMI enabled in PPUCTRL
                    self.nmi_output = True
                self.nmi_occurred = True
                # print(f"VBLANK Started: Scanline {self.scanline}, Cycle {self.cycle}, PPUCTRL: ${self.ppuctrl:02X}")
        
        # Advance PPU cycle and scanline
        self.cycle += 1
        if self.cycle >= PPU_CYCLES_PER_SCANLINE:
            self.cycle = 0
            self.scanline += 1
            if self.scanline >= SCANLINES_PER_FRAME -1 : # -1 because pre-render is -1
                 self.scanline = -1 # Pre-render line for next frame
                 self.frame_count += 1
                 # self.render_full_frame() # Render the visible frame now
                 # If not rendering per scanline, this is where the full frame is "ready"
    
    def render_scanline_pixel(self, x, y):
        # Simplified: Render a single pixel (if background enabled)
        # This would involve fetching nametable, attribute, pattern data
        if not (self.ppumask & 0x08): return # Background not enabled
        
        # Determine which nametable based on PPUCTRL and scroll
        nt_select = self.ppuctrl & 0x03
        # Rough calculation for tile
        tile_col = (x + (self.vram_addr & 0x1F) * 8 + self.fine_x_scroll) // 8 # Simplistic scroll
        tile_row = (y + ((self.vram_addr >> 5) & 0x1F) * 8) // 8 # Simplistic scroll
        
        # Determine nametable address (incorporating PPUCTRL for base nametable)
        base_nt_addr = 0x2000 | (nt_select << 10)
        nametable_offset = (tile_row % 30) * 32 + (tile_col % 32)
        tile_index_addr = base_nt_addr + nametable_offset
        
        tile_index = self.read_ppu_memory(tile_index_addr)

        # Determine attribute table address & palette
        attr_table_addr = base_nt_addr + 0x03C0 + (tile_row // 4) * 8 + (tile_col // 4)
        attr_byte = self.read_ppu_memory(attr_table_addr)
        # Determine which 2x2 tile region this tile is in
        attr_shift = ((tile_row % 4 // 2) << 1) | (tile_col % 4 // 2)
        palette_idx_high_bits = (attr_byte >> (attr_shift * 2)) & 0x03
        
        # Determine pattern table address from PPUCTRL
        bg_pattern_table_addr = 0x1000 if (self.ppuctrl & 0x10) else 0x0000
        tile_addr = bg_pattern_table_addr + tile_index * 16
        
        # Get pixel data from pattern table
        pixel_x_in_tile = (x + self.fine_x_scroll) % 8 # Add fine_x here
        pixel_y_in_tile = y % 8 # This coarse_y needs to be from vram_addr

        # This is where fine_x_scroll would apply to the pixel_x_in_tile
        # And coarse X/Y and fine Y from vram_addr would determine tile_addr and pixel_y_in_tile
        
        plane0 = self.read_ppu_memory(tile_addr + pixel_y_in_tile)
        plane1 = self.read_ppu_memory(tile_addr + pixel_y_in_tile + 8)
        
        color_bit0 = (plane0 >> (7 - pixel_x_in_tile)) & 1
        color_bit1 = (plane1 >> (7 - pixel_x_in_tile)) & 1
        palette_entry_low_bits = (color_bit1 << 1) | color_bit0

        if palette_entry_low_bits == 0: # Background color
            color_val = self.read_ppu_memory(0x3F00)
        else:
            palette_addr = 0x3F01 + (palette_idx_high_bits << 2) + palette_entry_low_bits -1
            color_val = self.read_ppu_memory(palette_addr)
            
        self.framebuffer.set_at((x, y), NES_PALETTE[color_val & 0x3F])


    def render_full_frame(self): # Call this at the end of a PPU frame or per scanline
        if not (self.ppumask & 0x08) and not (self.ppumask & 0x10): # BG and Sprites disabled
            self.framebuffer.fill(NES_PALETTE[self.read_ppu_memory(0x3F00) & 0x3F])
            self.screen.blit(self.framebuffer, (0,0))
            pygame.display.flip()
            return

        # --- Render Background ---
        if self.ppumask & 0x08: # If background enabled
            # This is a simplified full-frame render, not scanline accurate
            # Base nametable from PPUCTRL bits 0-1
            base_nt_x = (self.ppuctrl & 0x01) * 256
            base_nt_y = ((self.ppuctrl >> 1) & 0x01) * 240
            
            # Use vram_addr for scroll (simplified)
            # coarse_x = self.vram_addr & 0x1F
            # coarse_y = (self.vram_addr >> 5) & 0x1F
            # fine_y = (self.vram_addr >> 12) & 0x07
            # nt_select_from_v = (self.vram_addr >> 10) & 0x03

            # Simplified scroll for now, assuming ppuscroll sets something that translates to pixel offsets
            scroll_x = 0 # Would come from vram_addr / fine_x_scroll
            scroll_y = 0 # Would come from vram_addr

            # For full frame render, we iterate through all visible pixels
            for y_pixel in range(VISIBLE_SCANLINES):
                for x_pixel in range(SCREEN_WIDTH):
                    # These calculations need to be based on the PPU's internal v and t registers
                    # and how they update per scanline and per tile.
                    # This is a placeholder for a much more complex process.
                    
                    # Determine current nametable based on scroll and base nametable
                    # Effective X and Y for fetching tile data
                    eff_x = x_pixel + scroll_x # This scroll needs to be more nuanced
                    eff_y = y_pixel + scroll_y

                    # Which nametable are we in?
                    current_nt_idx = (self.ppuctrl & 0x03) # Base
                    if eff_x >= 256: current_nt_idx ^= 0x01 # Horizontal flip for NT
                    if eff_y >= 240: current_nt_idx ^= 0x02 # Vertical flip for NT
                    
                    tile_x_in_nt = (eff_x // 8) % 32
                    tile_y_in_nt = (eff_y // 8) % 30
                    
                    pixel_x_in_tile = eff_x % 8
                    pixel_y_in_tile = eff_y % 8

                    # Nametable address calculation with mirroring
                    nt_base_for_idx = 0x2000 | (current_nt_idx << 10)
                    tile_id_addr = nt_base_for_idx + tile_y_in_nt * 32 + tile_x_in_nt
                    tile_id = self.read_ppu_memory(tile_id_addr)

                    # Attribute table
                    attr_addr = nt_base_for_idx + 0x03C0 + (tile_y_in_nt // 4) * 8 + (tile_x_in_nt // 4)
                    attr_byte = self.read_ppu_memory(attr_addr)
                    attr_quadrant = ((tile_y_in_nt % 4 // 2) << 1) | (tile_x_in_nt % 4 // 2)
                    palette_high_bits = (attr_byte >> (attr_quadrant * 2)) & 0x03
                    
                    # Pattern table
                    pattern_table_base = 0x1000 if (self.ppuctrl & 0x10) else 0x0000
                    tile_pattern_addr = pattern_table_base + tile_id * 16
                    
                    plane0_byte = self.read_ppu_memory(tile_pattern_addr + pixel_y_in_tile)
                    plane1_byte = self.read_ppu_memory(tile_pattern_addr + pixel_y_in_tile + 8)
                    
                    color_bit0 = (plane0_byte >> (7 - pixel_x_in_tile)) & 1
                    color_bit1 = (plane1_byte >> (7 - pixel_x_in_tile)) & 1
                    palette_low_bits = (color_bit1 << 1) | color_bit0
                    
                    final_color_idx = 0
                    if palette_low_bits == 0: # Background color
                        final_color_idx = self.read_ppu_memory(0x3F00)
                    else:
                        palette_num = 0x3F00 + (palette_high_bits << 2)
                        final_color_idx = self.read_ppu_memory(palette_num + palette_low_bits)
                    
                    self.framebuffer.set_at((x_pixel, y_pixel), NES_PALETTE[final_color_idx & 0x3F])
        else: # Background disabled, fill with universal background color
             self.framebuffer.fill(NES_PALETTE[self.read_ppu_memory(0x3F00) & 0x3F])


        # --- Render Sprites (Simplified) ---
        if self.ppumask & 0x10: # If sprites enabled
            sprite_pattern_base = 0x1000 if (self.ppuctrl & 0x08) else 0x0000
            sprite_height = 16 if (self.ppuctrl & 0x20) else 8

            # Iterate OAM backwards for priority (sprite 0 is highest)
            for i in range(255, -1, -4): 
                y_coord = self.oam[i]
                tile_id = self.oam[i+1]
                attributes = self.oam[i+2]
                x_coord = self.oam[i+3]

                if y_coord >= 0xEF : continue # Sprite is off-screen (or invalid)
                y_coord += 1 # Sprite Y is top scanline + 1

                palette_high_bits = attributes & 0x03
                priority = (attributes >> 5) & 1 # 0: In front of BG, 1: Behind BG
                flip_h = (attributes >> 6) & 1
                flip_v = (attributes >> 7) & 1

                # For 8x16 sprites, tile_id LSB ignored for pattern table base, used for top/bottom
                actual_tile_id = tile_id
                if sprite_height == 16:
                    sprite_pattern_base = 0x1000 if (tile_id & 0x01) else 0x0000
                    actual_tile_id &= 0xFE # Use even tile number for top

                for row in range(sprite_height):
                    if y_coord + row >= VISIBLE_SCANLINES : continue

                    tile_row_to_fetch = row
                    if flip_v:
                        tile_row_to_fetch = (sprite_height - 1) - row
                    
                    current_tile_id_in_sprite = actual_tile_id
                    if sprite_height == 16 and row >= 8: # Bottom half of 8x16 sprite
                        current_tile_id_in_sprite += 1
                        tile_row_to_fetch -=8

                    sprite_tile_addr = sprite_pattern_base + current_tile_id_in_sprite * 16
                    plane0_byte = self.read_ppu_memory(sprite_tile_addr + tile_row_to_fetch)
                    plane1_byte = self.read_ppu_memory(sprite_tile_addr + tile_row_to_fetch + 8)

                    for bit in range(8):
                        if x_coord + bit >= SCREEN_WIDTH: continue
                        
                        pixel_col_to_fetch = bit
                        if flip_h:
                            pixel_col_to_fetch = 7 - bit
                        
                        color_bit0 = (plane0_byte >> (7 - pixel_col_to_fetch)) & 1
                        color_bit1 = (plane1_byte >> (7 - pixel_col_to_fetch)) & 1
                        palette_low_bits = (color_bit1 << 1) | color_bit0

                        if palette_low_bits == 0: continue # Transparent

                        # Sprite 0 Hit (very simplified check)
                        if i == 0 and (self.ppumask & 0x08) and (self.ppumask & 0x10): # Sprite 0, BG on, Sprites on
                            if x_coord + bit < 255 and y_coord + row < 239: # On screen
                                # Check if BG pixel is non-transparent
                                # This needs the actual BG pixel color index here.
                                # For now, if sprite 0 pixel is opaque, assume hit if BG also opaque
                                if not (self.ppustatus & 0x40): # If not already set
                                     # This check is too simple. Real hit detection is per-pixel.
                                     self.ppustatus |= 0x40 
                                     # print(f"Sprite 0 Hit at ({x_coord+bit}, {y_coord+row}) (simplified)")


                        # Priority check (simplified)
                        if priority == 1: # Behind background
                            # Get current BG pixel's palette_low_bits
                            # If BG pixel is not color 0 of its palette, sprite pixel is obscured
                            # This is complex; skipping true priority for this simplified render
                            pass
                        
                        palette_num = 0x3F10 + (palette_high_bits << 2)
                        final_color_idx = self.read_ppu_memory(palette_num + palette_low_bits)
                        self.framebuffer.set_at((x_coord + bit, y_coord + row), NES_PALETTE[final_color_idx & 0x3F])

        self.screen.blit(self.framebuffer, (0,0))
        pygame.display.flip()

# --- APU Class (Placeholder) ---
class APU:
    def __init__(self, nes):
        self.nes = nes
        try:
            pygame.mixer.init(frequency=44100, size=-16, channels=1, buffer=512) # Mono for simplicity
            self.channel = pygame.mixer.Channel(0)
            self.sound_enabled = True
            # Basic square wave for testing
            sample_rate = 44100
            duration = 0.02 # Short blip for frame sync
            frequency = 440 # A4
            n_samples = int(round(duration * sample_rate))
            buf = np.zeros((n_samples, 1), dtype=np.int16) # Mono
            max_sample = 2**15 - 1
            for i in range(n_samples):
                t = float(i) / sample_rate
                buf[i][0] = int(round(max_sample * np.sign(np.sin(2 * np.pi * frequency * t))))
            self.test_sound = pygame.sndarray.make_sound(buf)
        except pygame.error as e:
            print(f"Pygame mixer init error: {e}. Sound will be disabled.")
            self.sound_enabled = False

    def reset(self):
        pass # Reset APU state

    def step(self): # Called by CPU potentially
        pass

    def play_frame_sync_sound(self): # Called once per frame
        if self.sound_enabled and not self.channel.get_busy():
            # self.channel.play(self.test_sound) # Can be annoying
            pass

# --- Controller Class ---
class Controller:
    def __init__(self):
        self.buttons = [False] * 8 # A, B, Select, Start, Up, Down, Left, Right
        self.strobe = False
        self.index = 0
        self.key_map = {
            pygame.K_x: 0,      # A
            pygame.K_z: 1,      # B
            pygame.K_RSHIFT: 2, # Select
            pygame.K_RETURN: 3, # Start
            pygame.K_UP: 4,     # Up
            pygame.K_DOWN: 5,   # Down
            pygame.K_LEFT: 6,   # Left
            pygame.K_RIGHT: 7,  # Right
        }

    def update_state(self, events, keys):
        for event in events:
            if event.type == pygame.KEYDOWN:
                if event.key in self.key_map:
                    self.buttons[self.key_map[event.key]] = True
            elif event.type == pygame.KEYUP:
                if event.key in self.key_map:
                    self.buttons[self.key_map[event.key]] = False
        # For held keys (alternative to event based for some buttons)
        # for key_code, index in self.key_map.items():
        #    self.buttons[index] = keys[key_code]


    def write(self, value):
        self.strobe = (value & 1) == 1
        if self.strobe:
            self.index = 0 # Reset button index on strobe

    def read(self):
        if self.index >= 8: return 1 # After all buttons read, returns 1
        
        value = 0x40 # Open bus bit
        if self.buttons[self.index]:
            value |= 0x01
        
        if not self.strobe: # Only advance index if strobe is low
            self.index += 1
        elif self.strobe: # If strobe is high, first button (A) is repeatedly reported
            self.index = 0

        return value

# --- NES Class (Integrator) ---
class NES:
    def __init__(self, rom_data):
        self.rom = ROM(rom_data)
        self.cpu = CPU(self)
        self.ppu = PPU(self)
        self.apu = APU(self)
        self.controller1 = Controller()
        self.controller2 = Controller() # Placeholder for 2nd controller
        
        self.cpu.reset()
        self.ppu.reset()
        self.apu.reset()
        
        self.running = False
        self.paused = False
        self.total_cpu_cycles_this_frame = 0

    def step_frame(self):
        # Approximate NTSC CPU clock: 1.789773 MHz
        # PPU runs 3x faster. Target 60 FPS.
        # CPU cycles per frame = 1789773 / 60 = ~29829.55
        # PPU cycles per frame = CPU cycles * 3 = ~89488.65
        # PPU cycles per scanline = 341. Scanlines = 262. Total = 341 * 262 = 89342.
        # So CPU runs ~29780 cycles per frame.

        self.total_cpu_cycles_this_frame = 0
        target_cpu_cycles_per_frame = 29781 # Target for one frame

        while self.total_cpu_cycles_this_frame < target_cpu_cycles_per_frame:
            cpu_cycles_executed = self.cpu.step() # CPU runs for some cycles
            self.total_cpu_cycles_this_frame += cpu_cycles_executed
            
            # PPU runs 3 cycles for every 1 CPU cycle
            ppu_steps_to_take = cpu_cycles_executed * 3
            for _ in range(ppu_steps_to_take):
                self.ppu.step_ppu()
                if self.ppu.nmi_output:
                    self.cpu.nmi()
                    self.ppu.nmi_output = False # Consume NMI signal
            
            # APU steps (TODO: proper timing)
            # self.apu.step()
        
        self.apu.play_frame_sync_sound() # Once per visual frame

    def run_loop(self):
        pygame_events = pygame.event.get()
        keys_pressed = pygame.key.get_pressed()

        for event in pygame_events:
            if event.type == pygame.QUIT:
                self.running = False
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_q: # Quit
                    self.running = False
                if event.key == pygame.K_p: # Pause
                    self.paused = not self.paused
                if event.key == pygame.K_r: # Reset
                    self.cpu.reset()
                    self.ppu.reset()
                    self.apu.reset()

        if self.paused:
            self.ppu.clock.tick(30) # Keep pygame responsive
            return

        self.controller1.update_state(pygame_events, keys_pressed)
        # self.controller2.update_state(pygame_events, keys_pressed) # If using second controller

        self.step_frame() # Execute one full frame of CPU/PPU emulation
        self.ppu.render_full_frame() # Render the PPU's output to screen

        self.ppu.clock.tick(60) # Target 60 FPS for display

    async def main_async_loop(self):
        self.running = True
        while self.running:
            self.run_loop()
            await asyncio.sleep(0) # Yield for web environment
        pygame.quit()

    def main_sync_loop(self):
        self.running = True
        while self.running:
            self.run_loop()
        pygame.quit()

# --- Sample ROM with a Minimal Program ---
# This ROM will initialize the stack, then loop waiting for VBlank via PPUSTATUS ($2002).
# It also sets up an NMI handler that just does RTI.
# The PPU is expected to show the checkerboard tile (Tile 1) across the screen
# because the PPU's VRAM is initialized to use Tile 1 for the first nametable.

simple_prg_code = bytes([
    0x78,             # SEI         ; Disable interrupts
    0xD8,             # CLD         ; Disable decimal mode
    0xA2, 0xFF,       # LDX #$FF    ; Load FF into X
    0x9A,             # TXS         ; Transfer X to Stack Pointer
    # main_loop:
    0xAD, 0x02, 0x20, # LDA $2002   ; Read PPUSTATUS (to clear VBlank and get status)
    0x29, 0x80,       # AND #$80    ; Check VBlank flag (bit 7)
    0xF0, 0xFA,       # BEQ main_loop (to LDA $2002, FA is -6) ; Wait if VBlank not set
    # VBlank occurred, do something or just loop
    # Example: change palette color 0
    0xA9, 0x17,       # LDA #$17    ; Load a color (e.g., light red)
    0x8D, 0x00, 0x3F, # STA $3F00   ; Store to universal background color
    0x4C, 0x05, 0xC0  # JMP main_loop (to LDA $2002)
]) # $C000 - $C010

nmi_handler_code = bytes([
    # Simple NMI: change palette color 1 to a different color then RTI
    0xA9, 0x28,       # LDA #$28    ; Load another color (e.g., light green)
    0x8D, 0x01, 0x3F, # STA $3F01   ; Store to palette entry 1
    0x40              # RTI
]) # $C100 - $C105

# Create a sample ROM bytearray
SAMPLE_ROM_DATA = bytearray(b"NES\x1a")
SAMPLE_ROM_DATA.append(1)  # PRG ROM banks (16KB)
SAMPLE_ROM_DATA.append(1)  # CHR ROM banks (8KB)
SAMPLE_ROM_DATA.append(0)  # Mapper 0 (NROM), Vertical mirroring
SAMPLE_ROM_DATA.append(0)  # Mapper flags
SAMPLE_ROM_DATA.extend(b'\0' * 8) # Padding

# PRG ROM (16KB)
prg_rom_content = bytearray(16384)
prg_rom_content[0x0000 : len(simple_prg_code)] = simple_prg_code # Code at $C000
prg_rom_content[0x0100 : 0x0100 + len(nmi_handler_code)] = nmi_handler_code # NMI at $C100

# Set Reset Vector ($FFFC) to $C000 (relative to start of the 16KB PRG bank)
# Since our 16KB PRG is mapped to $C000-$FFFF, $FFFC is at offset $3FFC
prg_rom_content[0x3FFC] = 0x00 # Low byte of $C000
prg_rom_content[0x3FFD] = 0xC0 # High byte of $C000
# Set NMI Vector ($FFFA) to $C100
prg_rom_content[0x3FFA] = 0x00 # Low byte of $C100
prg_rom_content[0x3FFB] = 0xC1 # High byte of $C100
# Set IRQ/BRK Vector ($FFFE) to $C000 (for BRK, though not explicitly used by simple_prg)
prg_rom_content[0x3FFE] = 0x00 
prg_rom_content[0x3FFF] = 0xC0 

SAMPLE_ROM_DATA.extend(prg_rom_content)

# CHR ROM (8KB)
chr_rom_content = bytearray(8192)
# Tile 0: All black
chr_rom_content[0:16] = b"\x00" * 16
# Tile 1: Checkerboard pattern
chr_rom_content[16:32] = b"\xAA\x55" * 4 + b"\x55\xAA" * 4 
# Tile 2: Solid white (example)
# For solid white, if palette is 0F (black), 11 (gray), 21 (light gray), 30 (white)
# A pixel value of 3 (binary 11) would pick the 4th color.
# Plane0 = 11111111 (all LSBs are 1) = 0xFF
# Plane1 = 11111111 (all MSBs are 1) = 0xFF
chr_rom_content[32:48] = b"\xFF\xFF" * 8

SAMPLE_ROM_DATA.extend(chr_rom_content)


# --- Main Execution ---
async def main_async():
    print("Starting NES Emulator (Async for Web)...")
    # To load a ROM file:
    # try:
    #     with open("your_rom_file.nes", "rb") as f:
    #         rom_bytes = f.read()
    #     nes = NES(rom_bytes)
    # except FileNotFoundError:
    #     print("ROM file not found. Using sample ROM.")
    #     nes = NES(SAMPLE_ROM_DATA)
    # except ValueError as e:
    #     print(f"Error loading ROM: {e}")
    #     return
    
    nes = NES(SAMPLE_ROM_DATA) # Use the built-in sample for now
    await nes.main_async_loop()

def main_sync():
    print("Starting NES Emulator (Sync)...")
    nes = NES(SAMPLE_ROM_DATA)
    nes.main_sync_loop()

if __name__ == "__main__":
    if platform.system() == "Emscripten": # For Pyodide/WASM environments
        asyncio.ensure_future(main_async())
    else:
        main_sync()
