import asyncio
import math
import random
import sys
from dataclasses import dataclass, field
from typing import List, Tuple, Optional

import pygame

# Try to import pyscript if available for browser execution support
try:
    import pyscript
    IS_PYSCRIPT = True
except ImportError:
    IS_PYSCRIPT = False

Vec = pygame.math.Vector2

# ------------------------- Config ---------------------------------

WIDTH, HEIGHT = 1024, 640
FPS = 60
ROOM_MARGIN = 48

FONT_NAME = None  # Use default system font for broader compatibility

# Colors
WHITE = (240, 240, 240)
BLACK = (15, 15, 15)
GREY = (60, 60, 60)
RED = (220, 70, 70)
GREEN = (70, 220, 120)
BLUE = (80, 180, 255)
CYAN = (80, 220, 220)
YELLOW = (240, 215, 95)
PURPLE = (170, 120, 230)
ORANGE = (240, 150, 70)

# Gameplay
STARTING_LEVEL = 1
SLIME_BASE_HP = 12
SLIME_BASE_SPEED = 60
SLIME_MIN_SIZE = 1
SLIME_MAX_SIZE = 3

PORTAL_RADIUS = 30

SHIELD_REGEN_DELAY = 3.0      # seconds after last damage before regen starts
SHIELD_REGEN_RATE = 10.0      # shield per second

# ------------------------- Helpers --------------------------------

def clamp(v, lo, hi):
    return max(lo, min(hi, v))

def sign(x: float) -> int:
    return -1 if x < 0 else (1 if x > 0 else 0)

# ------------------------- Entities --------------------------------

@dataclass
class Projectile:
    pos: Vec
    vel: Vec
    radius: float
    damage: int
    lifetime: float
    pierce: int = 0  # how many enemies it can pass through (>=0)
    color: Tuple[int, int, int] = WHITE
    owner_id: int = 0

    def update(self, dt: float):
        self.pos += self.vel * dt
        self.lifetime -= dt

    def draw(self, surf: pygame.Surface):
        pygame.draw.circle(surf, self.color, (int(self.pos.x), int(self.pos.y)), int(self.radius))

@dataclass
class Player:
    pid: int
    name: str
    color: Tuple[int, int, int]
    class_type: str
    pos: Vec
    speed: float = 200.0
    radius: float = 14.0
    hp: float = 100.0
    max_hp: float = 100.0
    shield: float = 25.0
    max_shield: float = 25.0
    damage: int = 12
    fire_rate: float = 3.0    # shots per second OR melee swings/s
    proj_speed: float = 400.0
    proj_range: float = 420.0
    last_attack: float = 0.0
    facing: Vec = field(default_factory=lambda: Vec(1, 0))
    alive: bool = True
    last_damaged_time: float = -9999.0
    level: int = 1

    def take_damage(self, amount: float, now: float):
        if self.shield > 0:
            absorbed = min(self.shield, amount)
            self.shield -= absorbed
            amount -= absorbed
        if amount > 0:
            self.hp -= amount
        self.last_damaged_time = now
        if self.hp <= 0:
            self.alive = False

    def regen_shield(self, dt: float, now: float):
        if now - self.last_damaged_time >= SHIELD_REGEN_DELAY and self.shield < self.max_shield:
            self.shield = clamp(self.shield + SHIELD_REGEN_RATE * dt, 0, self.max_shield)

    def attack_ready(self, now: float) -> bool:
        return (now - self.last_attack) >= (1.0 / self.fire_rate)

    def center(self) -> Vec:
        return self.pos

@dataclass
class Slime:
    pos: Vec
    size: int  # 1..3
    hp: float
    speed: float
    color: Tuple[int, int, int]
    radius: float

    def update(self, dt: float, players: List[Player]):
        targets = [p for p in players if p.alive]
        if not targets:
            return
        target = min(targets, key=lambda p: (p.pos - self.pos).length_squared())
        to = (target.pos - self.pos)
        if to.length_squared() > 1e-6:
            to = to.normalize()
        self.pos += to * self.speed * dt
        self.pos.x = clamp(self.pos.x, ROOM_MARGIN, WIDTH - ROOM_MARGIN)
        self.pos.y = clamp(self.pos.y, ROOM_MARGIN, HEIGHT - ROOM_MARGIN)

    def draw(self, surf: pygame.Surface):
        pygame.draw.circle(surf, self.color, (int(self.pos.x), int(self.pos.y)), int(self.radius))

    def hit(self, dmg: float) -> bool:
        self.hp -= dmg
        return self.hp <= 0

# ------------------------- Game systems ----------------------------

class InputMap:
    """Keyboard mapping for two local players."""
    def __init__(self):
        self.p1_move = {pygame.K_w: Vec(0, -1), pygame.K_s: Vec(0, 1),
                        pygame.K_a: Vec(-1, 0), pygame.K_d: Vec(1, 0)}
        self.p1_attack = [pygame.K_f, pygame.K_SPACE]

        self.p2_move = {pygame.K_UP: Vec(0, -1), pygame.K_DOWN: Vec(0, 1),
                        pygame.K_LEFT: Vec(-1, 0), pygame.K_RIGHT: Vec(1, 0)}
        self.p2_attack = [pygame.K_RCTRL, pygame.K_RSHIFT, pygame.K_SLASH]

    def read_move(self, keys, pid: int) -> Vec:
        move = Vec(0, 0)
        mapping = self.p1_move if pid == 1 else self.p2_move
        for k, v in mapping.items():
            if keys[k]:
                move += v
        if move.length_squared() > 0:
            move = move.normalize()
        return move

    def attack_pressed(self, keys, pid: int) -> bool:
        arr = self.p1_attack if pid == 1 else self.p2_attack
        return any(keys[k] for k in arr if k < len(keys))

# --------------- Class presets & attacks ---------------------------

CLASS_PRESETS = {
    "Thief": dict(color=YELLOW, speed=230.0, damage=14, fire_rate=4.0, proj_speed=0.0, proj_range=50.0, max_shield=18.0, shield=18.0),
    "Archer": dict(color=GREEN, speed=200.0, damage=12, fire_rate=3.0, proj_speed=500.0, proj_range=520.0, max_shield=22.0, shield=22.0),
    "Mage": dict(color=PURPLE, speed=190.0, damage=10, fire_rate=2.2, proj_speed=400.0, proj_range=460.0, max_shield=28.0, shield=28.0),
}

def create_player(pid: int, class_name: str, pos: Tuple[float, float]) -> Player:
    base = Player(pid=pid, name=f"P{pid}", color=WHITE, class_type=class_name, pos=Vec(pos))
    preset = CLASS_PRESETS.get(class_name, CLASS_PRESETS["Thief"])
    for k, v in preset.items():
        setattr(base, k, v)
    base.max_hp = 100.0
    base.hp = base.max_hp
    return base

class LD_stuff:
    classes = ["Thief", "Archer", "Mage"]
    
    @staticmethod
    def Thief(PlayerClass, player):
        facing = player.facing if player.facing.length_squared() > 0 else Vec(1, 0)
        pos = player.pos + facing * (player.radius + 6)
        vel = facing * 40.0
        return Projectile(pos=pos, vel=vel, radius=16, damage=player.damage, lifetime=0.15, pierce=999, color=YELLOW, owner_id=player.pid)
        
    @staticmethod
    def Archer(PlayerClass, player):
        facing = player.facing if player.facing.length_squared() > 0 else Vec(1, 0)
        pos = player.pos + facing * (player.radius + 4)
        vel = facing * player.proj_speed
        return Projectile(pos=pos, vel=vel, radius=6, damage=player.damage, lifetime=max(0.4, player.proj_range / max(100.0, player.proj_speed)), pierce=0, color=GREEN, owner_id=player.pid)
        
    @staticmethod
    def LD2(PlayerClass, player):
        facing = player.facing if player.facing.length_squared() > 0 else Vec(1, 0)
        pos = player.pos + facing * (player.radius + 4)
        vel = facing * player.proj_speed
        return Projectile(pos=pos, vel=vel, radius=100, damage=player.damage, lifetime=max(0.4, player.proj_range / max(100.0, player.proj_speed)), pierce=1000, color=(255,255,255), owner_id=player.pid)
        
    @staticmethod
    def LD3(PlayerClass, player):
        facing = player.facing if player.facing.length_squared() > 0 else Vec(1, 0)
        pos = player.pos + facing
        vel = facing * player.proj_speed * 0
        return Projectile(pos=pos, vel=vel, radius=200, damage=player.damage, lifetime=max(0.4, player.proj_range / max(100.0, player.proj_speed)), pierce=1000, color=(255,255,255), owner_id=player.pid)
        
    @staticmethod
    def Mage(PlayerClass, player):
        facing = player.facing if player.facing.length_squared() > 0 else Vec(1, 0)
        pos = player.pos + facing * (player.radius + 4)
        vel = facing * player.proj_speed * 0.85
        return Projectile(pos=pos, vel=vel, radius=8, damage=player.damage + 2, lifetime=max(0.45, player.proj_range / max(100.0, player.proj_speed*0.85)), pierce=2, color=PURPLE, owner_id=player.pid)

LD_stuff.atks = {"Thief": LD_stuff.Thief, "Archer": LD_stuff.Archer, "Mage": LD_stuff.Mage}
LD_stuff.class_atks = {"Thief": LD_stuff.Thief, "Archer": LD_stuff.Archer, "Mage": LD_stuff.Mage}

def create_class(name, stats=None, atk=None):
    if stats is None:
        stats = CLASS_PRESETS["Thief"]
    if atk is None:
        atk = LD_stuff.Thief
        
    if isinstance(atk, str):
        LD_stuff.class_atks[name] = LD_stuff.atks.get(atk, LD_stuff.Thief)
    else:
        LD_stuff.class_atks[name] = atk
    CLASS_PRESETS[name] = stats
    if name not in LD_stuff.classes:
        LD_stuff.classes.append(name)

def create_atk(name, starting_dist, proj_speed_multiplier, min_proj_range, lifetime_multiplier, damage_multiplier, proj_size, pierce, color):
    def atk(PlayerClass, player):
        facing = player.facing if player.facing.length_squared() > 0 else Vec(1, 0)
        pos = player.pos + facing * (player.radius + starting_dist)
        vel = facing * player.proj_speed * proj_speed_multiplier
        return Projectile(pos=pos, vel=vel, radius=proj_size, damage=int(player.damage * damage_multiplier), lifetime=player.proj_range / max(min_proj_range, player.proj_speed * proj_speed_multiplier) * lifetime_multiplier, pierce=pierce, color=color, owner_id=player.pid)
    LD_stuff.atks[name] = atk

def player_attack(player: Player, now: float) -> List[Projectile]:
    if not player.attack_ready(now):
        return []
    player.last_attack = now
    
    atk_func = LD_stuff.class_atks.get(player.class_type, LD_stuff.Thief)
    proj = atk_func(Player, player)
    return [proj]

# --------------------------- Upgrades ------------------------------

UPGRADES = [
    ("+Max Health", "max_hp", 20.0, "Increase max HP by 20 and heal to full.", "+"),
    ("+Max Shield", "max_shield", 10.0, "Increase max shields by 10 and refill shields.", "+"),
    ("+Damage", "damage", 2, "Increase damage by 2.", "+"),
    ("+Move Speed", "speed", 20.0, "Increase move speed by 20.", "+"),
    ("+Fire Rate", "fire_rate", 0.35, "Increase attacks/second by 0.35.", "+"),
    ("+Projectile Range", "proj_range", 80.0, "Increase projectile range by ~80.", "+"),
    ("+Projectile Speed", "proj_speed", 60.0, "Increase projectile speed by 60.", "+"),
]

def apply_upgrade(game, p: Player, key: str, delta, title: str, typ: str):
    if isinstance(typ, int):
        delta(typ)
    elif str(typ).lower() == "set":
        if key == "max_hp":
            p.max_hp = delta
            p.hp = p.max_hp
        elif key == "max_shield":
            p.max_shield = delta
            p.shield = p.max_shield
        elif key == "func":
            pass
        elif key == "level":
            game.level += delta
        else:
            setattr(p, key, delta)
    else:
        if key == "max_hp":
            p.max_hp += delta
            p.hp = p.max_hp
        elif key == "level":
            game.level += delta
        elif key == "max_shield":
            p.max_shield += delta
            p.shield = p.max_shield
        elif key == "func":
            delta(p)
        else:
            cur = getattr(p, key, 0)
            setattr(p, key, cur + delta)

def create_upgrade(name, att, amount, mesg, typ="+"):
    UPGRADES.append((name, att, amount, mesg, typ))

# --------------------------- Level gen -----------------------------

def make_slime(size: int, x: float, y: float) -> Slime:
    hp = SLIME_BASE_HP * size
    speed = SLIME_BASE_SPEED * (0.6 + 0.2 * (SLIME_MAX_SIZE - size))
    color = (80, max(0, 200 - size * 20), min(255, 120 + size * 20))
    radius = 16 + size * 6
    return Slime(pos=Vec(x, y), size=size, hp=hp, speed=speed, color=color, radius=radius)

def spawn_wave(level: int) -> List[Slime]:
    enemies: List[Slime] = []
    n = 4 + level
    for _ in range(n):
        size = random.choice([SLIME_MAX_SIZE, SLIME_MAX_SIZE - 1])
        x = random.uniform(ROOM_MARGIN, WIDTH - ROOM_MARGIN)
        y = random.uniform(ROOM_MARGIN, HEIGHT - ROOM_MARGIN)
        enemies.append(make_slime(size, x, y))
    return enemies

# -------------------------- Collision ------------------------------

def circle_collision(a_pos: Vec, a_r: float, b_pos: Vec, b_r: float) -> bool:
    return (a_pos - b_pos).length_squared() <= (a_r + b_r) ** 2

# --------------------------- UI -----------------------------------

def draw_bar(surf, x, y, w, h, frac, fg, bg):
    frac = clamp(frac, 0.0, 1.0)
    pygame.draw.rect(surf, bg, (x, y, w, h), border_radius=4)
    if w * frac > 0:
        pygame.draw.rect(surf, fg, (x, y, max(1, int(w * frac)), h), border_radius=4)
    pygame.draw.rect(surf, (0, 0, 0), (x, y, w, h), 2, border_radius=4)

def draw_player_panel(surf, font_small, p: Player, x: int, y: int):
    draw_bar(surf, x, y, 220, 14, p.hp / p.max_hp if p.max_hp > 0 else 0, RED, GREY)
    draw_bar(surf, x, y + 18, 220, 10, p.shield / p.max_shield if p.max_shield > 0 else 0, CYAN, GREY)
    text = f"{p.name} [{p.class_type}] HP:{int(p.hp)}/{int(p.max_hp)} SH:{int(p.shield)}/{int(p.max_shield)} Lvl:{p.level}"
    surf.blit(font_small.render(text, True, WHITE), (x, y + 32))

def wrap_text(font, text, max_w):
    words = text.split()
    lines = []
    cur = ""
    for w in words:
        test = (cur + " " + w).strip()
        if font.size(test)[0] <= max_w:
            cur = test
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines

# --------------------------- Game States ---------------------------

STATE_CLASS_SELECT = "class_select"
STATE_PLAY = "play"
STATE_LEVEL_UP = "level_up"
STATE_GAME_OVER = "game_over"

class Game:
    def __init__(self):
        pygame.init()
        pygame.display.set_caption("Two-Player Slimes (Pygame-ce)")
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT))
        self.clock = pygame.time.Clock()
        
        # Safe font loading fallback
        try:
            self.font = pygame.font.Font(FONT_NAME, 20)
            self.font_small = pygame.font.Font(FONT_NAME, 14)
            self.font_big = pygame.font.Font(FONT_NAME, 36)
        except Exception:
            self.font = pygame.font.SysFont(None, 20)
            self.font_small = pygame.font.SysFont(None, 14)
            self.font_big = pygame.font.SysFont(None, 36)

        self.inputs = InputMap()
        self.state = STATE_CLASS_SELECT

        self.level = STARTING_LEVEL
        self.players: List[Player] = [
            create_player(1, "Thief", (WIDTH * 0.3, HEIGHT * 0.5)),
            create_player(2, "Archer", (WIDTH * 0.7, HEIGHT * 0.5)),
        ]
        self.class_choices = LD_stuff.classes
        self.class_index = [0, 1]

        self.enemies: List[Slime] = []
        self.shots: List[Projectile] = []
        self.portal_pos: Optional[Vec] = None

        self.levelup_options = {1: [], 2: []}
        self.levelup_selected = {1: 0, 2: 0}

        self.elapsed = 0.0
        self._events = []

    def update_class_select(self, dt):
        if self._pressed_once(pygame.K_q) or self._pressed_once(pygame.K_a):
            self.class_index[0] = (self.class_index[0] - 1) % len(self.class_choices)
        if self._pressed_once(pygame.K_e) or self._pressed_once(pygame.K_d):
            self.class_index[0] = (self.class_index[0] + 1) % len(self.class_choices)

        if self._pressed_once(pygame.K_LEFT) or self._pressed_once(pygame.K_COMMA):
            self.class_index[1] = (self.class_index[1] - 1) % len(self.class_choices)
        if self._pressed_once(pygame.K_RIGHT) or self._pressed_once(pygame.K_PERIOD):
            self.class_index[1] = (self.class_index[1] + 1) % len(self.class_choices)

        if self._pressed_once(pygame.K_RETURN):
            for i, p in enumerate(self.players):
                chosen = self.class_choices[self.class_index[i]]
                self.players[i] = create_player(p.pid, chosen, p.pos)
            self.start_level(self.level)
            self.state = STATE_PLAY

    def draw_class_select(self):
        self.screen.fill(BLACK)
        title = self.font_big.render("Select Classes (Enter to start)", True, WHITE)
        self.screen.blit(title, (WIDTH // 2 - title.get_width() // 2, 40))

        for i, pid in enumerate([1, 2]):
            x = WIDTH // 2 + (-240 if pid == 1 else 240)
            y = HEIGHT // 2 - 40
            label = self.font.render(f"P{pid}", True, WHITE)
            self.screen.blit(label, (x - label.get_width() // 2, y - 80))

            cls = self.class_choices[self.class_index[i]]
            color = CLASS_PRESETS.get(cls, CLASS_PRESETS["Thief"])["color"]
            rect = pygame.Rect(x - 80, y - 40, 160, 80)
            pygame.draw.rect(self.screen, GREY, rect, border_radius=12)
            name = self.font.render(cls, True, color)
            self.screen.blit(name, (x - name.get_width() // 2, y - name.get_height() // 2))

            if pid == 1:
                hint = "P1: Q/E to change • Move: WASD • Attack: F/Space"
            else:
                hint = "P2: ←/→ to change • Move: Arrows • Attack: RightCtrl/Slash"
            hh = self.font_small.render(hint, True, WHITE)
            self.screen.blit(hh, (x - hh.get_width() // 2, y + 60))

    def start_level(self, level: int):
        self.enemies = spawn_wave(level)
        self.shots = []
        self.portal_pos = None

        for p in self.players:
            p.pos = Vec(WIDTH * 0.3, HEIGHT * 0.5) if p.pid == 1 else Vec(WIDTH * 0.7, HEIGHT * 0.5)
            p.alive = True
            p.hp = p.max_hp
            p.shield = p.max_shield

    def update_play(self, dt):
        now = self.elapsed
        keys = pygame.key.get_pressed()
        
        for p in self.players:
            if not p.alive:
                continue
            move = self.inputs.read_move(keys, p.pid)
            if move.length_squared() > 0:
                p.facing = move
            p.pos += move * p.speed * dt
            p.pos.x = clamp(p.pos.x, ROOM_MARGIN, WIDTH - ROOM_MARGIN)
            p.pos.y = clamp(p.pos.y, ROOM_MARGIN, HEIGHT - ROOM_MARGIN)

            if self.inputs.attack_pressed(keys, p.pid):
                self.shots += player_attack(p, now)

            p.regen_shield(dt, now)

        for s in self.enemies:
            s.update(dt, self.players)

        for pr in self.shots:
            pr.update(dt)
        self.shots = [pr for pr in self.shots if pr.lifetime > 0]

        for pr in list(self.shots):
            for s in list(self.enemies):
                if circle_collision(pr.pos, pr.radius, s.pos, s.radius):
                    dead = s.hit(pr.damage)
                    if dead:
                        if s.size > SLIME_MIN_SIZE:
                            for _ in range(2):
                                jitter = Vec(random.uniform(-1, 1), random.uniform(-1, 1)).normalize() * (s.radius * 0.5)
                                child = make_slime(s.size - 1, s.pos.x + jitter.x, s.pos.y + jitter.y)
                                self.enemies.append(child)
                        if s in self.enemies:
                            self.enemies.remove(s)
                    if pr.pierce > 0:
                        pr.pierce -= 1
                    else:
                        if pr in self.shots:
                            self.shots.remove(pr)
                    break

        for s in self.enemies:
            for p in self.players:
                if p.alive and circle_collision(p.pos, p.radius, s.pos, s.radius):
                    p.take_damage(16 * dt, self.elapsed)

        if all(not p.alive for p in self.players):
            self.state = STATE_GAME_OVER
            return

        if not self.enemies and self.portal_pos is None:
            self.portal_pos = Vec(WIDTH * 0.5, HEIGHT * 0.5)
            
        if self.portal_pos is not None:
            numalive = sum(1 for p in self.players if p.alive)
            inside = [circle_collision(p.pos, p.radius, self.portal_pos, PORTAL_RADIUS) and p.alive for p in self.players]
            if numalive > 0 and sum(inside) >= numalive:
                self.prepare_levelup()
                self.state = STATE_LEVEL_UP

    def draw_play(self):
        self.screen.fill((25, 25, 28))

        pygame.draw.rect(self.screen, GREY, (ROOM_MARGIN - 8, ROOM_MARGIN - 8, WIDTH - 2 * (ROOM_MARGIN - 8), HEIGHT - 2 * (ROOM_MARGIN - 8)), 2, border_radius=8)

        if self.portal_pos is not None:
            pygame.draw.circle(self.screen, CYAN, (int(self.portal_pos.x), int(self.portal_pos.y)), PORTAL_RADIUS, width=3)
            pygame.draw.circle(self.screen, BLUE, (int(self.portal_pos.x), int(self.portal_pos.y)), int(PORTAL_RADIUS * 0.6), width=2)

        for s in self.enemies:
            s.draw(self.screen)

        for pr in self.shots:
            pr.draw(self.screen)

        for p in self.players:
            if p.alive:
                color = CLASS_PRESETS.get(p.class_type, CLASS_PRESETS["Thief"])["color"]
                pygame.draw.circle(self.screen, color, (int(p.pos.x), int(p.pos.y)), int(p.radius))
                tip = p.pos + (p.facing if p.facing.length_squared() > 0 else Vec(1, 0)) * (p.radius + 8)
                pygame.draw.line(self.screen, WHITE, (int(p.pos.x), int(p.pos.y)), (int(tip.x), int(tip.y)), 2)
            else:
                pygame.draw.circle(self.screen, (120, 120, 120), (int(p.pos.x), int(p.pos.y)), int(p.radius), 2)

        draw_player_panel(self.screen, self.font_small, self.players[0], 16, 12)
        draw_player_panel(self.screen, self.font_small, self.players[1], WIDTH - 16 - 220, 12)

        top = self.font.render(f"Level {self.level} • Enemies: {len(self.enemies)}", True, WHITE)
        self.screen.blit(top, (WIDTH // 2 - top.get_width() // 2, 8))

    def prepare_levelup(self):
        for p in self.players:
            p.level += 1
            options = random.sample(UPGRADES, k=min(3, len(UPGRADES)))
            self.levelup_options[p.pid] = options
            self.levelup_selected[p.pid] = 0

    def update_levelup(self, dt):
        if self._pressed_once(pygame.K_a):
            self.levelup_selected[1] = (self.levelup_selected[1] - 1) % 3
        if self._pressed_once(pygame.K_d):
            self.levelup_selected[1] = (self.levelup_selected[1] + 1) % 3

        if self._pressed_once(pygame.K_LEFT):
            self.levelup_selected[2] = (self.levelup_selected[2] - 1) % 3
        if self._pressed_once(pygame.K_RIGHT):
            self.levelup_selected[2] = (self.levelup_selected[2] + 1) % 3

        keys = pygame.key.get_pressed()
        p1_confirm = keys[pygame.K_f] or keys[pygame.K_SPACE] or keys[pygame.K_RETURN]
        p2_confirm = (keys[pygame.K_RCTRL] if len(keys) > pygame.K_RCTRL else False) or keys[pygame.K_RSHIFT] or keys[pygame.K_SLASH]

        if p1_confirm and p2_confirm:
            for p in self.players:
                opts = self.levelup_options.get(p.pid)
                if opts:
                    title, attr, delta, desc, typ = opts[self.levelup_selected[p.pid]]
                    apply_upgrade(self, p, attr, delta, title, typ)
            self.level += 1
            self.start_level(self.level)
            self.state = STATE_PLAY

    def draw_levelup(self):
        self.screen.fill((18, 18, 22))
        header = self.font_big.render("Level Up: Choose an upgrade (Both must confirm)", True, WHITE)
        self.screen.blit(header, (WIDTH // 2 - header.get_width() // 2, 36))

        for idx, p in enumerate(self.players):
            x_center = WIDTH // 2 + (-280 if p.pid == 1 else 280)
            y = 140
            class_color = CLASS_PRESETS.get(p.class_type, CLASS_PRESETS["Thief"])["color"]
            who = self.font.render(f"P{p.pid} [{p.class_type}] -> pick one", True, class_color)
            self.screen.blit(who, (x_center - who.get_width() // 2, y - 40))

            options = self.levelup_options.get(p.pid, [])
            selected = self.levelup_selected.get(p.pid, 0)
            for i, (title, attr, delta, desc, typ) in enumerate(options):
                box = pygame.Rect(x_center - 160, y + i * 110, 320, 96)
                pygame.draw.rect(self.screen, GREY, box, border_radius=10)
                if i == selected:
                    pygame.draw.rect(self.screen, WHITE, box, width=3, border_radius=10)
                t = self.font.render(title, True, WHITE)
                self.screen.blit(t, (box.x + 16, box.y + 12))
                lines = wrap_text(self.font_small, desc, 320 - 32)
                for li, line in enumerate(lines[:3]):
                    self.screen.blit(self.font_small.render(line, True, (220, 220, 220)), (box.x + 16, box.y + 40 + li * 16))

            hint = "P1: A/D to select, F/Space/Enter to confirm" if p.pid == 1 else "P2: ←/→ to select, RightCtrl/Slash to confirm"
            hh = self.font_small.render(hint, True, WHITE)
            self.screen.blit(hh, (x_center - hh.get_width() // 2, HEIGHT - 64))

    def update_game_over(self, dt):
        if self._pressed_once(pygame.K_RETURN):
            self.level = STARTING_LEVEL
            self.state = STATE_CLASS_SELECT
            for i, p in enumerate(self.players):
                self.players[i] = create_player(p.pid, self.class_choices[self.class_index[i]], (WIDTH * 0.3 if p.pid == 1 else WIDTH * 0.7, HEIGHT * 0.5))

    def draw_game_over(self):
        self.screen.fill((10, 10, 10))
        t = self.font_big.render("GAME OVER", True, RED)
        self.screen.blit(t, (WIDTH // 2 - t.get_width() // 2, HEIGHT // 2 - 120))
        s = self.font.render("Press Enter to return to Class Select", True, WHITE)
        self.screen.blit(s, (WIDTH // 2 - s.get_width() // 2, HEIGHT // 2 - 60))

    def _pressed_once(self, key):
        for event in self._events:
            if event.type == pygame.KEYDOWN and event.key == key:
                return True
        return False

    def lvlup(self, lvl):
        self.level += lvl

    async def run(self):
        running = True
        while running:
            dt = self.clock.tick(FPS) / 1000.0
            self.elapsed += dt
            
            self._events = pygame.event.get()
            for event in self._events:
                if event.type == pygame.QUIT:
                    running = False
                if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                    running = False

            if self.state == STATE_CLASS_SELECT:
                self.update_class_select(dt)
            elif self.state == STATE_PLAY:
                self.update_play(dt)
            elif self.state == STATE_LEVEL_UP:
                self.update_levelup(dt)
            elif self.state == STATE_GAME_OVER:
                self.update_game_over(dt)

            if self.state == STATE_CLASS_SELECT:
                self.draw_class_select()
            elif self.state == STATE_PLAY:
                self.draw_play()
            elif self.state == STATE_LEVEL_UP:
                self.draw_levelup()
            elif self.state == STATE_GAME_OVER:
                self.draw_game_over()

            pygame.display.flip()
            
            # Yield control in browser environments (PyScript)
            if IS_PYSCRIPT:
                await asyncio.sleep(0)

        pygame.quit()

# --------------------------- Mods Setup ----------------------------

def mods():
    def LD():
        create_class("LD", {'color': (0, 0, 0), 'speed': 1000, 'damage': 100, 'fire_rate': 100, 'proj_range': 1000, 'max_shield': 18.0, 'shield': 100}, LD_stuff.Archer)

    def new_mage():
        presets_copy = dict(CLASS_PRESETS['Mage'])
        presets_copy["fire_rate"] = 0.5
        create_atk('new_mage_atk', 100, 0, 0.01, 0.00005, 0.1, 90, 1000, GREEN)
        create_class('new_mage', presets_copy, "new_mage_atk")

    def upgrades():
        create_upgrade('curse of denial speed', 'speed', 99999999999999999999999999999999, 'click if you dare!!!')
        create_upgrade('curse of no speed', 'speed', 0, 'click if you dare!!!')
        create_upgrade('green', 'color', (0, 255, 100), 'green', "set")
        create_upgrade('extrasuper dupur hard', 'level', 1000, 'slimes lvl + 1000', "+")
        create_upgrade('super dupur hard', 'level', 100, 'slimes lvl + 100', "+")
        create_upgrade('super hard', 'level', 10, 'slimes lvl + 10', "+")

    def LD2():
        LD_stuff.atks['LD2.0'] = LD_stuff.LD2
        create_class("LD2.0", {'color': (255, 255, 255), 'speed': 1000, 'damage': 1000, 'fire_rate': 1000, 'proj_range': 1000, 'max_shield': 18.0, 'shield': 100}, LD_stuff.atks['LD2.0'])

    def LD3():
        LD_stuff.atks['LD3.0'] = LD_stuff.LD3
        create_class("LD3.0", {'color': (0, 255, 255), 'speed': 1000, 'damage': 1000, 'fire_rate': 1000, 'proj_range': 1000, 'max_shield': 18.0, 'shield': 100}, LD_stuff.atks['LD3.0'])

    LD3()
    LD2()
    upgrades()
    new_mage()
    LD()

mods()

# --------------------------- Main ----------------------------------

def main():
    game = Game()
    if IS_PYSCRIPT:
        asyncio.ensure_future(game.run())
    else:
        asyncio.run(game.run())

if __name__ == "__main__":
    main()