from datetime import datetime, timedelta, timezone
from flask import Flask, request, jsonify
from flask_cors import CORS
import secrets
import hashlib
import os
from functools import wraps
from pymongo import MongoClient

# ===== KHỞI TẠO APP =====
app = Flask(__name__)
CORS(app)

# ===== KẾT NỐI MONGODB =====
MONGO_URI = "mongodb+srv://admin:solomon1st@cluster0.v9coy2k.mongodb.net/?appName=Cluster0"
client = MongoClient(MONGO_URI)
db = client["nlpa_db"]
users_col = db["users"]
tokens_col = db["tokens"]

print("✅ Đã kết nối MongoDB Atlas thành công!")

# ===== TIỆN ÍCH CHUNG =====
def _hash(pw: str) -> str:
    return hashlib.sha256(pw.encode()).hexdigest()

def _auth():
    h = request.headers.get("Authorization", "")
    if not h.startswith("Bearer "):
        return None
    tok = h.split(" ", 1)[1].strip()
    token_entry = tokens_col.find_one({"token": tok})
    return token_entry["username"] if token_entry else None

def _is_trial_account(info: dict) -> bool:
    return not info.get("paid_until")

def _count_trials_for_machine_including_pending(mc: str) -> int:
    """Đếm số tài khoản TRIAL gắn với máy mc (machines hoặc pending_machine)."""
    if not mc:
        return 0
    return users_col.count_documents({
        "$and": [
            {"paid_until": None},
            {"$or": [
                {f"machines.{mc}": {"$exists": True}},
                {"pending_machine": mc}
            ]}
        ]
    })

MAX_TRIALS_PER_MACHINE = 2

# ===== API NGƯỜI DÙNG =====
@app.post("/api/register")
def register():
    data = request.get_json(force=True)
    u = (data.get("username") or "").strip().lower()
    p = data.get("password") or ""
    mc = (data.get("fingerprint") or "").strip().upper()

    if not u or not p:
        return jsonify({"ok": False, "message": "Thiếu thông tin"}), 400
    if not mc:
        return jsonify({"ok": False, "message": "Thiếu mã máy (fingerprint)."}), 400

    if users_col.find_one({"username": u}):
        return jsonify({"ok": False, "message": "Tài khoản đã tồn tại"})

    used = _count_trials_for_machine_including_pending(mc)
    if used >= MAX_TRIALS_PER_MACHINE:
        return jsonify({
            "ok": False,
            "message": "Máy này đã đạt số lần dùng thử tối đa. Vui lòng liên hệ admin."
        }), 403

    users_col.insert_one({
        "username": u,
        "pw_hash": _hash(p),
        "paid_until": None,
        "machines": {},
        "pending_machine": mc
    })
    return jsonify({"ok": True, "message": "Đăng ký thành công"})

@app.post("/api/login")
def login():
    data = request.get_json(force=True)
    u = (data.get("username") or "").strip().lower()
    p = data.get("password") or ""
    mc = (data.get("fingerprint") or "").strip().upper()

    if not mc:
        return jsonify({"ok": False, "message": "Thiếu mã máy (fingerprint)."}), 400

    user = users_col.find_one({"username": u})
    if not user or user["pw_hash"] != _hash(p):
        return jsonify({"ok": False, "message": "Sai tài khoản hoặc mật khẩu"}), 401

    now = datetime.now(timezone.utc)

    # --- FIX: đảm bảo paid_until là datetime trước khi so sánh ---
    paid_until_raw = user.get("paid_until")
    paid_until = datetime.fromisoformat(paid_until_raw) if isinstance(paid_until_raw, str) else paid_until_raw
    # -------------------------------------------------------------

    machines = user.get("machines") or {}
    pending = (user.get("pending_machine") or "").upper()

    if paid_until and paid_until <= now:
        return jsonify({"ok": False, "message": "Tài khoản đã hết hạn, vui lòng gia hạn"}), 403

    if len(machines) == 0:
        if _is_trial_account(user):
            if pending and pending != mc:
                return jsonify({
                    "ok": False,
                    "message": "Tài khoản này được đăng ký trên máy khác."
                }), 403

            used = _count_trials_for_machine_including_pending(mc)
            if used > MAX_TRIALS_PER_MACHINE:
                return jsonify({
                    "ok": False,
                    "message": "Máy này đã đạt số lần dùng thử tối đa. Vui lòng liên hệ admin."
                }), 403

            users_col.update_one({"username": u}, {
                "$set": {"machines": {mc: now.isoformat()}, "pending_machine": None}
            })
        else:
            users_col.update_one({"username": u}, {
                "$set": {"machines": {mc: now.isoformat()}, "pending_machine": None}
            })
    else:
        if mc not in machines:
            return jsonify({"ok": False, "message": "Tài khoản này đã được sử dụng trên một máy khác"}), 403

        if _is_trial_account(user):
            start_str = machines.get(mc)
            start = datetime.fromisoformat(start_str) if start_str else now
            if now > start + timedelta(days=1):
                return jsonify({"ok": False, "message": "Tài khoản đã hết hạn dùng thử"}), 403

    tok = secrets.token_urlsafe(24)
    tokens_col.insert_one({"token": tok, "username": u})
    return jsonify({"ok": True, "token": tok})

@app.get("/api/profile")
def profile():
    u = _auth()
    if not u:
        return jsonify({"message": "Unauthorized"}), 401

    user = users_col.find_one({"username": u})
    now = datetime.now(timezone.utc)
    paid_until = user.get("paid_until")

    mc = request.headers.get("X-Machine", "")
    if not mc and user.get("machines"):
        mc = list(user["machines"].keys())[0]

    if paid_until:
        paid_dt = datetime.fromisoformat(paid_until) if isinstance(paid_until, str) else paid_until
        days = int((paid_dt - now).total_seconds() // 86400)
        return jsonify({"username": u, "plan": "paid", "days_left": days})

    machines = user.get("machines") or {}
    start_str = machines.get(mc)
    if not start_str:
        return jsonify({"username": u, "plan": "trial", "days_left": 1})
    start = datetime.fromisoformat(start_str)
    remaining = (start + timedelta(days=1) - now).total_seconds() / 86400
    days = max(1, int(remaining)) if remaining > 0 else 0
    return jsonify({"username": u, "plan": "trial", "days_left": days})

@app.post("/api/change_password")
def change_password():
    u = _auth()
    if not u:
        return jsonify({"ok": False, "message": "Unauthorized"}), 401
    data = request.get_json(force=True)
    old = data.get("old") or ""
    new = data.get("new") or ""

    user = users_col.find_one({"username": u})
    if user["pw_hash"] != _hash(old):
        return jsonify({"ok": False, "message": "Mật khẩu hiện tại không đúng"})
    users_col.update_one({"username": u}, {"$set": {"pw_hash": _hash(new)}})
    return jsonify({"ok": True, "message": "Đã đổi mật khẩu"})

@app.post("/api/redeem_key")
def redeem_key():
    u = _auth()
    if not u:
        return jsonify({"ok": False, "message": "Unauthorized"}), 401
    data = request.get_json(force=True)
    code = (data.get("code") or "").strip().upper()

    add_days = {"DX7": 7, "DX30": 30, "DX365": 365}.get(code, 0)
    if not add_days:
        return jsonify({"ok": False, "message": "Mã không hợp lệ"})

    now = datetime.now(timezone.utc)
    user = users_col.find_one({"username": u})
    current = user.get("paid_until")
    if current:
        current_dt = datetime.fromisoformat(current) if isinstance(current, str) else current
        if current_dt > now:
            new_paid = current_dt + timedelta(days=add_days)
        else:
            new_paid = now + timedelta(days=add_days)
    else:
        new_paid = now + timedelta(days=add_days)

    users_col.update_one({"username": u}, {
        "$set": {"paid_until": new_paid.isoformat(), "pending_machine": None}
    })
    return jsonify({"ok": True, "message": f"Gia hạn thành công thêm {add_days} ngày"})

# ===== ADMIN API =====
ADMIN_USER = os.getenv("ADMIN_USER")
ADMIN_PASS = os.getenv("ADMIN_PASS")
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
    result = {}
    for u in users_col.find():
        result[u["username"]] = {
            "paid_until": u.get("paid_until"),
            "machines": list((u.get("machines") or {}).keys()),
            "pending_machine": u.get("pending_machine")
        }
    return jsonify({"ok": True, "users": result})

@app.post("/admin/users/<username>/set_paid")
@require_admin
def admin_set_paid(username):
    username = username.lower()
    data = request.get_json(force=True)
    days = int(data.get("days", 0))
    user = users_col.find_one({"username": username})
    if not user:
        return jsonify({"ok": False, "message": "Không tìm thấy user"}), 404
    now = datetime.now(timezone.utc)
    current = user.get("paid_until")
    if current:
        current_dt = datetime.fromisoformat(current) if isinstance(current, str) else current
        if current_dt > now:
            new_paid = current_dt + timedelta(days=days)
        else:
            new_paid = now + timedelta(days=days)
    else:
        new_paid = now + timedelta(days=days)
    users_col.update_one({"username": username}, {
        "$set": {"paid_until": new_paid.isoformat(), "pending_machine": None}
    })
    return jsonify({"ok": True, "message": f"Gia hạn {username} thêm {days} ngày"})

@app.post("/admin/users/<username>/set_paid_exact")
@require_admin
def admin_set_paid_exact(username):
    username = username.lower()
    data = request.get_json(force=True)
    try:
        days = int(data.get("days", 0))
    except Exception:
        return jsonify({"ok": False, "message": "Giá trị 'days' không hợp lệ"}), 400

    if days <= 0:
        return jsonify({"ok": False, "message": "days phải > 0"}), 400

    user = users_col.find_one({"username": username})
    if not user:
        return jsonify({"ok": False, "message": "Không tìm thấy user"}), 404

    now = datetime.now(timezone.utc)
    new_paid = now + timedelta(days=days)

    users_col.update_one(
        {"username": username},
        {"$set": {"paid_until": new_paid.isoformat(), "pending_machine": None}}
    )
    return jsonify({"ok": True, "message": f"Đã đặt paid_until của {username} = {days} ngày kể từ hiện tại"})

@app.post("/admin/users/<username>/reset_password")
@require_admin
def admin_reset_password(username):
    username = username.lower()
    data = request.get_json(force=True)
    new_pw = data.get("new_password", "123456")  # mặc định nếu không gửi thì là 123456

    user = users_col.find_one({"username": username})
    if not user:
        return jsonify({"ok": False, "message": "Không tìm thấy user"}), 404

    users_col.update_one(
        {"username": username},
        {"$set": {"pw_hash": _hash(new_pw)}}
    )

    return jsonify({
        "ok": True,
        "message": f"✅ Đã đặt lại mật khẩu cho '{username}' thành '{new_pw}'"
    })

@app.delete("/admin/users/<username>")
@require_admin
def admin_delete_user(username):
    username = username.lower()
    users_col.delete_one({"username": username})
    return jsonify({"ok": True, "message": f"Đã xóa user {username}"})

@app.get("/ping")
def ping():
    return {"ok": True, "message": "NLPA server is alive"}

# ===== ADMIN: create user =====
@app.post("/admin/users/create")
@require_admin
def admin_create_user():
    data = request.get_json(force=True)
    username = (data.get("username") or "").strip().lower()
    password = data.get("password") or ""
    pending_machine = (data.get("pending_machine") or "").strip().upper()
    paid_days = int(data.get("paid_days") or 0)

    if not username or not password:
        return jsonify({"ok": False, "message": "Thiếu username hoặc password"}), 400

    if users_col.find_one({"username": username}):
        return jsonify({"ok": False, "message": "Tài khoản đã tồn tại"}), 400

    if pending_machine:
        used = users_col.count_documents({
            "$and": [
                {"paid_until": None},
                {"$or": [
                    {f"machines.{pending_machine}": {"$exists": True}},
                    {"pending_machine": pending_machine}
                ]}
            ]
        })
        if used >= 2 and paid_days <= 0:
            return jsonify({"ok": False, "message": "Máy này đã đạt số lần dùng thử tối đa"}), 403

    now = datetime.now(timezone.utc)
    paid_until = None
    if paid_days > 0:
        paid_until = (now + timedelta(days=paid_days)).isoformat()

    users_col.insert_one({
        "username": username,
        "pw_hash": _hash(password),
        "paid_until": paid_until,
        "machines": {},
        "pending_machine": pending_machine or None
    })
    return jsonify({"ok": True, "message": f"Đã tạo {username}"})


# ===== ADMIN: rename user =====
@app.post("/admin/users/<username>/rename")
@require_admin
def admin_rename_user(username):
    username = username.lower()
    data = request.get_json(force=True)
    new_username = (data.get("new_username") or "").strip().lower()

    if not new_username:
        return jsonify({"ok": False, "message": "Tên mới trống"}), 400
    if new_username == username:
        return jsonify({"ok": False, "message": "Tên mới trùng tên cũ"}), 400
    if users_col.find_one({"username": new_username}):
        return jsonify({"ok": False, "message": "Tên mới đã tồn tại"}), 400

    user = users_col.find_one({"username": username})
    if not user:
        return jsonify({"ok": False, "message": "Không tìm thấy user"}), 404

    users_col.update_one({"_id": user["_id"]}, {"$set": {"username": new_username}})
    tokens_col.update_many({"username": username}, {"$set": {"username": new_username}})

    return jsonify({"ok": True, "message": f"Đã đổi tên {username} → {new_username}"})

# ===== CHẠY SERVER =====
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
