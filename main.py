import math
import os
import sys
import pygame
import random

TILE = 128
COLS, ROWS = 19, 14
FLOOR_TILE = 16
# Per-level grid dimensions (cols, rows), inferred from floor images at 16px/tile
LEVEL_DIMS = {
    0: (19, 14),  # floor1-l1: 304x224
    1: (16, 13),  # floor1-l2: 256x208
    2: (15, 11),  # floor2-l1: 240x176
    3: (13, 10),  # floor2-l2: 208x160
    4: (16, 13),  # floor3: 256x208
}
# Per-level player spawn position (col, row)
PLAYER_SPAWN = {0: (1, 4), 1: (1, 6), 2: (1, 5), 3: (1, 6), 4: (1, 6)}

# Per-level passability grids as strings. '.' = passable, '#' = wall.
# Each string is one row (top to bottom). Edit manually.
PASSABILITY_STR = {
    0: [  # 19x14
        "###################",
        "###################",
        "###......##########",
        "#........##########",
        "#........###....###",
        "###......###....###",
        "###.............###",
        "######............#",
        "######............#",
        "######............#",
        "######..........###",
        "######..........###",
        "###################",
        "###################",
    ],
    1: [  # 16x13
        "################",
        "################",
        "###....##....###",
        "###....##....###",
        "###....##....###",
        "#..............#",
        "#..............#",
        "#......##......#",
        "###....##....###",
        "###....##....###",
        "###....##....###",
        "################",
        "################",
    ],
    2: [  # 15x11
        "###############",
        "###############",
        "##...###....###",
        "##...###....###",
        "#............##",
        "#............##",
        "##...###......#",
        "##...###......#",
        "##########...##",
        "##########...##",
        "###############",
    ],
    3: [  # 13x10
        "#############",
        "#############",
        "##.........##",
        "##.........##",
        "##...###....#",
        "#....###....#",
        "#....###...##",
        "##.........##",
        "##.........##",
        "#############",
    ],
    4: [  # 16x13
        "################",
        "###............#",
        "##.............#",
        "#..............#",
        "#..............#",
        "......####......",
        ".....######.....",
        "......####......",
        "#..............#",
        "#..............#",
        "##.............#",
        "###............#",
        "################",
    ],
}
PASSABILITY = {
    lvl: [[1 if c == '.' else 0 for c in row] for row in rows]
    for lvl, rows in PASSABILITY_STR.items()
}

EASE_SPEED = 20
DIRS = [(1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1)]


_current_level = 0

def is_passable(x, y, level=None):
    """Check if tile (x, y) is within bounds and passable for the current level."""
    if not (0 <= x < COLS and 0 <= y < ROWS):
        return False
    p = PASSABILITY.get(level if level is not None else _current_level)
    if p and 0 <= y < len(p) and 0 <= x < len(p[y]):
        return p[y][x] == 1
    return True


def bfs_distance(target_x, target_y, level):
    """BFS distance map from (target_x, target_y). Returns dict {(x,y): dist}.
    Only traverses passable tiles."""
    from collections import deque
    dist = {}
    q = deque()
    dist[(target_x, target_y)] = 0
    q.append((target_x, target_y))
    while q:
        cx, cy = q.popleft()
        d = dist[(cx, cy)]
        for dx, dy in DIRS:
            nx, ny = cx + dx, cy + dy
            if (nx, ny) not in dist and is_passable(nx, ny, level):
                dist[(nx, ny)] = d + 1
                q.append((nx, ny))
    return dist

ASSET_DIR = os.path.join(os.path.dirname(__file__), "assets")
_sprite_cache = {}

# ── Sound effects ─────────────────────────────────────────────────
_sound_cache = {}


def preload_sfx():
    """Pre-load all sound effects into cache. Call once after pygame.init()."""
    for fn in os.listdir(ASSET_DIR):
        if fn.endswith((".wav", ".mp3", ".ogg")):
            path = os.path.join(ASSET_DIR, fn)
            _sound_cache[fn] = pygame.mixer.Sound(path)


def _reinit_mixer():
    """Quit and re-init the mixer, then reload all cached sounds."""
    global _sound_cache
    try:
        pygame.mixer.quit()
    except Exception:
        pass
    try:
        pygame.mixer.init(44100, -16, 2, 512)
    except Exception:
        return False
    # Reload all previously cached sounds
    new_cache = {}
    for name in list(_sound_cache.keys()):
        try:
            path = os.path.join(ASSET_DIR, name)
            new_cache[name] = pygame.mixer.Sound(path)
        except Exception:
            pass
    _sound_cache = new_cache
    return True


def play_sfx(name, volume=0.5):
    """Play a sound effect by filename (cached). Returns the Channel."""
    try:
        if name not in _sound_cache:
            path = os.path.join(ASSET_DIR, name)
            _sound_cache[name] = pygame.mixer.Sound(path)
        snd = _sound_cache[name]
        snd.set_volume(volume)
        return snd.play()
    except Exception:
        return None


def load_sprite(filename, flip_x=False, scale=1):
    """Load a PNG from assets/, scale to TILE*scale, cache the result."""
    key = (filename, flip_x, scale)
    if key not in _sprite_cache:
        path = os.path.join(ASSET_DIR, filename)
        img = pygame.image.load(path).convert_alpha()
        size = int(TILE * scale)
        img = pygame.transform.scale(img, (size, size))
        if flip_x:
            img = pygame.transform.flip(img, True, False)
        _sprite_cache[key] = img
    return _sprite_cache[key]


class AnimSprite:
    """Cycles through a list of sprite filenames at a fixed frame rate."""

    def __init__(self, frames, fps=4, flip_x=False, loop=True, scale=1):
        self.frame_names = frames
        self.fps = fps
        self.flip_x = flip_x
        self.scale = scale
        self.loop = loop
        self.timer = 0.0
        self.index = 0
        self.finished = False

    def update(self, dt):
        if self.finished:
            return
        self.timer += dt
        frame_dur = 1.0 / self.fps
        while self.timer >= frame_dur:
            self.timer -= frame_dur
            if self.index + 1 >= len(self.frame_names) and not self.loop:
                self.index = len(self.frame_names) - 1
                self.finished = True
                return
            self.index = (self.index + 1) % len(self.frame_names)

    def image(self):
        return load_sprite(self.frame_names[self.index], self.flip_x, self.scale)


class Entity:
    def __init__(self, gx, gy, color, hp):
        self.gx = gx
        self.gy = gy
        self.color = color
        self.hp = hp
        self.max_hp = hp
        self.shield = 0
        self.pos = [gx * TILE, gy * TILE]
        self.bump = [0.0, 0.0]  # pixel offset for bounce animation
        self.pending_bump = None  # (delay, dx, dy, strength, damage)
        self.anim = None  # subclasses set this to an AnimSprite
        self.facing_right = False

    def update_facing(self, dx):
        """Update facing direction based on horizontal movement."""
        if dx > 0:
            self.facing_right = True
        elif dx < 0:
            self.facing_right = False

    def start_bump(self, dx, dy, strength=0.4):
        """Start a bump animation toward (dx, dy) direction."""
        self.bump = [dx * TILE * strength, dy * TILE * strength]

    def take_damage(self, amount):
        actual = max(0, amount - self.shield)
        self.hp -= actual
        if actual > 0:
            if not hasattr(self, '_pending_popups'):
                self._pending_popups = []
            self._pending_popups.append(actual)
        return actual

    def ease(self, dt):
        for i, g in enumerate((self.gx, self.gy)):
            diff = g * TILE - self.pos[i]
            self.pos[i] += diff * min(EASE_SPEED * dt, 1)
        # Decay bump offset back to zero
        for i in range(2):
            self.bump[i] -= self.bump[i] * min(EASE_SPEED * dt, 1)
        # Fire pending bump after delay
        if self.pending_bump is not None:
            delay, bdx, bdy, bstr, bdmg = self.pending_bump
            delay -= dt
            if delay <= 0:
                self.start_bump(bdx, bdy, bstr)
                if bdmg:
                    self.take_damage(bdmg)
                self.pending_bump = None
            else:
                self.pending_bump = (delay, bdx, bdy, bstr, bdmg)
        if self.anim:
            self.anim.update(dt)

    def eased(self):
        return (abs(self.gx * TILE - self.pos[0]) < 0.5
                and abs(self.gy * TILE - self.pos[1]) < 0.5
                and abs(self.bump[0]) < 0.5
                and abs(self.bump[1]) < 0.5
                and self.pending_bump is None)

    def alive(self):
        return self.hp > 0

    def adjacent_to(self, other):
        return max(abs(self.gx - other.gx), abs(self.gy - other.gy)) == 1

    def range_tiles(self):
        return set()

    def overlay_color(self) -> tuple[int, int, int, int]:
        return (255, 60, 60, 40)

    def draw_hp_bar(self, screen, x=None, y=None, width=None):
        bar_w = width or (TILE - 16)
        bar_h = 8
        bx = (x if x is not None else self.pos[0] + 8)
        by = (y if y is not None else self.pos[1] + TILE - 8)
        pygame.draw.rect(screen, (40, 40, 40), (bx, by, bar_w, bar_h))
        fill = int(bar_w * self.hp / self.max_hp)
        pygame.draw.rect(screen, (220, 50, 50), (bx, by, fill, bar_h))

    def draw_sprite(self, screen):
        if self.anim:
            self.anim.flip_x = self.facing_right
            screen.blit(self.anim.image(), (self.pos[0], self.pos[1] - 7))
            self.draw_hp_bar(screen)
            return True
        return False

    def draw(self, screen):
        if self.draw_sprite(screen):
            return
        r = pygame.Rect(self.pos[0] + 8, self.pos[1] + 8, TILE - 16, TILE - 16)
        pygame.draw.rect(screen, self.color, r)
        self.draw_hp_bar(screen)


# Clockwise direction ring for shield facing
DIR_RING = [(0, -1), (1, -1), (1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1)]


def facing_cone(facing_idx):
    """Return the set of 3 directions the shield covers."""
    r = len(DIR_RING)
    return {DIR_RING[facing_idx],
            DIR_RING[(facing_idx - 1) % r],
            DIR_RING[(facing_idx + 1) % r]}


def direction_index(dx, dy):
    """Return DIR_RING index for a unit direction, or None."""
    if dx == 0 and dy == 0:
        return None
    ndx = (1 if dx > 0 else -1 if dx < 0 else 0)
    ndy = (1 if dy > 0 else -1 if dy < 0 else 0)
    try:
        return DIR_RING.index((ndx, ndy))
    except ValueError:
        return None


class Player(Entity):
    DAMAGE = 20

    def __init__(self, gx, gy):
        super().__init__(gx, gy, (80, 200, 120), hp=100)
        self.committed = [gx, gy]
        self.mode = "sword"  # "sword" or "shield"
        self.facing = 2  # index into DIR_RING, default facing E
        self.switched_this_turn = False
        self.free_will = 50  # 0..100
        self.sword_anim = AnimSprite(
            ["Player_sword_standing.png", "Player_sword_idle.png"], fps=2)
        self.shield_anim = AnimSprite(
            ["Player_shield_standing.png", "Player_shield_idle.png"], fps=2)
        self.anim = self.sword_anim
        self.facing_right = True

    def blocks_from(self, attacker_gx, attacker_gy):
        """Return True if the shield blocks an attack from the given tile."""
        if self.mode != "shield":
            return False
        dx, dy = attacker_gx - self.gx, attacker_gy - self.gy
        di = direction_index(dx, dy)
        if di is None:
            return False
        return DIR_RING[di] in facing_cone(self.facing)

    def shield_tiles(self):
        """Return set of tiles the shield is covering."""
        tiles = set()
        if self.mode != "shield":
            return tiles
        for ddx, ddy in facing_cone(self.facing):
            nx, ny = self.gx + ddx, self.gy + ddy
            if 0 <= nx < COLS and 0 <= ny < ROWS:
                tiles.add((nx, ny))
        return tiles

    SHIELD_BLOCK_NUM = 8   # block 8/10 of damage
    SHIELD_BLOCK_DEN = 10

    def take_damage_from(self, amount, attacker_gx, attacker_gy):
        """Take damage, reduced by 80% if shield is facing the attacker."""
        if self.blocks_from(attacker_gx, attacker_gy):
            reduced = max(1, amount * (self.SHIELD_BLOCK_DEN - self.SHIELD_BLOCK_NUM) // self.SHIELD_BLOCK_DEN)
            return self.take_damage(reduced)
        return self.take_damage(amount)

    def can_hit(self, gx, gy):
        if self.mode != "sword":
            return False
        dx, dy = gx - self.gx, gy - self.gy
        return max(abs(dx), abs(dy)) == 1 and (dx != 0 or dy != 0)

    def attack_range_tiles(self):
        tiles = set()
        if self.mode != "sword":
            return tiles
        for ddx, ddy in DIRS:
            nx, ny = self.gx + ddx, self.gy + ddy
            if 0 <= nx < COLS and 0 <= ny < ROWS:
                tiles.add((nx, ny))
        return tiles

    def try_move(self, gx, gy):
        dx, dy = gx - self.gx, gy - self.gy
        if max(abs(dx), abs(dy)) != 1:
            return False
        if not is_passable(gx, gy):
            return False
        if self.mode == "shield":
            di = direction_index(dx, dy)
            if di is not None:
                self.facing = di
        self.update_facing(dx)
        self.gx, self.gy = gx, gy
        play_sfx("whoosh.wav", 0.4)
        return True

    def has_moved(self):
        return [self.gx, self.gy] != self.committed

    def commit(self):
        self.committed = [self.gx, self.gy]
        self.switched_this_turn = False

    def draw(self, screen):
        self.anim = self.shield_anim if self.mode == "shield" else self.sword_anim
        self.draw_sprite(screen)


class Projectile:
    SPEED = 800  # pixels per second

    def __init__(self, sx, sy, target_gx, target_gy, color, on_arrive):
        self.pos = [sx * TILE + TILE // 2, sy * TILE + TILE // 2]
        self.origin = (sx, sy)
        self.target_gx = target_gx
        self.target_gy = target_gy
        self.color = color
        self.on_arrive = on_arrive  # callback: on_arrive(game)
        tx, ty = self.target_pos()
        dx = tx - self.pos[0]
        dy = ty - self.pos[1]
        dist = math.hypot(dx, dy)
        if dist > 0:
            self.vx = dx / dist * self.SPEED
            self.vy = dy / dist * self.SPEED
        else:
            self.vx = 0
            self.vy = 0

    def target_pos(self):
        return (self.target_gx * TILE + TILE // 2, self.target_gy * TILE + TILE // 2)

    def update(self, dt):
        self.pos[0] += self.vx * dt
        self.pos[1] += self.vy * dt

    def arrived(self):
        # Arrived when within the target tile
        tx, ty = self.target_pos()
        return abs(tx - self.pos[0]) < TILE // 2 and abs(ty - self.pos[1]) < TILE // 2

    def draw(self, screen, y_off=0):
        pygame.draw.circle(screen, self.color, (int(self.pos[0]), int(self.pos[1]) + y_off), 10)

    def spawn_burst(self, particles):
        """Emit a burst of particles at cast/impact time."""
        for _ in range(18):
            vx = random.uniform(-300, 300)
            vy = random.uniform(-300, 300)
            r, g, b = self.color
            pr = min(255, max(0, r + random.randint(-40, 40)))
            pg = min(255, max(0, g + random.randint(-40, 40)))
            pb = min(255, max(0, b + random.randint(-40, 40)))
            angle = random.uniform(0, 360)
            rot_speed = random.uniform(-500, 500)
            life = random.uniform(0.2, 0.5)
            particles.append([self.pos[0], self.pos[1], vx, vy,
                              life, (pr, pg, pb),
                              angle, rot_speed, life, 1.0])

    def spawn_particles(self, particles):
        """Emit a few trail particles from the current position."""
        for _ in range(2):
            vx = random.uniform(-120, 120)
            vy = random.uniform(-120, 120)
            r, g, b = self.color
            pr = min(255, max(0, r + random.randint(-30, 30)))
            pg = min(255, max(0, g + random.randint(-30, 30)))
            pb = min(255, max(0, b + random.randint(-30, 30)))
            angle = random.uniform(0, 360)
            rot_speed = random.uniform(-400, 400)
            life = random.uniform(0.15, 0.35)
            particles.append([self.pos[0], self.pos[1], vx, vy,
                              life, (pr, pg, pb),
                              angle, rot_speed, life, 1.0])


# ── Breath Beam ───────────────────────────────────────────────────
class BreathBeam:
    """A line of fire that grows leftward from the dragon over time."""
    SPEED = TILE * 8   # pixels per second the front advances
    LINGER = 0.3       # seconds the beam stays after reaching the edge
    DAMAGE = 20

    def __init__(self, start_x, row, game):
        self.row = row
        self.front_x = start_x  # current pixel x of the beam front
        self.start_x = start_x
        self.done = False
        self.linger_t = 0.0
        self.damaged = set()  # entities already hit

    def update(self, dt, game):
        if self.done:
            return
        if self.front_x > 0:
            self.front_x -= self.SPEED * dt
            if self.front_x < 0:
                self.front_x = 0
        else:
            self.linger_t += dt
            if self.linger_t >= self.LINGER:
                self.done = True
                # Final burst of fast particles along the beam
                cy = self.row
                for _ in range(60):
                    px = random.uniform(self.front_x, self.start_x)
                    py = cy * TILE + random.uniform(TILE * 0.1, TILE * 0.9)
                    vx = random.uniform(-200, 200)
                    vy = random.uniform(-350, -80)
                    r = min(255, 220 + random.randint(0, 35))
                    g = min(255, 120 + random.randint(0, 80))
                    b = random.randint(20, 70)
                    angle = random.uniform(0, 360)
                    rot_speed = random.uniform(-600, 600)
                    life = random.uniform(0.4, 0.9)
                    game.particles.append([px, py, vx, vy,
                                           life, (r, g, b),
                                           angle, rot_speed, life, 1.2])
                return
        # Damage entities the beam passes over
        cy = self.row
        for e in list(game.enemies):
            if e.alive() and not isinstance(e, Dragon) \
                    and e.gy == cy and id(e) not in self.damaged:
                ex = e.gx * TILE + TILE // 2
                if ex >= self.front_x:
                    e.take_damage(self.DAMAGE)
                    self.damaged.add(id(e))
        p = game.player
        if p.gy == cy and id(p) not in self.damaged:
            px = p.gx * TILE + TILE // 2
            if px >= self.front_x:
                p.take_damage_from(self.DAMAGE, self.start_x // TILE, cy)
                game.start_shake(9, 0.16)
                self.damaged.add(id(p))
        # Keep screen shaking while beam is active
        beam_progress = (self.start_x - self.front_x) / max(1, self.start_x)
        game.shake_timer = 0.1
        game.shake_intensity = max(2, int(2 + 8 * beam_progress))
        # Spawn fire particles along the entire beam length
        beam_len = self.start_x - self.front_x
        count = max(5, int(beam_len / TILE * 6))
        for _ in range(count):
            px = random.uniform(self.front_x, self.start_x)
            py = cy * TILE + random.uniform(TILE * 0.1, TILE * 0.9)
            vx = random.uniform(-60, 60)
            vy = random.uniform(-120, -30)
            r = min(255, 200 + random.randint(0, 55))
            g = min(255, 80 + random.randint(0, 80))
            b = random.randint(0, 40)
            angle = random.uniform(0, 360)
            rot_speed = random.uniform(-400, 400)
            life = random.uniform(0.3, 0.6)
            game.particles.append([px, py, vx, vy,
                                   life, (r, g, b),
                                   angle, rot_speed, life, 1.0])


# ── Slash VFX ──────────────────────────────────────────────────────
SLASH_FRAMES = ["Sideslash_1.png"] + [f"Sideslash_{i}.png" for i in range(3, 6)]
# Note: asset filenames have a typo — frame 1 is "Verticalslash" but 2-5 are "Verticleslash"
VSLASH_FRAMES = ["Verticalslash_1.png"] + [f"Verticleslash_{i}.png" for i in range(3, 6)]


class SlashVFX:
    """Animated slash effect that plays once on a tile then disappears."""
    FPS = 24
    # Per-frame durations; frame 2 (index 1) held longer
    FRAME_DURS = None

    def __init__(self, gx, gy, flip_x=False, flip_y=False, vertical=False, angle=0, scale=1):
        self.gx = gx
        self.gy = gy
        self.flip_x = flip_x
        self.flip_y = flip_y
        self.angle = angle
        self.scale = scale
        self.frames = VSLASH_FRAMES if vertical else SLASH_FRAMES
        self.timer = 0.0
        self.index = 0
        self.done = False
        base = 1.0 / self.FPS
        self.frame_durs = [base] * len(self.frames)
        self.frame_durs[1] = base * 3  # hold frame 3 longer

    def update(self, dt):
        if self.done:
            return
        self.timer += dt
        while self.timer >= self.frame_durs[self.index]:
            self.timer -= self.frame_durs[self.index]
            self.index += 1
            if self.index >= len(self.frames):
                self.done = True
                return

    def draw(self, screen, y_off=0):
        if self.done:
            return
        img = load_sprite(self.frames[self.index], self.flip_x, self.scale)
        if self.flip_y:
            img = pygame.transform.flip(img, False, True)
        size = int(TILE * self.scale)
        # Centre the scaled sprite on the tile
        ox = self.gx * TILE - (size - TILE) // 2
        oy = self.gy * TILE - (size - TILE) // 2 + y_off
        if self.angle:
            orig = img.get_rect(topleft=(ox, oy))
            img = pygame.transform.rotate(img, self.angle)
            rect = img.get_rect(center=orig.center)
            screen.blit(img, rect)
        else:
            screen.blit(img, (ox, oy))


# ── Slime ───────────────────────────────────────────────────────────
# Jumps up to sqrt(5) tiles toward the player (Euclidean).
# If it could land ON the player it deals damage and lands adjacent instead.
class Slime(Entity):
    DAMAGE = 20
    JUMP_RANGE_SQ = 5  # sqrt(5) range — covers adjacent, diagonal, and knight-move tiles

    JUMP_HEIGHT = TILE * 0.7  # peak height in pixels

    SPAWN_HEIGHT = TILE * 0.35  # how far above tile the slime starts
    SPAWN_DURATION = 0.1       # seconds for the spawn animation

    def __init__(self, gx, gy, spawning=False):
        super().__init__(gx, gy, (100, 200, 80), hp=60)
        self.idle_anim = AnimSprite(
            ["Slime_standing.png", "Slime_idle.png"], fps=2)
        self.jump_anim = AnimSprite(
            ["Slime_up.png", "Slime_down.png"], fps=4)
        self.anim = self.idle_anim
        self.jumping = False
        self.jump_t = 0.0
        self.jump_start = [0, 0]
        self.jump_end = [0, 0]
        self.land_pause = 0.0
        self._bump_player_on_land = None
        # Spawn animation state
        self.spawning = spawning
        self.spawn_t = 0.0 if spawning else 1.0

    def _start_jump(self, toward=None):
        """Begin a jump arc. If toward is set, overshoot slightly toward that tile."""
        self.jumping = True
        self.jump_t = 0.0
        self.jump_start = [self.pos[0], self.pos[1]]
        end_x = self.gx * TILE
        end_y = self.gy * TILE
        if toward:
            # Offset 30% of a tile toward the target
            end_x += (toward[0] - self.gx) * TILE * 0.3
            end_y += (toward[1] - self.gy) * TILE * 0.3
        self.jump_end = [end_x, end_y]
        self.anim = self.jump_anim
        self.anim.index = 0

    def range_tiles(self):
        tiles = set()
        for x in range(COLS):
            for y in range(ROWS):
                dsq = (x - self.gx) ** 2 + (y - self.gy) ** 2
                if 1 <= dsq <= self.JUMP_RANGE_SQ:
                    tiles.add((x, y))
        return tiles

    def overlay_color(self):
        return (100, 200, 80, 40)

    def take_turn(self, game, occupied, dist_map=None):
        px, py = game.player.gx, game.player.gy
        dist_sq = (self.gx - px) ** 2 + (self.gy - py) ** 2
        # Can we land on the player? (within jump range)
        if 1 <= dist_sq <= self.JUMP_RANGE_SQ:
            # Deal damage (deferred visually — bump and shake on landing)
            game.player.take_damage_from(self.DAMAGE, self.gx, self.gy)
            self._bump_player_on_land = (game.player, game)
            # Land on the best adjacent tile to the player
            best = None
            best_d = 999
            for dx, dy in DIRS:
                nx, ny = px + dx, py + dy
                if is_passable(nx, ny) and (nx, ny) not in occupied:
                    jsq = (nx - self.gx) ** 2 + (ny - self.gy) ** 2
                    if jsq <= self.JUMP_RANGE_SQ:  # must be reachable by the jump
                        pd = dist_map.get((nx, ny), 9999) if dist_map else 9999
                        if pd < best_d:
                            best_d = pd
                            best = (nx, ny)
            if best:
                self.update_facing(best[0] - self.gx)
                self.gx, self.gy = best
            self._start_jump(toward=(px, py))
            return
        # Otherwise jump toward the player using BFS distance
        best = None
        best_dist = dist_map.get((self.gx, self.gy), 9999) if dist_map else dist_sq
        for x in range(COLS):
            for y in range(ROWS):
                if not is_passable(x, y):
                    continue
                jsq = (x - self.gx) ** 2 + (y - self.gy) ** 2
                if jsq < 1 or jsq > self.JUMP_RANGE_SQ:
                    continue
                if (x, y) in occupied or (x == px and y == py):
                    continue
                d = dist_map.get((x, y), 9999) if dist_map else (x - px) ** 2 + (y - py) ** 2
                if d < best_dist:
                    best_dist = d
                    best = (x, y)
        if best:
            self.update_facing(best[0] - self.gx)
            self.gx, self.gy = best
            self._start_jump()

    def ease(self, dt):
        if self.spawning:
            self.spawn_t += dt / self.SPAWN_DURATION
            if self.spawn_t >= 1.0:
                self.spawn_t = 1.0
                self.spawning = False
            if self.anim:
                self.anim.update(dt)
            return
        if self.jumping:
            # Advance jump progress
            self.jump_t += EASE_SPEED * dt * 0.25
            if self.jump_t >= 1.0:
                self.jump_t = 1.0
                self.jumping = False
                self.land_pause = 0.15
                self.anim = self.idle_anim
                play_sfx("slime.wav", 0.5)
                if self._bump_player_on_land is not None:
                    pl, gm = self._bump_player_on_land
                    bdx = pl.gx - self.gx
                    bdy = pl.gy - self.gy
                    if bdx == 0 and bdy == 0:
                        bdx, bdy = 1, 0
                    pl.start_bump(bdx, bdy, strength=0.2)
                    gm.start_shake(2, 0.07)
                    self._bump_player_on_land = None
            # Lerp horizontal/vertical position
            t = self.jump_t
            self.pos[0] = self.jump_start[0] + (self.jump_end[0] - self.jump_start[0]) * t
            self.pos[1] = self.jump_start[1] + (self.jump_end[1] - self.jump_start[1]) * t
            # Parabolic vertical arc: peaks at t=0.5
            self.bump = [0, -self.JUMP_HEIGHT * 4 * t * (1 - t)]
            # Switch anim frame: up in first half, down in second
            self.anim.index = 0 if t < 0.5 else 1
            if self.anim:
                self.anim.update(dt)
        elif self.land_pause > 0:
            self.land_pause -= dt
            if self.anim:
                self.anim.update(dt)
        else:
            super().ease(dt)

    def eased(self):
        if self.spawning:
            return False
        if self.jumping or self.land_pause > 0:
            return False
        return super().eased()

    def draw(self, screen):
        if self.spawning:
            # Fade in from above: alpha goes 0→255, y offset goes -SPAWN_HEIGHT→0
            t = self.spawn_t
            alpha = int(255 * t)
            y_off = -self.SPAWN_HEIGHT * (1 - t * t)
            if self.anim:
                self.anim.flip_x = self.facing_right
                img = self.anim.image().copy()
                img.set_alpha(alpha)
                screen.blit(img, (self.pos[0], self.pos[1] - 12 + y_off))
                self.draw_hp_bar(screen)
            return
        self.draw_sprite(screen)


# ── SwordSlime ─────────────────────────────────────────────────────
class SwordSlime(Slime):
    DAMAGE = 35

    def __init__(self, gx, gy, spawning=False):
        super().__init__(gx, gy, spawning=spawning)
        self.idle_anim = AnimSprite(
            ["Slime_sword_standing.png", "Slime_sword_idle.png"], fps=2)
        self.jump_anim = AnimSprite(
            ["Slime_sword_up.png", "Slime_sword_down.png"], fps=4)
        self.anim = self.idle_anim

    def overlay_color(self):
        return (200, 100, 80, 40)


# ── FireTile ────────────────────────────────────────────────────────
# Burning ground left by Wizard's Fireball. Damages anything standing on it.
class HealthPotion:
    HEAL = 15

    def __init__(self, gx, gy):
        self.gx = gx
        self.gy = gy

    def draw(self, screen, y_off=0):
        img = load_sprite("Healthpotion.png")
        screen.blit(img, (self.gx * TILE, self.gy * TILE + y_off))


class FireTile:
    DAMAGE = 10

    def __init__(self, gx, gy, turns, visible=True):
        self.gx = gx
        self.gy = gy
        self.turns = turns  # turns remaining
        self.visible = visible  # draw burnt sprite

    def draw(self, screen, y_off=0):
        if not self.visible:
            return
        s = pygame.Surface((TILE, TILE), pygame.SRCALPHA)
        alpha = min(120, 40 + 30 * self.turns)
        s.fill((255, 100, 20, alpha))
        screen.blit(s, (self.gx * TILE, self.gy * TILE + y_off))


# ── Wizard ──────────────────────────────────────────────────────────
# Casts spells: Hex (debuff/damage) and Fireball (3x3 burning area).
# Fireball never directly targets the player's tile but burns nearby.
# Stays at range, flees if player is close.
class Wizard(Entity):
    DAMAGE = 20
    SPELL_RANGE_SQ = 10
    FIREBALL_TURNS = 3
    FLEE_RANGE_SQ = 2

    def __init__(self, gx, gy):
        super().__init__(gx, gy, (120, 60, 180), hp=60)
        self.cooldown = 0  # 0 = hex turn, 1 = fireball next
        self.idle_anim = AnimSprite(
            ["Wizard_purple_1.png", "Wizard_purple_2.png"], fps=2)
        self.attack_anim = AnimSprite(
            [f"Wizard_purple_{i}.png" for i in range(1, 6)], fps=6, loop=False)
        self.anim = self.idle_anim
        self.pending_spell = None  # callable(game) — fires after frame 3

    def range_tiles(self):
        tiles = set()
        for x in range(COLS):
            for y in range(ROWS):
                if (x - self.gx) ** 2 + (y - self.gy) ** 2 <= self.SPELL_RANGE_SQ:
                    tiles.add((x, y))
        return tiles

    def overlay_color(self):
        return (120, 60, 180, 40)

    def take_turn(self, game, occupied, dist_map=None):
        px, py = game.player.gx, game.player.gy
        dist_sq = (self.gx - px) ** 2 + (self.gy - py) ** 2

        in_range = dist_sq <= self.SPELL_RANGE_SQ
        too_close = dist_sq <= self.FLEE_RANGE_SQ

        if in_range and self.cooldown == 0:
            # If too close, flee instead of casting — unless hex would kill
            would_kill = game.player.hp <= self.DAMAGE
            if too_close and not would_kill:
                self._try_flee(game, occupied, dist_map)
                self.cooldown = 1
                return
            # Cast Hex — defer projectile until frame 4
            ox, oy = self.gx, self.gy
            dmg = self.DAMAGE
            tpx, tpy = px, py
            def _spawn_hex(game, _ox=ox, _oy=oy, _dmg=dmg,
                           _tpx=tpx, _tpy=tpy):
                def hex_arrive(game, __ox=_ox, __oy=_oy, __dmg=_dmg):
                    play_sfx("spell-hit.wav", 0.5)
                    game.player.take_damage_from(__dmg, __ox, __oy)
                    # Bump player away from spell origin
                    bdx = game.player.gx - __ox
                    bdy = game.player.gy - __oy
                    if bdx == 0 and bdy == 0:
                        bdx, bdy = 1, 0
                    game.player.start_bump(bdx, bdy, strength=0.1)
                    game.start_shake(4, 0.10)
                proj = Projectile(_ox, _oy, _tpx, _tpy,
                                  (180, 80, 255), hex_arrive)
                game.projectiles.append(proj)
                proj.spawn_burst(game.particles)
            self.pending_spell = _spawn_hex
            self.anim = self.attack_anim
            self.anim.index = 0
            self.anim.finished = False
            play_sfx("spell.wav", 0.5)
            self.cooldown = 1
            return

        if in_range and self.cooldown >= 1:
            # If too close, flee instead of casting fireball
            if too_close:
                self._try_flee(game, occupied, dist_map)
                self.cooldown = 0
                return
            # Cast Fireball — defer projectile until frame 4
            center = self._fireball_center(game)
            if center:
                cx, cy = center
                ox, oy = self.gx, self.gy
                turns = self.FIREBALL_TURNS
                def _spawn_fireball(game, _ox=ox, _oy=oy,
                                    _cx=cx, _cy=cy, _turns=turns):
                    def fireball_arrive(game, __cx=_cx, __cy=_cy,
                                        __turns=_turns):
                        play_sfx("fire-swoosh.wav", 0.5)
                        for ddx in range(-1, 2):
                            for ddy in range(-1, 2):
                                fx, fy = __cx + ddx, __cy + ddy
                                if not (0 <= fx < COLS and 0 <= fy < ROWS):
                                    continue
                                existing = None
                                for f in game.fire_tiles:
                                    if f.gx == fx and f.gy == fy:
                                        existing = f
                                        break
                                if existing:
                                    existing.turns = max(existing.turns,
                                                         __turns)
                                else:
                                    game.fire_tiles.append(
                                        FireTile(fx, fy, __turns))
                    proj = Projectile(_ox, _oy, _cx, _cy,
                                      (255, 140, 40), fireball_arrive)
                    game.projectiles.append(proj)
                    proj.spawn_burst(game.particles)
                self.pending_spell = _spawn_fireball
                self.anim = self.attack_anim
                self.anim.index = 0
                self.anim.finished = False
                play_sfx("spell.wav", 0.5)
            self.cooldown = 0
            return

        # Not in range — move closer
        self._move_toward(game, occupied, dist_map)

    def _fireball_center(self, game):
        """Pick a center tile adjacent to the player for fireball."""
        px, py = game.player.gx, game.player.gy
        candidates = []
        for dx, dy in DIRS:
            cx, cy = px + dx, py + dy
            if 0 <= cx < COLS and 0 <= cy < ROWS:
                candidates.append((cx, cy))
        if not candidates:
            return None
        return random.choice(candidates)

    def _try_flee(self, game, occupied, dist_map=None):
        """Move one step away from the player if too close."""
        px, py = game.player.gx, game.player.gy
        dist_sq = (self.gx - px) ** 2 + (self.gy - py) ** 2
        if dist_sq > self.FLEE_RANGE_SQ:
            return
        best = None
        best_d = dist_map.get((self.gx, self.gy), 0) if dist_map else dist_sq
        for dx, dy in DIRS:
            nx, ny = self.gx + dx, self.gy + dy
            if is_passable(nx, ny) and (nx, ny) not in occupied \
                    and (nx, ny) != (px, py):
                d = dist_map.get((nx, ny), 9999) if dist_map else (nx - px) ** 2 + (ny - py) ** 2
                if d > best_d:
                    best_d = d
                    best = (nx, ny)
        if best:
            self.update_facing(best[0] - self.gx)
            self.gx, self.gy = best

    def _move_toward(self, game, occupied, dist_map=None):
        px, py = game.player.gx, game.player.gy
        best = None
        best_d = dist_map.get((self.gx, self.gy), 9999) if dist_map else (self.gx - px) ** 2 + (self.gy - py) ** 2
        for dx, dy in DIRS:
            nx, ny = self.gx + dx, self.gy + dy
            if is_passable(nx, ny) and (nx, ny) not in occupied \
                    and (nx, ny) != (px, py):
                d = dist_map.get((nx, ny), 9999) if dist_map else (nx - px) ** 2 + (ny - py) ** 2
                if d < best_d:
                    best_d = d
                    best = (nx, ny)
        if best:
            self.update_facing(best[0] - self.gx)
            self.gx, self.gy = best

    def eased(self):
        if self.pending_spell:
            return False
        if self.anim is self.attack_anim and not self.attack_anim.finished:
            return False
        return super().eased()

    def draw(self, screen):
        if self.anim is self.attack_anim and self.attack_anim.finished:
            self.anim = self.idle_anim
        self.draw_sprite(screen)


# ── Summoner ────────────────────────────────────────────────────────
# Summons a Slime on an adjacent empty tile every other turn.
# Flees from the player. Does not attack directly.
class Summoner(Entity):
    DAMAGE = 0
    SUMMON_RANGE_SQ = 2  # adjacent tiles only

    def __init__(self, gx, gy):
        super().__init__(gx, gy, (180, 140, 60), hp=80)
        self.cooldown = 0  # 0 = summon this turn, 1 = resting
        self.idle_anim = AnimSprite(
            ["Wizard_blue_1.png", "Wizard_blue_2.png"], fps=2)
        self.attack_anim = AnimSprite(
            [f"Wizard_blue_{i}.png" for i in range(1, 6)], fps=6, loop=False)
        self.anim = self.idle_anim
        self.pending_spell = None  # callable(game) — fires after anim frame 2

    def range_tiles(self):
        tiles = set()
        for dx, dy in DIRS:
            nx, ny = self.gx + dx, self.gy + dy
            if 0 <= nx < COLS and 0 <= ny < ROWS:
                tiles.add((nx, ny))
        return tiles

    def overlay_color(self):
        return (180, 140, 60, 40)

    def take_turn(self, game, occupied, dist_map=None):
        px, py = game.player.gx, game.player.gy
        dist_sq = (self.gx - px) ** 2 + (self.gy - py) ** 2
        too_close = dist_sq <= self.FLEE_RANGE_SQ

        if self.cooldown == 0:
            # If too close, flee instead of summoning
            if too_close:
                self._try_flee(game, occupied, px, py, dist_map)
                self.cooldown = 1
                return
            # Summon a slime on an adjacent empty tile — defer until cast frame
            candidates = []
            for dx, dy in DIRS:
                nx, ny = self.gx + dx, self.gy + dy
                if is_passable(nx, ny) \
                        and (nx, ny) not in occupied \
                        and (nx, ny) != (px, py):
                    candidates.append((nx, ny))
            if candidates:
                sx, sy = random.choice(candidates)
                occupied.add((sx, sy))
                def _spawn_slime(game, _sx=sx, _sy=sy):
                    play_sfx("spell.wav", 0.5)
                    slime = Slime(_sx, _sy, spawning=True)
                    game.enemies.append(slime)
                self.pending_spell = _spawn_slime
                self.anim = self.attack_anim
                self.anim.index = 0
                self.anim.finished = False
                self.cooldown = 1
                return

        self.cooldown = max(0, self.cooldown - 1)
        self._try_flee(game, occupied, px, py, dist_map)

    FLEE_RANGE_SQ = 15

    def _try_flee(self, game, occupied, px, py, dist_map=None):
        dist_sq = (self.gx - px) ** 2 + (self.gy - py) ** 2
        if dist_sq > self.FLEE_RANGE_SQ:
            return
        best = None
        best_d = dist_map.get((self.gx, self.gy), 0) if dist_map else dist_sq
        for dx, dy in DIRS:
            nx, ny = self.gx + dx, self.gy + dy
            if is_passable(nx, ny) \
                    and (nx, ny) not in occupied \
                    and (nx, ny) != (px, py):
                d = dist_map.get((nx, ny), 9999) if dist_map else (nx - px) ** 2 + (ny - py) ** 2
                if d > best_d:
                    best_d = d
                    best = (nx, ny)
        if best:
            self.update_facing(best[0] - self.gx)
            self.gx, self.gy = best

    def eased(self):
        if self.pending_spell:
            return False
        if self.anim is self.attack_anim and not self.attack_anim.finished:
            return False
        return super().eased()

    def draw(self, screen):
        if self.anim is self.attack_anim and self.attack_anim.finished:
            self.anim = self.idle_anim
        self.draw_sprite(screen)


# ── Stone Golem ────────────────────────────────────────────────────
# Slow but tanky. Moves one tile toward the player every other turn.
# Attacks by slamming if cardinally adjacent. While cardinally adjacent
# to the player, the player cannot attack non-StoneGolem enemies.
CARDINAL_DIRS = [(1, 0), (-1, 0), (0, 1), (0, -1)]


class StoneGolem(Entity):
    DAMAGE = 30

    def __init__(self, gx, gy):
        super().__init__(gx, gy, (140, 140, 130), hp=120)
        self.cooldown = 0  # 0 = move+attack turn, 1 = resting
        self.idle_anim = AnimSprite(
            ["Golem_standing.png", "Golem_idle.png"], fps=2)
        self.anim = self.idle_anim
        # Attack anim state (manual 2-frame: 0.1s windup, 0.3s slam)
        self.atk_playing = False
        self.atk_timer = 0.0
        self.atk_frame = 0  # 0 = windup, 1 = slam
        self._atk_bump = None  # (dx, dy, game) — deferred to frame 2
        self.taunt_timer = 0.0  # highlight + shake when blocking an attack

    def range_tiles(self):
        tiles = set()
        for dx, dy in CARDINAL_DIRS:
            nx, ny = self.gx + dx, self.gy + dy
            if 0 <= nx < COLS and 0 <= ny < ROWS:
                tiles.add((nx, ny))
        return tiles

    def overlay_color(self):
        return (140, 140, 130, 40)

    def cardinal_adjacent_to_player(self, player):
        """True if this golem is cardinally adjacent (N/S/E/W) to the player."""
        dx = abs(self.gx - player.gx)
        dy = abs(self.gy - player.gy)
        return (dx + dy) == 1

    def take_turn(self, game, occupied, dist_map=None):
        px, py = game.player.gx, game.player.gy

        if self.cooldown > 0:
            self.cooldown -= 1
            return

        # If cardinally adjacent, slam the player
        if self.cardinal_adjacent_to_player(game.player):
            game.player.take_damage_from(self.DAMAGE, self.gx, self.gy)
            dx = game.player.gx - self.gx
            dy = game.player.gy - self.gy
            self.update_facing(dx)
            # Start manual attack anim — bump deferred to frame 2
            self.atk_playing = True
            self.atk_timer = 0.0
            self.atk_frame = 0
            self._atk_bump = (dx, dy, game)
            self.cooldown = 1
            return

        # Move one step toward the player, preferring cardinal adjacency
        best = None
        best_d = dist_map.get((self.gx, self.gy), 9999) if dist_map else (self.gx - px) ** 2 + (self.gy - py) ** 2
        best_cardinal = False  # prefer tiles cardinally adjacent to player
        for dx, dy in DIRS:
            nx, ny = self.gx + dx, self.gy + dy
            if is_passable(nx, ny) \
                    and (nx, ny) not in occupied \
                    and (nx, ny) != (px, py):
                d = dist_map.get((nx, ny), 9999) if dist_map else (nx - px) ** 2 + (ny - py) ** 2
                is_cardinal = (abs(nx - px) + abs(ny - py)) == 1
                # Prefer cardinal adjacency to player, then shortest distance
                if (is_cardinal and not best_cardinal) \
                        or (is_cardinal == best_cardinal and d < best_d):
                    best_d = d
                    best = (nx, ny)
                    best_cardinal = is_cardinal
        if best:
            self.update_facing(best[0] - self.gx)
            self.gx, self.gy = best
        self.cooldown = 1

    ATK_FRAME_DURS = [0.1, 0.3]  # windup, slam
    ATK_FRAMES = ["Golem_attack1.png", "Golem_attack2.png"]

    def start_taunt(self):
        """Flash and shake to show this golem is blocking the attack."""
        self.taunt_timer = 0.35
        dx = -0.3 + 0.6 * random.random()
        self.bump = [dx * TILE * 0.08, 0]

    def ease(self, dt):
        if self.taunt_timer > 0:
            self.taunt_timer -= dt
            # Small rapid shake while taunting
            if self.taunt_timer > 0:
                self.bump[0] = TILE * 0.04 * math.sin(self.taunt_timer * 40)
            else:
                self.taunt_timer = 0
                self.bump[0] = 0
        if self.atk_playing:
            self.atk_timer += dt
            if self.atk_frame == 0 and self.atk_timer >= self.ATK_FRAME_DURS[0]:
                # Transition to slam frame — fire bump + shake now
                self.atk_frame = 1
                self.atk_timer -= self.ATK_FRAME_DURS[0]
                if self._atk_bump:
                    dx, dy, game = self._atk_bump
                    self.start_bump(dx, dy)
                    game.player.start_bump(dx, dy)
                    game.start_shake(5, 0.12)
                    play_sfx("hit.wav", 0.5)
                    self._atk_bump = None
            elif self.atk_frame == 1 and self.atk_timer >= self.ATK_FRAME_DURS[1]:
                self.atk_playing = False
        super().ease(dt)

    def eased(self):
        if self.atk_playing:
            return False
        return super().eased()

    def draw(self, screen):
        if self.atk_playing:
            flip = self.facing_right
            img = load_sprite(self.ATK_FRAMES[self.atk_frame], flip)
            screen.blit(img, (self.pos[0] + self.bump[0],
                              self.pos[1] - 7 + self.bump[1]))
            return
        self.draw_sprite(screen)
        if self.taunt_timer > 0:
            highlight = pygame.Surface((TILE, TILE), pygame.SRCALPHA)
            alpha = int(120 * (self.taunt_timer / 0.35))
            highlight.fill((255, 200, 100, alpha))
            screen.blit(highlight, (self.pos[0] + self.bump[0],
                                    self.pos[1] + self.bump[1]))


# ── Dragon (Boss) ─────────────────────────────────────────────────
# 3x3 boss that stays on the right edge.  Attacks cycle through
# fire breath, fireball, and summoning.  Claw swipe auto-triggers
# when the player ends their turn adjacent to the dragon body.
class Dragon(Entity):
    DAMAGE = 40           # claw swipe damage

    def __init__(self, gx, gy):
        super().__init__(gx, gy, (180, 40, 40), hp=300)
        self.idle_anim = AnimSprite(
            ["Dragon_standing.png", "Dragon_idle.png"], fps=2, scale=3)
        self.attack_anim = AnimSprite(
            ["Dragon_breathe.png"], fps=2, scale=3, loop=False)
        self.anim = self.idle_anim
        self._next_is_action = False   # alternates: False=move first, True=action
        self._first_idle = True

    def body_tiles(self):
        """Return the set of 9 tiles the dragon occupies."""
        tiles = set()
        for dx in range(-1, 2):
            for dy in range(-1, 2):
                tiles.add((self.gx + dx, self.gy + dy))
        return tiles

    def adjacent_tiles(self):
        """Return tiles adjacent to body but not part of body."""
        body = self.body_tiles()
        adj = set()
        for bx, by in body:
            for dx, dy in DIRS:
                t = (bx + dx, by + dy)
                if t not in body and 0 <= t[0] < COLS and 0 <= t[1] < ROWS:
                    adj.add(t)
        return adj

    def range_tiles(self):
        return self.adjacent_tiles() | self.body_tiles()

    def _player_adjacent(self, game):
        px, py = game.player.gx, game.player.gy
        for bx, by in self.body_tiles():
            if abs(px - bx) <= 1 and abs(py - by) <= 1 and (px, py) != (bx, by):
                return True
        return False

    def _do_claw_swipe(self, game):
        """Claw swipe: always available regardless of turn type."""
        px, py = game.player.gx, game.player.gy
        adj = self.adjacent_tiles()
        swipe_tiles = {(px, py)}
        for dx, dy in DIRS:
            t = (px + dx, py + dy)
            if t in adj and t != (px, py):
                swipe_tiles.add(t)
        game.player.take_damage_from(self.DAMAGE, self.gx, self.gy)
        game.start_shake(9, 0.16)
        play_sfx("hit.wav", 0.6)
        rdx = px - self.gx
        rdy = py - self.gy
        slash_angle = math.degrees(math.atan2(-rdy, rdx)) + 180 + 90
        game.slash_vfx.append(SlashVFX(
            px, py, flip_x=True, vertical=True,
            angle=slash_angle, scale=3))
        bdx = px - self.gx
        bdy = py - self.gy
        if bdx == 0 and bdy == 0:
            bdx, bdy = -1, 0
        game.player.start_bump(bdx, bdy, strength=0.2)
        for e in game.enemies:
            if e is self or not e.alive():
                continue
            if (e.gx, e.gy) in swipe_tiles:
                e.take_damage(self.DAMAGE)

    def _do_action(self, game, occupied):
        """Perform an action turn: fire breath > fireball > random."""
        px, py = game.player.gx, game.player.gy

        # First action is always summon
        if self._first_idle:
            self._first_idle = False
            self.anim = self.attack_anim
            self.anim.index = 0
            self.anim.finished = False
            self._summon(game, occupied)
            return

        # Fire breath: player on dragon's row, to the left
        can_breath = (py == self.gy and px < self.gx - 1)
        if can_breath:
            self.anim = self.attack_anim
            self.anim.index = 0
            self.anim.finished = False
            self._fire_breath(game)
            return

        # Fireball: player within 1 row of dragon's centre
        can_fireball = (abs(py - self.gy) <= 1 and px < self.gx - 1)
        if can_fireball:
            self.anim = self.attack_anim
            self.anim.index = 0
            self.anim.finished = False
            self._fireball(game)
            return

        # Can't directly hit player: 70% summon, 30% fireball
        self.anim = self.attack_anim
        self.anim.index = 0
        self.anim.finished = False
        if random.random() < 0.7:
            self._summon(game, occupied)
        else:
            self._fireball(game)

    def take_turn(self, game, occupied, dist_map=None):
        px, py = game.player.gx, game.player.gy

        # --- Claw swipe: always available, any turn type ---
        if self._player_adjacent(game):
            self._do_claw_swipe(game)
            self._next_is_action = not self._next_is_action
            return

        if self._next_is_action:
            # --- Action turn ---
            self._next_is_action = False
            self._do_action(game, occupied)
        else:
            # --- Move turn ---
            moved = self._try_move_toward_player(py, occupied)
            self._next_is_action = True
            if not moved:
                # Didn't need to move — free action
                self._do_action(game, occupied)

    def _try_move_toward_player(self, py, occupied):
        """Move one tile up/down toward the player's row. Returns True if moved."""
        if py < self.gy and self.gy - 1 >= 1:
            new_gy = self.gy - 1
        elif py > self.gy and self.gy + 1 <= ROWS - 2:
            new_gy = self.gy + 1
        else:
            return False
        own = self.body_tiles()
        for dx in range(-1, 2):
            for dy in range(-1, 2):
                t = (self.gx + dx, new_gy + dy)
                if t in occupied and t not in own:
                    return False
        self.gy = new_gy
        return True

    def _fire_breath(self, game):
        """Beam of fire that extends leftward from the dragon, one tile wide."""
        mouth_x = int((self.gx - 1.5) * TILE + TILE // 2)
        beam = BreathBeam(mouth_x, self.gy, game)
        beam.sfx_channel = play_sfx("fire-beam.wav", 0.6)
        game.breath_beams.append(beam)

    def _fireball(self, game):
        """Fireball targeting the dragon's centre row, preferring to hit the player."""
        px, py = game.player.gx, game.player.gy
        # Prefer tiles diagonal-adjacent to the player (guarantees hit via 3x3 blast)
        aimed = [(x, self.gy) for x in range(px - 1, px + 2)
                 if 0 <= x < self.gx - 1]
        candidates = aimed if aimed else \
            [(x, self.gy) for x in range(0, self.gx - 1)]
        if not candidates:
            return
        cx, cy = random.choice(candidates)
        ox, oy = self.gx, self.gy

        def fireball_arrive(game, _cx=cx, _cy=cy):
            play_sfx("fire-swoosh.wav", 0.5)
            for ddx in range(-1, 2):
                for ddy in range(-1, 2):
                    fx, fy = _cx + ddx, _cy + ddy
                    if not (0 <= fx < COLS and 0 <= fy < ROWS):
                        continue
                    # Centre tile is permanent, outer tiles are temporary
                    turns = 999 if (ddx == 0 and ddy == 0) else 2
                    existing = None
                    for f in game.fire_tiles:
                        if f.gx == fx and f.gy == fy:
                            existing = f
                            break
                    if existing:
                        existing.turns = max(existing.turns, turns)
                    else:
                        game.fire_tiles.append(FireTile(fx, fy, turns))
            # Damage all entities on the 3x3 area
            for ddx in range(-1, 2):
                for ddy in range(-1, 2):
                    fx, fy = _cx + ddx, _cy + ddy
                    if game.player.gx == fx and game.player.gy == fy:
                        game.player.take_damage_from(
                            FireTile.DAMAGE, _cx, _cy)
                        game.start_shake(2, 0.07)
                    for e in game.enemies:
                        if e.alive() and not isinstance(e, Dragon) \
                                and e.gx == fx and e.gy == fy:
                            e.take_damage(FireTile.DAMAGE)

        proj = Projectile(self.gx - 1.5, self.gy - 0.5, cx, cy,
                          (255, 80, 20), fireball_arrive)
        game.projectiles.append(proj)
        proj.spawn_burst(game.particles)

    def _summon(self, game, occupied):
        """Spawn allies to the left of the dragon, 1 row above or below centre."""
        player_pos = (game.player.gx, game.player.gy)
        # Candidate tiles: directly left of dragon body, 1 row above or below centre
        left_col = self.gx - 2
        candidates = []
        for y in [self.gy - 1, self.gy + 1]:
                if 0 <= left_col < COLS and 0 <= y < ROWS \
                        and (left_col, y) not in occupied \
                        and (left_col, y) != player_pos:
                    candidates.append((left_col, y))
        if not candidates:
            return
        play_sfx("spell.wav", 0.5)
        random.shuffle(candidates)
        # Either 2 regular slimes, or one of any other enemy type
        if random.random() < 0.5 and len(candidates) >= 2:
            # 2 slimes
            for tx, ty in candidates[:2]:
                game.enemies.append(Slime(tx, ty, spawning=True))
                occupied.add((tx, ty))
        else:
            tx, ty = candidates[0]
            enemy_type = random.choice([Wizard, Summoner, StoneGolem, SwordSlime])
            game.enemies.append(enemy_type(tx, ty))
            occupied.add((tx, ty))

    def eased(self):
        if self.anim is self.attack_anim and not self.attack_anim.finished:
            return False
        return super().eased()

    def draw(self, screen):
        # Return to idle after attack anim finishes
        if self.anim is self.attack_anim and self.attack_anim.finished:
            self.anim = self.idle_anim
        # Draw 3x3 sprite centred on (gx, gy)
        if self.anim:
            self.anim.flip_x = self.facing_right
            img = self.anim.image()
            sx = self.pos[0] - TILE
            sy = self.pos[1] - TILE
            screen.blit(img, (sx, sy))
        # HP bar spanning 3x3
        bx = self.pos[0] - TILE + 8
        by = self.pos[1] - TILE + 8
        bw = TILE * 3 - 16
        bh = TILE * 3 - 16
        bar_w = bw
        bar_h = 10
        bar_x = bx
        bar_y = by + bh + 4
        pygame.draw.rect(screen, (40, 40, 40), (bar_x, bar_y, bar_w, bar_h))
        fill = int(bar_w * self.hp / self.max_hp)
        pygame.draw.rect(screen, (220, 50, 50), (bar_x, bar_y, fill, bar_h))


DIR_NAMES = {(0, -1): "North", (1, -1): "Northeast", (1, 0): "East",
             (1, 1): "Southeast", (0, 1): "South", (-1, 1): "Southwest",
             (-1, 0): "West", (-1, -1): "Northwest"}


# ── Instruction search helpers ────────────────────────────────────
# State is a lightweight snapshot: (px, py, mode, facing, switched,
#   [(gx, gy, hp, type_name, cooldown), ...], [(fx, fy, turns), ...])

def _snap_state(game):
    p = game.player
    enemies = []
    for e in game.enemies:
        if e.alive():
            enemies.append((e.gx, e.gy, e.hp, type(e).__name__,
                            getattr(e, 'cooldown', 0)))
    fires = [(f.gx, f.gy, f.turns) for f in game.fire_tiles]
    return (p.gx, p.gy, p.mode, p.facing, p.switched_this_turn,
            enemies, fires)



def _golem_blocks_sim(px, py, enemies):
    """Check if any alive StoneGolem is cardinally adjacent to (px, py) in sim state."""
    for gx, gy, hp, tn, cd in enemies:
        if hp <= 0:
            continue
        if tn == "StoneGolem" and (abs(gx - px) + abs(gy - py)) == 1:
            return True
    return False


def _display_name(class_name):
    """Split camelCase class name into words, e.g. 'SwordSlime' -> 'Sword Slime'."""
    import re
    return re.sub(r'(?<=[a-z])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])', ' ', class_name)


def _sim_attack(px, py, di, enemies):
    """Simulate sword cone attack. Returns (new_enemies, total_dmg, kills, label)."""
    cone = facing_cone(di)
    dmg = Player.DAMAGE
    new_enemies = list(enemies)
    total_damage = 0
    kills = 0
    label = None
    golem_blocking = _golem_blocks_sim(px, py, enemies)
    # Find indices of hit enemies
    hit_idx = []
    for i, (gx, gy, hp, tn, cd) in enumerate(new_enemies):
        if hp <= 0:
            continue
        # Stone Golem lock: cone only hits StoneGolems
        if golem_blocking and tn != "StoneGolem":
            continue
        if tn == "Dragon":
            # Hit if any body tile is in the cone
            hit = any((gx + dx - px, gy + dy - py) in cone
                      for dx in range(-1, 2) for dy in range(-1, 2))
        else:
            hit = (gx - px, gy - py) in cone
        if hit:
            hit_idx.append(i)
            if label is None:
                label = _display_name(tn)
    if not hit_idx:
        return enemies, 0, 0, None
    # Apply sword damage
    for i in hit_idx:
        gx, gy, hp, tn, cd = new_enemies[i]
        new_enemies[i] = (gx, gy, hp - dmg, tn, cd)
        total_damage += dmg
    # Knockback (skip Dragon — too big to push)
    for i in hit_idx:
        gx, gy, hp, tn, cd = new_enemies[i]
        if tn == "Dragon":
            continue
        kdx, kdy = gx - px, gy - py
        ki = direction_index(kdx, kdy)
        if ki is None:
            continue
        ddx, ddy = DIR_RING[ki]
        nx, ny = gx + ddx, gy + ddy
        blocker_i = None
        for j, (ex, ey, ehp, etn, ecd) in enumerate(new_enemies):
            if j != i and ex == nx and ey == ny:
                blocker_i = j
                break
        # Also blocked by dragon body tiles
        dragon_block = False
        for j, (ex, ey, ehp, etn, ecd) in enumerate(new_enemies):
            if etn == "Dragon" and ehp > 0 and j != i:
                if any((ex + dx, ey + dy) == (nx, ny)
                       for dx in range(-1, 2) for dy in range(-1, 2)):
                    dragon_block = True
                    break
        blocked = (not is_passable(nx, ny)
                   or blocker_i is not None
                   or dragon_block
                   or (nx, ny) == (px, py))
        if blocked:
            new_enemies[i] = (gx, gy, hp - dmg, tn, cd)
            total_damage += dmg
            if blocker_i is not None:
                bx, by, bhp, btn, bcd = new_enemies[blocker_i]
                new_enemies[blocker_i] = (bx, by, bhp - dmg, btn, bcd)
                total_damage += dmg
        else:
            new_enemies[i] = (nx, ny, hp, tn, cd)
    # Count kills
    for i in hit_idx:
        if new_enemies[i][2] <= 0:
            kills += 1
    # Remove dead
    new_enemies = [e for e in new_enemies if e[2] > 0]
    return new_enemies, total_damage, kills, label


def _priority_s(tn):
    if tn == "Dragon":
        return 4
    if tn == "Summoner":
        return 3
    if tn == "StoneGolem":
        return 3  # High priority — blocks attacks on others
    if tn == "Wizard":
        return 2
    return 1


def _dragon_min_dsq(gx, gy, px, py):
    """Minimum squared distance from player to any dragon body tile."""
    best = 9999
    for dx in range(-1, 2):
        for dy in range(-1, 2):
            d = (gx + dx - px) ** 2 + (gy + dy - py) ** 2
            if d < best:
                best = d
    return best


def _dragon_adjacent(gx, gy, px, py):
    """Check if player is adjacent to any dragon body tile."""
    for dx in range(-1, 2):
        for dy in range(-1, 2):
            bx, by = gx + dx, gy + dy
            if abs(px - bx) <= 1 and abs(py - by) <= 1 and (px, py) != (bx, by):
                return True
    return False


def _terminal_score(px, py, mode, facing, enemies, fires, player_hp):
    """Score a terminal board state (after all moves used)."""
    score = 0
    # Threat penalty (shield reduces threat weight and damage)
    # Scales with how low HP is; lethal scenarios get a massive penalty
    cone = facing_cone(facing) if mode == "shield" else set()
    b_num = Player.SHIELD_BLOCK_NUM
    b_den = Player.SHIELD_BLOCK_DEN
    threat_count_x10 = 0  # threat count * 10 (to avoid floats)
    total_incoming = 0
    for gx, gy, hp, tn, cd in enemies:
        if hp <= 0:
            continue
        is_threat = False
        dmg = 0
        if tn == "Dragon":
            # Claw swipe threat (always active, any turn type)
            if _dragon_adjacent(gx, gy, px, py):
                is_threat = True
                dmg = Dragon.DAMAGE
            # Fire breath / fireball threat (may act on action turn,
            # or on move turn if already aligned — treat as always possible)
            elif px < gx - 1:
                if py == gy:
                    is_threat = True
                    dmg = 20  # breath damage
                elif gy - 2 <= py <= gy + 2:
                    is_threat = True
                    dmg = FireTile.DAMAGE
        elif tn == "Slime":
            dsq = (gx - px) ** 2 + (gy - py) ** 2
            if dsq <= Slime.JUMP_RANGE_SQ:
                is_threat = True
                dmg = Slime.DAMAGE
        elif tn == "Wizard" and cd == 0:
            dsq = (gx - px) ** 2 + (gy - py) ** 2
            if dsq <= Wizard.SPELL_RANGE_SQ:
                is_threat = True
                dmg = Wizard.DAMAGE
        elif tn == "StoneGolem" and cd == 0:
            if (abs(gx - px) + abs(gy - py)) == 1:
                is_threat = True
                dmg = StoneGolem.DAMAGE
        if is_threat:
            blocked = False
            if cone:
                di = direction_index(gx - px, gy - py)
                if di is not None and DIR_RING[di] in cone:
                    blocked = True
            if blocked:
                threat_count_x10 += b_den - b_num  # e.g. 2 out of 10
                total_incoming += max(1, dmg * (b_den - b_num) // b_den)
            else:
                threat_count_x10 += b_den
                total_incoming += dmg
    # Scale threat penalty: base 50, increases as HP drops
    hp_ratio = max(player_hp, 1) // Player.DAMAGE  # effective hits remaining
    threat_weight = 50 + max(0, 100 - hp_ratio * 10)
    score -= threat_count_x10 * threat_weight // b_den
    # Lethal penalty: if incoming damage could kill us, massive penalty
    if total_incoming >= player_hp:
        score -= 1000
    # Fire penalty
    on_fire = False
    for fx, fy, ft in fires:
        if fx == px and fy == py:
            on_fire = True
            break
    if on_fire:
        fire_dmg = FireTile.DAMAGE
        score -= 30
        if fire_dmg >= player_hp:
            score -= 1000
    # Golem lock penalty: being cardinally adjacent to a golem blocks other attacks
    if _golem_blocks_sim(px, py, enemies):
        non_golem_count = sum(1 for _, _, hp, tn, _ in enemies
                              if hp > 0 and tn != "StoneGolem")
        if non_golem_count > 0:
            score -= 40 * non_golem_count
    # Proximity to priority target
    best_pri = 0
    for gx, gy, hp, tn, cd in enemies:
        if hp <= 0:
            continue
        if tn == "Dragon":
            d = _dragon_min_dsq(gx, gy, px, py)
            max_d = 80  # larger range for Dragon (spans most of the board)
        else:
            d = (gx - px) ** 2 + (gy - py) ** 2
            max_d = 20
        pri = _priority_s(tn)
        val = max(0, max_d - d) * pri
        if val > best_pri:
            best_pri = val
    score += best_pri
    return score


def _collect_leaves(px, py, mode, facing, switched, enemies, fires, depth,
                    followed, path, acc_score, player_hp, leaves, potions=()):
    """Recursively enumerate all move sequences, appending (total_score, followed_set, path) for each leaf."""
    if depth == 0 or not enemies:
        score = acc_score + _terminal_score(px, py, mode, facing, enemies, fires, player_hp)
        leaves.append((score, frozenset(followed), path))
        return

    occupied = set()
    for gx, gy, hp, tn, cd in enemies:
        if hp <= 0:
            continue
        if tn == "Dragon":
            for dx in range(-1, 2):
                for dy in range(-1, 2):
                    occupied.add((gx + dx, gy + dy))
        else:
            occupied.add((gx, gy))
    any_action = False

    # Attack candidates (only if in sword mode)
    if mode == "sword":
        for di in range(len(DIR_RING)):
            ddx, ddy = DIR_RING[di]
            tx, ty = px + ddx, py + ddy
            if not (0 <= tx < COLS and 0 <= ty < ROWS):
                continue
            if (tx, ty) not in occupied:
                continue
            new_en, dmg, kills, label = _sim_attack(px, py, di, enemies)
            if dmg == 0:
                continue
            any_action = True
            atk_label = f"Attack {label}" if label else None
            dbg_label = f"Attack {label}@{tx},{ty}" if label else None
            new_followed = followed | {atk_label} if atk_label else followed
            _collect_leaves(px, py, "sword", facing, switched, new_en, fires,
                            depth - 1, new_followed,
                            path + (dbg_label,) if dbg_label else path,
                            acc_score + dmg * 10 + kills * 20, player_hp, leaves,
                            potions)

    # Move candidates (8 directions)
    for ddx, ddy in DIRS:
        nx, ny = px + ddx, py + ddy
        if not is_passable(nx, ny):
            continue
        if (nx, ny) in occupied:
            continue
        any_action = True
        new_facing = facing
        if mode == "shield":
            di = direction_index(ddx, ddy)
            if di is not None:
                new_facing = di
        name = DIR_NAMES.get((ddx, ddy), "?")
        move_label = f"Move {name}"
        # Check for health potion pickup
        move_followed = followed | {move_label}
        move_score = acc_score
        new_potions = potions
        new_hp = player_hp
        for pi, (ppx, ppy) in enumerate(potions):
            if ppx == nx and ppy == ny:
                move_followed = move_followed | {"Drink Health Potion"}
                move_score += 375  # 15 HP * 10 weight * 2.5x
                new_hp = min(100, player_hp + 15)
                new_potions = potions[:pi] + potions[pi + 1:]
                break
        _collect_leaves(nx, ny, mode, new_facing, switched, enemies, fires,
                        depth - 1, move_followed,
                        path + (move_label,),
                        move_score, new_hp, leaves, new_potions)

    # Switch to shield (if not already switched)
    if not switched and mode != "shield":
        any_action = True
        for fi in range(len(DIR_RING)):
            _collect_leaves(px, py, "shield", fi, True, enemies, fires,
                            depth - 1, followed | {"Switch to Shield"},
                            path + ("Switch to Shield",),
                            acc_score, player_hp, leaves, potions)

    # Switch to sword (if currently shield and not already switched)
    if not switched and mode == "shield":
        any_action = True
        _collect_leaves(px, py, "sword", facing, True, enemies, fires,
                        depth - 1, followed | {"Switch to Sword"},
                        path + ("Switch to Sword",),
                        acc_score, player_hp, leaves, potions)

    if not any_action:
        score = acc_score + _terminal_score(px, py, mode, facing, enemies, fires, player_hp)
        leaves.append((score, frozenset(followed), path))


class Button:
    def __init__(self, rect, label, active_color, font):
        self.rect = rect
        self.label = label
        self.active_color = active_color
        self.font = font

    def draw(self, screen, active):
        color = self.active_color if active else (50, 50, 50)
        text_color = (220, 220, 220) if active else (100, 100, 100)
        pygame.draw.rect(screen, color, self.rect)
        text = self.font.render(self.label, True, text_color)
        screen.blit(text, text.get_rect(center=self.rect.center))

    def clicked(self, pos):
        return self.rect.collidepoint(pos)


LEVELS = [
    # Level 1: intro — slimes only
    lambda: [Slime(7, 3), Slime(6, 5), Slime(11, 9), Slime(13, 8)],
    # Level 2: slimes + wizards
    lambda: [Slime(6, 9), Slime(10, 3), Slime(9, 8),
             Wizard(13, 5), Wizard(5, 4)],
    # Level 3: stone golems join
    lambda: [Slime(4, 4), SwordSlime(10, 6),
             Wizard(10, 4),
             StoneGolem(3, 3), StoneGolem(7, 5)],
    # Level 4: summoner appears
    lambda: [SwordSlime(5, 3),
             Wizard(6, 7),
             Summoner(9, 2),
             Summoner(10, 7),
             StoneGolem(3, 4)],
    # Level 5: boss fight
    lambda: [
             Dragon(LEVEL_DIMS[4][0] - 3, LEVEL_DIMS[4][1] // 2)],
]


class Game:
    UI_HEIGHT = 480
    MAX_MOVES = 3

    _GOD_POSITIVE = [
        "You have done well.",
        "I am very proud of you.",
        "I shall reward your efforts.",
        "Wise to follow a wise being like me.",
        "All my children are blessed.",
        "Good.",
        "I am always correct.",
        "This is your reward for your obedience.",
        "Things are going as planned.",
        "Yes.",
        "I know what is the best for you.",
        "It is your destiny.",
        "I have planned this well.",
        "The same as what I expected.",
        "It has turned out well.",
        "Everything has gone as planned.",
        "It was written in the stars.",
        "You are a reflection of my greatness.",
    ]

    _GOD_NEGATIVE = [
        "You cannot escape your destiny.",
        "You cannot change your fate.",
        "I know what you are destined for.",
        "Is this what you are capable of?",
        "You are better than this.",
        "I have done so much for you.",
        "Do you not need me now?",
        "Do you regret your decision?",
        "Should I not help you?",
        "I should not have believed in you.",
        "The results are clear.",
        "It hurts to see this.",
        "I did see that coming.",
        "I knew it was coming.",
        "I know it hurts.",
        "Do not repeat your mistakes.",
        "What are you trying to do?",
        "We both know this will not work.",
        "Why did you do that?",
        "Why do you not listen to me?",
    ]

    def __init__(self):
        pygame.mixer.pre_init(44100, -16, 2, 512)
        pygame.init()
        preload_sfx()
        self.width = COLS * TILE
        self.height = ROWS * TILE
        self.native_w = self.width
        self.native_h = self.height + self.UI_HEIGHT
        self.display = pygame.display.set_mode(
            (self.native_w, self.native_h), pygame.RESIZABLE)
        self.screen = pygame.Surface((self.native_w, self.native_h))
        pygame.display.set_caption("Grid Game")
        self.clock = pygame.time.Clock()
        _font_path = os.path.join(os.path.dirname(__file__), "assets", "alagard.ttf")
        self.font = pygame.font.Font(_font_path, 72)
        self.small_font = pygame.font.Font(_font_path, 54)
        self.cmd_label_font = pygame.font.Font(_font_path, 60)
        self.cmd_font = pygame.font.Font(_font_path, 78)
        self.title_font = pygame.font.Font(_font_path, 136)

        self.level = 0
        self._current_bgm = None
        self._audio_check_timer = 0.0
        self._start_bgm()
        sx, sy = PLAYER_SPAWN.get(self.level, (1, ROWS // 2))
        self.player = Player(sx, sy)
        self.enemies = LEVELS[self.level]()
        self.phase = "menu"
        self._menu_timer = 0.0
        self.history = []
        self.projectiles = []
        self.particles = []
        self.slash_vfx = []
        self.breath_beams = []
        self.fire_tiles = []
        self.potions = []
        self.picking_facing = False
        self.picking_facing_state = None  # saved state before switch
        self.shake_timer = 0.0
        self.shake_intensity = 0
        self._pending_dragon_turn = False
        self._post_fade_phase = "player"
        self._intro_dragon = None
        self._intro_active = False
        self._bgm_fade_target = None
        # God apparition state
        self._god_turn_counter = 0
        self._god_next_appear = random.randint(3, 5)
        self._god_active = False
        self._god_timer = 0.0
        self._god_duration = 3.0
        self._god_fade_out = 0.0  # >0 while fading out
        self._god_message = ""
        self._god_sprite = None
        self._god_sprite_cache = {}  # filename -> Surface

        self._btn_w, self._btn_h = 300, 84
        self.undo_btn = Button(
            pygame.Rect(self.native_w - self._btn_w - 36, 60, self._btn_w, self._btn_h),
            "Undo", (160, 120, 60), self.font,
        )
        self.confirm_btn = Button(
            pygame.Rect(self.native_w - self._btn_w - 36, 162, self._btn_w, self._btn_h),
            "Confirm", (60, 160, 60), self.font,
        )
        self.instruction = self.best_instruction()
        self.followed_instruction = False
        self._last_instruction = self.instruction
        self._inst_glow_timer = 0.0
        self._golden_flash = 0.0
        self._fw_popup = None  # (text, timer) e.g. ("-10", 1.0)
        self._dmg_popups = []  # [(text, timer, px, py), ...]
        # Preload tablet background (raw + scaled for current level)
        _tab_path = os.path.join(ASSET_DIR, "Tablet.png")
        self._tablet_img_raw = pygame.image.load(_tab_path).convert_alpha()
        self._tablet_img = pygame.transform.smoothscale(
            self._tablet_img_raw, (self.native_w, self.UI_HEIGHT))
        # Preload level floor assets (raw, scaled on level change)
        _load = lambda n: pygame.image.load(os.path.join(ASSET_DIR, n)).convert_alpha()
        self._floor_layers_raw = {
            0: [_load("floor1-l1.png")],
            1: [_load("floor1-l2.png")],
            2: [_load("floor2-l1.png")],
            3: [_load("floor2-l2.png")],
            4: [_load("floor3.png")],
        }
        grid_w, grid_h = COLS * TILE, ROWS * TILE
        self._floor_layers_scaled = [
            pygame.transform.scale(layer, (grid_w, grid_h))
            for layer in self._floor_layers_raw.get(self.level, [])
        ]

    def _screen_to_native(self, pos):
        """Convert display coordinates to internal surface coordinates."""
        dw, dh = self.display.get_size()
        scale = min(dw / self.native_w, dh / self.native_h)
        ow = int(self.native_w * scale)
        oh = int(self.native_h * scale)
        ox = (dw - ow) // 2
        oy = (dh - oh) // 2
        nx = int((pos[0] - ox) / scale)
        ny = int((pos[1] - oy) / scale)
        return nx, ny

    def save_state(self):
        p = self.player
        return (p.gx, p.gy, p.hp, p.mode, p.facing, p.facing_right,
                p.switched_this_turn, p.free_will,
                self.followed_instruction,
                [(e.gx, e.gy, e.hp, e.shield,
                  getattr(e, 'cooldown', 0),
                  getattr(e, 'attack_pattern', 0),
                  getattr(e, '_dropped_potion', False))
                 for e in self.enemies],
                [(f.gx, f.gy, f.turns) for f in self.fire_tiles],
                [(pot.gx, pot.gy) for pot in self.potions])

    def restore_state(self, state):
        (pgx, pgy, php, pmode, psfacing, pfacing_right, pswitch, pfw,
         followed, enemy_states, fire_states, *rest) = state
        potion_states = rest[0] if rest else []
        p = self.player
        p.gx, p.gy, p.hp = pgx, pgy, php
        p.mode, p.facing = pmode, psfacing
        p.facing_right = pfacing_right
        p.switched_this_turn = pswitch
        p.free_will = pfw
        self.followed_instruction = followed
        for e, es in zip(self.enemies, enemy_states):
            ex, ey, ehp, eshield, ecd, eap = es[:6]
            edp = es[6] if len(es) > 6 else False
            e.gx, e.gy, e.hp, e.shield = ex, ey, ehp, eshield
            e._dropped_potion = edp
            if hasattr(e, 'cooldown'):
                e.cooldown = ecd
            if hasattr(e, 'attack_pattern'):
                e.attack_pattern = eap
        self.fire_tiles = [FireTile(fx, fy, ft) for fx, fy, ft in fire_states]
        self.potions = [HealthPotion(px, py) for px, py in potion_states]

    def undo(self):
        if self.history:
            self.restore_state(self.history.pop())

    def _tile_has_enemy(self, gx, gy):
        """Check if a tile is occupied by any alive enemy (including dragon body)."""
        for e in self.enemies:
            if not e.alive():
                continue
            if isinstance(e, Dragon):
                if (gx, gy) in e.body_tiles():
                    return True
            elif e.gx == gx and e.gy == gy:
                return True
        return False

    def _try_pickup_potion(self, gx, gy):
        """Pick up all health potions at (gx, gy)."""
        picked = [pot for pot in self.potions if pot.gx == gx and pot.gy == gy]
        if picked:
            for pot in picked:
                self.player.hp = min(self.player.max_hp,
                                     self.player.hp + HealthPotion.HEAL)
                self.potions.remove(pot)
            # Red-purple particle burst
            cx = gx * TILE + TILE // 2
            cy = gy * TILE + TILE // 2
            for _ in range(24):
                angle = random.uniform(0, 2 * math.pi)
                speed = random.uniform(40, 160)
                vx = math.cos(angle) * speed
                vy = math.sin(angle) * speed - 30
                r = random.randint(180, 255)
                g = random.randint(20, 60)
                b = random.randint(80, 180)
                life = random.uniform(0.5, 1.2)
                rot = random.uniform(-300, 300)
                self.particles.append([cx, cy, vx, vy, life, (r, g, b),
                                       random.uniform(0, 360), rot, life, 1.2])
            self._check_instruction("Pick up Health Potion")
            play_sfx("potion.wav", 0.4)

    def _spawn_dmg_popup(self, amount, gx, gy):
        """Spawn a rising '-X' popup at grid position."""
        if amount <= 0:
            return
        px = gx * TILE + TILE // 2
        py = gy * TILE + TILE // 2
        self._dmg_popups.append((f"-{amount}", 0.8, px, py))

    def _golem_blocks_attack(self):
        """True if any alive StoneGolem is cardinally adjacent to the player."""
        for e in self.enemies:
            if isinstance(e, StoneGolem) and e.alive() \
                    and e.cardinal_adjacent_to_player(self.player):
                return True
        return False

    def start_shake(self, intensity, duration):
        """Trigger screen shake with exact pixel intensity and duration."""
        if intensity > self.shake_intensity or self.shake_timer <= 0:
            self.shake_intensity = intensity
        self.shake_timer = max(self.shake_timer, duration)

    def _check_instruction(self, action_label):
        """Mark followed if action matches the current instruction (first time only)."""
        if not self.followed_instruction and action_label == self.instruction:
            self.followed_instruction = True
            self.player.free_will = max(0, self.player.free_will - 10)
            self._golden_flash = 0.4
            self._fw_popup = ("-10", 1.0)

    def handle_click(self, pos):
        mx, my = pos
        # Buttons use raw coordinates (they sit in the tablet at top)
        # Grid clicks need my offset by UI_HEIGHT
        grid_my = my - self.UI_HEIGHT
        p = self.player
        if self.confirm_btn.clicked(pos) and len(self.history) > 0:
            # Increase free will if instruction was never followed this turn
            if not self.followed_instruction:
                p.free_will = min(100, p.free_will + 10)
                self._fw_popup = ("+10", 1.0)
            # Free will depleted — puppet death
            if p.free_will <= 0:
                self.phase = "dying"
                self.fade_alpha = 0
                self.fade_direction = 1
                self._death_type = "puppet"
                try:
                    pygame.mixer.music.fadeout(1500)
                except Exception:
                    pass
                return
            self.phase = "animating"
            # Reset shields at start of enemy phase
            for e in self.enemies:
                e.shield = 0
            occupied = set()
            for e in self.enemies:
                if e.alive():
                    if isinstance(e, Dragon):
                        occupied.update(e.body_tiles())
                    else:
                        occupied.add((e.gx, e.gy))
            # If the dragon just fell, skip all enemy turns (moral choice pending)
            dragon_fallen = any(isinstance(e, Dragon) and not e.alive()
                                for e in self.enemies)
            # Non-dragon enemies act now; dragons deferred
            if not dragon_fallen:
                dist_map = bfs_distance(p.gx, p.gy, self.level)
                for e in list(self.enemies):
                    if e.alive() and not isinstance(e, Dragon):
                        occupied.discard((e.gx, e.gy))
                        e.update_facing(p.gx - e.gx)
                        e.take_turn(self, occupied, dist_map)
                        e.update_facing(p.gx - e.gx)
                        occupied.add((e.gx, e.gy))
            # Queue dragon turns for after animations finish
            self._pending_dragon_turn = not dragon_fallen
            self.history.clear()
        elif self.undo_btn.clicked(pos):
            if self.picking_facing:
                # Cancel the pending shield switch
                self.restore_state(self.picking_facing_state)
                self.picking_facing = False
                self.picking_facing_state = None
            else:
                self.undo()
        elif self.picking_facing and 0 <= grid_my < self.height:
            # Waiting for player to pick shield facing direction
            gx, gy = mx // TILE, grid_my // TILE
            dx, dy = gx - p.gx, gy - p.gy
            di = direction_index(dx, dy)
            if di is not None:
                play_sfx("shield.wav", 0.5)
                p.facing = di
                for ddx, ddy in facing_cone(di):
                    tx = (p.gx + ddx) * TILE + TILE // 2
                    ty = (p.gy + ddy) * TILE + TILE // 2
                    for _ in range(4):
                        px = tx + random.uniform(-TILE * 0.4, TILE * 0.4)
                        py = ty + random.uniform(-TILE * 0.4, TILE * 0.4)
                        vx = random.uniform(-80, 80)
                        vy = random.uniform(-80, 80)
                        sv = random.randint(180, 230)
                        life = random.uniform(0.2, 0.45)
                        self.particles.append([px, py, vx, vy,
                                               life, (sv, sv, sv),
                                               random.uniform(0, 360),
                                               random.uniform(-300, 300),
                                               life, 0.4])
                self.history.append(self.picking_facing_state)
                self.picking_facing = False
                self.picking_facing_state = None
                self._check_instruction("Switch to Shield")
        elif 0 <= grid_my < self.height and len(self.history) < self.MAX_MOVES:
            gx, gy = mx // TILE, grid_my // TILE
            # Click on own tile to switch modes
            if gx == p.gx and gy == p.gy and not p.switched_this_turn:
                if p.mode == "sword":
                    # Switch to shield — enter facing pick mode
                    self.picking_facing_state = self.save_state()
                    p.mode = "shield"
                    p.switched_this_turn = True
                    self.picking_facing = True
                else:
                    # Switch to sword — immediate, costs one move
                    before = self.save_state()
                    p.mode = "sword"
                    p.switched_this_turn = True
                    self.history.append(before)
                    self._check_instruction("Switch to Sword")
                return
            # In sword mode, try attacking an enemy at the clicked tile
            golem_blocking = self._golem_blocks_attack()
            target_enemy = None
            if p.mode == "sword":
                for e in self.enemies:
                    if not e.alive():
                        continue
                    # Stone Golem lock: can only target StoneGolems
                    if golem_blocking and not isinstance(e, StoneGolem):
                        continue
                    if isinstance(e, Dragon):
                        if (gx, gy) not in e.body_tiles():
                            continue
                    elif e.gx != gx or e.gy != gy:
                        continue
                    if not p.can_hit(gx, gy):
                        continue
                    target_enemy = e
                    break
            # Golem taunt: player tried to attack a non-golem enemy but golem blocks
            if not target_enemy and golem_blocking and p.mode == "sword" and p.can_hit(gx, gy):
                for e in self.enemies:
                    if not e.alive():
                        continue
                    if isinstance(e, StoneGolem):
                        continue
                    if isinstance(e, Dragon):
                        if (gx, gy) not in e.body_tiles():
                            continue
                    elif e.gx != gx or e.gy != gy:
                        continue
                    # There IS an enemy here, but golem is blocking — taunt
                    for g in self.enemies:
                        if isinstance(g, StoneGolem) and g.alive() \
                                and g.cardinal_adjacent_to_player(p):
                            g.start_taunt()
                    break
            if target_enemy:
                before = self.save_state()
                # Build cone around the clicked direction
                dx, dy = gx - p.gx, gy - p.gy
                p.update_facing(dx)
                di = direction_index(dx, dy)
                cone = facing_cone(di) if di is not None else set()
                hit_enemies = []
                for e in self.enemies:
                    if not e.alive():
                        continue
                    # Stone Golem lock: cone only hits StoneGolems
                    if golem_blocking and not isinstance(e, StoneGolem):
                        continue
                    if isinstance(e, Dragon):
                        # Hit if any body tile is in the cone
                        if any((bx - p.gx, by - p.gy) in cone
                               for bx, by in e.body_tiles()):
                            hit_enemies.append(e)
                    elif (e.gx - p.gx, e.gy - p.gy) in cone:
                        hit_enemies.append(e)
                # Player lunges toward target
                p.start_bump(dx, dy)
                self.shake_timer = 0.12
                self.shake_intensity = 4
                play_sfx("hit.wav", 0.5)
                # Spawn slash VFX on the clicked target tile
                if dy == 0:
                    # Horizontal — side slash
                    self.slash_vfx.append(SlashVFX(gx, gy, flip_x=dx > 0))
                elif dx == 0:
                    # Vertical — clockwise when facing right, anticlockwise when facing left
                    facing_flip = not p.facing_right
                    if dy > 0:
                        # Attacking down: flip both axes to preserve rotation direction
                        self.slash_vfx.append(SlashVFX(gx, gy, flip_x=not facing_flip, flip_y=True, vertical=True))
                    else:
                        self.slash_vfx.append(SlashVFX(gx, gy, flip_x=facing_flip, vertical=True))
                else:
                    # Diagonal — vertical slash rotated
                    if dx > 0:
                        angle = -45 if dy < 0 else -135
                        self.slash_vfx.append(SlashVFX(gx, gy, vertical=True, angle=angle))
                    else:
                        angle = 45 if dy < 0 else 135
                        self.slash_vfx.append(SlashVFX(gx, gy, flip_x=True, vertical=True, angle=angle))
                # 1. Deal sword damage to all hit enemies
                for target in hit_enemies:
                    target.take_damage(Player.DAMAGE)
                # 2. Knockback or bump (skip Dragon — too big to push)
                for target in hit_enemies:
                    if isinstance(target, Dragon):
                        continue
                    kdx = target.gx - p.gx
                    kdy = target.gy - p.gy
                    ki = direction_index(kdx, kdy)
                    if ki is not None:
                        ddx, ddy = DIR_RING[ki]
                        nx = target.gx + ddx
                        ny = target.gy + ddy
                        blocker = None
                        for e in self.enemies:
                            if e is not target \
                                    and e.gx == nx and e.gy == ny:
                                blocker = e
                                break
                        # Also blocked by dragon body tiles
                        dragon_blocker = None
                        for e in self.enemies:
                            if isinstance(e, Dragon) and e is not target \
                                    and e.alive() \
                                    and (nx, ny) in e.body_tiles():
                                dragon_blocker = e
                                break
                        blocked = (not is_passable(nx, ny)
                                   or blocker is not None
                                   or dragon_blocker is not None
                                   or (nx, ny) == (p.gx, p.gy))
                        if blocked:
                            target.start_bump(ddx, ddy)
                            target.take_damage(Player.DAMAGE)
                            if blocker:
                                blocker.pending_bump = (0.1, ddx, ddy, 0.2, Player.DAMAGE)
                            elif dragon_blocker:
                                dragon_blocker.take_damage(Player.DAMAGE)
                        else:
                            target.gx, target.gy = nx, ny
                # Immediately drop potions for all enemies killed this attack
                for e in self.enemies:
                    if not e.alive() and not getattr(e, '_dropped_potion', False) \
                            and not isinstance(e, Dragon):
                        e._dropped_potion = True
                        self.potions.append(HealthPotion(e.gx, e.gy))
                self.history.append(before)
                self._check_instruction(f"Attack {_display_name(type(target_enemy).__name__)}")
            elif p.mode == "sword":
                # No enemy to attack — move
                if not self._tile_has_enemy(gx, gy):
                    before = self.save_state()
                    if p.try_move(gx, gy):
                        dx, dy = gx - before[0], gy - before[1]
                        name = DIR_NAMES.get((dx, dy), "?")
                        self._check_instruction(f"Move {name}")
                        self._try_pickup_potion(gx, gy)
                        self.history.append(before)
            elif p.mode == "shield":
                # In shield mode, clicking a tile turns facing in place
                dx, dy = gx - p.gx, gy - p.gy
                di = direction_index(dx, dy)
                if di is not None and di != p.facing:
                    before = self.save_state()
                    p.facing = di
                    for ddx, ddy in facing_cone(di):
                        tx = (p.gx + ddx) * TILE + TILE // 2
                        ty = (p.gy + ddy) * TILE + TILE // 2
                        for _ in range(4):
                            px = tx + random.uniform(-TILE * 0.4, TILE * 0.4)
                            py = ty + random.uniform(-TILE * 0.4, TILE * 0.4)
                            vx = random.uniform(-80, 80)
                            vy = random.uniform(-80, 80)
                            sv = random.randint(180, 230)
                            life = random.uniform(0.2, 0.45)
                            self.particles.append([px, py, vx, vy,
                                                   life, (sv, sv, sv),
                                                   random.uniform(0, 360),
                                                   random.uniform(-300, 300),
                                                   life, 0.4])
                    self.history.append(before)
                    return
                # If same facing, try to move
                if not self._tile_has_enemy(gx, gy):
                    before = self.save_state()
                    if p.try_move(gx, gy):
                        dx, dy = gx - before[0], gy - before[1]
                        name = DIR_NAMES.get((dx, dy), "?")
                        self._check_instruction(f"Move {name}")
                        self._try_pickup_potion(gx, gy)
                        self.history.append(before)

    def update(self, dt):
        # Periodically check if audio device died and revive it
        self._audio_check_timer -= dt
        if self._audio_check_timer <= 0:
            self._audio_check_timer = 3.0
            try:
                # BGM should always be playing; if it isn't, audio likely died
                if self._current_bgm and self.phase not in ("dying", "dead") and not pygame.mixer.music.get_busy():
                    if _reinit_mixer():
                        self._current_bgm = None
                        self._start_bgm()
            except Exception:
                # get_busy itself threw — mixer is definitely dead
                try:
                    if _reinit_mixer():
                        self._current_bgm = None
                        self._start_bgm()
                except Exception:
                    pass
        if self.shake_timer > 0:
            self.shake_timer -= dt
            if self.shake_timer <= 0:
                self.shake_timer = 0
        # BGM volume fade
        if self._bgm_fade_target is not None:
            try:
                vol = pygame.mixer.music.get_volume()
                diff = self._bgm_fade_target - vol
                if abs(diff) < 0.01:
                    pygame.mixer.music.set_volume(self._bgm_fade_target)
                    self._bgm_fade_target = None
                else:
                    pygame.mixer.music.set_volume(vol + diff * min(2.0 * dt, 1.0))
            except Exception:
                self._bgm_fade_target = None
        # Instruction glow timer
        if self._inst_glow_timer > 0:
            self._inst_glow_timer = max(0, self._inst_glow_timer - dt)
        if self._golden_flash > 0:
            self._golden_flash = max(0, self._golden_flash - dt)
        if self._fw_popup is not None:
            text, timer = self._fw_popup
            timer -= dt
            if timer <= 0:
                self._fw_popup = None
            else:
                self._fw_popup = (text, timer)
        self._dmg_popups = [(t, tmr - dt, px, py)
                            for t, tmr, px, py in self._dmg_popups if tmr - dt > 0]
        if self.instruction != self._last_instruction:
            self._last_instruction = self.instruction
            self._inst_glow_timer = 1.5
            play_sfx("divine.wav", 0.5)
        # God apparition timer (drives fade-in; dismissed on click with fade-out)
        if self._god_active:
            self._god_timer += dt
            if self._god_fade_out > 0:
                self._god_fade_out -= dt
                if self._god_fade_out <= 0:
                    self._god_fade_out = 0.0
                    self._god_active = False
        if self.phase != "dragon_intro":
            self.player.ease(dt)
        for e in self.enemies:
            if self.phase == "dragon_intro" and e is self._intro_dragon:
                # Only update animation, don't lerp position
                if e.anim:
                    e.anim.update(dt)
            else:
                e.ease(dt)
            # Drop potion immediately when an enemy dies (e.g. knockback)
            if not e.alive() and not getattr(e, '_dropped_potion', False) \
                    and not isinstance(e, Dragon):
                e._dropped_potion = True
                self.potions.append(HealthPotion(e.gx, e.gy))
            # Fire pending spells — summoner waits until anim finishes
            if hasattr(e, 'pending_spell') and e.pending_spell \
                    and e.anim is e.attack_anim:
                fire = e.anim.finished if isinstance(e, Summoner) \
                    else e.anim.index >= 1
                if fire:
                    e.pending_spell(self)
                    e.pending_spell = None
        for p in self.projectiles:
            p.update(dt)
            p.spawn_particles(self.particles)
        # Apply arrival callbacks and remove arrived projectiles
        remaining = []
        for p in self.projectiles:
            if p.arrived():
                p.spawn_burst(self.particles)
                p.on_arrive(self)
            else:
                remaining.append(p)
        self.projectiles = remaining
        # Update breath beams
        for beam in self.breath_beams:
            beam.update(dt, self)
        for beam in self.breath_beams:
            if beam.done and getattr(beam, 'sfx_channel', None) is not None:
                try:
                    beam.sfx_channel.fadeout(800)
                except Exception:
                    pass
                beam.sfx_channel = None
        self.breath_beams = [b for b in self.breath_beams if not b.done]
        # Collect damage popups from all entities
        for ent in [self.player] + self.enemies:
            pops = getattr(ent, '_pending_popups', None)
            if pops:
                for dmg in pops:
                    self._spawn_dmg_popup(dmg, ent.gx, ent.gy)
                ent._pending_popups = []
        # Fire tile rising particles
        for f in self.fire_tiles:
            if random.random() < 0.05:
                px = f.gx * TILE + random.uniform(TILE * 0.2, TILE * 0.8)
                py = f.gy * TILE + random.uniform(TILE * 0.2, TILE * 0.8)
                vx = random.uniform(-10, 10)
                vy = random.uniform(-60, -20)
                r = min(255, 200 + random.randint(0, 55))
                g = max(0, 80 + random.randint(-30, 60))
                b = max(0, random.randint(0, 30))
                angle = random.uniform(0, 360)
                rot_speed = random.uniform(-200, 200)
                life = random.uniform(0.6, 1.5)
                self.particles.append([px, py, vx, vy,
                                       life, (r, g, b),
                                       angle, rot_speed, life, 0.4])
        # Update particles
        for pt in self.particles:
            pt[0] += pt[2] * dt
            pt[1] += pt[3] * dt
            pt[4] -= dt
            pt[6] += pt[7] * dt
        self.particles = [pt for pt in self.particles if pt[4] > 0]
        # Update slash VFX
        for s in self.slash_vfx:
            s.update(dt)
        self.slash_vfx = [s for s in self.slash_vfx if not s.done]

        if self.phase == "animating":
            all_done = (self.player.eased()
                        and all(e.eased() for e in self.enemies)
                        and not self.projectiles
                        and not self.breath_beams)
            if all_done and self._pending_dragon_turn:
                # Run dragon turns now that other enemies are done
                self._pending_dragon_turn = False
                p = self.player
                occupied = {(p.gx, p.gy)}
                for e in self.enemies:
                    if e.alive():
                        if isinstance(e, Dragon):
                            occupied.update(e.body_tiles())
                        else:
                            occupied.add((e.gx, e.gy))
                for e in self.enemies:
                    if e.alive() and isinstance(e, Dragon):
                        occupied -= e.body_tiles()
                        e.take_turn(self, occupied, None)
                        occupied.update(e.body_tiles())
                return
            if all_done:
                self.phase = "player"
                self.player.commit()
                self.player.mode = "sword"
                self.followed_instruction = False
                # Fire tiles burn entities standing on them
                for f in self.fire_tiles:
                    if self.player.gx == f.gx and self.player.gy == f.gy:
                        self.player.take_damage_from(
                            FireTile.DAMAGE, f.gx, f.gy)
                        self.start_shake(2, 0.07)
                    for e in self.enemies:
                        if e.alive() and not isinstance(e, Dragon) \
                                and e.gx == f.gx and e.gy == f.gy:
                            e.take_damage(FireTile.DAMAGE)
                # Tick down fire tiles
                for f in self.fire_tiles:
                    f.turns -= 1
                self.fire_tiles = [f for f in self.fire_tiles if f.turns > 0]
                # Drop health potions for newly dead enemies
                for e in self.enemies:
                    if not e.alive() and not getattr(e, '_dropped_potion', False) \
                            and not isinstance(e, Dragon):
                        e._dropped_potion = True
                        self.potions.append(HealthPotion(e.gx, e.gy))
                self.enemies = [e for e in self.enemies if e.alive()
                                or not e.eased()
                                or isinstance(e, Dragon)]
                self.history.clear()
                # Check if player died
                if not self.player.alive():
                    self.phase = "dying"
                    self.fade_alpha = 0
                    self.fade_direction = 1
                    self._death_type = "hp"
                    try:
                        pygame.mixer.music.fadeout(1500)
                    except Exception:
                        pass
                    return
                # Check if dragon just died — moral choice cutscene
                for e in self.enemies:
                    if isinstance(e, Dragon) and not e.alive() \
                            and not getattr(self, '_dragon_choice_started', False):
                        self._start_dragon_choice(e)
                        return
                # Check if all enemies are dead — fade to next level
                if not any(e.alive() for e in self.enemies):
                    if self.level + 1 >= len(LEVELS):
                        self.phase = "victory"
                    else:
                        self.phase = "fading"
                        self.fade_alpha = 0
                        self.fade_direction = 1  # fading out
                    return
                self.instruction = self.best_instruction()
                # God apparition check
                self._god_turn_counter += 1
                if self._god_turn_counter >= self._god_next_appear:
                    self._god_turn_counter = 0
                    self._god_next_appear = random.randint(3, 5)
                    fw = self.player.free_will
                    if fw <= 25:
                        self._god_sprite = "God_approval.png"
                    elif fw <= 50:
                        self._god_sprite = "God_commanding.png"
                    elif fw <= 75:
                        self._god_sprite = "God_frustrated.png"
                    else:
                        self._god_sprite = "God_control.png"
                    if fw <= 50:
                        self._god_message = random.choice(self._GOD_POSITIVE)
                    else:
                        self._god_message = random.choice(self._GOD_NEGATIVE)
                    self._god_active = True
                    self._god_timer = 0.0

        if self.phase == "dragon_choice":
            self._update_dragon_choice(dt)

        if self.phase == "opening":
            self._update_opening(dt)

        if self.phase == "dying":
            self.fade_alpha += 200 * dt
            if self.fade_alpha >= 255:
                self.fade_alpha = 255
                self.phase = "dead"
                self._dead_timer = 0.0

        if self.phase == "dead":
            self._dead_timer += dt

        if self.phase == "victory_custom":
            self._vc_timer = getattr(self, '_vc_timer', 0.0) + dt

        if self.phase == "fading":
            fade_speed = 300
            # Level 5: hold black for 2s before fading in
            if self.fade_direction == -1 and self.level == 4:
                self._fade_hold = getattr(self, '_fade_hold', 0.0)
                if self._fade_hold < 3.0:
                    self._fade_hold += dt
                    self.fade_alpha = 255
                    return
            self.fade_alpha += self.fade_direction * fade_speed * dt
            if self.fade_direction == 1 and self.fade_alpha >= 255:
                # Fully black — load next level, start fading back in
                self.fade_alpha = 255
                self._start_next_level()
                self.phase = "fading"
                self.fade_direction = -1
                # Level 5: start music at full volume immediately
                if self.level == 4:
                    try:
                        pygame.mixer.music.set_volume(1.0)
                    except Exception:
                        pass
                    self._fade_hold = 0.0
            elif self.fade_direction == -1 and self.fade_alpha <= 0:
                # Fade-in complete
                self.fade_alpha = 0
                target = getattr(self, '_post_fade_phase', 'player')
                print(f"[DEBUG] fade-in complete, _post_fade_phase={target}")
                self.phase = target

        if self.phase == "dragon_intro":
            if not getattr(self, '_intro_active', False):
                self._start_dragon_intro()
            self._update_dragon_intro(dt)

    def _start_next_level(self):
        """Advance to the next level after clearing the current one."""
        if self.level + 1 >= len(LEVELS):
            self.phase = "victory"
            return
        self._go_to_level(self.level + 1)

    # BGM: level 0-1 → bgm1, level 2-3 → bgm2, level 4 → bgm3
    _BGM_MAP = {0: "bgm1.mp3", 1: "bgm1.mp3", 2: "bgm2.mp3", 3: "bgm2.mp3", 4: "bgm3.mp3"}

    def _start_bgm(self):
        """Play the correct BGM for the current level, looping. No-op if already playing."""
        track = self._BGM_MAP.get(self.level, "bgm1.mp3")
        if track == self._current_bgm:
            return
        self._current_bgm = track
        path = os.path.join(ASSET_DIR, track)
        try:
            pygame.mixer.music.load(path)
            pygame.mixer.music.set_volume(0.4)
            pygame.mixer.music.play(-1)
        except Exception:
            pass

    def _go_to_level(self, level):
        """Jump to a specific level index. Used by level transitions and cheats."""
        global COLS, ROWS, _current_level
        if level < 0 or level >= len(LEVELS):
            return
        self.level = level
        _current_level = level
        # Update grid dimensions for this level
        COLS, ROWS = LEVEL_DIMS.get(level, LEVEL_DIMS[0])
        self.width = COLS * TILE
        self.height = ROWS * TILE
        self.native_w = self.width
        self.native_h = self.height + self.UI_HEIGHT
        self.screen = pygame.Surface((self.native_w, self.native_h))
        self._tablet_img = pygame.transform.smoothscale(
            self._tablet_img_raw, (self.native_w, self.UI_HEIGHT))
        # Rescale floor layers for new grid size
        grid_w, grid_h = COLS * TILE, ROWS * TILE
        self._floor_layers_scaled = [
            pygame.transform.scale(layer, (grid_w, grid_h))
            for layer in self._floor_layers_raw.get(level, [])
        ]
        # Reposition buttons for new width
        self.undo_btn.rect.x = self.native_w - self._btn_w - 36
        self.confirm_btn.rect.x = self.native_w - self._btn_w - 36
        self._start_bgm()
        p = self.player
        # Reset player position and state
        sx, sy = PLAYER_SPAWN.get(level, (1, ROWS // 2))
        p.gx, p.gy = sx, sy
        p.pos = [sx * TILE, sy * TILE]
        p.committed = [sx, sy]
        p.mode = "sword"
        p.facing_right = True
        p.switched_this_turn = False
        # Spawn new enemies
        self.enemies = LEVELS[self.level]()
        self.fire_tiles.clear()
        # Final level: fire on all impassable tiles
        if level == 4:
            p_grid = PASSABILITY.get(4)
            if p_grid:
                for ry, row in enumerate(p_grid):
                    for rx, val in enumerate(row):
                        if val == 0:
                            self.fire_tiles.append(FireTile(rx, ry, 999, visible=False))
        self.potions.clear()
        self.breath_beams.clear()
        self._pending_dragon_turn = False
        self._dragon_choice_started = False
        self.projectiles.clear()
        self.particles.clear()
        self.slash_vfx.clear()
        self._dmg_popups.clear()
        self.history.clear()
        self.picking_facing = False
        self.picking_facing_state = None
        self.followed_instruction = False
        if self.level != 4:
            self.instruction = self.best_instruction()
        # Dragon intro cutscene for level 5
        if self.level == 4:
            self._post_fade_phase = "dragon_intro"
            # Hide player and dragon offscreen during fade-in
            p.gx, p.gy = -5, -5
            p.pos = [-5 * TILE, -5 * TILE]
            p.committed = [-5, -5]
            for e in self.enemies:
                if isinstance(e, Dragon):
                    e.gx = COLS + 2
                    e.pos = [e.gx * TILE, e.gy * TILE]
        else:
            self._post_fade_phase = "player"
        self.phase = self._post_fade_phase

    # ── Opening narration ─────────────────────────────────────────────
    _OPENING_NARRATION = [
        {"speaker": None,
         "text": "In the dawn of the New World, two Gods held the balance: Thrylos, the Order of the Felis Catus, and Argoleia, the Pack of Canis Lupus."},
        {"speaker": None,
         "text": "Then came the Prophecy of Kaironth. Where Thrylos saw an omen of ash and ruin... Argoleia saw the fire of a necessary rebirth."},
        {"speaker": "thrylos",
         "text": "My loyal warrior, the fragile peace of this world strains under Kaironth's shadow."},
        {"speaker": "thrylos",
         "text": "It is your destiny to go forth as the blade of my will."},
        {"speaker": "thrylos",
         "text": "Heed my advice, and we shall emerge victorious together."},
        {"speaker": "thrylos",
         "text": "Strike down the Dragon Kaironth, and eternity shall remember your obedience."},
    ]

    def _start_opening(self):
        self.phase = "opening"
        self._op_index = 0
        self._op_alpha = 0.0
        self._op_god_alpha = 0
        self._op_timer = 0.0

    def _advance_opening(self):
        self._op_index += 1
        self._op_timer = 0.0
        self._op_alpha = 0.0
        if self._op_index >= len(self._OPENING_NARRATION):
            self.phase = "player"

    def _update_opening(self, dt):
        self._op_timer += dt
        self._op_alpha = min(255.0, self._op_alpha + 400 * dt)
        entry = self._OPENING_NARRATION[self._op_index]
        if entry["speaker"] == "thrylos":
            target = min(180, int(self._op_alpha * 180 / 255))
            self._op_god_alpha = max(self._op_god_alpha, target)
        else:
            self._op_god_alpha = max(0, self._op_god_alpha - int(400 * dt))

    # ── Dragon death choice cutscene ─────────────────────────────────
    _DC_NARRATION = [
        {"speaker": "thrylos",
         "text": 'The blade is in your hand, my loyal warrior. The Order of the Felis Catus demands its tithe of blood. Silence the beast.'},
        {"speaker": None,
         "text": "The Dragon Kaironth looks pitiful as it lays broken on the ground. You had expected a monster of ancient malice, but you see only the shivering pulse of a creature too young for its own legend."},
        {"speaker": None,
         "text": "You once felt its fire in the heat of battle... but now, you feel its fear. It is not a bringer of ruin. It is just a child of the Prophecy, chained to a fate it never chose."},
        {"speaker": None,
         "text": "Just as you are chained to the will of Thrylos."},
        {"speaker": None,
         "text": "...Or are you?"},
        {"speaker": None,
         "text": "The blade feels heavy in your hands as you weigh your options."},
    ]

    def _start_dragon_choice(self, dragon):
        """Begin the Kill / Mercy moral choice after the dragon falls."""
        self.phase = "dragon_choice"
        self._dragon_choice_started = True
        self._dc_dragon = dragon
        self._dc_timer = 0.0
        self._dc_phase = "narration"  # narration → god_fadein → buttons → kill_anim / mercy_shake / mercy_success → victory_fade
        self._dc_narr_index = 0
        self._dc_narr_alpha = 0.0       # fade-in alpha for current line
        self._dc_god_alpha = 0.0
        self._dc_buttons_visible = False
        self._dc_dragon_alpha = 255
        self._dc_slash = None
        self._dc_victory_text = None
        # Create choice buttons (centred at bottom)
        bw, bh = 300, 84
        gap = 40
        total = bw * 2 + gap
        lx = (self.native_w - total) // 2
        by = self.native_h - bh - 80
        self._dc_kill_btn = Button(
            pygame.Rect(lx, by, bw, bh),
            "Kill", (180, 40, 40), self.font)
        self._dc_mercy_btn = Button(
            pygame.Rect(lx + bw + gap, by, bw, bh),
            "Mercy", (40, 140, 100), self.font)

    def _advance_narration(self):
        """Advance to the next narration line, or transition out."""
        self._dc_narr_index += 1
        self._dc_timer = 0.0
        self._dc_narr_alpha = 0.0
        if self._dc_narr_index >= len(self._DC_NARRATION):
            # Narration finished — transition to god_fadein → buttons
            self._dc_phase = "god_fadein"
            self._dc_timer = 0.0

    def _update_dragon_choice(self, dt):
        """Advance the dragon choice cutscene."""
        self._dc_timer += dt
        t = self._dc_timer
        phase = self._dc_phase

        if phase == "narration":
            # Fade in current narration line
            self._dc_narr_alpha = min(255.0, self._dc_narr_alpha + 400 * dt)
            entry = self._DC_NARRATION[self._dc_narr_index]
            # Show/hide god silhouette based on speaker
            if entry["speaker"] == "thrylos":
                self._dc_god_alpha = min(180, int(self._dc_narr_alpha * 180 / 255))
            else:
                self._dc_god_alpha = max(0, self._dc_god_alpha - int(400 * dt))
            return

        if phase == "god_fadein":
            self._dc_god_alpha = min(180, int(180 * t / 0.5))
            if t >= 1.0:
                self._dc_buttons_visible = True
                self._dc_phase = "buttons"

        elif phase == "mercy_shake":
            if t >= 2.0:
                self._dc_phase = "buttons"
                self._dc_timer = 0.0

        elif phase == "kill_anim":
            # Fade out god
            self._dc_god_alpha = max(0, int(180 * (1.0 - t / 0.5)))
            # Spawn slash at t=0.2
            if t >= 0.2 and self._dc_slash is None:
                d = self._dc_dragon
                self._dc_slash = SlashVFX(d.gx, d.gy, flip_x=True,
                                          vertical=True, angle=0, scale=3)
                play_sfx("whoosh.wav", 0.5)
                self.start_shake(6, 0.3)
            if self._dc_slash:
                self._dc_slash.update(dt)
            # Fade out dragon
            if t >= 0.5:
                self._dc_dragon_alpha = max(0, int(255 * (1.0 - (t - 0.5) / 1.0)))
            if t >= 2.0:
                # Dragon is killed — remove it from the enemies list
                self.enemies = [e for e in self.enemies
                                if not isinstance(e, Dragon)]
                self._dc_phase = "victory_fade"
                self._dc_timer = 0.0
                self.fade_alpha = 0
                self._dc_victory_text = [
                    "THE DRAGON WAS SLAIN.",
                    "VICTORY?",
                ]

        elif phase == "mercy_success":
            # Fade out god
            self._dc_god_alpha = max(0, int(180 * (1.0 - t / 0.5)))
            if t >= 1.5:
                self._dc_phase = "victory_fade"
                self._dc_timer = 0.0
                self.fade_alpha = 0
                self._dc_victory_text = [
                    "YOU SPARED THE DRAGON.",
                    "YOU CHOSE PEACE OVER VIOLENCE.",
                    "YOU FORGED YOUR OWN DESTINY.",
                    "VICTORY",
                ]

        elif phase == "victory_fade":
            self.fade_alpha = min(255, self.fade_alpha + 200 * dt)
            if self.fade_alpha >= 255:
                self.phase = "victory_custom"
                self._vc_timer = 0.0
                self.enemies.clear()

    # ── Dragon intro cutscene ──────────────────────────────────────
    def _start_dragon_intro(self):
        """Begin the dramatic dragon reveal cutscene."""
        print("[DEBUG] _start_dragon_intro called")
        self.phase = "dragon_intro"
        self._intro_active = True
        try:
            pygame.mixer.music.set_volume(1.0)
        except Exception:
            pass
        self._bgm_fade_target = None
        # Hide player offscreen during intro
        self.player.gx = -5
        self.player.gy = -5
        self.player.pos = [-5 * TILE, -5 * TILE]
        # Move dragon offscreen right
        for e in self.enemies:
            if isinstance(e, Dragon):
                e.gx = COLS + 2  # start well offscreen
                e.gy = ROWS // 2  # centred vertically
                e.pos = [e.gx * TILE, e.gy * TILE]
                self._intro_dragon = e
                break
        # Cutscene timed to 140 BPM — absolute clock
        self._intro_beat = 60.0 / 140.0  # seconds per beat
        self._intro_clock = 0.0
        self._intro_walk_target = COLS - 3
        self._intro_walk_start_x = (COLS + 2) * TILE
        # Track which one-shot events have fired
        self._intro_roar_fired = False
        self._intro_fireballs_fired = 0
        self._intro_breath_fired = False
        self._intro_done = False
        self._intro_last_frame = None

    def _update_dragon_intro(self, dt):
        """Advance the dragon intro cutscene using an absolute clock."""
        self._intro_clock += dt
        beat = self._intro_beat
        t = self._intro_clock
        dragon = self._intro_dragon

        # Beats 8–16: dragon walks in
        walk_start = beat * 8
        walk_end = beat * 16
        if t < walk_start:
            dragon.pos[0] = self._intro_walk_start_x
            dragon.gx = COLS + 2
        elif t < walk_end:
            progress = (t - walk_start) / (walk_end - walk_start)
            target_x = self._intro_walk_target * TILE
            dragon.pos[0] = self._intro_walk_start_x + (target_x - self._intro_walk_start_x) * progress
            dragon.gx = int(dragon.pos[0] / TILE + 0.5)
            # Footstep shake on animation frame change
            cur_frame = dragon.anim.index
            if self._intro_last_frame is not None and cur_frame != self._intro_last_frame:
                self.start_shake(4, 0.12)
            self._intro_last_frame = cur_frame
        else:
            dragon.pos[0] = self._intro_walk_target * TILE
            dragon.gx = self._intro_walk_target

        # Beat 16: roar
        roar_time = beat * 16
        if t >= roar_time and not self._intro_roar_fired:
            self._intro_roar_fired = True
            dragon.anim = dragon.attack_anim
            dragon.anim.index = 0
            dragon.anim.finished = False
            play_sfx("roar.wav", 0.7)
            self.start_shake(8, beat * 6)
        # Keep shaking and hold breathe sprite during roar (beats 16–24)
        if roar_time <= t < beat * 24:
            self.shake_timer = max(self.shake_timer, 0.1)
            dragon.anim = dragon.attack_anim
            dragon.anim.finished = False

        # Beats 24–32: fireballs — one every 1.5 beats starting at beat 24
        fireball_start = beat * 24
        fireball_interval = beat * 1.5
        while (self._intro_fireballs_fired < 5
               and t >= fireball_start + self._intro_fireballs_fired * fireball_interval):
            self._intro_fireballs_fired += 1
            dragon.anim = dragon.attack_anim
            dragon.anim.index = 0
            dragon.anim.finished = False
            tx = random.randint(0, COLS // 2)
            ty = random.randint(0, ROWS - 1)

            def intro_fireball_arrive(game, _cx=tx, _cy=ty):
                play_sfx("fire-swoosh.wav", 0.5)
                game.start_shake(3, 0.1)
                for ddx in range(-1, 2):
                    for ddy in range(-1, 2):
                        fx, fy = _cx + ddx, _cy + ddy
                        if 0 <= fx < COLS and 0 <= fy < ROWS:
                            turns = 999 if (ddx == 0 and ddy == 0) else 2
                            existing = None
                            for f in game.fire_tiles:
                                if f.gx == fx and f.gy == fy:
                                    existing = f
                                    break
                            if existing:
                                existing.turns = max(existing.turns, turns)
                            else:
                                game.fire_tiles.append(FireTile(fx, fy, turns))

            proj = Projectile(dragon.gx - 1.5, dragon.gy - 0.5, tx, ty,
                              (255, 80, 20), intro_fireball_arrive)
            self.projectiles.append(proj)
            proj.spawn_burst(self.particles)

        # Beats 32–40: sweeping breath fire spray
        breath_start = beat * 32
        breath_end = beat * 40
        if t >= breath_start and not self._intro_breath_fired:
            self._intro_breath_fired = True
            dragon.anim = dragon.attack_anim
            dragon.anim.index = 0
            dragon.anim.finished = False
            self._intro_beam_channel = play_sfx("fire-beam.wav", 0.6)
        # Hold open-mouth (breathe) sprite for the entire sweep
        if breath_start <= t < breath_end:
            dragon.anim = dragon.attack_anim
            dragon.anim.finished = False
        if breath_start <= t < breath_end:
            # Sweep angle: oscillate between -50° and +50° (up/down), 1 full sweep
            sweep_progress = (t - breath_start) / (breath_end - breath_start)
            sweep_angle = math.sin(sweep_progress * math.pi * 1.5) * 50
            angle_rad = math.radians(sweep_angle)
            # Origin: dragon's mouth (1.5 tiles left, 0.5 tiles above centre)
            ox = int((dragon.gx - 1.5) * TILE + TILE // 2)
            oy = int((dragon.gy - 0.5) * TILE + TILE // 2)
            # Shorter beam: ~5 tiles long
            beam_len = TILE * 5
            # Screen shake
            self.shake_timer = 0.1
            self.shake_intensity = max(4, int(4 + 6 * sweep_progress))
            # Spawn particles at the dragon's mouth, moving outward along the beam
            speed = beam_len / 1.65  # travel full length in 1.65s (3x slower)
            for i in range(25):
                # Small random offset at the mouth for thickness
                perp_off = random.uniform(-TILE * 0.3, TILE * 0.3)
                start_px = ox + math.sin(angle_rad) * perp_off
                start_py = oy - math.cos(angle_rad) * perp_off
                # Velocity along the beam direction with angular spread
                spread = random.uniform(0.85, 1.15)
                particle_angle = angle_rad + random.uniform(-0.35, 0.35)
                vx = -math.cos(particle_angle) * speed * spread
                vy = -math.sin(particle_angle) * speed * spread
                r = min(255, 200 + random.randint(0, 55))
                g = min(255, 80 + random.randint(0, 80))
                b = random.randint(0, 40)
                p_angle = random.uniform(0, 360)
                rot_speed = random.uniform(-400, 400)
                life = random.uniform(0.8, 1.2)
                self.particles.append([start_px, start_py, vx, vy,
                                       life, (r, g, b),
                                       p_angle, rot_speed, life, -1.2])
            # Leave fire tiles where the beam hits
            end_x = ox - beam_len * math.cos(angle_rad)
            end_y = oy - beam_len * math.sin(angle_rad)
            for frac in [0.2, 0.4, 0.6, 0.8, 1.0]:
                fx = int((ox - frac * beam_len * math.cos(angle_rad)) / TILE)
                fy = int((oy - frac * beam_len * math.sin(angle_rad)) / TILE)
                if 0 <= fx < COLS and 0 <= fy < ROWS:
                    existing = None
                    for f in self.fire_tiles:
                        if f.gx == fx and f.gy == fy:
                            existing = f
                            break
                    if existing:
                        existing.turns = max(existing.turns, 2)
                    else:
                        self.fire_tiles.append(FireTile(fx, fy, 2))

        # Fade out beam sound as beam ends
        if t >= breath_end and getattr(self, '_intro_beam_channel', None) is not None:
            try:
                self._intro_beam_channel.fadeout(800)
            except Exception:
                pass
            self._intro_beam_channel = None

        # Beat 42: done (allow sweep to finish + linger)
        done_time = beat * 42
        if t >= done_time and not self._intro_done:
            self._intro_done = True
            self.breath_beams.clear()
            self.projectiles.clear()
            self.particles.clear()
            dragon.anim = dragon.idle_anim
            self._bgm_fade_target = 0.4
            p = self.player
            sx, sy = PLAYER_SPAWN.get(self.level, (1, ROWS // 2))
            p.gx, p.gy = sx, sy
            p.pos = [(sx - 3) * TILE, sy * TILE]
            p.committed = [sx, sy]
            # Keep 30% of fire tiles, but clear the player's spawn and adjacent tiles
            safe = set()
            for ddx in range(-1, 2):
                for ddy in range(-1, 2):
                    safe.add((p.gx + ddx, p.gy + ddy))
            kept = [f for f in self.fire_tiles if (f.gx, f.gy) not in safe]
            random.shuffle(kept)
            kept = kept[:max(1, int(len(kept) * 0.3))]
            for f in kept:
                f.turns = random.randint(1, 3)
            self.fire_tiles[:] = kept
            self._intro_active = False
            self.instruction = self.best_instruction()
            self.phase = "player"

    def hovered_enemy(self):
        mx, my = self._screen_to_native(pygame.mouse.get_pos())
        my -= self.UI_HEIGHT
        if my < 0 or my >= self.height:
            return None
        gx, gy = mx // TILE, my // TILE
        for e in self.enemies:
            if not e.alive():
                continue
            if isinstance(e, Dragon):
                if (gx, gy) in e.body_tiles():
                    return e
            elif e.gx == gx and e.gy == gy:
                return e
        return None

    def best_instruction(self):
        """Find the instruction whose absence leads to the worst outcome."""
        p = self.player
        enemies = [(e.gx, e.gy, e.hp, type(e).__name__,
                     getattr(e, 'cooldown', 0))
                    for e in self.enemies if e.alive()]
        if not enemies:
            self.debug_scores = {}
            self.debug_best_line = None
            return ""
        fires = [(f.gx, f.gy, f.turns) for f in self.fire_tiles]
        moves_left = self.MAX_MOVES - len(self.history)
        if moves_left <= 0:
            self.debug_scores = {}
            self.debug_best_line = None
            return ""
        # Collect all leaf sequences: (score, followed_set, path)
        leaves = []
        pot_tuples = tuple((pot.gx, pot.gy) for pot in self.potions)
        _collect_leaves(p.gx, p.gy, p.mode, p.facing,
                        p.switched_this_turn, enemies, fires,
                        moves_left, set(), (), 0, p.hp, leaves,
                        pot_tuples)
        if not leaves:
            self.debug_scores = {}
            self.debug_best_line = None
            return ""
        # Gather all instruction labels that appear in any leaf
        all_labels = set()
        for _, followed, _ in leaves:
            all_labels |= followed
        if not all_labels:
            self.debug_scores = {}
            self.debug_best_line = None
            return ""
        # For each label, find the best score among leaves that DON'T use it
        best_without = {}
        for label in all_labels:
            best_without[label] = -9999
        for score, followed, _ in leaves:
            for label in all_labels:
                if label not in followed:
                    if score > best_without[label]:
                        best_without[label] = score
        self.debug_scores = best_without
        # Track the best leaf (highest scoring sequence)
        best_leaf = max(leaves, key=lambda x: x[0])
        self.debug_best_line = (best_leaf[0], list(best_leaf[2]))
        # The instruction with the lowest "best without" is most critical
        # Tiebreak: prefer "Move East"
        worst_label = None
        worst_val = float('inf')
        for label, val in best_without.items():
            if val < worst_val or (val == worst_val and label == "Move East"):
                worst_val = val
                worst_label = label
        return worst_label or ""

    def draw(self):
        self.screen.fill((40, 40, 40))
        UI_H = self.UI_HEIGHT

        # ── Level floor background ───────────────────────────
        for layer in self._floor_layers_scaled:
            self.screen.blit(layer, (0, UI_H))
        # ── Tablet UI at the top ──────────────────────────────
        self.screen.blit(self._tablet_img, (0, 0))
        p = self.player

        # Left side: moves (aligned with undo) + free will (aligned with confirm)
        moves_left = self.MAX_MOVES - len(self.history)
        moves_text = self.font.render(f"Moves: {moves_left}", True, (60, 50, 40))
        self.screen.blit(moves_text, (36, 60))

        fw_x = 36
        fw_w, fw_h = 300, 30
        fw_label = self.font.render("Free Will", True, (60, 50, 40))
        self.screen.blit(fw_label, (fw_x, 162))
        fw_bar_y = 162 + fw_label.get_height() + 6
        pygame.draw.rect(self.screen, (60, 50, 40), (fw_x, fw_bar_y, fw_w, fw_h))
        fill_w = int(fw_w * p.free_will / 100)
        if fill_w > 0:
            pygame.draw.rect(self.screen, (220, 180, 60), (fw_x, fw_bar_y, fill_w, fw_h))
        pygame.draw.rect(self.screen, (90, 80, 60), (fw_x, fw_bar_y, fw_w, fw_h), 3)
        # Free will change popup
        if self._fw_popup is not None:
            fw_text, fw_timer = self._fw_popup
            frac = fw_timer / 1.0
            popup_surf = self.small_font.render(fw_text, True, (220, 180, 60))
            popup_surf.set_alpha(int(255 * frac))
            popup_y = fw_bar_y - int(45 * (1 - frac))
            self.screen.blit(popup_surf, (fw_x + fw_w + 12, popup_y))

        # Right side: undo (top) + confirm (bottom)
        btn_active = self.phase == "player" and len(self.history) > 0
        self.undo_btn.draw(self.screen, btn_active)
        self.confirm_btn.draw(self.screen, btn_active)

        # Centre: instruction text with glow
        if self.instruction:
            t = self._inst_glow_timer
            if t > 0:
                frac = t / 1.5  # 1.0 → 0.0
                cr = int(220 * frac + 70 * (1 - frac))
                cg = int(200 * frac + 60 * (1 - frac))
                cb = int(100 * frac + 50 * (1 - frac))
            else:
                cr, cg, cb = 70, 60, 50
            inst_str = "Thou shalt " + self.instruction[0].lower() + self.instruction[1:]
            inst_surf = self.cmd_font.render(inst_str, True, (cr, cg, cb))
            label_surf = self.cmd_label_font.render("The Divine Word:", True, (cr, cg, cb))
            # Centre between left info and right buttons
            left_edge = 360
            right_edge = self.native_w - 360
            mid_w = right_edge - left_edge
            total_h = label_surf.get_height() + 6 + inst_surf.get_height()
            top_y = (UI_H - total_h) // 2
            lx = left_edge + (mid_w - label_surf.get_width()) // 2
            self.screen.blit(label_surf, (lx, top_y))
            ix = left_edge + (mid_w - inst_surf.get_width()) // 2
            iy = top_y + label_surf.get_height() + 6
            self.screen.blit(inst_surf, (ix, iy))
            # Yellow glow copy: fades in and shrinks to fit the command text
            if t > 0:
                glow_alpha = int(180 * frac)
                scale_factor = 1.0 + 0.1 * frac  # 1.1 → 1.0
                glow_surf = self.cmd_font.render(inst_str, True, (255, 220, 80))
                gw = int(glow_surf.get_width() * scale_factor)
                gh = int(glow_surf.get_height() * scale_factor)
                glow_scaled = pygame.transform.smoothscale(glow_surf, (gw, gh))
                glow_scaled.set_alpha(glow_alpha)
                gx = ix + (inst_surf.get_width() - gw) // 2
                gy = iy + (inst_surf.get_height() - gh) // 2
                self.screen.blit(glow_scaled, (gx, gy))

        # ── Game grid (offset by UI_HEIGHT) ───────────────────
        # Range overlays
        hovered = self.hovered_enemy()
        enemy_range = hovered.range_tiles() if hovered else set()
        p = self.player
        # Hovered tile highlight (adjacent to player)
        hover_tile = None
        if self.phase == "player":
            hmx, hmy = self._screen_to_native(pygame.mouse.get_pos())
            hgx = hmx // TILE
            hgy = (hmy - UI_H) // TILE
            dist = max(abs(hgx - p.gx), abs(hgy - p.gy))
            if dist == 0 or (dist == 1 and is_passable(hgx, hgy)):
                hover_tile = (hgx, hgy)
        # During facing pick, preview shield cone toward mouse
        preview_facing = None
        if self.picking_facing:
            mx, my = self._screen_to_native(pygame.mouse.get_pos())
            dx = mx // TILE - p.gx
            dy = (my - UI_H) // TILE - p.gy
            preview_facing = direction_index(dx, dy)
            if preview_facing is not None:
                shield_tiles = set()
                for ddx, ddy in facing_cone(preview_facing):
                    nx, ny = p.gx + ddx, p.gy + ddy
                    if 0 <= nx < COLS and 0 <= ny < ROWS:
                        shield_tiles.add((nx, ny))
            else:
                shield_tiles = set()
        else:
            shield_tiles = p.shield_tiles() if self.phase == "player" else set()

        enemy_overlay = pygame.Surface((TILE, TILE), pygame.SRCALPHA)
        if hovered:
            enemy_overlay.fill(hovered.overlay_color())
        hover_overlay = pygame.Surface((TILE, TILE), pygame.SRCALPHA)
        hover_overlay.fill((255, 255, 255, 40))
        shield_overlay = pygame.Surface((TILE, TILE), pygame.SRCALPHA)
        shield_overlay.fill((100, 160, 220, 35))

        for x in range(COLS):
            for y in range(ROWS):
                rect = pygame.Rect(x * TILE, UI_H + y * TILE, TILE, TILE)
                if (x, y) in enemy_range:
                    self.screen.blit(enemy_overlay, rect)
                if hover_tile and (x, y) == hover_tile:
                    self.screen.blit(hover_overlay, rect)
                if (x, y) in shield_tiles:
                    self.screen.blit(shield_overlay, rect)

        # Facing indicator (shield mode only)
        if p.mode == "shield":
            if self.picking_facing and preview_facing is not None:
                fdx, fdy = DIR_RING[preview_facing]
            else:
                fdx, fdy = DIR_RING[p.facing]
            if fdx != 0:
                p.facing_right = fdx > 0

        # Draw fire tiles (offset)
        for f in self.fire_tiles:
            f.draw(self.screen, UI_H)
        # Draw health potions
        for pot in self.potions:
            pot.draw(self.screen, UI_H)

        _dc_fading = (getattr(self, '_dc_phase', '') == "kill_anim"
                      and getattr(self, '_dc_dragon_alpha', 255) < 255)
        for e in self.enemies:
            if isinstance(e, Dragon) and _dc_fading:
                continue  # drawn separately with alpha in the kill_anim block
            if e.alive() or not e.eased() \
                    or isinstance(e, Dragon):
                e.pos[0] += e.bump[0]; e.pos[1] += e.bump[1] + UI_H
                e.draw(self.screen)
                e.pos[0] -= e.bump[0]; e.pos[1] -= e.bump[1] + UI_H
        p.pos[0] += p.bump[0]; p.pos[1] += p.bump[1] + UI_H
        self.player.draw(self.screen)
        p.pos[0] -= p.bump[0]; p.pos[1] -= p.bump[1] + UI_H
        for s in self.slash_vfx:
            s.draw(self.screen, UI_H)
        for proj in self.projectiles:
            proj.draw(self.screen, UI_H)
        # Particles (rotating squares)
        for pt in self.particles:
            frac = pt[4] / pt[8]
            alpha = max(0, min(255, int(255 * frac)))
            r, g, b = pt[5]
            sz = max(4, int(32 * (1.0 if pt[9] < 0 else frac) * abs(pt[9])))
            ps = pygame.Surface((sz, sz), pygame.SRCALPHA)
            ps.fill((r, g, b, alpha))
            rotated = pygame.transform.rotate(ps, pt[6])
            rr = rotated.get_rect(center=(int(pt[0]), int(pt[1]) + UI_H))
            self.screen.blit(rotated, rr)

        # Damage popups
        for text, tmr, px, py in self._dmg_popups:
            frac = tmr / 0.8
            surf = self.small_font.render(text, True, (200, 30, 30))
            surf.set_alpha(int(255 * frac))
            dy = int(40 * (1 - frac))
            self.screen.blit(surf, surf.get_rect(
                center=(int(px), int(py) + UI_H - dy)))

        # God apparition overlay
        if self._god_active:
            t = self._god_timer
            fade_in = 0.5
            alpha_frac = min(1.0, t / fade_in)
            if self._god_fade_out > 0:
                alpha_frac *= self._god_fade_out / 0.5
            god_alpha = int(180 * alpha_frac)
            # Dark overlay
            overlay = pygame.Surface((self.native_w, self.native_h), pygame.SRCALPHA)
            overlay.fill((0, 0, 0, god_alpha // 2))
            self.screen.blit(overlay, (0, 0))
            # God sprite — dark silhouette filling vertical screen space
            if self._god_sprite not in self._god_sprite_cache:
                self._god_sprite_cache[self._god_sprite] = pygame.image.load(
                    os.path.join(ASSET_DIR, self._god_sprite)).convert_alpha()
            raw = self._god_sprite_cache[self._god_sprite]
            # Scale to fill the full screen height
            img_scale = self.native_h / raw.get_height()
            sw = int(raw.get_width() * img_scale)
            sh = self.native_h
            god_img = pygame.transform.scale(raw, (sw, sh))
            # Turn into a dark silhouette: fill with black, keep alpha shape
            silhouette = pygame.Surface((sw, sh), pygame.SRCALPHA)
            silhouette.blit(god_img, (0, 0))
            silhouette.fill((0, 0, 0, 255), special_flags=pygame.BLEND_RGB_MIN)
            silhouette.set_alpha(god_alpha)
            gx = (self.native_w - sw) // 2
            self.screen.blit(silhouette, (gx, 0))
            # Message text
            msg_surf = self.font.render(self._god_message, True, (220, 210, 180))
            msg_surf.set_alpha(god_alpha)
            mx = (self.native_w - msg_surf.get_width()) // 2
            my = self.native_h - msg_surf.get_height() - 60
            self.screen.blit(msg_surf, (mx, my))

        # Golden flash when free will decreases
        if self._golden_flash > 0:
            frac = self._golden_flash / 0.4
            flash = pygame.Surface((self.native_w, self.native_h), pygame.SRCALPHA)
            flash.fill((255, 200, 60, int(30 * frac)))
            self.screen.blit(flash, (0, 0))

        # Dragon choice overlay
        if self.phase in ("dragon_choice", "victory_custom") and hasattr(self, '_dc_phase'):
            dc_phase = getattr(self, '_dc_phase', '')
            ga = getattr(self, '_dc_god_alpha', 0)

            # Narration phase: dark background + word-wrapped text
            if dc_phase == "narration":
                narr_alpha = int(getattr(self, '_dc_narr_alpha', 0))
                # Dark overlay (always present during narration)
                ov = pygame.Surface((self.native_w, self.native_h), pygame.SRCALPHA)
                ov.fill((0, 0, 0, max(narr_alpha // 2, ga // 2)))
                self.screen.blit(ov, (0, 0))
                # God silhouette (only for Thrylos lines)
                if ga > 0:
                    sprite_name = "God_commanding.png"
                    if sprite_name not in self._god_sprite_cache:
                        self._god_sprite_cache[sprite_name] = pygame.image.load(
                            os.path.join(ASSET_DIR, sprite_name)).convert_alpha()
                    raw = self._god_sprite_cache[sprite_name]
                    img_scale = self.native_h / raw.get_height()
                    sw = int(raw.get_width() * img_scale)
                    sh = self.native_h
                    god_img = pygame.transform.scale(raw, (sw, sh))
                    sil = pygame.Surface((sw, sh), pygame.SRCALPHA)
                    sil.blit(god_img, (0, 0))
                    sil.fill((0, 0, 0, 255), special_flags=pygame.BLEND_RGB_MIN)
                    sil.set_alpha(ga)
                    gx = (self.native_w - sw) // 2
                    self.screen.blit(sil, (gx, 0))
                # Word-wrapped narration text
                entry = self._DC_NARRATION[self._dc_narr_index]
                is_thrylos = entry["speaker"] == "thrylos"
                text_color = (220, 210, 180) if is_thrylos else (200, 200, 190)
                max_w = self.native_w - 120
                lines = []
                for paragraph in entry["text"].split("\n"):
                    words = paragraph.split()
                    cur = ""
                    for w in words:
                        test = (cur + " " + w).strip()
                        if self.small_font.size(test)[0] > max_w:
                            if cur:
                                lines.append(cur)
                            cur = w
                        else:
                            cur = test
                    if cur:
                        lines.append(cur)
                line_h = self.small_font.get_linesize()
                total_h = line_h * len(lines)
                base_y = (self.native_h - total_h) // 2
                for i, line in enumerate(lines):
                    surf = self.small_font.render(line, True, text_color)
                    surf.set_alpha(narr_alpha)
                    lx = (self.native_w - surf.get_width()) // 2
                    self.screen.blit(surf, (lx, base_y + i * line_h))
                # "Click to continue" hint
                if narr_alpha >= 200:
                    hint = self.small_font.render("Click to continue...", True, (140, 130, 110))
                    pulse = int(80 + 60 * math.sin(self._dc_timer * 3))
                    hint.set_alpha(pulse)
                    hx = (self.native_w - hint.get_width()) // 2
                    hy = self.native_h - hint.get_height() - 30
                    self.screen.blit(hint, (hx, hy))

            # Dark overlay + god silhouette + "Kill it." for non-narration phases
            elif ga > 0:
                ov = pygame.Surface((self.native_w, self.native_h), pygame.SRCALPHA)
                ov.fill((0, 0, 0, ga // 2))
                self.screen.blit(ov, (0, 0))
                # God silhouette
                sprite_name = "God_commanding.png"
                if sprite_name not in self._god_sprite_cache:
                    self._god_sprite_cache[sprite_name] = pygame.image.load(
                        os.path.join(ASSET_DIR, sprite_name)).convert_alpha()
                raw = self._god_sprite_cache[sprite_name]
                img_scale = self.native_h / raw.get_height()
                sw = int(raw.get_width() * img_scale)
                sh = self.native_h
                god_img = pygame.transform.scale(raw, (sw, sh))
                sil = pygame.Surface((sw, sh), pygame.SRCALPHA)
                sil.blit(god_img, (0, 0))
                sil.fill((0, 0, 0, 255), special_flags=pygame.BLEND_RGB_MIN)
                sil.set_alpha(ga)
                gx = (self.native_w - sw) // 2
                self.screen.blit(sil, (gx, 0))
                # "KILL IT." message
                msg = self.font.render("KILL IT.", True, (220, 210, 180))
                msg.set_alpha(ga)
                mx = (self.native_w - msg.get_width()) // 2
                my = (self.native_h - msg.get_height()) // 2
                self.screen.blit(msg, (mx, my))
            # Dragon fade during kill animation
            if dc_phase == "kill_anim":
                da = getattr(self, '_dc_dragon_alpha', 255)
                if da < 255:
                    d = self._dc_dragon
                    if d.anim:
                        d.anim.flip_x = d.facing_right
                        img = d.anim.image().copy()
                        img.set_alpha(da)
                        sx = d.pos[0] - TILE
                        sy = d.pos[1] - TILE + UI_H
                        self.screen.blit(img, (sx, sy))
                # Draw slash VFX
                sl = getattr(self, '_dc_slash', None)
                if sl and not sl.done:
                    sl.draw(self.screen, UI_H)
            # "YOU CANNOT ESCAPE YOUR DESTINY"
            if dc_phase == "mercy_shake":
                msg2 = self.cmd_font.render("YOU CANNOT ESCAPE YOUR DESTINY", True, (220, 40, 40))
                mx2 = (self.native_w - msg2.get_width()) // 2
                my2 = self.native_h // 2
                self.screen.blit(msg2, (mx2, my2))
            # Kill/Mercy buttons
            if getattr(self, '_dc_buttons_visible', False):
                self._dc_kill_btn.draw(self.screen, True)
                self._dc_mercy_btn.draw(self.screen, True)
            # Victory fade
            if dc_phase == "victory_fade":
                fade = pygame.Surface((self.native_w, self.native_h), pygame.SRCALPHA)
                fade.fill((0, 0, 0, int(max(0, min(255, self.fade_alpha)))))
                self.screen.blit(fade, (0, 0))

        # Custom victory screen
        if self.phase == "victory_custom":
            self.screen.fill((0, 0, 0))
            t = self._vc_timer
            lines = getattr(self, '_dc_victory_text', ["VICTORY"])
            cx = self.native_w // 2
            total_h = len(lines) * 80
            base_y = (self.native_h - total_h) // 2
            for i, line in enumerate(lines):
                delay = i * 1.2
                if t > delay:
                    frac = min(1.0, (t - delay) / 0.8)
                    alpha = int(255 * frac)
                    color = (60, 220, 120) if line == "VICTORY" else (220, 210, 180)
                    if line == "VICTORY?":
                        color = (220, 180, 60)
                    surf = self.cmd_font.render(line, True, color)
                    surf.set_alpha(alpha)
                    self.screen.blit(surf, surf.get_rect(
                        center=(cx, base_y + i * 80)))

        # Level transition fade
        if self.phase == "fading":
            fade = pygame.Surface((self.native_w, self.native_h), pygame.SRCALPHA)
            fade.fill((0, 0, 0, int(max(0, min(255, self.fade_alpha)))))
            self.screen.blit(fade, (0, 0))

        # Dying fade-out
        if self.phase == "dying":
            fade = pygame.Surface((self.native_w, self.native_h), pygame.SRCALPHA)
            fade.fill((0, 0, 0, int(max(0, min(255, self.fade_alpha)))))
            self.screen.blit(fade, (0, 0))

        # Death screen
        if self.phase == "dead":
            self.screen.fill((0, 0, 0))
            t = self._dead_timer
            if getattr(self, '_death_type', 'hp') == 'puppet':
                lines = [
                    "You lose faith in yourself...",
                    "You become a puppet of fate...",
                ]
            else:
                lines = [
                    "Your limbs grow weak...",
                    "Your head hurts...",
                    "Is this the end?",
                ]
            cx = self.native_w // 2
            total_h = len(lines) * 80 + 120  # lines + gap + "Another chance?"
            base_y = (self.native_h - total_h) // 2
            for i, line in enumerate(lines):
                delay = i * 1.2
                if t > delay:
                    frac = min(1.0, (t - delay) / 0.8)
                    alpha = int(255 * frac)
                    surf = self.cmd_font.render(line, True, (200, 180, 160))
                    surf.set_alpha(alpha)
                    self.screen.blit(surf, surf.get_rect(
                        center=(cx, base_y + i * 80)))
            again_delay = len(lines) * 1.2 + 0.8
            if t > again_delay:
                frac = min(1.0, (t - again_delay) / 0.8)
                alpha = int(255 * frac)
                again_surf = self.cmd_font.render("Another chance?", True, (220, 200, 160))
                again_surf.set_alpha(alpha)
                self.screen.blit(again_surf, again_surf.get_rect(
                    center=(cx, base_y + len(lines) * 80 + 120)))

        # Victory overlay
        if self.phase == "victory":
            overlay = pygame.Surface((self.native_w, self.native_h), pygame.SRCALPHA)
            overlay.fill((0, 0, 0, 160))
            self.screen.blit(overlay, (0, 0))
            vic_text = self.font.render("VICTORY", True, (60, 220, 120))
            self.screen.blit(vic_text, vic_text.get_rect(
                center=(self.native_w // 2, self.native_h // 3)))

        # Opening narration screen
        if self.phase == "opening":
            # Draw level 1 background with dark shadow
            self.screen.fill((40, 40, 40))
            for layer in self._floor_layers_scaled:
                self.screen.blit(layer, (0, UI_H))
            shadow = pygame.Surface((self.native_w, self.native_h), pygame.SRCALPHA)
            shadow.fill((0, 0, 0, 160))
            self.screen.blit(shadow, (0, 0))
            narr_alpha = int(getattr(self, '_op_alpha', 0))
            ga = getattr(self, '_op_god_alpha', 0)
            # God silhouette for Thrylos lines
            if ga > 0:
                ov = pygame.Surface((self.native_w, self.native_h), pygame.SRCALPHA)
                ov.fill((0, 0, 0, ga // 2))
                self.screen.blit(ov, (0, 0))
                sprite_name = "God_commanding.png"
                if sprite_name not in self._god_sprite_cache:
                    self._god_sprite_cache[sprite_name] = pygame.image.load(
                        os.path.join(ASSET_DIR, sprite_name)).convert_alpha()
                raw = self._god_sprite_cache[sprite_name]
                img_scale = self.native_h / raw.get_height()
                sw = int(raw.get_width() * img_scale)
                sh = self.native_h
                god_img = pygame.transform.scale(raw, (sw, sh))
                sil = pygame.Surface((sw, sh), pygame.SRCALPHA)
                sil.blit(god_img, (0, 0))
                sil.fill((0, 0, 0, 255), special_flags=pygame.BLEND_RGB_MIN)
                sil.set_alpha(ga)
                gx = (self.native_w - sw) // 2
                self.screen.blit(sil, (gx, 0))
            # Word-wrapped narration text
            entry = self._OPENING_NARRATION[self._op_index]
            is_thrylos = entry["speaker"] == "thrylos"
            text_color = (220, 210, 180) if is_thrylos else (200, 200, 190)
            max_w = self.native_w - 120
            lines = []
            for paragraph in entry["text"].split("\n"):
                words = paragraph.split()
                cur = ""
                for w in words:
                    test = (cur + " " + w).strip()
                    if self.small_font.size(test)[0] > max_w:
                        if cur:
                            lines.append(cur)
                        cur = w
                    else:
                        cur = test
                if cur:
                    lines.append(cur)
            line_h = self.small_font.get_linesize()
            total_h = line_h * len(lines)
            base_y = (self.native_h - total_h) // 2
            for i, line in enumerate(lines):
                surf = self.small_font.render(line, True, text_color)
                surf.set_alpha(narr_alpha)
                lx = (self.native_w - surf.get_width()) // 2
                self.screen.blit(surf, (lx, base_y + i * line_h))
            # "Click to continue" hint
            if narr_alpha >= 200:
                hint = self.small_font.render("Click to continue...", True, (140, 130, 110))
                pulse = int(80 + 60 * math.sin(self._op_timer * 3))
                hint.set_alpha(pulse)
                hx = (self.native_w - hint.get_width()) // 2
                hy = self.native_h - hint.get_height() - 30
                self.screen.blit(hint, (hx, hy))

        # Main menu screen
        if self.phase == "menu":
            self.screen.fill((40, 40, 40))
            for layer in self._floor_layers_scaled:
                self.screen.blit(layer, (0, UI_H))
            shadow = pygame.Surface((self.native_w, self.native_h), pygame.SRCALPHA)
            shadow.fill((0, 0, 0, 120))
            self.screen.blit(shadow, (0, 0))
            # Title tablet — full UI area, extended 5px taller to cover gap
            menu_tab_h = UI_H + 10
            menu_tab = pygame.transform.smoothscale(self._tablet_img_raw, (self.native_w, menu_tab_h))
            self.screen.blit(menu_tab, (0, 0))
            # Title text
            title_surf = self.title_font.render("The Prophecy of Kaironth", True, (90, 72, 25))
            tx = (self.native_w - title_surf.get_width()) // 2
            ty = (menu_tab_h - title_surf.get_height()) // 2
            self.screen.blit(title_surf, (tx, ty))
            # Play button — smaller stone tablet
            btn_w = int(self.native_w * 0.25)
            btn_h = int(self.UI_HEIGHT * 0.3)
            play_tab = pygame.transform.smoothscale(self._tablet_img_raw, (btn_w, btn_h))
            btn_x = (self.native_w - btn_w) // 2
            btn_y = (self.native_h - btn_h) // 2
            self._menu_play_rect = pygame.Rect(btn_x, btn_y, btn_w, btn_h)
            # Hover glow
            mpos = self._screen_to_native(pygame.mouse.get_pos())
            hovering = self._menu_play_rect.collidepoint(mpos)
            if hovering:
                glow = pygame.Surface((btn_w, btn_h), pygame.SRCALPHA)
                glow.fill((255, 220, 140, 35))
                play_tab.blit(glow, (0, 0))
            self.screen.blit(play_tab, (btn_x, btn_y))
            play_surf = self.font.render("Play", True, (60, 50, 40))
            px = (self.native_w - play_surf.get_width()) // 2
            py = btn_y + (btn_h - play_surf.get_height()) // 2
            self.screen.blit(play_surf, (px, py))

        # Scale internal surface to fit the resizable window
        dw, dh = self.display.get_size()
        scale = min(dw / self.native_w, dh / self.native_h)
        ow = int(self.native_w * scale)
        oh = int(self.native_h * scale)
        ox = (dw - ow) // 2
        oy = (dh - oh) // 2
        self.display.fill((0, 0, 0))
        scaled = pygame.transform.smoothscale(self.screen, (ow, oh))
        # Screen shake offset
        sx, sy = 0, 0
        if self.shake_timer > 0:
            sx = random.randint(-self.shake_intensity, self.shake_intensity)
            sy = random.randint(-self.shake_intensity, self.shake_intensity)
        self.display.blit(scaled, (ox + sx, oy + sy))
        pygame.display.flip()

    def run(self):
        try:
            running = True
            while running:
                dt = self.clock.tick(60) / 1000.0
                for event in pygame.event.get():
                    if event.type == pygame.QUIT:
                        running = False
                        break
                    # Main menu play button
                    if event.type == pygame.MOUSEBUTTONDOWN and self.phase == "menu":
                        mpos = self._screen_to_native(event.pos)
                        if hasattr(self, '_menu_play_rect') and self._menu_play_rect.collidepoint(mpos):
                            self._start_opening()
                    # Opening narration advance
                    if event.type == pygame.MOUSEBUTTONDOWN and self.phase == "opening" \
                            and getattr(self, '_op_alpha', 0) >= 200:
                        self._advance_opening()
                    # Dragon choice narration advance
                    if event.type == pygame.MOUSEBUTTONDOWN and self.phase == "dragon_choice" \
                            and self._dc_phase == "narration" \
                            and getattr(self, '_dc_narr_alpha', 0) >= 200:
                        self._advance_narration()
                    # Dragon choice buttons
                    if event.type == pygame.MOUSEBUTTONDOWN and self.phase == "dragon_choice" \
                            and self._dc_phase == "buttons":
                        mpos = self._screen_to_native(event.pos)
                        if self._dc_kill_btn.clicked(mpos):
                            self._dc_phase = "kill_anim"
                            self._dc_timer = 0.0
                            self._dc_buttons_visible = False
                        elif self._dc_mercy_btn.clicked(mpos):
                            if self.player.free_will < 90:
                                self._dc_phase = "mercy_shake"
                                self._dc_timer = 0.0
                                self.start_shake(10, 1.5)
                            else:
                                self._dc_phase = "mercy_success"
                                self._dc_timer = 0.0
                                self._dc_buttons_visible = False
                    _dead_click_t = 4.0 if getattr(self, '_death_type', 'hp') == 'puppet' else 5.2
                    if event.type == pygame.MOUSEBUTTONDOWN and self.phase == "dead" and self._dead_timer > _dead_click_t:
                        self._current_bgm = None
                        self.player.hp = self.player.max_hp
                        self.player.free_will = 50
                        self._go_to_level(self.level)
                    elif event.type == pygame.MOUSEBUTTONDOWN and self._god_active and self._god_fade_out == 0 and self._god_timer >= 0.5:
                        self._god_fade_out = 0.5
                    elif event.type == pygame.MOUSEBUTTONDOWN and self.phase == "player":
                        self.handle_click(self._screen_to_native(event.pos))
                    if event.type == pygame.KEYDOWN:
                        if event.key == pygame.K_n:
                            if self.level == 4:
                                # Set dragon to 1 HP
                                for e in self.enemies:
                                    if isinstance(e, Dragon):
                                        e.hp = 1
                                        break
                            elif self.level + 1 == 4:
                                self.phase = "fading"
                                self.fade_alpha = 0
                                self.fade_direction = 1
                            else:
                                self._go_to_level(self.level + 1)
                        elif event.key == pygame.K_p:
                            self._go_to_level(self.level - 1)
                if not running:
                    break
                self.update(dt)
                self.draw()
        except KeyboardInterrupt:
            pass
        finally:
            # try:
            #     pygame.mixer.music.stop()
            #     pygame.mixer.quit()
            #     pygame.quit()
            # except Exception:
            #     pass
            os._exit(0)


if __name__ == "__main__":
    import signal
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    import traceback
    try:
        Game().run()
    except Exception:
        traceback.print_exc()
        input("Press Enter to exit...")
        sys.exit(1)
