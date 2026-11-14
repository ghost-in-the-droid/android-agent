"""chess helpers (Square Chess, com.dataespresso.squarechess).

Every board square is an accessibility node with content-desc "e2, white pawn" / "a6, empty", so the whole position is
readable. A move is two taps (from square, then to square). The computer answers by itself; its reply and the SAN move
list are real text. Moves are given as UCI squares ("e2e4", "g1f3"; a fifth letter q/r/b/n picks a promotion).

Uses the engine-fixed API: python_action returns a plain dict that is merged into context.result.
"""
from __future__ import annotations

import re
import time

_PIECE = {"king": "k", "queen": "q", "rook": "r", "bishop": "b", "knight": "n", "pawn": "p"}
# a selected piece or a legal target can carry a suffix ("e4, empty, legal move"), so only the prefix is fixed
_SQ = re.compile(r"^([a-h][1-8]), (empty|white (king|queen|rook|bishop|knight|pawn)|black (king|queen|rook|bishop|knight|pawn))")


def _xml(device) -> str:
    """Portal tree (engine fix 0064b380 keeps legal-target squares and transient nodes)."""
    return device.dump_xml()


def _nodes(device) -> list[dict]:
    out = []
    for m in re.finditer(r"<node ([^>]*)>", _xml(device)):
        a = dict(re.findall(r'([\w-]+)="([^"]*)"', m.group(1)))
        nums = [int(v) for v in re.findall(r"-?\d+", a.get("bounds", ""))]
        if len(nums) == 4 and nums[2] > nums[0] and nums[3] > nums[1] and nums[0] >= 0:
            out.append({"text": a.get("text", "").replace("&#10;", "\n"), "desc": a.get("content-desc", ""),
                        "bounds": tuple(nums)})
    return out


def _centre(b):
    return (b[0] + b[2]) // 2, (b[1] + b[3]) // 2


def squares(nodes) -> dict[str, tuple[str, tuple]]:
    sq = {}
    for n in nodes:
        m = _SQ.match(n["desc"])
        if m:
            sq[m.group(1)] = (m.group(2), n["bounds"])
    return sq


def _board_nodes(device, tries: int = 6) -> list[dict]:
    """Nodes with all 64 squares: right after a tap or a new game the tree can lag (62 of 64); poll briefly.
    Returns whatever the last read had when no board is on screen (home, dialog)."""
    nodes = _nodes(device)
    for _ in range(tries):
        n = len(squares(nodes))
        if n == 64 or n == 0 and not any(x["text"] in ("Menu", "Review") for x in nodes):
            return nodes
        time.sleep(0.5)
        nodes = _nodes(device)
    return nodes


def read_board(device) -> dict:
    nodes = _board_nodes(device)
    sq = squares(nodes)
    placement = ""
    if len(sq) == 64:
        rows = []
        for rank in "87654321":
            row, empty = "", 0
            for f in "abcdefgh":
                what = sq[f + rank][0]
                if what == "empty":
                    empty += 1
                    continue
                if empty:
                    row += str(empty)
                    empty = 0
                colour, piece = what.split()
                p = _PIECE[piece]
                row += p.upper() if colour == "white" else p
            rows.append(row + (str(empty) if empty else ""))
        placement = "/".join(rows)
    status = next((n["text"] for n in nodes if n["text"].startswith(("Your move", "Game over", "Computer", "Thinking"))), "")
    lines = status.split("\n")
    moves_text = next((n["text"] for n in nodes if re.match(r"^\s*1\.\s", n["text"])), "")
    san = re.findall(r"(?:O-O-O|O-O|[KQRBNP]?[a-h]?[1-8]?x?[a-h][1-8](?:=[QRBN])?[+#]?)", re.sub(r"\d+\.", " ", moves_text))
    over = lines[0].startswith("Game over")
    return {"in_game": len(sq) == 64, "placement": placement, "status": lines[0], "opening": lines[1] if len(lines) > 1 else "",
            "moves": san, "move_text": " ".join(moves_text.split()), "last_move": san[-1] if san else "", "game_over": over,
            "your_move": lines[0].startswith("Your move")}


def read_move_list(device) -> dict:
    """Menu > Move list: the SAN moves are only readable inside that dialog (the board footer is painted). Closes it again."""
    nodes = _nodes(device)
    menu = next((n for n in nodes if n["text"] == "Menu"), None)
    if not menu:
        return {"moves": [], "opening": ""}
    device.tap(*_centre(menu["bounds"]), delay=1.2)
    item = next((n for n in _nodes(device) if n["text"] == "Move list"), None)
    if not item:
        to_board(device, {}, None)
        return {"moves": [], "opening": ""}
    device.tap(*_centre(item["bounds"]), delay=1.4)
    nodes = _nodes(device)
    lines = [re.sub(r"\s+", " ", n["text"]).strip() for n in nodes if re.match(r"^\d+\.", n["text"])]
    opening = next((n["text"] for n in nodes if re.match(r"^[A-E]\d\d ", n["text"])), "")
    moves = []
    for ln in lines:
        moves += [t for t in ln.split(" ")[1:] if t]
    close = next((n for n in nodes if n["text"] == "Close"), None)
    if close:
        device.tap(*_centre(close["bounds"]), delay=1.0)
    return {"moves": moves, "opening": opening}


def _tap_square(device, name: str):
    sq = squares(_board_nodes(device))
    if name not in sq:
        seen = [n["text"] for n in _nodes(device) if n["text"]][:8]
        raise RuntimeError(f"board not on screen ({len(sq)} squares; texts: {seen})")
    device.tap(*_centre(sq[name][1]), delay=0.7)


def _wait_reply(device, before_placement: str, timeout=25.0) -> dict:
    """Wait for the computer's answer: your_move again (or game over) and a changed position."""
    end = time.monotonic() + timeout
    b = read_board(device)
    while time.monotonic() < end:
        b = read_board(device)
        if b["game_over"] or (b["your_move"] and b["placement"] != before_placement):
            time.sleep(0.4)
            return read_board(device)
        time.sleep(0.6)
    return b


def _parse(move: str) -> tuple[str, str, str]:
    m = re.fullmatch(r"([a-h][1-8])\W?([a-h][1-8])([qrbn]?)", move.strip().lower())
    if not m:
        raise RuntimeError(f"bad move {move!r}: use UCI squares like e2e4 (or e7e8q to promote)")
    return m.group(1), m.group(2), m.group(3)


def _do_move(device, move: str) -> dict:
    src, dst, promo = _parse(move)
    before = read_board(device)
    if not before["in_game"] or not before["your_move"]:
        raise RuntimeError(f"not your move (status: {before['status'] or 'no game'})")
    _tap_square(device, src)
    _tap_square(device, dst)
    time.sleep(0.8)
    nodes = _nodes(device)
    if promo or any("romot" in (n["text"] + n["desc"]) for n in nodes):
        names = {"q": "queen", "r": "rook", "b": "bishop", "n": "knight"}
        want = names.get(promo or "q")
        hit = next((n for n in nodes if want in (n["text"] + n["desc"]).lower() and not _SQ.match(n["desc"])), None)
        if hit:
            device.tap(*_centre(hit["bounds"]), delay=0.8)
    after = _wait_reply(device, before["placement"])
    if after["placement"] == before["placement"]:
        raise RuntimeError(f"move {move} was rejected (illegal or no piece on {src})")
    ml = read_move_list(device)
    after.update({"moves": ml["moves"], "last_move": ml["moves"][-1] if ml["moves"] else "", "opening": ml["opening"] or after["opening"]})
    return {"before": before, "after": after}


def _confirm(params, what):
    # the CLI parses confirm=yes as a YAML boolean, so True arrives as well as "yes"
    if str(params.get("confirm", "")).lower() not in ("yes", "true", "1"):
        raise RuntimeError(f"{what}: pass confirm=yes")


# ── python_action targets ───────────────────────────────────────────────────

def to_home(device, params, context):
    """Whatever the state: close dialogs, Menu > Save & home, until the home list shows."""
    for _ in range(6):
        nodes = _nodes(device)
        texts = {n["text"] for n in nodes}
        if "Play against computer" in texts:
            return {}
        target = next((n for n in nodes if n["text"] in ("Save & home", "Save &amp; home")), None)
        if target:
            device.tap(*_centre(target["bounds"]), delay=1.5)
            continue
        if "Keep playing" in texts:
            device.tap(*_centre(next(n for n in nodes if n["text"] == "Keep playing")["bounds"]), delay=1.0)
            continue
        menu = next((n for n in nodes if n["text"] == "Menu"), None)
        if menu:
            device.tap(*_centre(menu["bounds"]), delay=1.2)
            continue
        device.back()
        time.sleep(0.8)
    raise RuntimeError("could not reach the home screen")


def to_board(device, params, context):
    """Close any dialog left on top of the board (menu: Back to board; resign: Keep playing)."""
    for _ in range(3):
        nodes = _nodes(device)
        back = next((n for n in nodes if n["text"] in ("Back to board", "Keep playing", "Cancel")), None)
        if not back:
            return {}
        device.tap(*_centre(back["bounds"]), delay=1.0)
    return {}


def start(device, params, context):
    side = str(params.get("side", "white")).lower()
    level = int(params.get("level", 3))
    if side not in ("white", "black") or not 1 <= level <= 9:
        raise RuntimeError("side must be white or black, level 1-9")
    nodes = _nodes(device)
    device.tap(*_centre(next(n for n in nodes if n["text"] == "Play against computer")["bounds"]), delay=1.5)
    # difficulty slider: 9 dots from x 122 in steps of about 52.7 at 720 px width
    device.tap(int(122 + 52.7 * (level - 1)), 458, delay=0.6)
    nodes = _nodes(device)
    chosen = next((n["text"] for n in nodes if n["text"].startswith("Level ")), "")
    label = next(n for n in nodes if n["text"].lower() == side)
    device.tap(*_centre(label["bounds"]), delay=0.6)
    device.tap(*_centre(next(n for n in _nodes(device) if n["text"] == "Start game")["bounds"]), delay=2.5)
    b = read_board(device)
    if side == "black":
        b = _wait_reply(device, "", timeout=25)  # the computer opens
    return {"side": side, "level": chosen, "board": b}


def make_move(device, params, context):
    r = _do_move(device, str(params["move"]))
    return {"move": str(params["move"]).lower(), "before": r["before"], "board": r["after"],
            "computer_reply": r["after"]["last_move"]}


def make_moves(device, params, context):
    seq = [s for s in re.split(r"[,\s]+", str(params["moves"]).strip()) if s]
    if not seq:
        raise RuntimeError("no moves given")
    log = []
    before = read_board(device)
    for mv in seq:
        r = _do_move(device, mv)
        log.append({"move": mv.lower(), "reply": r["after"]["last_move"], "status": r["after"]["status"]})
        if r["after"]["game_over"]:
            break
    return {"before": before, "log": log, "board": read_board(device)}


def undo(device, params, context):
    before = read_board(device)
    nodes = _nodes(device)
    device.tap(*_centre(next(n for n in nodes if n["text"] == "Menu")["bounds"]), delay=1.2)
    item = next((n for n in _nodes(device) if n["text"] == "Undo / take back"), None)
    if not item:  # no move to take back yet: close the menu again
        to_board(device, {}, None)
        raise RuntimeError("nothing to take back (no moves played)")
    device.tap(*_centre(item["bounds"]), delay=1.5)
    ok = next((n for n in _nodes(device) if n["text"] == "Take back"), None)  # confirmation dialog
    if ok:
        device.tap(*_centre(ok["bounds"]), delay=1.5)
    time.sleep(1.0)
    return {"before": before, "board": read_board(device)}


def resign(device, params, context):
    _confirm(params, "resign ends the game")
    before = read_board(device)
    nodes = _nodes(device)
    device.tap(*_centre(next(n for n in nodes if n["text"] == "Menu")["bounds"]), delay=1.2)
    device.tap(*_centre(next(n for n in _nodes(device) if n["text"] == "Resign")["bounds"]), delay=1.2)
    device.tap(*_centre(next(n for n in _nodes(device) if n["text"] == "Resign")["bounds"]), delay=1.5)
    texts = [n["text"] for n in _nodes(device)]
    result = next((t for t in texts if t in ("You lost", "You won", "Draw")), "")
    return {"before": before, "result": result, "resigned": result == "You lost"}


def get_board(device, params, context):
    b = read_board(device)
    if b["in_game"] and not b["game_over"]:
        ml = read_move_list(device)
        b.update({"moves": ml["moves"], "last_move": ml["moves"][-1] if ml["moves"] else "", "opening": ml["opening"] or b["opening"]})
    return {"board": b}


# ── validators ──────────────────────────────────────────────────────────────

_START = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR"


def new_started(device, context) -> bool:
    r = context.result
    b = read_board(device)
    return b["in_game"] and r["board"]["in_game"] and (b["placement"] == _START or r["side"] == "black")


def moved(device, context) -> bool:
    r = context.result
    b = read_board(device)
    return b["in_game"] and b["placement"] == r["board"]["placement"] and b["placement"] != r["before"]["placement"]


def moves_played(device, context) -> bool:
    r = context.result
    b = read_board(device)
    return b["in_game"] and len(r["log"]) >= 1 and b["placement"] == r["board"]["placement"] and b["placement"] != r["before"]["placement"]


def board_read(device, context) -> bool:
    got = context.result["board"]
    return got["in_game"] and got["placement"] == read_board(device)["placement"] and isinstance(got["moves"], list)


def undone(device, context) -> bool:
    r = context.result
    b = read_board(device)
    return b["in_game"] and b["placement"] == r["board"]["placement"] and b["placement"] != r["before"]["placement"]


def resigned(device, context) -> bool:
    return bool(context.result.get("resigned")) and "Play again" in " ".join(n["text"] for n in _nodes(device))
