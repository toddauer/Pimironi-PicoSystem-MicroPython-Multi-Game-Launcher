from picosystem import *
import random
import os
import machine

# =========================================================
# CONFIG / SAVE
# =========================================================
GAME_TITLE = "tetris"
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
# Screen & board
# ==========================
SW, SH = 120, 120
COLS, ROWS = 10, 20
CELL = 5
BOARD_X = 5
BOARD_Y = 10
PANEL_X = BOARD_X + COLS * CELL + 4
PANEL_W = SW - PANEL_X - 2

# ==========================
# Pieces and colors
# ==========================
PIECES = [
    [[1,1,1,1]],
    [[1,1],[1,1]],
    [[0,1,0],[1,1,1]],
    [[1,0,0],[1,1,1]],
    [[0,0,1],[1,1,1]],
    [[0,1,1],[1,1,0]],
    [[1,1,0],[0,1,1]],
]
COLOURS = [
    (0,15,15),(15,15,0),(15,0,15),
    (0,0,15),(15,8,0),(0,15,0),(15,0,0),
]

hi_score = load_hi()

# ==========================
# Game state
# ==========================
score      = 0
level      = 1
lines      = 0
state      = 0   # 0=play, 1=dead

# ==========================
# Effects state
# ==========================
shake_frames  = 0
flash_frames  = 0
flash_color   = (15, 15, 15)
lock_flash    = 0            # brief highlight when piece locks
clear_rows    = []           # rows being held bright before wipe
clear_timer   = 0            # frames to hold cleared rows
CLEAR_HOLD    = 10           # frames to flash cleared lines
score_popup   = ""
score_popup_y = 0
score_popup_t = 0

# ==========================
# Music sequencer
# ==========================
# Tetris-flavoured minor descending melody, tempo scales with level
MELODY = [
    (659,8),(494,4),(523,8),(587,8),
    (523,4),(494,4),(440,8),(440,4),
    (523,8),(659,8),(587,4),(523,4),
    (494,12),(523,4),(659,8),
    (587,8),(523,4),(494,4),(440,16),
    (392,8),(392,4),(523,8),(659,8),
    (587,8),(523,4),(494,12),
    (523,4),(440,8),(440,16),
]
music_voice = Voice(3, 3, 60, 150)
music_voice.effects(reverb=40)
music_idx   = 0
music_timer = 0

def music_tick():
    global music_idx, music_timer
    if state != 0 or clear_timer > 0:
        return
    if music_timer <= 0:
        freq, dur = MELODY[music_idx]
        # Speed up music with level — higher level = shorter note duration
        scaled = max(3, dur - (level - 1))
        music_voice.play(freq, scaled * 12, 30)
        music_idx   = (music_idx + 1) % len(MELODY)
        music_timer = scaled
    music_timer -= 1

# ==========================
# Sound effects
# ==========================
move_snd  = Voice(2, 2, 20, 30)
rot_snd   = Voice(2, 2, 20, 40)
lock_snd  = Voice(5, 5, 30, 80)
clear_snd = Voice(5, 5, 80, 300)
clear_snd.effects(reverb=60)
clear_snd.bend(200, 400)
tetris_snd = Voice(10, 10, 100, 500)
tetris_snd.effects(reverb=80)
tetris_snd.bend(500, 600)
drop_snd  = Voice(3, 3, 10, 50)

# ==========================
# Piece state
# ==========================
board     = [[0] * COLS for _ in range(ROWS)]
piece     = None
piece_x   = 0
piece_y   = 0
piece_idx = 0
next_idx  = random.randint(0, 6)
fall_tick = 0
lock_delay = 0

# DAS
btn_l = btn_r = btn_u = btn_a = btn_d = False
das_left = das_right = 0
DAS_DELAY  = 8
DAS_REPEAT = 2

# ==========================
# Helpers
# ==========================
def new_piece():
    global piece, piece_x, piece_y, piece_idx, next_idx, fall_tick, lock_delay
    piece_idx = next_idx
    next_idx  = random.randint(0, 6)
    piece     = [row[:] for row in PIECES[piece_idx]]
    piece_x   = COLS // 2 - len(piece[0]) // 2
    piece_y   = 0
    fall_tick = 0
    lock_delay = 0
    if collide(piece, piece_x, piece_y):
        return False
    return True

def collide(p, ox, oy):
    for r, row in enumerate(p):
        for c, v in enumerate(row):
            if v:
                nx, ny = ox + c, oy + r
                if nx < 0 or nx >= COLS or ny >= ROWS:
                    return True
                if ny >= 0 and board[ny][nx]:
                    return True
    return False

def rotate(p):
    return [[p[r][c] for r in range(len(p)-1, -1, -1)] for c in range(len(p[0]))]

def ghost_y():
    gy = piece_y
    while not collide(piece, piece_x, gy + 1):
        gy += 1
    return gy

def lock_piece():
    global score, hi_score, lines, level, state
    global shake_frames, flash_frames, flash_color
    global clear_rows, clear_timer, score_popup, score_popup_y, score_popup_t
    global lock_flash

    ci = piece_idx + 1
    for r, row in enumerate(piece):
        for c, v in enumerate(row):
            if v and piece_y + r >= 0:
                board[piece_y + r][piece_x + c] = ci

    lock_flash = 4
    lock_snd.play(300, 60, 70)

    # Find cleared lines
    full_rows = [r for r in range(ROWS) if all(board[r][c] for c in range(COLS))]
    cleared   = len(full_rows)

    if cleared:
        clear_rows  = full_rows[:]
        clear_timer = CLEAR_HOLD

        pts = [0, 100, 300, 500, 800][cleared] * level
        score += pts
        lines += cleared
        level  = 1 + lines // 10
        hi_score = max(hi_score, score)
        try:
            with open(hi_score_file, "w") as f:
                f.write(str(hi_score))
        except:
            pass

        # Score popup
        score_popup   = f"+{pts}"
        score_popup_y = BOARD_Y + (full_rows[0] * CELL)
        score_popup_t = 45

        if cleared == 4:
            tetris_snd.play(880, 400, 90)
            flash_frames = 12
            flash_color  = (15, 15, 0)
        else:
            clear_snd.play(600 + cleared * 80, 200, 80)
            flash_frames = 6
            flash_color  = (15, 15, 15)
    else:
        if not new_piece():
            state        = 1
            shake_frames = 20
            flash_frames = 8
            flash_color  = (15, 0, 0)

def apply_clear():
    """Called after clear_timer expires — actually remove the rows."""
    global clear_rows, clear_timer
    if not clear_rows:
        return
    new_board = [row for i, row in enumerate(board) if i not in clear_rows]
    for _ in range(len(clear_rows)):
        new_board.insert(0, [0] * COLS)
    board[:] = new_board
    clear_rows = []
    clear_timer = 0
    if not new_piece():
        global state, shake_frames, flash_frames, flash_color
        state        = 1
        shake_frames = 20
        flash_frames = 8
        flash_color  = (15, 0, 0)

# ==========================
# Initialise
# ==========================
board = [[0] * COLS for _ in range(ROWS)]
new_piece()

# ==========================
# Update
# ==========================
def update(tick):
    global piece, piece_x, piece_y, piece_idx, next_idx
    global fall_tick, lock_delay, state
    global btn_l, btn_r, btn_u, btn_a, btn_d
    global das_left, das_right
    global score, lines, level, hi_score, board
    global shake_frames, flash_frames, lock_flash
    global clear_timer, score_popup_t

    music_tick()

    if shake_frames > 0: shake_frames -= 1
    if flash_frames > 0: flash_frames -= 1
    if lock_flash   > 0: lock_flash   -= 1
    if score_popup_t > 0: score_popup_t -= 1

    if pressed(Y):
        machine.soft_reset()

    nb_l = button(LEFT)
    nb_r = button(RIGHT)
    nb_u = button(UP)
    nb_a = button(A)
    nb_d = button(DOWN)

    if state == 1:
        if nb_a and not btn_a:
            board  = [[0] * COLS for _ in range(ROWS)]
            score  = 0
            lines  = 0
            level  = 1
            state  = 0
            new_piece()
        btn_l = nb_l; btn_r = nb_r; btn_u = nb_u
        btn_a = nb_a; btn_d = nb_d
        return

    # Waiting for line clear animation
    if clear_timer > 0:
        clear_timer -= 1
        if clear_timer == 0:
            apply_clear()
        btn_l = nb_l; btn_r = nb_r; btn_u = nb_u
        btn_a = nb_a; btn_d = nb_d
        return

    # Rotation
    if nb_u and not btn_u:
        rot = rotate(piece)
        for kick in [0, 1, -1, 2, -2]:
            if not collide(rot, piece_x + kick, piece_y):
                piece   = rot
                piece_x += kick
                rot_snd.play(800, 20, 50)
                break

    # DAS left
    if nb_l:
        das_left = 0 if not btn_l else das_left + 1
        if das_left == 0 or (das_left >= DAS_DELAY and (das_left - DAS_DELAY) % DAS_REPEAT == 0):
            if not collide(piece, piece_x - 1, piece_y):
                piece_x -= 1
                move_snd.play(600, 10, 40)
    else:
        das_left = 0

    # DAS right
    if nb_r:
        das_right = 0 if not btn_r else das_right + 1
        if das_right == 0 or (das_right >= DAS_DELAY and (das_right - DAS_DELAY) % DAS_REPEAT == 0):
            if not collide(piece, piece_x + 1, piece_y):
                piece_x += 1
                move_snd.play(600, 10, 40)
    else:
        das_right = 0

    # Hard drop
    if nb_a and not btn_a:
        drop_pts = 0
        while not collide(piece, piece_x, piece_y + 1):
            piece_y  += 1
            drop_pts += 2
        score += drop_pts
        drop_snd.play(200, 40, 60)
        lock_piece()

    btn_l = nb_l; btn_r = nb_r; btn_u = nb_u
    btn_a = nb_a; btn_d = nb_d

    # Gravity
    fall_rate = max(2, 45 - level * 4)
    if nb_d:
        fall_rate = 2
    fall_tick += 1
    if fall_tick >= fall_rate:
        fall_tick = 0
        if not collide(piece, piece_x, piece_y + 1):
            piece_y   += 1
            lock_delay = 0
            if nb_d:
                score += 1   # soft drop bonus point per row
        else:
            # Soft drop: lock immediately when piece hits ground
            if nb_d:
                lock_piece()
            else:
                lock_delay += 1
                if lock_delay >= 30:
                    lock_piece()

# ==========================
# Draw
# ==========================
def draw(tick):
    ox = random.randint(-2, 2) if shake_frames > 0 else 0
    oy = random.randint(-2, 2) if shake_frames > 0 else 0

    # Flash overlay
    if flash_frames > 0:
        r, g, b = flash_color
        pen(r, g, b)
        clear()
    else:
        pen(0, 0, 1)
        clear()

    # -------- BOARD BORDER --------
    pen(3, 3, 5)
    frect(BOARD_X - 2 + ox, BOARD_Y - 2 + oy, COLS * CELL + 4, ROWS * CELL + 4)
    pen(0, 0, 1)
    frect(BOARD_X + ox, BOARD_Y + oy, COLS * CELL, ROWS * CELL)

    # -------- GRID LINES --------
    pen(1, 1, 2)
    for col in range(1, COLS):
        frect(BOARD_X + col * CELL + ox, BOARD_Y + oy, 1, ROWS * CELL)
    for row in range(1, ROWS):
        frect(BOARD_X + ox, BOARD_Y + row * CELL + oy, COLS * CELL, 1)

    # -------- BOARD CELLS --------
    for r in range(ROWS):
        # Cleared row flash: draw bright white
        if r in clear_rows:
            flash_v = 15 if (clear_timer % 3) < 2 else 8
            pen(flash_v, flash_v, flash_v)
            frect(BOARD_X + ox, BOARD_Y + r * CELL + oy, COLS * CELL, CELL)
            continue
        for c in range(COLS):
            v = board[r][c]
            if v:
                cr, cg, cb = COLOURS[v - 1]
                pen(cr, cg, cb)
                frect(BOARD_X + c * CELL + ox, BOARD_Y + r * CELL + oy, CELL, CELL)
                # highlight edges
                pen(min(15, cr + 5), min(15, cg + 5), min(15, cb + 5))
                frect(BOARD_X + c * CELL + ox, BOARD_Y + r * CELL + oy, CELL, 1)
                frect(BOARD_X + c * CELL + ox, BOARD_Y + r * CELL + oy, 1, CELL)
                # shadow
                pen(max(0, cr - 4), max(0, cg - 4), max(0, cb - 4))
                frect(BOARD_X + c * CELL + ox, BOARD_Y + r * CELL + CELL - 1 + oy, CELL, 1)
                frect(BOARD_X + c * CELL + CELL - 1 + ox, BOARD_Y + r * CELL + oy, 1, CELL)

    # -------- GHOST PIECE --------
    if piece and state == 0 and clear_timer == 0:
        gy = ghost_y()
        gcr, gcg, gcb = COLOURS[piece_idx]
        pen(gcr // 5, gcg // 5, gcb // 5)
        for r, row in enumerate(piece):
            for c, v in enumerate(row):
                if v:
                    frect(BOARD_X + (piece_x + c) * CELL + ox,
                          BOARD_Y + (gy + r) * CELL + oy, CELL, CELL)

        # -------- ACTIVE PIECE --------
        pcr, pcg, pcb = COLOURS[piece_idx]
        # lock flash: brighten the piece briefly when it locks
        if lock_flash > 0:
            pcr = min(15, pcr + 6)
            pcg = min(15, pcg + 6)
            pcb = min(15, pcb + 6)
        pen(pcr, pcg, pcb)
        for r, row in enumerate(piece):
            for c, v in enumerate(row):
                if v and piece_y + r >= 0:
                    px2 = BOARD_X + (piece_x + c) * CELL + ox
                    py2 = BOARD_Y + (piece_y + r) * CELL + oy
                    frect(px2, py2, CELL, CELL)
                    pen(min(15, pcr + 5), min(15, pcg + 5), min(15, pcb + 5))
                    frect(px2, py2, CELL, 1)
                    frect(px2, py2, 1, CELL)

    # -------- RIGHT PANEL --------
    pen(2, 2, 4)
    frect(PANEL_X - 1, BOARD_Y - 2, PANEL_W + 2, ROWS * CELL + 4)

    pen(15, 15, 15)
    text("HI", PANEL_X + 1, BOARD_Y)
    pen(15, 13, 0)
    text(str(hi_score), PANEL_X + 1, BOARD_Y + 7)

    pen(15, 15, 15)
    text("SC", PANEL_X + 1, BOARD_Y + 17)
    pen(12, 15, 12)
    text(str(score), PANEL_X + 1, BOARD_Y + 24)

    pen(15, 15, 15)
    text("LV", PANEL_X + 1, BOARD_Y + 34)
    pen(12, 12, 15)
    text(str(level), PANEL_X + 1, BOARD_Y + 41)

    pen(15, 15, 15)
    text("LN", PANEL_X + 1, BOARD_Y + 51)
    pen(12, 15, 15)
    text(str(lines), PANEL_X + 1, BOARD_Y + 58)

    # -------- NEXT PIECE PREVIEW BOX --------
    pen(15, 15, 15)
    text("NX", PANEL_X + 1, BOARD_Y + 68)
    pen(3, 3, 6)
    frect(PANEL_X, BOARD_Y + 76, PANEL_W, 22)
    if piece:
        npiece         = PIECES[next_idx]
        ncr, ncg, ncb = COLOURS[next_idx]
        pen(ncr, ncg, ncb)
        # centre the preview
        pw = len(npiece[0]) * CELL
        ph = len(npiece)    * CELL
        nx_off = PANEL_X + (PANEL_W - pw) // 2
        ny_off = BOARD_Y + 76 + (22 - ph) // 2
        for r, row in enumerate(npiece):
            for c, v in enumerate(row):
                if v:
                    frect(nx_off + c * CELL, ny_off + r * CELL, CELL - 1, CELL - 1)

    # -------- SCORE POPUP --------
    if score_popup_t > 0 and score_popup:
        alpha = min(score_popup_t, 15)
        pen(15, 15, 0)
        rise = (45 - score_popup_t) // 3
        text(score_popup, BOARD_X + 6, score_popup_y - rise)

    # -------- GAME OVER OVERLAY --------
    if state == 1:
        pen(0, 0, 0)
        frect(BOARD_X + 2 + ox, SH // 2 - 18 + oy, COLS * CELL - 4, 42)
        pen(15, 0, 0)
        text("GAME OVER", BOARD_X + 4 + ox, SH // 2 - 12 + oy)
        pen(15, 15, 15)
        text(f"Score:{score}", BOARD_X + 4 + ox, SH // 2 - 2 + oy)
        pen(10, 10, 10)
        text("A: retry", BOARD_X + 8 + ox, SH // 2 + 8 + oy)
        text("Y: menu", BOARD_X + 8 + ox, SH // 2 + 16 + oy)
        if score > hi_score:
            save_hi(score)

# ==========================
# Start
# ==========================
start()