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

# CPU Class for 6502 emulation (expanded for basic functionality)
class CPU:
    def __init__(self, rom, ppu):
        self.rom = rom
        self.ppu = ppu
        self.chr_ram = rom.chr_rom if self.rom.chr_banks == 0 else None
        self.ram = bytearray(0x0800)
        self.reset()

    def reset(self):
        self.pc = self.read_word(0xFFFC)
        self.sp = 0xFD
        self.acc = 0
        self.x = 0
        self.y = 0
        self.status = 0x24  # Interrupt disable set

    def set_zero_negative_flags(self, value):
        self.status = (self.status & 0x7D) | (0x80 if value & 0x80 else 0) | (0x02 if value == 0 else 0)

    def step(self):
        opcode = self.read(self.pc)
        self.pc += 1
        if opcode == 0xA9:  # LDA Immediate
            self.acc = self.read(self.pc)
            self.pc += 1
            self.set_zero_negative_flags(self.acc)
        elif opcode == 0xAD:  # LDA Absolute
            addr = self.read_word(self.pc)
            self.pc += 2
            self.acc = self.read(addr)
            self.set_zero_negative_flags(self.acc)
        elif opcode == 0x8D:  # STA Absolute
            addr = self.read_word(self.pc)
            self.pc += 2
            self.write(addr, self.acc)
        elif opcode == 0x4C:  # JMP Absolute
            self.pc = self.read_word(self.pc)
        elif opcode == 0x00:  # BRK (simplified)
            self.pc += 1
        return opcode

    def read(self, addr):
        if 0x0000 <= addr < 0x2000:
            return self.ram[addr % 0x0800]
        elif 0x2000 <= addr < 0x2008:
            return self.ppu.read_register(addr - 0x2000)
        elif 0x8000 <= addr < 0x10000:
            offset = addr - 0x8000
            if len(self.rom.prg_rom) == 0x4000:
                return self.rom.prg_rom[offset % 0x4000]
            return self.rom.prg_rom[offset % 0x8000]
        return 0

    def write(self, addr, value):
        if 0x0000 <= addr < 0x2000:
            self.ram[addr % 0x0800] = value
        elif 0x2000 <= addr < 0x2008:
            self.ppu.write_register(addr - 0x2000, value)

    def read_word(self, addr):
        return self.read(addr) | (self.read(addr + 1) << 8)

# PPU Class for rendering graphics
class PPU:
    def __init__(self, cpu):
        pygame.init()
        pygame.display.set_caption("NES Emulator - Nesticle Style")
        self.screen = pygame.display.set_mode((256, 240))
        self.framebuffer = pygame.Surface((256, 240))
        self.cpu = cpu
        self.clock = pygame.time.Clock()
        self.vram = bytearray(0x0800)  # 2KB for nametables
        self.palette_ram = bytearray([0x0F, 0x01, 0x02, 0x03] + [0] * 28)  # Basic palette
        self.ppu_addr = 0
        self.ppu_addr_high = False
        self.ppu_ctrl = 0
        # Hardcode nametable for testing
        self.vram[0:0x03C0] = [1] * 0x03C0  # Use tile 1
        # Authentic NES color palette
        self.NES_PALETTE = [
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

    def get_vram_index(self, addr):
        addr = addr & 0x2FFF  # Mirror 0x3000-0x3EFF to 0x2000-0x2EFF
        if 0x2000 <= addr < 0x3000:
            nt = (addr - 0x2000) // 0x0400
            offset = addr % 0x0400
            if self.cpu.rom.mirroring == 0:  # Vertical
                if nt in [0, 2]:
                    return offset
                else:
                    return 0x0400 + offset
            else:  # Horizontal
                if nt in [0, 1]:
                    return offset
                else:
                    return 0x0400 + offset
        return None

    def write_register(self, reg, value):
        if reg == 6:  # PPUADDR
            if self.ppu_addr_high:
                self.ppu_addr = (self.ppu_addr & 0xFF) | (value << 8)
            else:
                self.ppu_addr = (self.ppu_addr & 0xFF00) | value
            self.ppu_addr_high = not self.ppu_addr_high
        elif reg == 7:  # PPUDATA
            self.write_ppu_memory(self.ppu_addr, value)
            self.ppu_addr += 32 if self.ppu_ctrl & 0x04 else 1

    def read_register(self, reg):
        if reg == 7:  # PPUDATA
            value = self.read_ppu_memory(self.ppu_addr)
            self.ppu_addr += 32 if self.ppu_ctrl & 0x04 else 1
            return value
        return 0

    def write_ppu_memory(self, addr, value):
        if 0x0000 <= addr < 0x2000 and self.cpu.chr_ram is not None:
            self.cpu.chr_ram[addr] = value
        elif 0x2000 <= addr < 0x3F00:
            index = self.get_vram_index(addr)
            if index is not None:
                self.vram[index] = value
        elif 0x3F00 <= addr < 0x4000:
            self.palette_ram[addr - 0x3F00] = value & 0x3F

    def read_ppu_memory(self, addr):
        if 0x0000 <= addr < 0x2000:
            return self.cpu.chr_ram[addr] if self.cpu.chr_ram else self.cpu.rom.chr_rom[addr]
        elif 0x2000 <= addr < 0x3F00:
            index = self.get_vram_index(addr)
            if index is not None:
                return self.vram[index]
            return 0
        elif 0x3F00 <= addr < 0x4000:
            return self.palette_ram[addr - 0x3F00]
        return 0

    def render_frame(self, chr_data):
        self.framebuffer.fill((0, 0, 0))
        chr_source = self.cpu.chr_ram if self.cpu.chr_ram else chr_data
        for tile_y in range(30):
            for tile_x in range(32):
                nametable_addr = tile_y * 32 + tile_x
                tile_index = self.vram[nametable_addr]
                palette = [self.NES_PALETTE[self.palette_ram[i] & 0x3F] for i in range(4)]
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
                self.framebuffer.set_at((x + bit, y + row), palette[color_bit])

# APU Class for audio generation
class APU:
    def __init__(self):
        pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=512)
        self.channel = pygame.mixer.Channel(0)
        self.sound = self.generate_square(440, 1/60)

    def generate_square(self, frequency, duration):
        samples = int(44100 * duration)
        t = np.linspace(0, duration, samples, endpoint=False)
        wave_mono = np.where(np.sin(2 * np.pi * frequency * t) > 0, 16383, -16384)
        wave_stereo = np.column_stack((wave_mono, wave_mono)).astype(np.int16)
        return pygame.sndarray.make_sound(wave_stereo)

    def play(self):
        if not self.channel.get_busy():
            self.channel.play(self.sound)

# NES Class to integrate components
class NES:
    def __init__(self, rom_data):
        self.rom = ROM(rom_data)
        self.ppu = PPU(None)  # Temporary, before CPU is set
        self.cpu = CPU(self.rom, self.ppu)
        self.ppu.cpu = self.cpu  # Set CPU reference in PPU
        self.apu = APU()
        self.running = False

    def update_loop(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
        keys = pygame.key.get_pressed()
        if keys[pygame.K_q]:
            self.running = False
        # Simulate ~1 frame of CPU cycles
        for _ in range(29780):  # Approx cycles per frame for 60 FPS
            self.cpu.step()
        self.ppu.render_frame(self.rom.chr_rom)
        self.apu.play()

    def setup(self):
        self.running = True

    async def run(self):
        self.setup()
        while self.running:
            self.update_loop()
            self.ppu.clock.tick(60)  # Ensure 60 FPS
        pygame.quit()

# Test ROM with a visible pattern
SAMPLE_ROM = bytearray(b"NES\x1a\x01\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00" + b"\x00" * 16384 + b"\x00" * 8192)
# Tile 1: Checkerboard pattern
SAMPLE_ROM[16 + 16384 + 16:16 + 16384 + 32] = b"\xAA\x55" * 4 + b"\x55\xAA" * 4

async def main():
    nes = NES(SAMPLE_ROM)
    await nes.run()

if platform.system() == "Emscripten":
    asyncio.ensure_future(main())
else:
    if __name__ == "__main__":
        asyncio.run(main())
