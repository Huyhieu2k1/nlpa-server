from datetime import datetime, timedelta, timezone
from flask import Flask, request, jsonify
from flask_cors import CORS
import secrets
import hashlib
import json
import os
from functools import wraps

# ===== KHỞI TẠO APP =====
app = Flask(__name__)
CORS(app)

# ===== DỮ LIỆU NGƯỜI DÙNG =====
USERS = {}  # username -> {pw_hash, paid_until, machines}
TOKENS = {}  # token -> username
DATA_FILE = "users.json"

# ===== HÀM LƯU & TẢI DỮ LIỆU =====
def save_users():
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(USERS, f, default=str, ensure_ascii=False, indent=2)

def load_users():
    global USERS
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            for u, info in data.items():
                if info.get("paid_until"):
                    try:
                        info["paid_until"] = datetime.fromisoformat(info["paid_until"])
                    except Exception:
                        info["paid_until"] = None
            USERS = data

# Tải dữ liệu khi khởi động
load_users()
print(f"✅ Loaded {len(USERS)} user(s) from file.")

# ===== TIỆN ÍCH CHUNG =====
def _hash(pw: str) -> str:
    return hashlib.sha256(pw.encode()).hexdigest()

def _auth():
    h = request.headers.get("Authorization", "")
    if not h.startswith("Bearer "):
        return None
    tok = h.split(" ", 1)[1].strip()
    return TOKENS.get(tok)

# ===== API NGƯỜI DÙNG =====
@app.post("/api/register")
def register():
    data = request.get_json(force=True)
    u = (data.get("username") or "").strip().lower()
    p = data.get("password") or ""
    if not u or not p:
        return jsonify({"ok": False, "message": "Thiếu thông tin"}), 400
    if u in USERS:
        return jsonify({"ok": False, "message": "Tài khoản đã tồn tại"})
    USERS[u] = {"pw_hash": _hash(p), "paid_until": None, "machines": {}}
    save_users()
    return jsonify({"ok": True, "message": "Đăng ký thành công"})

@app.post("/api/login")
def login():
    data = request.get_json(force=True)
    u = (data.get("username") or "").strip().lower()
    p = data.get("password") or ""
    mc = (data.get("fingerprint") or "").strip().upper()
    user = USERS.get(u)
    if not user or user["pw_hash"] != _hash(p):
        return jsonify({"ok": False, "message": "Sai tài khoản hoặc mật khẩu"}), 401

    now = datetime.now(timezone.utc)
    if not user["paid_until"]:
        if mc not in user["machines"]:
            user["machines"][mc] = now
            save_users()

    tok = secrets.token_urlsafe(24)
    TOKENS[tok] = u
    return jsonify({"ok": True, "token": tok})

@app.get("/api/profile")
def profile():
    u = _auth()
    if not u:
        return jsonify({"message": "Unauthorized"}), 401
    user = USERS[u]
    now = datetime.now(timezone.utc)
    paid_until = user["paid_until"]
    mc = request.headers.get("X-Machine", "")
    if not mc and user["machines"]:
        mc = list(user["machines"].keys())[0]

    if paid_until:
        days = int((paid_until - now).total_seconds() // 86400)
        return jsonify({"username": u, "plan": "paid", "days_left": days})

    start = user["machines"].get(mc)
    if not start:
        return jsonify({"username": u, "plan": "trial", "days_left": 1})
    end = start + timedelta(days=1)
    remaining = (end - now).total_seconds() / 86400
    days = int(remaining)
    if remaining > 0 and days < 1:
        days = 1
    return jsonify({"username": u, "plan": "trial", "days_left": days})

@app.post("/api/change_password")
def change_password():
    u = _auth()
    if not u:
        return jsonify({"ok": False, "message": "Unauthorized"}), 401
    data = request.get_json(force=True)
    old = data.get("old") or ""
    new = data.get("new") or ""
    if USERS[u]["pw_hash"] != _hash(old):
        return jsonify({"ok": False, "message": "Mật khẩu hiện tại không đúng"})
    USERS[u]["pw_hash"] = _hash(new)
    save_users()
    return jsonify({"ok": True, "message": "Đã đổi mật khẩu"})

@app.post("/api/redeem_key")
def redeem_key():
    u = _auth()
    if not u:
        return jsonify({"ok": False, "message": "Unauthorized"}), 401
    data = request.get_json(force=True)
    code = (data.get("code") or "").strip().upper()

    add_days = {"D7": 7, "D30": 30, "D365": 365}.get(code, 0)
    if not add_days:
        return jsonify({"ok": False, "message": "Mã không hợp lệ"})

    now = datetime.now(timezone.utc)
    current = USERS[u]["paid_until"]
    if current and current > now:
        USERS[u]["paid_until"] = current + timedelta(days=add_days)
    else:
        USERS[u]["paid_until"] = now + timedelta(days=add_days)
    save_users()
    return jsonify({"ok": True, "message": f"Gia hạn thành công thêm {add_days} ngày"})

# ===== ADMIN API =====
ADMIN_USER = os.getenv("ADMIN_USER", "admin")
ADMIN_PASS = os.getenv("ADMIN_PASS", "123456")
ADMIN_TOKEN = None

def require_admin(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        global ADMIN_TOKEN
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            return jsonify({"ok": False, "message": "Unauthorized"}), 401
        token = auth.split(" ", 1)[1]
        if token != ADMIN_TOKEN:
            return jsonify({"ok": False, "message": "Invalid token"}), 403
        return f(*args, **kwargs)
    return wrapper

@app.post("/admin/login")
def admin_login():
    global ADMIN_TOKEN
    data = request.get_json(force=True)
    username = data.get("username", "")
    password = data.get("password", "")
    if username == ADMIN_USER and password == ADMIN_PASS:
        ADMIN_TOKEN = secrets.token_urlsafe(24)
        return jsonify({"ok": True, "token": ADMIN_TOKEN})
    return jsonify({"ok": False, "message": "Sai tài khoản hoặc mật khẩu"}), 403

@app.get("/admin/users")
@require_admin
def admin_list_users():
    data = {
        u: {
            "paid_until": str(info["paid_until"]) if info["paid_until"] else None,
            "machines": list(info["machines"].keys()),
        }
        for u, info in USERS.items()
    }
    return jsonify({"ok": True, "users": data})

@app.post("/admin/users/<username>/set_paid")
@require_admin
def admin_set_paid(username):
    username = username.lower()
    data = request.get_json(force=True)
    days = int(data.get("days", 0))
    if username not in USERS:
        return jsonify({"ok": False, "message": "Không tìm thấy user"}), 404
    now = datetime.now(timezone.utc)
    current = USERS[username]["paid_until"]
    if current and current > now:
        USERS[username]["paid_until"] = current + timedelta(days=days)
    else:
        USERS[username]["paid_until"] = now + timedelta(days=days)
    save_users()
    return jsonify({"ok": True, "message": f"Gia hạn {username} thêm {days} ngày"})

@app.delete("/admin/users/<username>")
@require_admin
def admin_delete_user(username):
    username = username.lower()
    if username not in USERS:
        return jsonify({"ok": False, "message": "Không tìm thấy user"}), 404
    USERS.pop(username)
    save_users()
    return jsonify({"ok": True, "message": f"Đã xóa user {username}"})

# ===== CHẠY SERVER =====
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
