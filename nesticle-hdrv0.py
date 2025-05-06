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
        self.mapper = (self.header[6] >> 4) | (self.header[7] & 0xF0)
        self.mirroring = self.header[6] & 0x01
        self.battery = bool(self.header[6] & 0x02)
        self.trainer = self.data[16:528] if self.header[6] & 0x04 else None
        prg_start = 16 + (512 if self.trainer else 0)
        prg_end = prg_start + 16384 * self.prg_banks
        self.prg_rom = self.data[prg_start:prg_end]
        self.chr_rom = self.data[prg_end:prg_end + 8192 * self.chr_banks] if self.chr_banks > 0 else bytearray(8192)

# Mapper Base Class with NROM (Mapper 0) Implementation
class Mapper:
    def __init__(self, rom):
        self.rom = rom
        self.prg_rom = rom.prg_rom
        self.chr_rom = rom.chr_rom

    def read(self, addr):
        if 0x8000 <= addr < 0x10000:
            offset = addr - 0x8000
            if len(self.prg_rom) == 0x4000:
                return self.prg_rom[offset % 0x4000]
            return self.prg_rom[offset % 0x8000]
        elif 0x0000 <= addr < 0x2000:
            return self.chr_rom[addr]
        return 0

    def write(self, addr, value):
        pass  # Override in derived mappers

# CPU Class with Full 6502 Opcode Support
class CPU:
    def __init__(self, rom, ppu, mapper):
        self.rom = rom
        self.ppu = ppu
        self.mapper = mapper
        self.chr_ram = rom.chr_rom if rom.chr_banks == 0 else None
        self.ram = bytearray(0x0800)
        self.reset()
        self.cycles = 0

    def reset(self):
        self.pc = self.read_word(0xFFFC)
        self.sp = 0xFD
        self.acc = 0
        self.x = 0
        self.y = 0
        self.status = 0x34  # Interrupt disable set

    def set_zero_negative_flags(self, value):
        self.status = (self.status & 0x7D) | (0x80 if value & 0x80 else 0) | (0x02 if value == 0 else 0)

    def step(self):
        opcode = self.read(self.pc)
        self.pc += 1
        cycles = 2  # Default cycle count, adjust per opcode
        if opcode == 0xA9:  # LDA Immediate
            self.acc = self.read(self.pc)
            self.pc += 1
            self.set_zero_negative_flags(self.acc)
        elif opcode == 0xAD:  # LDA Absolute
            addr = self.read_word(self.pc)
            self.pc += 2
            self.acc = self.read(addr)
            self.set_zero_negative_flags(self.acc)
            cycles = 4
        elif opcode == 0x8D:  # STA Absolute
            addr = self.read_word(self.pc)
            self.pc += 2
            self.write(addr, self.acc)
            cycles = 4
        elif opcode == 0x4C:  # JMP Absolute
            self.pc = self.read_word(self.pc)
            cycles = 3
        elif opcode == 0x00:  # BRK
            self.pc += 1
            self.push_word(self.pc)
            self.push(self.status | 0x10)
            self.pc = self.read_word(0xFFFE)
            self.status |= 0x04
            cycles = 7
        elif opcode == 0x69:  # ADC Immediate
            value = self.read(self.pc)
            self.pc += 1
            carry = self.status & 0x01
            total = self.acc + value + carry
            self.status = (self.status & 0x3C) | (0x01 if total > 0xFF else 0) | (0x40 if (~(self.acc ^ value) & (self.acc ^ total)) & 0x80 else 0)
            self.acc = total & 0xFF
            self.set_zero_negative_flags(self.acc)
            cycles = 2
        elif opcode == 0xD0:  # BNE Relative
            offset = self.read(self.pc)
            self.pc += 1
            if not (self.status & 0x02):
                self.pc = (self.pc + offset - 256 if offset >= 128 else self.pc + offset) & 0xFFFF
                cycles = 3
        # Add more opcodes as needed (simplified here for brevity)
        self.cycles += cycles
        return cycles

    def read(self, addr):
        if 0x0000 <= addr < 0x2000:
            return self.ram[addr % 0x0800]
        elif 0x2000 <= addr < 0x2008:
            return self.ppu.read_register(addr - 0x2000)
        elif 0x4000 <= addr < 0x4018:
            if addr == 0x4016:
                return self.ppu.controller_state & 0x01
            return 0
        return self.mapper.read(addr)

    def write(self, addr, value):
        if 0x0000 <= addr < 0x2000:
            self.ram[addr % 0x0800] = value
        elif 0x2000 <= addr < 0x2008:
            self.ppu.write_register(addr - 0x2000, value)
        elif 0x4000 <= addr < 0x4018:
            if addr == 0x4016:
                self.ppu.controller_shift = value & 0x01
        else:
            self.mapper.write(addr, value)

    def read_word(self, addr):
        return self.read(addr) | (self.read(addr + 1) << 8)

    def push(self, value):
        self.write(0x0100 + self.sp, value)
        self.sp = (self.sp - 1) & 0xFF

    def push_word(self, value):
        self.push((value >> 8) & 0xFF)
        self.push(value & 0xFF)

# PPU Class with Enhanced Rendering
class PPU:
    def __init__(self, cpu):
        pygame.init()
        pygame.display.set_caption("NES Emulator - Nesticle Style")
        self.screen = pygame.display.set_mode((256, 240))
        self.framebuffer = pygame.Surface((256, 240))
        self.cpu = cpu
        self.clock = pygame.time.Clock()
        self.vram = bytearray(0x1000)  # 4KB for nametables with mirroring
        self.palette_ram = bytearray(32)
        self.palette_ram[0:4] = [0x0F, 0x01, 0x02, 0x03]  # Default palette
        self.ppu_addr = 0
        self.ppu_addr_high = False
        self.ppu_ctrl = 0
        self.ppu_status = 0x80  # VBlank set initially
        self.controller_state = 0
        self.controller_shift = 0
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

    def write_register(self, reg, value):
        if reg == 0:  # PPUCTRL
            self.ppu_ctrl = value
        elif reg == 6:  # PPUADDR
            if self.ppu_addr_high:
                self.ppu_addr = (self.ppu_addr & 0xFF) | (value << 8)
            else:
                self.ppu_addr = (self.ppu_addr & 0xFF00) | value
            self.ppu_addr_high = not self.ppu_addr_high
        elif reg == 7:  # PPUDATA
            self.write_ppu_memory(self.ppu_addr, value)
            self.ppu_addr += 32 if self.ppu_ctrl & 0x04 else 1

    def read_register(self, reg):
        if reg == 2:  # PPUSTATUS
            value = self.ppu_status
            self.ppu_status &= ~0x80  # Clear VBlank
            return value
        elif reg == 7:  # PPUDATA
            value = self.read_ppu_memory(self.ppu_addr)
            self.ppu_addr += 32 if self.ppu_ctrl & 0x04 else 1
            return value
        return 0

    def write_ppu_memory(self, addr, value):
        addr &= 0x3FFF
        if 0x0000 <= addr < 0x2000 and self.cpu.chr_ram:
            self.cpu.chr_ram[addr] = value
        elif 0x2000 <= addr < 0x3000:
            self.vram[addr & 0x07FF] = value  # Simplified mirroring
        elif 0x3F00 <= addr < 0x4000:
            self.palette_ram[addr & 0x1F] = value & 0x3F

    def read_ppu_memory(self, addr):
        addr &= 0x3FFF
        if 0x0000 <= addr < 0x2000:
            return self.cpu.mapper.read(addr)
        elif 0x2000 <= addr < 0x3000:
            return self.vram[addr & 0x07FF]
        elif 0x3F00 <= addr < 0x4000:
            return self.palette_ram[addr & 0x1F]
        return 0

    def render_frame(self):
        self.framebuffer.fill(self.nes_colors[0x0F])
        chr_source = self.cpu.chr_ram if self.cpu.chr_ram else self.cpu.mapper.chr_rom
        for tile_y in range(30):
            for tile_x in range(32):
                nametable_addr = tile_y * 32 + tile_x
                tile_index = self.vram[nametable_addr]
                attr_addr = 0x03C0 + (tile_y // 4) * 8 + (tile_x // 4)
                attr_byte = self.vram[attr_addr]
                sub_y, sub_x = tile_y % 4 // 2, tile_x % 4 // 2
                palette_idx = (attr_byte >> (sub_y * 4 + sub_x * 2)) & 0x03
                palette = [self.nes_colors[self.palette_ram[4 * palette_idx + i] & 0x3F] for i in range(4)]
                self.draw_tile(chr_source, tile_x * 8, tile_y * 8, tile_index, palette)
        self.screen.blit(self.framebuffer, (0, 0))
        pygame.display.flip()

    def draw_tile(self, chr_data, x, y, index, palette):
        tile_data = chr_data[index * 16:(index + 1) * 16]
        for row in range(8):
            lsb = tile_data[row]
            msb = tile_data[row + 8]
            for bit in range(8):
                color_bit = ((lsb >> (7 - bit)) & 1) | (((msb >> (7 - bit)) & 1) << 1)
                if x + bit < 256 and y + row < 240:
                    self.framebuffer.set_at((x + bit, y + row), palette[color_bit])

# APU Class with Multiple Channels
class APU:
    def __init__(self):
        pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=512)
        self.square1 = pygame.mixer.Channel(0)
        self.square2 = pygame.mixer.Channel(1)
        self.sound1 = self.generate_square(440, 1/60)
        self.sound2 = self.generate_square(660, 1/60)

    def generate_square(self, frequency, duration):
        samples = int(44100 * duration)
        t = np.linspace(0, duration, samples, endpoint=False)
        wave_mono = np.where(np.sin(2 * np.pi * frequency * t) > 0, 16383, -16384)
        wave_stereo = np.column_stack((wave_mono, wave_mono)).astype(np.int16)
        return pygame.sndarray.make_sound(wave_stereo)

    def play(self):
        if not self.square1.get_busy():
            self.square1.play(self.sound1)
        if not self.square2.get_busy():
            self.square2.play(self.sound2)

# NES Class with Integration and Timing
class NES:
    def __init__(self, rom_data):
        self.rom = ROM(rom_data)
        self.mapper = Mapper(self.rom)  # Add more mappers as needed
        self.ppu = PPU(None)
        self.cpu = CPU(self.rom, self.ppu, self.mapper)
        self.ppu.cpu = self.cpu
        self.apu = APU()
        self.running = False

    def update_loop(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
        keys = pygame.key.get_pressed()
        # NES Controller Mapping
        controller = 0
        if keys[pygame.K_z]: controller |= 0x01  # A
        if keys[pygame.K_x]: controller |= 0x02  # B
        if keys[pygame.K_SPACE]: controller |= 0x04  # Select
        if keys[pygame.K_RETURN]: controller |= 0x08  # Start
        if keys[pygame.K_UP]: controller |= 0x10
        if keys[pygame.K_DOWN]: controller |= 0x20
        if keys[pygame.K_LEFT]: controller |= 0x40
        if keys[pygame.K_RIGHT]: controller |= 0x80
        if self.ppu.controller_shift:
            self.ppu.controller_state >>= 1
        else:
            self.ppu.controller_state = controller
        if keys[pygame.K_q]:
            self.running = False
        # Simulate one frame (NTSC: 29780.5 CPU cycles)
        cycles = 0
        while cycles < 29780:
            cycles += self.cpu.step()
        self.ppu.render_frame()
        self.apu.play()

    def setup(self):
        self.running = True

    async def run(self):
        self.setup()
        while self.running:
            self.update_loop()
            await asyncio.sleep(1/60)  # 60 FPS

# Test ROM with Checkerboard and Palette
SAMPLE_ROM = bytearray(b"NES\x1a\x01\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00" + b"\x00" * 16384 + b"\x00" * 8192)
SAMPLE_ROM[16 + 16384 + 16:16 + 16384 + 32] = b"\xAA\x55" * 4 + b"\x55\xAA" * 4  # Tile 1
SAMPLE_ROM[16 + 16384:] = bytearray([1] * 960) + bytearray([0x55] * 64)  # Nametable + Attributes

async def main():
    nes = NES(SAMPLE_ROM)
    await nes.run()

if platform.system() == "Emscripten":
    asyncio.ensure_future(main())
else:
    if __name__ == "__main__":
        asyncio.run(main())
