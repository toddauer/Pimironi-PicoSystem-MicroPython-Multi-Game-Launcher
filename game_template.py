###########################################################
#################### GAME TEMPLATE ########################
###########################################################

# =========================================================
# CONFIG / SAVE
# =========================================================
GAME_TITLE = ""
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

def load_config():
    cfg = {"brightness": 8, "volume": 8, "sleep": 3}
    try:
        with open(CONFIG_PATH, "r") as f:
            for line in f:
                line = line.strip()
                if "=" in line and not line.startswith("#"):
                    key, _, val = line.partition("=")
                    key = key.strip()
                    if key in cfg:
                        cfg[key] = int(val.strip())
    except OSError:
        pass
    return cfg

# Apply system settings
_cfg = load_config()
backlight(_cfg["brightness"] * 6)
_vol = _cfg["volume"]


# GAME LOGIC
def update(tick):
    pass

def draw(tick):
    pass

start()