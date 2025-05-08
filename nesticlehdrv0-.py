import asyncio
import platform
import pygame
import numpy as np
import tkinter as tk
from tkinter import Canvas
from PIL import Image, ImageTk # Needs Pillow: pip install Pillow
import os

# --- Constants ---
SCREEN_WIDTH, SCREEN_HEIGHT = 256, 240
PPU_CYCLES_PER_SCANLINE = 341
SCANLINES_PER_FRAME = 262 # -1 to 260 (Pre-render, Visible, Post-render, VBlank)
VISIBLE_SCANLINES = 240
VBLANK_SCANLINE_START = 241 # Scanline where VBlank flag is set

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
        if self.chr_banks == 0: # CHR RAM
            self.chr_mem = bytearray(8192)
            self.is_chr_ram = True
        else:
            chr_end = chr_start + 8192 * self.chr_banks
            self.chr_mem = self.data[chr_start:chr_end]
            self.is_chr_ram = False
        
        print(f"ROM Loaded: PRG Banks: {self.prg_banks}, CHR Banks: {self.chr_banks}, Mapper: {self.mapper}, Mirroring: {'Horizontal' if self.mirroring else 'Vertical'}")
        if self.is_chr_ram:
            print("Using CHR RAM (8KB)")

# --- CPU Status Flags ---
class StatusFlags:
    C = (1 << 0); Z = (1 << 1); I = (1 << 2); D = (1 << 3)
    B = (1 << 4); U = (1 << 5); V = (1 << 6); N = (1 << 7)

# --- CPU Class (Expanded) ---
class CPU:
    def __init__(self, nes):
        self.nes = nes
        self.ram = bytearray(0x0800)
        self.reset()
        self.opcodes = {
            0x00: ("BRK", self.IMP, self.brk, 7), 0xEA: ("NOP", self.IMP, self.nop, 2),
            0xA9: ("LDA", self.IMM, self.lda, 2), 0xA5: ("LDA", self.ZP0, self.lda, 3),
            0xB5: ("LDA", self.ZPX, self.lda, 4), 0xAD: ("LDA", self.ABS, self.lda, 4),
            0xBD: ("LDA", self.ABX, self.lda, 4), 0xB9: ("LDA", self.ABY, self.lda, 4), 
            0xA1: ("LDA", self.IZX, self.lda, 6), 0xB1: ("LDA", self.IZY, self.lda, 5), 
            0xA2: ("LDX", self.IMM, self.ldx, 2), 0xA6: ("LDX", self.ZP0, self.ldx, 3),
            0xB6: ("LDX", self.ZPY, self.ldx, 4), 0xAE: ("LDX", self.ABS, self.ldx, 4),
            0xBE: ("LDX", self.ABY, self.ldx, 4), 
            0xA0: ("LDY", self.IMM, self.ldy, 2), 0xA4: ("LDY", self.ZP0, self.ldy, 3),
            0xB4: ("LDY", self.ZPX, self.ldy, 4), 0xAC: ("LDY", self.ABS, self.ldy, 4),
            0xBC: ("LDY", self.ABX, self.ldy, 4), 
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
            0x1A: ("NOP*", self.IMP, self.nop, 2), 0x3A: ("NOP*", self.IMP, self.nop, 2),
            0x5A: ("NOP*", self.IMP, self.nop, 2), 0x7A: ("NOP*", self.IMP, self.nop, 2),
            0xDA: ("NOP*", self.IMP, self.nop, 2), 0xFA: ("NOP*", self.IMP, self.nop, 2),
            0x80: ("NOP*", self.IMM, self.nop, 2), 
        }
        self.cycles_remaining = 0; self.total_cycles = 0; self.current_opcode = 0

    def reset(self):
        self.pc = self.read_word(0xFFFC)
        self.sp = 0xFD
        self.acc = 0; self.x = 0; self.y = 0
        self.status = StatusFlags.U | StatusFlags.I 
        self.cycles_remaining = 8; self.total_cycles = 0
        # print(f"CPU Reset: PC set to ${self.pc:04X}")

    def nmi(self):
        self.push_word(self.pc)
        self.push(self.status & ~StatusFlags.B | StatusFlags.U) 
        self.status |= StatusFlags.I 
        self.pc = self.read_word(0xFFFA)
        self.cycles_remaining += 7
        
    def irq(self):
        if not (self.status & StatusFlags.I):
            self.push_word(self.pc)
            self.push(self.status & ~StatusFlags.B | StatusFlags.U) 
            self.status |= StatusFlags.I
            self.pc = self.read_word(0xFFFE)
            self.cycles_remaining += 7

    def set_flag(self, flag, value): self.status = (self.status | flag) if value else (self.status & ~flag)
    def get_flag(self, flag): return bool(self.status & flag)
    def set_zn_flags(self, value):
        self.set_flag(StatusFlags.Z, value == 0)
        self.set_flag(StatusFlags.N, bool(value & 0x80))

    def read(self, addr):
        addr &= 0xFFFF 
        if 0x0000 <= addr < 0x2000: return self.ram[addr % 0x0800]
        elif 0x2000 <= addr < 0x4000: return self.nes.ppu.read_register(addr % 8)
        elif 0x4000 <= addr < 0x4018: 
            if addr == 0x4016: return self.nes.controller1.read()
            elif addr == 0x4017: return self.nes.controller2.read()
            return 0 
        elif 0x4018 <= addr < 0x4020: return 0
        elif 0x4020 <= addr < 0x6000: return 0 
        elif 0x6000 <= addr < 0x8000: return 0 # SRAM/PRG-RAM placeholder
        elif 0x8000 <= addr <= 0xFFFF: 
            if self.nes.rom.prg_banks == 1: # 16KB ROM
                return self.nes.rom.prg_rom[(addr - 0x8000) % 0x4000] 
            else: # 32KB ROM (or more, but NROM typically max 32KB)
                return self.nes.rom.prg_rom[addr - 0x8000] 
        return 0 

    def write(self, addr, value):
        addr &= 0xFFFF; value &= 0xFF
        if 0x0000 <= addr < 0x2000: self.ram[addr % 0x0800] = value
        elif 0x2000 <= addr < 0x4000: self.nes.ppu.write_register(addr % 8, value)
        elif 0x4000 <= addr < 0x4018: 
            if addr == 0x4014: self.nes.ppu.oam_dma(value)
            elif addr == 0x4016: 
                self.nes.controller1.write(value)
                self.nes.controller2.write(value)
        elif 0x6000 <= addr < 0x8000: pass 
        elif 0x8000 <= addr <= 0xFFFF: pass 

    def read_word(self, addr): return self.read(addr) | (self.read(addr + 1) << 8)
    def read_word_bug(self, addr): 
        low = self.read(addr)
        high_addr = (addr & 0xFF00) | ((addr + 1) & 0x00FF)
        high = self.read(high_addr)
        return (high << 8) | low

    def push(self, value): self.write(0x0100 + self.sp, value); self.sp = (self.sp - 1) & 0xFF
    def pop(self): self.sp = (self.sp + 1) & 0xFF; return self.read(0x0100 + self.sp)
    def push_word(self, value): self.push(value >> 8); self.push(value & 0xFF)       
    def pop_word(self): return self.pop() | (self.pop() << 8)
    
    def IMM(self): self.pc += 1; return self.pc - 1, False 
    def ZP0(self): self.pc += 1; return self.read(self.pc -1) & 0xFF, False
    def ZPX(self): self.pc += 1; return (self.read(self.pc -1) + self.x) & 0xFF, False
    def ZPY(self): self.pc += 1; return (self.read(self.pc -1) + self.y) & 0xFF, False 
    def ABS(self): self.pc += 2; return self.read_word(self.pc - 2), False
    def ABX(self): self.pc += 2; base = self.read_word(self.pc-2); eff = (base + self.x)&0xFFFF; return eff, (base&0xFF00)!=(eff&0xFF00)
    def ABY(self): self.pc += 2; base = self.read_word(self.pc-2); eff = (base + self.y)&0xFFFF; return eff, (base&0xFF00)!=(eff&0xFF00)
    def IZX(self): self.pc += 1; zp = (self.read(self.pc-1) + self.x)&0xFF; return self.read_word_bug(zp), False
    def IZY(self): self.pc += 1; zp = self.read(self.pc-1); base = self.read_word_bug(zp); eff = (base+self.y)&0xFFFF; return eff, (base&0xFF00)!=(eff&0xFF00)
    def IMP(self): return 0, False 
    def REL(self): self.pc += 1; off = self.read(self.pc-1); return (self.pc + (off - 0x100 if off & 0x80 else off))&0xFFFF, False
    def ACC(self): return 0, False 
    def ABS_JMP(self): self.pc +=2; return self.read_word(self.pc - 2), False 
    def IND_JMP(self): self.pc +=2; return self.read_word_bug(self.read_word(self.pc-2)), False 

    def _fetch_operand_value(self, addr_mode_func, addr):
        return self.acc if addr_mode_func == self.ACC else self.read(addr)

    def lda(self, addr, pc): val = self._fetch_operand_value(self.opcodes[self.current_opcode][1], addr); self.acc=val; self.set_zn_flags(val); return 1 if pc and self.opcodes[self.current_opcode][1] in [self.ABX,self.ABY,self.IZY] else 0
    def ldx(self, addr, pc): val = self._fetch_operand_value(self.opcodes[self.current_opcode][1], addr); self.x=val; self.set_zn_flags(val); return 1 if pc and self.opcodes[self.current_opcode][1] == self.ABY else 0 
    def ldy(self, addr, pc): val = self._fetch_operand_value(self.opcodes[self.current_opcode][1], addr); self.y=val; self.set_zn_flags(val); return 1 if pc and self.opcodes[self.current_opcode][1] == self.ABX else 0 
    def sta(self, addr, pc): self.write(addr, self.acc); return 0
    def stx(self, addr, pc): self.write(addr, self.x); return 0
    def sty(self, addr, pc): self.write(addr, self.y); return 0
    def tax(self, addr, pc): self.x=self.acc; self.set_zn_flags(self.x); return 0
    def tay(self, addr, pc): self.y=self.acc; self.set_zn_flags(self.y); return 0
    def tsx(self, addr, pc): self.x=self.sp; self.set_zn_flags(self.x); return 0
    def txa(self, addr, pc): self.acc=self.x; self.set_zn_flags(self.acc); return 0
    def txs(self, addr, pc): self.sp=self.x; return 0 
    def tya(self, addr, pc): self.acc=self.y; self.set_zn_flags(self.acc); return 0
    def pha(self, addr, pc): self.push(self.acc); return 0
    def pla(self, addr, pc): self.acc=self.pop(); self.set_zn_flags(self.acc); return 0
    def php(self, addr, pc): self.push(self.status | StatusFlags.B | StatusFlags.U); return 0 
    def plp(self, addr, pc): self.status = (self.pop() & ~StatusFlags.B & ~StatusFlags.U) | StatusFlags.U; return 0
    def _branch(self, cond, addr): add=0; if cond: add=1; if (self.pc&0xFF00)!=(addr&0xFF00): add+=1; self.pc=addr; return add
    def bpl(self, addr, pc): return self._branch(not self.get_flag(StatusFlags.N), addr)
    def bmi(self, addr, pc): return self._branch(self.get_flag(StatusFlags.N), addr)
    def bvc(self, addr, pc): return self._branch(not self.get_flag(StatusFlags.V), addr)
    def bvs(self, addr, pc): return self._branch(self.get_flag(StatusFlags.V), addr)
    def bcc(self, addr, pc): return self._branch(not self.get_flag(StatusFlags.C), addr)
    def bcs(self, addr, pc): return self._branch(self.get_flag(StatusFlags.C), addr)
    def bne(self, addr, pc): return self._branch(not self.get_flag(StatusFlags.Z), addr)
    def beq(self, addr, pc): return self._branch(self.get_flag(StatusFlags.Z), addr)
    def bit(self, addr, pc): val=self.read(addr); self.set_flag(StatusFlags.Z,(self.acc&val)==0); self.set_flag(StatusFlags.N,val&0x80); self.set_flag(StatusFlags.V,val&0x40); return 0
    def _compare(self, reg, mem): res=reg-mem; self.set_flag(StatusFlags.C,res>=0); self.set_zn_flags(res&0xFF)
    def cmp(self, addr, pc): self._compare(self.acc, self.read(addr)); return 1 if pc and self.opcodes[self.current_opcode][1] in [self.ABX,self.ABY,self.IZY] else 0
    def cpx(self, addr, pc): self._compare(self.x, self.read(addr)); return 0 
    def cpy(self, addr, pc): self._compare(self.y, self.read(addr)); return 0
    def _logical(self, op, addr, pc): val=self.read(addr); self.acc=op(self.acc,val)&0xFF; self.set_zn_flags(self.acc); return 1 if pc and self.opcodes[self.current_opcode][1] in [self.ABX,self.ABY,self.IZY] else 0
    def and_op(self, addr, pc): return self._logical(lambda a,b:a&b, addr, pc)
    def eor_op(self, addr, pc): return self._logical(lambda a,b:a^b, addr, pc)
    def ora_op(self, addr, pc): return self._logical(lambda a,b:a|b, addr, pc)
    def inc(self, addr, pc): val=(self.read(addr)+1)&0xFF; self.write(addr,val); self.set_zn_flags(val); return 0
    def dec(self, addr, pc): val=(self.read(addr)-1)&0xFF; self.write(addr,val); self.set_zn_flags(val); return 0
    def inx(self, addr, pc): self.x=(self.x+1)&0xFF; self.set_zn_flags(self.x); return 0
    def dex(self, addr, pc): self.x=(self.x-1)&0xFF; self.set_zn_flags(self.x); return 0
    def iny(self, addr, pc): self.y=(self.y+1)&0xFF; self.set_zn_flags(self.y); return 0
    def dey(self, addr, pc): self.y=(self.y-1)&0xFF; self.set_zn_flags(self.y); return 0
    def _asl(self,v): self.set_flag(StatusFlags.C,v&0x80); return (v<<1)&0xFF
    def _lsr(self,v): self.set_flag(StatusFlags.C,v&0x01); return v>>1
    def _rol(self,v): c=self.get_flag(StatusFlags.C); self.set_flag(StatusFlags.C,v&0x80); return ((v<<1)|c)&0xFF
    def _ror(self,v): c=self.get_flag(StatusFlags.C); self.set_flag(StatusFlags.C,v&0x01); return ((v>>1)|(c<<7))&0xFF
    def _shift_acc(self, op): self.acc=op(self.acc); self.set_zn_flags(self.acc); return 0
    def _shift_mem(self, op, addr): val=self.read(addr); res=op(val); self.write(addr,res); self.set_zn_flags(res); return 0
    def asl_acc(self, addr, pc): return self._shift_acc(self._asl)
    def asl_mem(self, addr, pc): return self._shift_mem(self._asl, addr)
    def lsr_acc(self, addr, pc): return self._shift_acc(self._lsr)
    def lsr_mem(self, addr, pc): return self._shift_mem(self._lsr, addr)
    def rol_acc(self, addr, pc): return self._shift_acc(self._rol)
    def rol_mem(self, addr, pc): return self._shift_mem(self._rol, addr)
    def ror_acc(self, addr, pc): return self._shift_acc(self._ror)
    def ror_mem(self, addr, pc): return self._shift_mem(self._ror, addr)
    def jmp(self, addr, pc): self.pc=addr; return 0
    def jsr(self, addr, pc): self.push_word(self.pc-1); self.pc=addr; return 0 
    def rts(self, addr, pc): self.pc=(self.pop_word()+1)&0xFFFF; return 0
    def rti(self, addr, pc): self.status=(self.pop()&~StatusFlags.B&~StatusFlags.U)|StatusFlags.U; self.pc=self.pop_word(); return 0
    def brk(self, addr, pc): self.pc+=1; self.push_word(self.pc); self.push(self.status|StatusFlags.B|StatusFlags.U); self.status|=StatusFlags.I; self.pc=self.read_word(0xFFFE); return 0
    def nop(self, addr, pc): return 0 
    def clc(self, addr, pc): self.set_flag(StatusFlags.C,0); return 0; def sec(self, addr, pc): self.set_flag(StatusFlags.C,1); return 0
    def cli(self, addr, pc): self.set_flag(StatusFlags.I,0); return 0; def sei(self, addr, pc): self.set_flag(StatusFlags.I,1); return 0
    def clv(self, addr, pc): self.set_flag(StatusFlags.V,0); return 0; def cld(self, addr, pc): self.set_flag(StatusFlags.D,0); return 0 
    def sed(self, addr, pc): self.set_flag(StatusFlags.D,1); return 0 

    def step(self):
        if self.cycles_remaining > 0:
            self.cycles_remaining -= 1
            return 1
        self.current_opcode = self.read(self.pc)
        self.pc = (self.pc + 1) & 0xFFFF
        op_info = self.opcodes.get(self.current_opcode)
        if not op_info:
            print(f"Unknown opcode: ${self.current_opcode:02X} at PC: ${self.pc-1:04X}")
            self.cycles_remaining = 1 
            return 1 
        op_name, addr_mode_func, op_func, base_cycles = op_info
        eff_addr, page_crossed = addr_mode_func()
        add_cycles = op_func(eff_addr, page_crossed) 
        total_op_cycles = base_cycles + add_cycles
        self.cycles_remaining = total_op_cycles -1 
        self.total_cycles += total_op_cycles
        return total_op_cycles

# --- PPU Class (Significantly Revised for Tkinter) ---
class PPU:
    def __init__(self, nes):
        self.nes = nes
        if not pygame.get_init(): pygame.init()
        self.framebuffer = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT)).convert()
        self.vram = bytearray(0x0800); self.palette_ram = bytearray(0x20)
        self.oam = bytearray(0x100); self.secondary_oam = bytearray(32)
        self.ppuctrl=0; self.ppumask=0; self.ppustatus=0; self.oamaddr=0
        self.vram_addr_v=0; self.temp_vram_addr_t=0; self.fine_x_scroll=0; self.addr_latch_w=False
        self.data_buffer=0; self.scanline=-1; self.cycle=0; self.frame_count=0
        self.nmi_occurred_this_frame=False; self.nmi_output=False
        self.bg_nt_latch=0; self.bg_at_latch=0; self.bg_pattern_lo_latch=0; self.bg_pattern_hi_latch=0
        self.bg_shifter_pattern_lo=0; self.bg_shifter_pattern_hi=0
        self.bg_shifter_attrib_lo=0; self.bg_shifter_attrib_hi=0
        self.sprite_count_scanline=0; self.sprite_shifter_pattern_lo=[0]*8
        self.sprite_shifter_pattern_hi=[0]*8; self.sprite_attributes=[0]*8
        self.sprite_x_counters=[0]*8; self.sprite_zero_hit_possible=False
        self.sprite_zero_being_rendered=False
        self.reset()

    def reset(self):
        self.ppuctrl=0; self.ppumask=0; self.ppustatus=StatusFlags.U; self.oamaddr=0
        self.vram_addr_v=0; self.temp_vram_addr_t=0; self.fine_x_scroll=0; self.addr_latch_w=False
        self.data_buffer=0; self.scanline=-1; self.cycle=0
        self.nmi_occurred_this_frame=False; self.nmi_output=False
        self.bg_nt_latch=0; self.bg_at_latch=0; self.bg_pattern_lo_latch=0; self.bg_pattern_hi_latch=0
        self.bg_shifter_pattern_lo=0; self.bg_shifter_pattern_hi=0
        self.bg_shifter_attrib_lo=0; self.bg_shifter_attrib_hi=0
        self.framebuffer.fill(NES_PALETTE[0x0D])

    def is_rendering_enabled(self): return (self.ppumask & 0x08) or (self.ppumask & 0x10)

    def oam_dma(self, page_addr):
        start_addr=page_addr<<8
        for i in range(256): self.oam[(self.oamaddr+i)&0xFF]=self.nes.cpu.read(start_addr+i)
        self.nes.cpu.cycles_remaining += 513 + (self.nes.cpu.total_cycles % 2)

    def read_register(self, reg_idx):
        val = 0
        if reg_idx == 2: # PPUSTATUS
            val = (self.ppustatus & 0xE0) | (self.data_buffer & 0x1F) 
            self.ppustatus &= ~0x80 
            self.addr_latch_w = False
            if self.scanline == VBLANK_SCANLINE_START and self.cycle <= 3: 
                 self.nmi_output = False 
        elif reg_idx == 4: val = self.oam[self.oamaddr] 
        elif reg_idx == 7: # PPUDATA
            val = self.data_buffer 
            self.data_buffer = self.read_ppu_memory(self.vram_addr_v) 
            if self.vram_addr_v >= 0x3F00: 
                 idx = self.vram_addr_v & 0x1F
                 if idx==0x10 or idx==0x14 or idx==0x18 or idx==0x1C: idx-=0x10
                 val = self.palette_ram[idx]
                 if self.ppumask & 0x01: val &= 0x30 
            inc = 32 if (self.ppuctrl & 0x04) else 1
            self.vram_addr_v = (self.vram_addr_v + inc) & 0x7FFF
        return val

    def write_register(self, reg_idx, value):
        self.data_buffer = value
        if reg_idx == 0: # PPUCTRL
            old_nmi = (self.ppuctrl & 0x80)
            self.ppuctrl = value
            self.temp_vram_addr_t = (self.temp_vram_addr_t & 0xF3FF) | ((value & 0x03) << 10)
            if not old_nmi and (value&0x80) and (self.ppustatus&0x80) and not self.nmi_occurred_this_frame: self.nmi_output=True
        elif reg_idx == 1: self.ppumask = value 
        elif reg_idx == 3: self.oamaddr = value 
        elif reg_idx == 4: self.oam[self.oamaddr] = value; self.oamaddr=(self.oamaddr+1)&0xFF 
        elif reg_idx == 5: # PPUSCROLL
            if not self.addr_latch_w:
                self.temp_vram_addr_t = (self.temp_vram_addr_t & 0xFFE0) | (value >> 3)
                self.fine_x_scroll = value & 0x07
            else:
                self.temp_vram_addr_t = (self.temp_vram_addr_t & 0x8C1F) | ((value & 0xF8) << 2)
                self.temp_vram_addr_t = (self.temp_vram_addr_t & 0xF3FF) | ((value & 0x07) << 12)
            self.addr_latch_w = not self.addr_latch_w
        elif reg_idx == 6: # PPUADDR
            if not self.addr_latch_w: self.temp_vram_addr_t = (self.temp_vram_addr_t & 0x00FF) | ((value & 0x3F) << 8)
            else: self.temp_vram_addr_t = (self.temp_vram_addr_t & 0xFF00) | value; self.vram_addr_v = self.temp_vram_addr_t
            self.addr_latch_w = not self.addr_latch_w
        elif reg_idx == 7: # PPUDATA
            self.write_ppu_memory(self.vram_addr_v, value)
            inc = 32 if (self.ppuctrl & 0x04) else 1
            self.vram_addr_v = (self.vram_addr_v + inc) & 0x7FFF
            
    def _get_physical_vram_index(self, ppu_addr): 
        m = self.nes.rom.mirroring 
        if m == 1: return (ppu_addr&0x3FF) + (0x400 if ppu_addr&0x400 else 0) 
        else: return (ppu_addr&0x3FF) + (0x400 if ppu_addr&0x800 else 0)       

    def read_ppu_memory(self, addr):
        addr &= 0x3FFF
        if addr >= 0x3000 and addr <= 0x3EFF: addr -= 0x1000 
        if addr < 0x2000: return self.nes.rom.chr_mem[addr]
        elif addr < 0x3F00: return self.vram[self._get_physical_vram_index(addr)]
        elif addr < 0x4000:
            idx = addr & 0x1F
            if idx==0x10 or idx==0x14 or idx==0x18 or idx==0x1C: idx -= 0x10
            val = self.palette_ram[idx]
            if self.ppumask & 0x01: val &= 0x30 
            return val
        return 0

    def write_ppu_memory(self, addr, value):
        addr &= 0x3FFF; value &= 0xFF
        if addr >= 0x3000 and addr <= 0x3EFF: addr -= 0x1000
        if addr < 0x2000: 
            if self.nes.rom.is_chr_ram: self.nes.rom.chr_mem[addr] = value
        elif addr < 0x3F00: self.vram[self._get_physical_vram_index(addr)] = value
        elif addr < 0x4000:
            idx = addr & 0x1F
            if idx==0x10 or idx==0x14 or idx==0x18 or idx==0x1C: idx -= 0x10
            self.palette_ram[idx] = value

    def _increment_scroll_x(self):
        if not self.is_rendering_enabled(): return
        if (self.vram_addr_v & 0x001F) == 31: self.vram_addr_v &= ~0x001F; self.vram_addr_v ^= 0x0400
        else: self.vram_addr_v += 1
    def _increment_scroll_y(self):
        if not self.is_rendering_enabled(): return
        if (self.vram_addr_v & 0x7000) != 0x7000: self.vram_addr_v += 0x1000
        else:
            self.vram_addr_v &= ~0x7000
            y = (self.vram_addr_v & 0x03E0) >> 5
            if y == 29: y = 0; self.vram_addr_v ^= 0x0800
            elif y == 31: y = 0
            else: y += 1
            self.vram_addr_v = (self.vram_addr_v & ~0x03E0) | (y << 5)
    def _transfer_address_x(self):
        if not self.is_rendering_enabled(): return
        self.vram_addr_v = (self.vram_addr_v & 0xFBE0) | (self.temp_vram_addr_t & 0x041F)
    def _transfer_address_y(self):
        if not self.is_rendering_enabled(): return
        self.vram_addr_v = (self.vram_addr_v & 0x841F) | (self.temp_vram_addr_t & 0x7BE0)
    def _load_background_shifters(self):
        self.bg_shifter_pattern_lo = (self.bg_shifter_pattern_lo & 0xFF00) | self.bg_pattern_lo_latch
        self.bg_shifter_pattern_hi = (self.bg_shifter_pattern_hi & 0xFF00) | self.bg_pattern_hi_latch
        at_sel = (0xFF if (self.bg_at_latch & 0x01) else 0x00)
        self.bg_shifter_attrib_lo = (self.bg_shifter_attrib_lo & 0xFF00) | at_sel
        at_sel = (0xFF if (self.bg_at_latch & 0x02) else 0x00)
        self.bg_shifter_attrib_hi = (self.bg_shifter_attrib_hi & 0xFF00) | at_sel
    def _update_shifters(self):
        if self.ppumask & 0x08: 
            self.bg_shifter_pattern_lo <<= 1; self.bg_shifter_pattern_hi <<= 1
            self.bg_shifter_attrib_lo <<= 1;  self.bg_shifter_attrib_hi <<= 1
        if self.ppumask & 0x10 and 1 <= self.cycle < 258: 
            for i in range(self.sprite_count_scanline):
                if self.sprite_x_counters[i] > 0: self.sprite_x_counters[i] -=1
                else: self.sprite_shifter_pattern_lo[i] <<=1; self.sprite_shifter_pattern_hi[i] <<=1

    def step_ppu(self):
        if self.scanline == -1: 
            if self.cycle == 1:
                self.ppustatus &= ~(StatusFlags.V | StatusFlags.B | 0x20) 
                self.nmi_occurred_this_frame = False; self.nmi_output = False
                for i in range(8): self.sprite_shifter_pattern_lo[i]=0; self.sprite_shifter_pattern_hi[i]=0
            if 280 <= self.cycle <= 304 and self.is_rendering_enabled(): self._transfer_address_y()

        if -1 <= self.scanline < VISIBLE_SCANLINES: 
            if self.cycle == 257 and self.is_rendering_enabled(): 
                self._evaluate_sprites_for_scanline(self.scanline + 1)
            
            if self.is_rendering_enabled():
                if (2 <= self.cycle < 258) or (322 <= self.cycle < 338): 
                    self._update_shifters()
                    fc_phase = (self.cycle -1) % 8
                    if fc_phase == 0: 
                        self._load_background_shifters()
                        self.bg_nt_latch = self.read_ppu_memory(0x2000 | (self.vram_addr_v & 0x0FFF))
                    elif fc_phase == 2: 
                        at_addr = 0x23C0 | (self.vram_addr_v&0x0C00) | (((self.vram_addr_v>>4)&0x38)) | (((self.vram_addr_v>>2)&0x07))
                        attr = self.read_ppu_memory(at_addr)
                        shift = ((self.vram_addr_v>>4)&4) | ((self.vram_addr_v>>2)&2) 
                        self.bg_at_latch = (attr >> shift) & 0x03
                    elif fc_phase == 4: 
                        pt_base = 0x1000 if (self.ppuctrl&0x10) else 0
                        fine_y = (self.vram_addr_v>>12)&7
                        self.bg_pattern_lo_latch = self.read_ppu_memory(pt_base + self.bg_nt_latch*16 + fine_y)
                    elif fc_phase == 6: 
                        pt_base = 0x1000 if (self.ppuctrl&0x10) else 0
                        fine_y = (self.vram_addr_v>>12)&7
                        self.bg_pattern_hi_latch = self.read_ppu_memory(pt_base + self.bg_nt_latch*16 + fine_y + 8)
                    elif fc_phase == 7: self._increment_scroll_x() 
                
                if self.cycle == 256 and self.is_rendering_enabled(): self._increment_scroll_y()
                if self.cycle == 257 and self.is_rendering_enabled(): self._transfer_address_x()

        if self.scanline == VBLANK_SCANLINE_START and self.cycle == 1:
            if not self.nmi_occurred_this_frame:
                self.ppustatus |= StatusFlags.V 
                if self.ppuctrl & 0x80: self.nmi_output = True
                self.nmi_occurred_this_frame = True
        
        if 0 <= self.scanline < VISIBLE_SCANLINES and 1 <= self.cycle <= SCREEN_WIDTH: 
            pixel_x = self.cycle - 1
            bg_pixel_color_idx = self.read_ppu_memory(0x3F00) 
            bg_pixel_pattern_val = 0 

            if self.ppumask & 0x08: 
                mux = 0x8000 >> self.fine_x_scroll
                p_low = (self.bg_shifter_pattern_lo & mux) > 0
                p_hi  = (self.bg_shifter_pattern_hi & mux) > 0
                bg_pixel_pattern_val = (p_hi << 1) | p_low
                
                if bg_pixel_pattern_val != 0:
                    attr_low = (self.bg_shifter_attrib_lo & mux) > 0
                    attr_hi  = (self.bg_shifter_attrib_hi & mux) > 0
                    bg_palette_high_bits = (attr_hi << 1) | attr_low
                    palette_addr = 0x3F00 + (bg_palette_high_bits << 2) + bg_pixel_pattern_val
                    bg_pixel_color_idx = self.read_ppu_memory(palette_addr)
            
            final_pixel_color_idx = bg_pixel_color_idx

            if self.sprite_zero_hit_possible and self.sprite_zero_being_rendered and \
               (self.ppumask & 0x08) and (self.ppumask & 0x10) and \
               not (self.ppustatus & 0x40) and \
               pixel_x != 255: 
                
                no_hit_due_to_clipping = False
                if pixel_x < 8:
                    if not (self.ppumask & 0x02): no_hit_due_to_clipping = True 
                    if not (self.ppumask & 0x04): no_hit_due_to_clipping = True 
                
                if not no_hit_due_to_clipping and bg_pixel_pattern_val != 0: 
                    self.ppustatus |= 0x40 
            
            if not (self.ppumask & 0x02) and pixel_x < 8 : 
                 self.framebuffer.set_at((pixel_x, self.scanline), NES_PALETTE[self.read_ppu_memory(0x3F00) & 0x3F])
            else:
                 self.framebuffer.set_at((pixel_x, self.scanline), NES_PALETTE[final_pixel_color_idx & 0x3F])

        self.cycle += 1
        if self.cycle > PPU_CYCLES_PER_SCANLINE -1:
            self.cycle = 0; self.scanline += 1
            if self.scanline > SCANLINES_PER_FRAME - 2:
                 self.scanline = -1; self.frame_count += 1
                 self._render_sprites_overlay() 

    def _evaluate_sprites_for_scanline(self, target_scanline):
        if not (0 <= target_scanline < VISIBLE_SCANLINES):
            self.sprite_count_scanline = 0; return

        self.sprite_count_scanline = 0; self.sprite_zero_hit_possible = False
        sprite_height = 16 if (self.ppuctrl & 0x20) else 8
        for i in range(len(self.secondary_oam)): self.secondary_oam[i] = 0xFF 

        num_found = 0
        for i in range(0, 256, 4): 
            y = self.oam[i] 
            if y >= 0xF0 : continue 

            if y <= target_scanline < y + sprite_height:
                if num_found < 8:
                    for j in range(4): self.secondary_oam[num_found*4+j] = self.oam[i+j]
                    if i == 0: self.sprite_zero_hit_possible = True
                    num_found += 1
                else:
                    self.ppustatus |= 0x20 
                    break
        self.sprite_count_scanline = num_found
        
        self.sprite_zero_being_rendered = False 
        for i in range(self.sprite_count_scanline):
            y_coord    = self.secondary_oam[i*4 + 0]
            tile_id    = self.secondary_oam[i*4 + 1]
            attributes = self.secondary_oam[i*4 + 2]
            x_coord    = self.secondary_oam[i*4 + 3]

            flip_h = (attributes >> 6) & 1; flip_v = (attributes >> 7) & 1
            row_in_sprite = target_scanline - y_coord
            if flip_v: row_in_sprite = (sprite_height - 1) - row_in_sprite

            pt_base_sprites = (0x1000 if (self.ppuctrl & 0x08) else 0) if sprite_height == 8 \
                              else (0x1000 if (tile_id & 0x01) else 0) 
            
            current_tile = tile_id
            if sprite_height == 16:
                current_tile &= 0xFE 
                if row_in_sprite >= 8: current_tile += 1; row_in_sprite -= 8
            
            addr = pt_base_sprites + current_tile * 16 + row_in_sprite
            p_low = self.read_ppu_memory(addr)
            p_hi  = self.read_ppu_memory(addr + 8)

            if flip_h:
                rev = lambda b: int('{:08b}'.format(b)[::-1], 2)
                p_low, p_hi = rev(p_low), rev(p_hi)

            self.sprite_shifter_pattern_lo[i] = p_low
            self.sprite_shifter_pattern_hi[i] = p_hi
            self.sprite_attributes[i] = attributes
            self.sprite_x_counters[i] = x_coord
            if i == 0 and self.sprite_zero_hit_possible : self.sprite_zero_being_rendered = True


    def _render_sprites_overlay(self): 
        if not (self.ppumask & 0x10): return
        sprite_height = 16 if (self.ppuctrl & 0x20) else 8
        
        for i in range(252, -1, -4): 
            y_coord = self.oam[i] 
            tile_id = self.oam[i+1]
            attr = self.oam[i+2]
            x_coord = self.oam[i+3]

            if y_coord >= 0xF0: continue 

            palette_idx_high = attr & 0x03
            priority_behind = (attr >> 5) & 1
            flip_h = (attr >> 6) & 1
            flip_v = (attr >> 7) & 1

            pt_base_sprites = (0x1000 if (self.ppuctrl & 0x08) else 0) 

            for row in range(sprite_height):
                draw_y = y_coord + row
                if not (0 <= draw_y < VISIBLE_SCANLINES): continue

                current_tile = tile_id
                eff_row = row
                final_pt_base = pt_base_sprites

                if sprite_height == 16:
                    final_pt_base = 0x1000 if (tile_id & 0x01) else 0 
                    current_tile &= 0xFE 
                    if flip_v: eff_row = (sprite_height - 1) - row 
                    if eff_row >= 8: current_tile += 1; eff_row -= 8 
                elif flip_v: eff_row = (sprite_height - 1) - row 

                addr = final_pt_base + current_tile * 16 + eff_row
                p_low = self.read_ppu_memory(addr)
                p_hi  = self.read_ppu_memory(addr + 8)

                for bit_idx in range(8):
                    draw_x = x_coord + bit_idx
                    if not (0 <= draw_x < SCREEN_WIDTH): continue
                    if not (self.ppumask & 0x04) and draw_x < 8: continue 

                    eff_bit = bit_idx
                    if flip_h: eff_bit = 7 - bit_idx
                    
                    color_bit0 = (p_low >> (7 - eff_bit)) & 1
                    color_bit1 = (p_hi >> (7 - eff_bit)) & 1
                    palette_idx_low = (color_bit1 << 1) | color_bit0

                    if palette_idx_low == 0: continue 

                    if priority_behind:
                        bg_color_tuple = self.framebuffer.get_at((draw_x, draw_y))[:3]
                        univ_bg_idx = self.read_ppu_memory(0x3F00) & 0x3F
                        if bg_color_tuple != NES_PALETTE[univ_bg_idx]: continue 

                    final_idx = self.read_ppu_memory(0x3F10 + (palette_idx_high<<2) + palette_idx_low)
                    self.framebuffer.set_at((draw_x, draw_y), NES_PALETTE[final_idx & 0x3F])

# --- APU Class (Placeholder) ---
class APU:
    def __init__(self, nes):
        self.nes = nes; self.sound_enabled = False; self.channel = None; self.test_sound = None
        try:
            if not pygame.mixer.get_init(): pygame.mixer.init(44100, -16, 1, 512)
            self.channel = pygame.mixer.Channel(0)
            self.sound_enabled = True
            sr, dur, freq = 44100, 0.02, 440
            samples = int(sr*dur)
            buf = np.array([np.sign(np.sin(2*np.pi*freq*t/sr)) for t in range(samples)], dtype=np.int16) * (2**15-1)
            self.test_sound = pygame.sndarray.make_sound(buf.reshape(samples,1))
        except pygame.error as e: print(f"Mixer init error: {e}. Sound disabled.")
    def reset(self): pass
    def step(self): pass
    def play_frame_sync_sound(self):
        if self.sound_enabled and self.channel and self.test_sound and not self.channel.get_busy():
            pass

# --- Controller Class ---
class Controller:
    def __init__(self):
        self.buttons = [False]*8; self.strobe=False; self.index=0
        self.key_map = {
            pygame.K_x:0, pygame.K_z:1, pygame.K_RSHIFT:2, pygame.K_RETURN:3,
            pygame.K_UP:4, pygame.K_DOWN:5, pygame.K_LEFT:6, pygame.K_RIGHT:7
        }
    def update_state(self, events, keys_pressed):
        for event in events:
            if event.type == pygame.KEYDOWN and event.key in self.key_map: self.buttons[self.key_map[event.key]] = True
            elif event.type == pygame.KEYUP and event.key in self.key_map: self.buttons[self.key_map[event.key]] = False
        for key,idx in self.key_map.items(): 
            if keys_pressed[key]: self.buttons[idx] = True
    def write(self, value): self.strobe=(value&1)==1;  (self.index:=0) if self.strobe else None
    def read(self):
        if self.strobe: self.index=0 
        if self.index >= 8: return 0x01 
        val = 0x01 if self.buttons[self.index] else 0x00
        if not self.strobe: self.index += 1
        return val 

# --- NES Class (Integrator, simplified for Tkinter) ---
class NES:
    def __init__(self, rom_data):
        self.rom = ROM(rom_data)
        self.cpu = CPU(self)
        self.ppu = PPU(self)
        self.apu = APU(self)
        self.controller1 = Controller(); self.controller2 = Controller()
        self.cpu.reset(); self.ppu.reset(); self.apu.reset()
        self.running = False; self.paused = False; self.total_cpu_cycles_this_frame = 0

    def step_frame(self):
        self.total_cpu_cycles_this_frame = 0
        target_cycles = 29781 
        
        while self.total_cpu_cycles_this_frame < target_cycles:
            if self.ppu.nmi_output:
                self.ppu.nmi_output = False 
                self.cpu.nmi()
            
            cpu_cycles = self.cpu.step()
            self.total_cpu_cycles_this_frame += cpu_cycles
            for _ in range(cpu_cycles * 3): self.ppu.step_ppu()
        
        self.apu.play_frame_sync_sound()

# --- EmulatorGUI Class for Tkinter ---
class EmulatorGUI:
    def __init__(self, nes_instance):
        self.nes = nes_instance; self.ppu = nes_instance.ppu
        self.root = tk.Tk(); self.root.title("NES Emulator - CATSDK Purrfection (Tkinter)")
        self.tk_win_w, self.tk_win_h = 600, 400
        self.root.geometry(f"{self.tk_win_w}x{self.tk_win_h}")

        sf_w = (self.tk_win_w - 20) // SCREEN_WIDTH
        sf_h = (self.tk_win_h - 70) // SCREEN_HEIGHT 
        self.scale = max(1, min(sf_w, sf_h))
        self.cnv_w, self.cnv_h = SCREEN_WIDTH*self.scale, SCREEN_HEIGHT*self.scale
        
        cf = tk.Frame(self.root); cf.pack(pady=10, expand=True) 
        self.canvas = Canvas(cf, width=self.cnv_w, height=self.cnv_h, bg="black")
        self.canvas.pack()
        self.photo_image = None 

        ctrl_f = tk.Frame(self.root); ctrl_f.pack(pady=10)
        self.pause_btn = tk.Button(ctrl_f, text="Pause", command=self.toggle_pause, width=10)
        self.pause_btn.pack(side=tk.LEFT,padx=5)
        tk.Button(ctrl_f, text="Reset", command=self.reset_nes, width=10).pack(side=tk.LEFT,padx=5)
        tk.Button(ctrl_f, text="Quit", command=self.on_closing, width=10).pack(side=tk.LEFT,padx=5)
        
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        self.root.bind_all("<KeyPress-p>", lambda e: self.toggle_pause())
        self.root.bind_all("<KeyPress-r>", lambda e: self.reset_nes())

    def toggle_pause(self):
        self.nes.paused = not self.nes.paused
        self.pause_btn.config(text="Resume" if self.nes.paused else "Pause")
        print(f"Emulator {'Paused' if self.nes.paused else 'Resumed'}")
    def reset_nes(self):
        print("Resetting NES..."); self.nes.cpu.reset(); self.nes.ppu.reset(); self.nes.apu.reset()
        self.nes.ppu.frame_count = 0 
        if self.nes.paused: self.toggle_pause()
    def on_closing(self): print("Closing..."); self.nes.running=False; self.root.destroy()
    def update_display(self):
        frame = self.ppu.framebuffer
        img_surf = pygame.transform.scale(frame, (self.cnv_w, self.cnv_h)) if self.scale!=1 else frame
        try:
            img_data = pygame.image.tostring(img_surf, "RGB")
            img = Image.frombytes("RGB", (self.cnv_w, self.cnv_h), img_data)
            self.photo_image = ImageTk.PhotoImage(image=img)
            self.canvas.create_image(0,0,image=self.photo_image,anchor=tk.NW)
        except Exception as e: print(f"Display error: {e}"); self.nes.running=False
    def game_loop(self):
        if not self.nes.running: return
        pygame_events = pygame.event.get(); keys = pygame.key.get_pressed()
        for e in pygame_events: 
            if e.type == pygame.QUIT: self.on_closing(); return
        if not self.nes.paused:
            self.nes.controller1.update_state(pygame_events, keys)
            self.nes.step_frame()
        self.update_display()
        self.root.after(16, self.game_loop) 
    def start(self): self.nes.running=True; self.game_loop(); self.root.mainloop()

# --- Sample ROM Data (Patched) ---
base_addr = 0xC000
simple_prg_code_orig = bytes([
    0x78,0xD8,0xA2,0xFF,0x9A,0xA9,0x90,0x8D,0x00,0x20,0xA9,0x1E,0x8D,0x01,0x20, 
    0xAD,0x02,0x20,0x29,0x80,0xF0,0xFA, 
    0xAD,0x02,0x20,0x29,0x80,0xF0,0xFA, 
    0xAD,0x16,0x40,0x29,0x01, 
    0xF0,0x00, 
    0xA9,0x16,0x8D,0x00,0x3F, 
    0x4C,0x00,0x00, 
    0xA9,0x12,0x8D,0x00,0x3F, 
    0x4C,0x00,0x00  
])
simple_prg_list = list(simple_prg_code_orig)
simple_prg_list[34+1] = 0x08
jmp_target1 = base_addr + 49
simple_prg_list[41+1] = jmp_target1 & 0xFF; simple_prg_list[41+2] = jmp_target1 >> 8
jmp_target2 = base_addr + 22
simple_prg_list[49+1] = jmp_target2 & 0xFF; simple_prg_list[49+2] = jmp_target2 >> 8
simple_prg_code = bytes(simple_prg_list)

nmi_handler_code = bytes([0xA9,0x28,0x8D,0x01,0x3F,0x40]) 
SAMPLE_ROM_DATA = bytearray(b"NES\x1a\x01\x01\x00\x00"+b'\0'*8)
prg = bytearray([0xEA]*16384)
prg[0:len(simple_prg_code)] = simple_prg_code
prg[0x100:0x100+len(nmi_handler_code)] = nmi_handler_code
prg[0x3FFC:0x3FFE] = (base_addr&0xFF, base_addr>>8) 
prg[0x3FFA:0x3FFC] = ((base_addr+0x100)&0xFF, (base_addr+0x100)>>8) 
prg[0x3FFE:0x4000] = (base_addr&0xFF, base_addr>>8) 
SAMPLE_ROM_DATA.extend(prg)
chr_data = bytearray([0]*8192); 
chr_data[16:24]=b'\xAA'*8; chr_data[24:32]=b'\x55'*8 
chr_data[32:48]=b'\xFF'*16 
SAMPLE_ROM_DATA.extend(chr_data)

# --- Main Execution ---
def main_tkinter():
    print("Starting NES Emulator (Tkinter GUI)... Purr!"); pygame.init()
    try:
        nes = NES(SAMPLE_ROM_DATA)
    except Exception as e: print(f"ROM/NES init error: {e}"); pygame.quit(); return
    gui = EmulatorGUI(nes); gui.start() 
    pygame.quit(); print("Emulator closed. Bye-bye, meow!")

if __name__ == "__main__":
    main_tkinter()
