from picosystem import *
import random
import machine

# =========================================================
# CONFIG / SAVE
# =========================================================
GAME_TITLE = "snake"
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
# Screen & grid
# ==========================
SW, SH = 120, 120
CELL = 8
COLS = SW // CELL
ROWS = (SH - 20) // CELL
OFFSET_Y = 20
TICK_RATE = 6

# ==========================
# Game state
# ==========================
STATE_PLAY = 0
STATE_DEAD = 1
state = STATE_PLAY
score = 0
hi_score = load_hi()

# ==========================
# Snake
# ==========================
snake = [(COLS//2, ROWS//2), (COLS//2-1, ROWS//2), (COLS//2-2, ROWS//2)]
dx, dy = 1, 0
next_dx, next_dy = 1, 0

# ==========================
# Fruit types
# ==========================
fruit = None
fruit_type = None
fruit_colour = (15, 2, 2)
FRUITS = [
    {"name":"apple",  "points":10, "colour":(15,2,2)},
    {"name":"banana", "points":20, "colour":(15,15,0)},
    {"name":"cherry", "points":30, "colour":(15,0,15)},
    {"name":"melon",  "points":50, "colour":(0,15,10)},
]

tick_count = 0
prev_left = prev_right = prev_up = prev_down = prev_a = False

# ==========================
# Sound
# ==========================
# Music track
MUSIC = [440, 550, 660, 550]  # simple repeating notes
music_idx = 0
music_timer = 0
music_voice = Voice(5, 2, 40, 60)

def music_tick():
    global music_idx, music_timer
    if state != STATE_PLAY:
        return
    if music_timer <= 0:
        sr = 20
        music_voice.play(MUSIC[music_idx], sr, 50)
        music_idx = (music_idx + 1) % len(MUSIC)
        music_timer = sr
    music_timer -= 1

# ==========================
# Helpers
# ==========================
def place_fruit():
    global fruit, fruit_type, fruit_colour
    occupied = set(snake)
    while True:
        fx = random.randint(0, COLS-1)
        fy = random.randint(0, ROWS-1)
        if (fx, fy) not in occupied:
            fruit = (fx, fy)
            fruit_type = random.choice(FRUITS)
            fruit_colour = fruit_type["colour"]
            return

def reset_game():
    global snake, dx, dy, next_dx, next_dy, score, state, tick_count
    snake  = [(COLS//2, ROWS//2), (COLS//2-1, ROWS//2), (COLS//2-2, ROWS//2)]
    dx, dy = 1, 0
    next_dx, next_dy = 1, 0
    score = 0
    state = STATE_PLAY
    tick_count = 0
    place_fruit()

place_fruit()

# ==========================
# Update
# ==========================
def update(tick):
    global dx, dy, next_dx, next_dy, snake, fruit, fruit_type, score, hi_score, state, tick_count
    global prev_left, prev_right, prev_up, prev_down, prev_a

    music_tick()

    if pressed(Y):
        machine.soft_reset()

    cl = button(LEFT); cr = button(RIGHT); cu = button(UP); cd = button(DOWN); ca = button(A)

    # Restart game if dead
    if state == STATE_DEAD:
        if ca and not prev_a:
            reset_game()
        prev_a = ca
        return

    # Direction (no 180 reversal)
    if cl and not prev_left and dx != 1:   next_dx, next_dy = -1, 0
    if cr and not prev_right and dx !=-1:  next_dx, next_dy =  1, 0
    if cu and not prev_up and dy != 1:     next_dx, next_dy =  0,-1
    if cd and not prev_down and dy !=-1:   next_dx, next_dy =  0, 1

    prev_left = cl; prev_right = cr; prev_up = cu; prev_down = cd; prev_a = ca

    tick_count += 1
    if tick_count < TICK_RATE:
        return
    tick_count = 0

    dx, dy = next_dx, next_dy
    hx, hy = snake[0]
    nx, ny = hx + dx, hy + dy

    # Check wall collision
    if nx < 0 or nx >= COLS or ny < 0 or ny >= ROWS:
        hi_score = max(hi_score, score)
        state = STATE_DEAD
        return

    # Self collision
    if (nx, ny) in snake:
        hi_score = max(hi_score, score)
        state = STATE_DEAD
        return

    snake.insert(0, (nx, ny))

    # Fruit collision
    if fruit and (nx, ny) == fruit:
        score += fruit_type["points"]
        hi_score = max(hi_score, score)
        place_fruit()
    else:
        snake.pop()

# ==========================
# Draw
# ==========================
def draw(tick):
    global snake, fruit, hi_score

    # Background
    pen(0,0,0)
    clear()

    # HUD
    pen(15,15,15)
    text(f"Score:{score}", 2, 2)
    text(f"Hi:{hi_score}", 60, 2)
    pen(3,3,3)
    frect(0, OFFSET_Y-1, SW, 1)

    # Game over
    if state == STATE_DEAD:
        pen(15,0,0);   text("GAME OVER", 28, 50)
        pen(15,15,15); text(f"Score:{score}", 30, 65)
        pen(8,8,8);    text("Press A to Retry", 18, 85)
        if score > hi_score:
            save_hi(score)
        return

    # Grid dots
    pen(1,1,1)
    for gy in range(ROWS):
        for gx in range(COLS):
            frect(gx*CELL + CELL//2, OFFSET_Y + gy*CELL + CELL//2, 1, 1)

    # Fruit
    if fruit:
        fx, fy = fruit
        pen(*fruit_colour)
        frect(fx*CELL + 1, OFFSET_Y + fy*CELL + 1, CELL-2, CELL-2)
        pen(15,15,15)
        frect(fx*CELL + 2, OFFSET_Y + fy*CELL + 2, 2,2)

    # Snake body
    for i, (sx, sy) in enumerate(snake):
        frac = 15 - (i * 8 // max(len(snake),1))
        g = max(4, frac)
        pen(0,g,0)
        frect(sx*CELL+1, OFFSET_Y+sy*CELL+1, CELL-2, CELL-2)

    # Snake head
    hx, hy = snake[0]
    pen(0,15,4)
    frect(hx*CELL, OFFSET_Y+hy*CELL, CELL, CELL)
    pen(15,15,15)
    # Eyes
    if dx == 1:
        frect(hx*CELL+5, OFFSET_Y+hy*CELL+1, 2,2)
        frect(hx*CELL+5, OFFSET_Y+hy*CELL+5, 2,2)
    elif dx == -1:
        frect(hx*CELL+1, OFFSET_Y+hy*CELL+1, 2,2)
        frect(hx*CELL+1, OFFSET_Y+hy*CELL+5, 2,2)
    elif dy == -1:
        frect(hx*CELL+1, OFFSET_Y+hy*CELL+1, 2,2)
        frect(hx*CELL+5, OFFSET_Y+hy*CELL+1, 2,2)
    else:
        frect(hx*CELL+1, OFFSET_Y+hy*CELL+5, 2,2)
        frect(hx*CELL+5, OFFSET_Y+hy*CELL+5, 2,2)

# ==========================
# Start game loop
# ==========================
start()