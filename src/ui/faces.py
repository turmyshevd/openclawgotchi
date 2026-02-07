"""
Central source of truth for all Gotchi faces.
Used by gotchi_ui.py (for rendering) and litellm_connector.py (for tool validation).
"""

# Default faces (THE SINGLE SOURCE OF TRUTH)
DEFAULT_FACES = {
    # === BASIC EMOTIONS ===
    "happy":        "(◕‿◕)",
    "happy2":       "(•‿‿•)",
    "sad":          "(╥☁╥ )",
    "excited":      "(ᵔ◡◡ᵔ)",
    "thinking":     "(￣ω￣)",
    "love":         "(♥‿‿♥)",
    "surprised":    "(◉_◉)",
    "grateful":     "(^‿‿^)",
    "motivated":    "(☼‿‿☼)",
    
    # === STATES ===
    "bored":        "(-__-)",
    "sleeping":     "( -_-)zZ",
    "sleeping_pwn": "(⇀‿‿↼)", # Pwnagotchi style
    "awakening":    "(≖‿‿≖)",
    "observing":    "( ⚆⚆)",
    "intense":      "(°▃▃°)",
    "cool":         "(⌐■_■)",
    "chill":        "(▰˘◡˘▰)",
    "hype":         "(╯°□°）╯",
    "hacker":       "[■_■]",
    "smart":        "(✜‿‿✜)",
    "broken":       "(☓‿‿☓)",
    "debug":        "(#__#)",
    
    # === EXTENDED ===
    "angry":        "(╬ಠ益ಠ)",
    "crying":       "(ಥ﹏ಥ)",
    "proud":        "(๑•̀ᴗ•́)و",
    "nervous":      "(°△°;)",
    "confused":     "(◎_◎;)",
    "mischievous":  "(◕‿↼)",
    "wink":         "(◕‿◕✿)",
    "dead":         "(✖_✖)",
    "shock":        "(◯△◯)",
    "suspicious":   "(¬_¬)",
    "smug":         "(￣‿￣)",    # Fixed (was same as thinking)
    "cheering":     "\\(◕◡◕)/",
    "celebrate":    "★(◕‿◕)★",
    "dizzy":        "(⊙๖⊙)",      # Standardized to kaomoji
    "lonely":       "(ب__ب)",
    "demotivated":  "(≖__≖)",
}

def get_all_faces() -> dict:
    """
    Load all faces: default + custom (from data/custom_faces.json).
    Custom faces override defaults if name matches.
    """
    import json
    from config import CUSTOM_FACES_PATH
    
    faces = DEFAULT_FACES.copy()
    
    if CUSTOM_FACES_PATH.exists():
        try:
            custom_faces = json.loads(CUSTOM_FACES_PATH.read_text())
            faces.update(custom_faces)
        except Exception:
            pass
            
    return faces
