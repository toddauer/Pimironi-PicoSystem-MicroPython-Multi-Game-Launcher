from picosystem import *
import random
import machine

# =========================================================
# CONFIG / SAVE
# =========================================================
GAME_TITLE = "space_invaders"
CONFIG_PATH = "/save_files/config.txt"
SAVE_PATH   = "/save_files/"+GAME_TITLE+"_hi.txt"



def load_hi():
    try:
        with open(SAVE_PATH, "r") as f:
            return int(f.read().strip())
    except OSError:
        return 0

def save_hi(score):
    try:
        with open(SAVE_PATH, "w") as f:
            f.write(str(score))
    except OSError:
        pass
    
# ==========================
# Screen
# ==========================
SW, SH = 120, 120

# ==========================
# Game states
# ==========================
STATE_PLAY = 0
STATE_DEAD = 1
STATE_WIN  = 2
STATE_WAVE = 3
hi_score = load_hi()

# ==========================
# Player
# ==========================
PLAYER_SPEED = 2
BULLET_SPEED = 5
px         = SW // 2 - 6
py         = SH - 14
p_bullet   = None
p_shoot_cd = 0

# ==========================
# Invaders
# ==========================
ROWS, COLS   = 4, 6
INV_W, INV_H = 11, 7
INV_XGAP     = 5
INV_YGAP     = 4
GRID_X_START = 8
GRID_Y_START = 14
INVADER_STEP = 22
inv_dx       = 1
inv_timer    = 0
inv_drop     = False
grid_ox      = 0
grid_oy      = 0
inv_frame    = 0
invaders     = []
living_cache = []   # cached alive() result, rebuilt once per tick

# ==========================
# UFO
# ==========================
ufo_x        = -1
ufo_active   = False
UFO_SPEED    = 1
ufo_timer    = 0
UFO_INTERVAL = 600

# ==========================
# Bombs
# ==========================
BOMB_SPEED = 2
bombs      = []

# ==========================
# Explosions
# ==========================
explosions = []   # [x, y, timer, type]

# ==========================
# Bunkers
# Stored as flat lists for speed:
# bx, by, cells[40 ints], shape[40 ints], hp (cached intact count)
# ==========================
BUNKER_SHAPE = [
    0,1,1,1,1,1,0,0,0,0,
    1,1,1,1,1,1,1,1,1,1,
    1,1,1,0,0,1,1,1,1,1,
    1,1,1,0,0,1,1,1,1,1,
]
BUNKER_TOTAL = sum(BUNKER_SHAPE)   # 32

def make_bunker(x, y):
    # [bx, by, cells(40), hp]
    return [x, y, list(BUNKER_SHAPE), BUNKER_TOTAL]

bunkers = [make_bunker(8, SH-32), make_bunker(48, SH-32), make_bunker(88, SH-32)]

def draw_bunker(b):
    bx, by, cells, hp = b[0], b[1], b[2], b[3]
    ratio = hp / BUNKER_TOTAL
    if ratio > 0.66:
        pen(0, 15, 0)
    elif ratio > 0.33:
        pen(12, 12, 0)
    else:
        pen(15, 4, 0)
    idx = 0
    for r in range(4):
        cy = by + r * 3
        for c in range(10):
            if BUNKER_SHAPE[idx] and cells[idx]:
                frect(bx + c*2, cy, 2, 3)
            idx += 1

def damage_bunker(b, bx2, by2, w, h):
    bx, by, cells = b[0], b[1], b[2]
    hit = False
    idx = 0
    for r in range(4):
        cy = by + r * 3
        for c in range(10):
            if BUNKER_SHAPE[idx] and cells[idx]:
                cx2 = bx + c*2
                if not (bx2+w < cx2 or bx2 > cx2+2 or by2+h < cy or by2 > cy+3):
                    cells[idx] = 0
                    b[3] -= 1   # decrement cached hp
                    hit = True
            idx += 1
    return hit

def bunker_intersects(bx2, by2, w, h):
    for b in bunkers:
        if b[3] > 0 and damage_bunker(b, bx2, by2, w, h):
            return True
    return False

# ==========================
# Game state
# ==========================
state        = STATE_PLAY
score        = 0
wave         = 1
lives        = 3
wave_msg_ttl = 0
prev_a       = False
shake_frames = 0
flash_frames = 0

# Cached HUD string widths — only recompute when values change
_hud_score     = -1
_hud_score_w   = 0
_hud_hi        = -1
_hud_hi_x      = 0

# ==========================
# Music
# ==========================
MARCH       = [160, 130, 110, 130]
march_idx   = 0
march_timer = 0
march_voice = Voice(5, 2, 40, 60)

def music_tick():
    global march_idx, march_timer
    if state != STATE_PLAY:
        return
    sr = current_step_rate()
    if march_timer <= 0:
        march_voice.play(MARCH[march_idx], sr * 8, 45)
        march_idx   = (march_idx + 1) % 4
        march_timer = sr
    march_timer -= 1

# ==========================
# Sound effects
# ==========================
shoot_snd   = Voice(3, 3, 20, 60)
shoot_snd.bend(300, 200)
inv_die_snd = Voice(5, 5, 40, 120)
inv_die_snd.bend(200, 300)
p_die_snd   = Voice(10, 10, 80, 400)
p_die_snd.effects(reverb=60)
ufo_snd     = Voice(3, 3, 30, 80)
ufo_snd.bend(400, 200)
wave_snd    = Voice(5, 5, 60, 300)
wave_snd.effects(reverb=50)
wave_snd.bend(300, 600)

# ==========================
# Helpers
# ==========================
def new_invaders():
    global invaders, living_cache
    invaders     = [[c, r, True] for r in range(ROWS) for c in range(COLS)]
    living_cache = invaders[:]

def refresh_living():
    global living_cache
    living_cache = [i for i in invaders if i[2]]

def ipos(inv):
    return (GRID_X_START + inv[0]*(INV_W+INV_XGAP) + grid_ox,
            GRID_Y_START + inv[1]*(INV_H+INV_YGAP) + grid_oy)

def intersects(x, y, w, h, cx, cy, cw, ch):
    return not (x+w < cx or x > cx+cw or y+h < cy or y > cy+ch)

def current_step_rate():
    n = len(living_cache)
    base = max(4, INVADER_STEP - wave * 2)
    return max(3, base - (ROWS*COLS - n) // 2)

def kill_score(inv):
    base        = [10, 20, 30, 40][inv[1]]
    speed_bonus = max(1, (ROWS*COLS - len(living_cache)) // 4)
    return base * speed_bonus * wave

def reset_game():
    global px, py, p_bullet, p_shoot_cd, bombs, explosions
    global inv_dx, inv_timer, inv_drop, grid_ox, grid_oy
    global score, lives, state, wave, prev_a
    global ufo_x, ufo_active, ufo_timer
    global shake_frames, flash_frames, wave_msg_ttl, inv_frame
    px         = SW // 2 - 6
    py         = SH - 14
    p_bullet   = None
    p_shoot_cd = 0
    bombs      = []
    explosions = []
    inv_dx     = 1
    inv_timer  = 0
    inv_drop   = False
    grid_ox    = 0
    grid_oy    = 0
    score      = 0
    lives      = 3
    wave       = 1
    state      = STATE_PLAY
    prev_a     = False
    ufo_x      = -1
    ufo_active = False
    ufo_timer  = 0
    shake_frames = 0
    flash_frames = 0
    wave_msg_ttl = 0
    inv_frame    = 0
    for b in bunkers:
        b[2] = list(BUNKER_SHAPE)
        b[3] = BUNKER_TOTAL
    new_invaders()

def next_wave():
    global inv_dx, inv_timer, inv_drop, grid_ox, grid_oy
    global bombs, explosions, state, wave_msg_ttl, inv_frame
    global ufo_x, ufo_active, ufo_timer
    wave_msg_ttl = 90
    bombs        = []
    explosions   = []
    inv_dx       = 1
    inv_timer    = 0
    inv_drop     = False
    inv_frame    = 0
    grid_ox      = 0
    grid_oy      = min(20, (wave - 1) * 4)
    ufo_x        = -1
    ufo_active   = False
    ufo_timer    = 0
    state        = STATE_WAVE
    wave_snd.play(660, 300, 80)
    new_invaders()

reset_game()

# ==========================
# Draw alien shapes
# ==========================
def draw_invader(ix, iy, row, frame, cr, cg, cb):
    pen(cr, cg, cb)
    if row == 0:
        frect(ix+2, iy+2, 7, 4)
        frect(ix+4, iy,   3, 2)
        pixel(ix+1, iy+1)
        pixel(ix+9, iy+1)
        if frame == 0:
            pixel(ix,    iy+5)
            pixel(ix+10, iy+5)
        else:
            pixel(ix,    iy+4)
            pixel(ix+10, iy+4)
        pixel(ix+2, iy+6)
        pixel(ix+8, iy+6)
    elif row <= 2:
        frect(ix+1, iy+1, 9, 4)
        frect(ix+3, iy,   5, 1)
        pen(0, 0, 0)
        pixel(ix+3, iy+2)
        pixel(ix+7, iy+2)
        pen(cr, cg, cb)
        if frame == 0:
            pixel(ix+1, iy+5)
            pixel(ix+4, iy+5)
            pixel(ix+6, iy+5)
            pixel(ix+9, iy+5)
        else:
            pixel(ix+2,  iy+5)
            pixel(ix+5,  iy+5)
            pixel(ix+7,  iy+5)
            pixel(ix+10, iy+5)
    else:
        frect(ix+2, iy+1, 7, 5)
        frect(ix+4, iy,   3, 1)
        if frame == 0:
            frect(ix,   iy+2, 2, 2)
            frect(ix+9, iy+2, 2, 2)
        else:
            frect(ix,   iy+3, 2, 2)
            frect(ix+9, iy+3, 2, 2)
        pen(max(0,cr-4), max(0,cg-4), max(0,cb-4))
        pixel(ix+4, iy+4)
        pixel(ix+6, iy+4)

def draw_player(x, y):
    pen(0, 12, 15)
    frect(x+2, y+2, 8, 4)
    frect(x+4, y,   4, 3)
    frect(x,   y+4, 3, 2)
    frect(x+9, y+4, 3, 2)
    pen(15, 15, 15)
    frect(x+5, y+1, 2, 2)

def draw_ufo(x, y):
    pen(15, 0, 0)
    frect(x+3, y+2, 14, 4)
    frect(x+5, y,   10, 3)
    pen(15, 12, 0)
    pixel(x+5,  y+3)
    pixel(x+9,  y+3)
    pixel(x+13, y+3)

# ==========================
# Update
# ==========================
def update(tick):
    global px, py, p_bullet, p_shoot_cd, state, prev_a
    global inv_dx, inv_timer, inv_drop, grid_ox, grid_oy
    global bombs, explosions, score, lives, hi_score, wave
    global ufo_x, ufo_active, ufo_timer
    global shake_frames, flash_frames, wave_msg_ttl, inv_frame

    music_tick()

    if shake_frames > 0: shake_frames -= 1
    if flash_frames > 0: flash_frames -= 1
    if wave_msg_ttl > 0: wave_msg_ttl -= 1
    if p_shoot_cd   > 0: p_shoot_cd   -= 1

    if pressed(Y):
        machine.soft_reset()

    nb_a = button(A)

    if state == STATE_WAVE:
        if wave_msg_ttl == 0:
            state = STATE_PLAY
        prev_a = nb_a
        return

    if state in (STATE_DEAD, STATE_WIN):
        if score > hi_score:
            save_hi(score)
        if nb_a and not prev_a:
            reset_game()
        prev_a = nb_a
        return

    # -------- PLAYER MOVEMENT --------
    if button(LEFT)  and px > 0:      px -= PLAYER_SPEED
    if button(RIGHT) and px < SW-12:  px += PLAYER_SPEED

    # -------- SHOOT --------
    if (nb_a or button(B)) and p_bullet is None and p_shoot_cd == 0:
        p_bullet   = [px + 5, py - 6]
        p_shoot_cd = 14
        shoot_snd.play(1200, 60, 60)

    # -------- BULLET MOVEMENT --------
    if p_bullet:
        p_bullet[1] -= BULLET_SPEED
        if p_bullet[1] < 0:
            p_bullet = None

    # -------- UFO --------
    ufo_timer += 1
    if not ufo_active and ufo_timer >= UFO_INTERVAL:
        ufo_active = True
        ufo_x      = -20
        ufo_timer  = 0
    if ufo_active:
        ufo_x += UFO_SPEED
        if ufo_x > SW + 20:
            ufo_active = False
            ufo_x      = -1

    # -------- INVADER STEP --------
    inv_timer += 1
    step_rate  = current_step_rate()

    if inv_timer >= step_rate:
        inv_timer = 0
        inv_frame = 1 - inv_frame
        living    = living_cache

        if living:
            # Compute all positions once
            positions = [ipos(i) for i in living]
            xs = [p[0] for p in positions]

            if inv_drop:
                grid_oy += 5
                inv_dx   = -inv_dx
                inv_drop = False
            else:
                if max(xs) + INV_W >= SW - 2 and inv_dx > 0:
                    inv_drop = True
                elif min(xs) <= 2 and inv_dx < 0:
                    inv_drop = True
                else:
                    grid_ox += inv_dx * 2

            # Bombs: bottom invader per column using cached positions
            col_bottom = {}
            for i, inv in enumerate(living):
                c = inv[0]
                if c not in col_bottom or inv[1] > col_bottom[c][0][1]:
                    col_bottom[c] = (inv, positions[i])

            bomb_chance = max(15, 60 - wave * 5)
            for inv, (bx2, by2) in col_bottom.values():
                if random.randint(0, bomb_chance) == 0:
                    bombs.append([bx2 + 4, by2 + INV_H])

    # -------- BOMB MOVEMENT --------
    next_bombs = []
    for b in bombs:
        b[1] += BOMB_SPEED
        if b[1] < SH:
            next_bombs.append(b)
    bombs[:] = next_bombs

    # -------- BULLET HITS UFO --------
    if p_bullet and ufo_active:
        bx2, by2 = p_bullet
        if intersects(bx2, by2, 2, 6, ufo_x, 4, 20, 6):
            pts       = random.choice([50, 100, 150, 300])
            score    += pts
            hi_score  = max(hi_score, score)
            explosions.append([ufo_x + 10, 7, 20, 2])
            ufo_active = False
            ufo_x      = -1
            p_bullet   = None
            ufo_snd.play(880, 200, 80)

    # -------- BULLET HITS INVADER --------
    if p_bullet:
        bx2, by2 = p_bullet
        for inv in invaders:
            if not inv[2]: continue
            ix, iy = ipos(inv)
            if intersects(bx2, by2, 2, 6, ix, iy, INV_W, INV_H):
                inv[2]   = False
                pts      = kill_score(inv)
                score   += pts
                hi_score = max(hi_score, score)
                explosions.append([ix + 4, iy + 2, 12, 0])
                p_bullet = None
                inv_die_snd.play(400 + inv[1]*80, 100, 70)
                refresh_living()   # update cache after kill
                break

    # -------- BULLET HITS BUNKER --------
    if p_bullet:
        if bunker_intersects(p_bullet[0], p_bullet[1], 2, 6):
            p_bullet = None

    # -------- BOMBS HIT PLAYER --------
    for b in bombs[:]:
        if intersects(b[0], b[1], 3, 6, px, py, 12, 8):
            bombs.remove(b)
            explosions.append([px + 4, py + 2, 20, 1])
            lives       -= 1
            shake_frames = 16
            flash_frames = 8
            p_die_snd.play(180, 400, 100)
            px       = SW // 2 - 6
            p_bullet = None
            if lives <= 0:
                hi_score = max(hi_score, score)
                state = STATE_DEAD
            break

    # -------- BOMBS HIT BUNKERS --------
    for b in bombs[:]:
        if bunker_intersects(b[0], b[1], 3, 6):
            if b in bombs:
                bombs.remove(b)

    # -------- INVADERS REACH PLAYER LINE --------
    for inv in living_cache:
        if ipos(inv)[1] + INV_H >= py:
            hi_score = max(hi_score, score)
            state = STATE_DEAD
            break

    # -------- WAVE CLEAR --------
    if not living_cache:
        wave += 1
        next_wave()

    # -------- REDUCE EXPLOSIONS --------
    explosions[:] = [[x, y, t-1, tp] for x, y, t, tp in explosions if t > 0]

    prev_a = nb_a

# ==========================
# Draw
# ==========================
# Pre-computed invader colour table
ICOLS = [(15, 0, 15), (15, 10, 0), (0, 15, 8), (0, 10, 15)]

def draw(tick):
    global _hud_score, _hud_score_w, _hud_hi, _hud_hi_x

    ox = random.randint(-2, 2) if shake_frames > 0 else 0
    oy = random.randint(-2, 2) if shake_frames > 0 else 0

    if flash_frames > 0:
        pen(15, 3, 0)
        clear()
    else:
        pen(0, 0, 0)
        clear()

    # -------- STARS (static positions, no per-frame math) --------
    pen(8, 8, 10)
    pixel(7,  21); pixel(38, 13); pixel(69, 30); pixel(100, 8)
    pixel(15, 45); pixel(55, 52); pixel(90, 41); pixel(110, 28)
    pixel(25, 70); pixel(75, 65); pixel(105,75); pixel(42, 85)

    # -------- HUD --------
    pen(15, 15, 15)
    # Cache score label width so measure() isn't called every frame
    if score != _hud_score:
        _hud_score   = score
        _hud_score_w, _ = measure(f"SC:{score}")
    text(f"SC:{score}", 2, 1)

    pen(15, 13, 0)
    if hi_score != _hud_hi:
        _hud_hi  = hi_score
        hw, _    = measure(f"HI:{hi_score}")
        _hud_hi_x = SW - hw - 2
    text(f"HI:{hi_score}", _hud_hi_x, 1)

    pen(10, 10, 12)
    text(f"W{wave}", SW//2 - 6, 1)

    # Lives as tiny ship icons
    pen(0, 10, 14)
    for l in range(lives):
        lx = 2 + l * 14
        ly = SH - 9
        frect(lx+2, ly+2, 6, 3)
        frect(lx+3, ly,   4, 3)
        frect(lx,   ly+3, 3, 2)
        frect(lx+7, ly+3, 3, 2)

    # -------- BUNKERS --------
    for b in bunkers:
        if b[3] > 0:
            draw_bunker(b)

    # -------- INVADERS --------
    for inv in invaders:
        if inv[2]:
            ix, iy = ipos(inv)
            cr, cg, cb = ICOLS[inv[1]]
            draw_invader(ix + ox, iy + oy, inv[1], inv_frame, cr, cg, cb)

    # -------- UFO --------
    if ufo_active:
        draw_ufo(ufo_x, 4)

    # -------- PLAYER --------
    if state == STATE_PLAY or state == STATE_WAVE:
        draw_player(px + ox, py + oy)

    # -------- BULLET --------
    if p_bullet:
        pen(15, 15, 0)
        frect(p_bullet[0] + ox, p_bullet[1] + oy, 2, 6)

    # -------- BOMBS --------
    pen(15, 4, 0)
    for b in bombs:
        frect(b[0],   b[1],   2, 2)
        frect(b[0]+1, b[1]+2, 2, 2)
        frect(b[0],   b[1]+4, 2, 2)

    # -------- EXPLOSIONS --------
    for ex in explosions:
        x, y, t, tp = ex
        if tp == 1:
            pen(15, 8, 0)
            r = (20 - t) // 3 + 1
            frect(x - r, y,     r*2, 2)
            frect(x,     y - r, 2,   r*2)
            pen(15, 15, 0)
            frect(x-1, y-1, 3, 3)
        elif tp == 2:
            pen(15, 13, 0)
            r = (20 - t) // 2 + 1
            frect(x - r, y - 1, r*2, 3)
            frect(x - 1, y - r, 3,   r*2)
        else:
            pen(15, min(15, 6 + t), 0)
            frect(x-2, y-2, 6, 6)
            pen(15, 15, 0)
            frect(x, y, 2, 2)

    # -------- WAVE BANNER --------
    if state == STATE_WAVE or wave_msg_ttl > 0:
        pen(0, 0, 0)
        frect(SW//2 - 40, SH//2 - 10, 80, 20)
        pen(0, 15, 8)
        text(f"WAVE {wave}", SW//2 - 22, SH//2 - 4)

    # -------- GAME OVER --------
    if state == STATE_DEAD:
        pen(0, 0, 0)
        frect(SW//2 - 44, SH//2 - 18, 88, 40)
        pen(15, 0, 0)
        text("GAME OVER", SW//2 - 34, SH//2 - 12)
        pen(15, 15, 15)
        text(f"Score: {score}", SW//2 - 26, SH//2 - 2)
        pen(10, 10, 10)
        text("Press A to retry", SW//2 - 38, SH//2 + 10)

# ==========================
# Start
# ==========================
start()