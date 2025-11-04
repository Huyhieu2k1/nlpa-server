import tkinter as tk
from tkinter import messagebox
import customtkinter as ctk
import requests
from datetime import datetime, timezone
import json, os

# ---------- helpers ----------
def iso_to_dt(value):
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    try:
        if isinstance(value, str) and value.endswith("Z"):
            value = value.replace("Z", "+00:00")
        return datetime.fromisoformat(value)
    except Exception:
        return None

def days_left_from_iso(value):
    dt = iso_to_dt(value)
    if not dt:
        return None
    now = datetime.now(timezone.utc)
    try:
        return int((dt - now).total_seconds() // 86400)
    except Exception:
        return None


# ---------- app ----------
class AdminApp:
    def __init__(self):
        ctk.set_appearance_mode("light")
        ctk.set_default_color_theme("green")

        self.root = ctk.CTk()
        self.root.title("NLPA Admin")
        self.root.geometry("1150x680")
        self.root.minsize(1150, 620)

        # state
        self.api_url = tk.StringVar(value="https://nlpa-server-2.onrender.com")
        self.admin_user = tk.StringVar(value="")
        self.admin_pass = tk.StringVar(value="")
        self.admin_token = None

        self.users_cache = {}
        self.filtered_users = []
        self.selected_user = tk.StringVar(value="")
        self.search_var = tk.StringVar(value="")
        self.search_var.trace_add("write", self._apply_filter)

        self._build_ui()
        self._load_config()

        if self.admin_token:
            try:
                self.refresh_users()
                self.btn_refresh.configure(state="normal")
                self.btn_create.configure(state="normal")
            except Exception:
                pass

    # ---------- config ----------
    def _config_path(self):
        return os.path.join(os.path.dirname(__file__), "admin_config.json")

    def _save_config(self):
        data = {
            "api_url": self.api_url.get(),
            "admin_user": self.admin_user.get(),
            "admin_pass": self.admin_pass.get(),
            "admin_token": self.admin_token,
        }
        try:
            with open(self._config_path(), "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _load_config(self):
        path = self._config_path()
        if not os.path.exists(path):
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                self.api_url.set(data.get("api_url", ""))
                self.admin_user.set(data.get("admin_user", ""))
                self.admin_pass.set(data.get("admin_pass", ""))
                self.admin_token = data.get("admin_token")
        except Exception:
            pass

    # ---------- ui ----------
    def _build_ui(self):
        top = ctk.CTkFrame(self.root, corner_radius=10)
        top.pack(fill="x", padx=12, pady=(12, 8))

        ctk.CTkLabel(top, text="API URL").grid(row=0, column=0, padx=(12, 6), pady=10, sticky="w")
        self.ent_api = ctk.CTkEntry(top, width=380, textvariable=self.api_url)
        self.ent_api.grid(row=0, column=1, padx=(0, 16), pady=10, sticky="w")

        ctk.CTkLabel(top, text="Admin").grid(row=0, column=2, padx=(0, 6), pady=10, sticky="e")
        self.ent_user = ctk.CTkEntry(top, width=150, placeholder_text="username", textvariable=self.admin_user)
        self.ent_user.grid(row=0, column=3, padx=(0, 6), pady=10)

        self.ent_pass = ctk.CTkEntry(top, width=150, placeholder_text="password", show="*", textvariable=self.admin_pass)
        self.ent_pass.grid(row=0, column=4, padx=(0, 6), pady=10)

        self.btn_login = ctk.CTkButton(top, text="Đăng nhập", width=120, command=self.on_login)
        self.btn_login.grid(row=0, column=5, padx=(0, 12), pady=10)

        self.btn_refresh = ctk.CTkButton(top, text="Tải users", width=120, command=self.refresh_users, state="disabled")
        self.btn_refresh.grid(row=0, column=6, padx=(0, 12), pady=10)

        tabs = ctk.CTkTabview(self.root, width=940, height=520, corner_radius=10)
        tabs.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        self.tab_users = tabs.add("Users")
        self.tab_create = tabs.add("Create")

        self._build_tab_users()
        self._build_tab_create()

    def _build_tab_users(self):
        body = self.tab_users
        body.grid_columnconfigure(0, weight=1)
        body.grid_columnconfigure(1, weight=2)
        body.grid_rowconfigure(1, weight=1)

        search_row = ctk.CTkFrame(body, corner_radius=8)
        search_row.grid(row=0, column=0, columnspan=2, sticky="ew", padx=12, pady=(12, 8))
        ctk.CTkLabel(search_row, text="Tìm người dùng").pack(side="left", padx=(12, 6), pady=8)
        self.ent_search = ctk.CTkEntry(search_row, width=280, textvariable=self.search_var, placeholder_text="gõ để lọc...")
        self.ent_search.pack(side="left", padx=(0, 12), pady=8)

        left = ctk.CTkFrame(body, corner_radius=10)
        left.grid(row=1, column=0, sticky="nsew", padx=(12, 8), pady=(0, 12))
        ctk.CTkLabel(left, text="Danh sách người dùng", font=("Arial", 14, "bold")).pack(padx=12, pady=(12, 6), anchor="w")
        self.listbox = tk.Listbox(left)
        self.listbox.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        self.listbox.bind("<<ListboxSelect>>", self.on_select_user)

        right = ctk.CTkFrame(body, corner_radius=10)
        right.grid(row=1, column=1, sticky="nsew", padx=(8, 12), pady=(0, 12))
        right.grid_columnconfigure((0, 1, 2, 3), weight=1)
        right.grid_rowconfigure(4, weight=1)

        ctk.CTkLabel(right, text="Chi tiết tài khoản", font=("Arial", 14, "bold")).grid(row=0, column=0, columnspan=4, sticky="w", padx=12, pady=(12, 8))
        self.lbl_user = ctk.CTkLabel(right, text="User: -", font=("Arial", 12))
        self.lbl_user.grid(row=1, column=0, columnspan=4, sticky="w", padx=12, pady=4)
        self.lbl_paid = ctk.CTkLabel(right, text="Paid until: - (days_left: -)", font=("Arial", 12))
        self.lbl_paid.grid(row=2, column=0, columnspan=4, sticky="w", padx=12, pady=4)
        self.lbl_pending = ctk.CTkLabel(right, text="Pending machine: -", font=("Arial", 12))
        self.lbl_pending.grid(row=3, column=0, columnspan=4, sticky="w", padx=12, pady=4)

        self.txt_machines = ctk.CTkTextbox(right, height=160)
        self.txt_machines.grid(row=4, column=0, columnspan=4, sticky="nsew", padx=12, pady=(6, 12))

        ctk.CTkLabel(right, text="Gia hạn (ngày):").grid(row=5, column=0, sticky="e", padx=(12, 6), pady=(0, 8))
        self.ent_days = ctk.CTkEntry(right, width=100, placeholder_text="vd 30")
        self.ent_days.grid(row=5, column=1, sticky="w", padx=(0, 12), pady=(0, 8))
        self.btn_extend = ctk.CTkButton(right, text="Gia hạn", width=120, command=self.on_extend, state="disabled")
        self.btn_extend.grid(row=5, column=2, sticky="w", padx=(0, 6), pady=(0, 8))
        self.btn_delete = ctk.CTkButton(right, text="Xóa tài khoản", fg_color="#b91c1c", hover_color="#991b1b",
                                        width=140, command=self.on_delete, state="disabled")
        self.btn_delete.grid(row=5, column=3, sticky="e", padx=(0, 12), pady=(0, 8))

        ctk.CTkLabel(right, text="Đặt lại mật khẩu:").grid(row=6, column=0, sticky="e", padx=(12, 6), pady=(0, 8))
        self.ent_new_pw = ctk.CTkEntry(right, width=180, placeholder_text="mật khẩu mới")
        self.ent_new_pw.grid(row=6, column=1, sticky="w", padx=(0, 12), pady=(0, 8))
        self.btn_reset_pw = ctk.CTkButton(right, text="Reset mật khẩu", width=140,
                                          command=self.on_reset_password, state="disabled")
        self.btn_reset_pw.grid(row=6, column=2, sticky="w", padx=(0, 6), pady=(0, 8))

        ctk.CTkLabel(right, text="Đổi tên (username mới):").grid(row=7, column=0, sticky="e", padx=(12, 6), pady=(0, 12))
        self.ent_new_name = ctk.CTkEntry(right, width=180, placeholder_text="tên mới")
        self.ent_new_name.grid(row=7, column=1, sticky="w", padx=(0, 12), pady=(0, 12))
        self.btn_rename = ctk.CTkButton(right, text="Đổi tên", width=120, command=self.on_rename, state="disabled")
        self.btn_rename.grid(row=7, column=2, sticky="w", padx=(0, 6), pady=(0, 12))

    def _build_tab_create(self):
        body = self.tab_create
        body.grid_columnconfigure(0, weight=1)
        form = ctk.CTkFrame(body, corner_radius=10)
        form.pack(padx=16, pady=16, fill="x")

        ctk.CTkLabel(form, text="Tạo tài khoản mới", font=("Arial", 16, "bold")).grid(row=0, column=0, columnspan=2, sticky="w", padx=12, pady=(12, 8))
        ctk.CTkLabel(form, text="Username").grid(row=1, column=0, sticky="e", padx=(12, 6), pady=6)
        self.cr_username = ctk.CTkEntry(form, width=260, placeholder_text="username")
        self.cr_username.grid(row=1, column=1, sticky="w", padx=(0, 12), pady=6)
        ctk.CTkLabel(form, text="Password").grid(row=2, column=0, sticky="e", padx=(12, 6), pady=6)
        self.cr_password = ctk.CTkEntry(form, width=260, placeholder_text="password")
        self.cr_password.grid(row=2, column=1, sticky="w", padx=(0, 12), pady=6)
        ctk.CTkLabel(form, text="Pending machine").grid(row=3, column=0, sticky="e", padx=(12, 6), pady=6)
        self.cr_pending = ctk.CTkEntry(form, width=260, placeholder_text="tùy chọn")
        self.cr_pending.grid(row=3, column=1, sticky="w", padx=(0, 12), pady=6)
        ctk.CTkLabel(form, text="Paid days").grid(row=4, column=0, sticky="e", padx=(12, 6), pady=6)
        self.cr_paid = ctk.CTkEntry(form, width=120, placeholder_text="vd 30")
        self.cr_paid.grid(row=4, column=1, sticky="w", padx=(0, 12), pady=6)
        self.btn_create = ctk.CTkButton(form, text="Tạo tài khoản", width=160, command=self.on_create_user, state="disabled")
        self.btn_create.grid(row=5, column=1, sticky="w", padx=(0, 12), pady=(12, 16))

    # ---------- actions ----------
    def _headers(self):
        return {"Authorization": f"Bearer {self.admin_token}"} if self.admin_token else {}

    def on_login(self):
        base = self.api_url.get().rstrip("/")
        user = self.admin_user.get().strip()
        pw = self.admin_pass.get()
        if not base or not user or not pw:
            messagebox.showerror("Lỗi", "Điền API URL, admin và mật khẩu.")
            return
        try:
            r = requests.post(f"{base}/admin/login", json={"username": user, "password": pw}, timeout=15)
            j = r.json()
        except Exception as e:
            messagebox.showerror("Lỗi", f"Không kết nối được: {e}")
            return
        if not j.get("ok"):
            messagebox.showerror("Lỗi", j.get("message", "Đăng nhập thất bại"))
            return
        self.admin_token = j.get("token")
        self.btn_refresh.configure(state="normal")
        self.btn_create.configure(state="normal")
        self._save_config()
        self.refresh_users()

    def refresh_users(self):
        if not self.admin_token:
            return
        base = self.api_url.get().rstrip("/")
        try:
            r = requests.get(f"{base}/admin/users", headers=self._headers(), timeout=20)
            j = r.json()
        except Exception as e:
            messagebox.showerror("Lỗi", f"Không tải danh sách: {e}")
            return
        if not j.get("ok"):
            messagebox.showerror("Lỗi", j.get("message", "Không tải được users"))
            return
        self.users_cache = j.get("users", {})
        self._apply_filter()
        self.selected_user.set("")
        self._show_user_details(None)
        self._set_detail_buttons(False)

    def _apply_filter(self, *_):
        key = (self.search_var.get() or "").strip().lower()
        names = sorted(self.users_cache.keys(), key=str.lower)
        if key:
            names = [n for n in names if key in n.lower()]
        self.filtered_users = names
        self.listbox.delete(0, tk.END)
        for n in self.filtered_users:
            self.listbox.insert(tk.END, n)

    def on_select_user(self, _evt):
        try:
            sel = self.listbox.get(self.listbox.curselection())
        except Exception:
            sel = None
        self.selected_user.set(sel or "")
        self._show_user_details(sel)
        self._set_detail_buttons(bool(sel))

    def _set_detail_buttons(self, enabled):
        state = "normal" if enabled else "disabled"
        self.btn_extend.configure(state=state)
        self.btn_delete.configure(state=state)
        self.btn_reset_pw.configure(state=state)
        self.btn_rename.configure(state=state)

    def _show_user_details(self, uname):
        if not uname or uname not in self.users_cache:
            self.lbl_user.configure(text="User: -")
            self.lbl_paid.configure(text="Paid until: - (days_left: -)")
            self.lbl_pending.configure(text="Pending machine: -")
            self.txt_machines.configure(state="normal")
            self.txt_machines.delete("1.0", tk.END)
            self.txt_machines.insert(tk.END, "Machines: (none)\n")
            self.txt_machines.configure(state="disabled")
            return

        info = self.users_cache[uname]
        paid = info.get("paid_until")
        pending = info.get("pending_machine")
        machines = info.get("machines") or []

        dl = days_left_from_iso(paid) if paid else None
        self.lbl_user.configure(text=f"User: {uname}")
        self.lbl_paid.configure(text=f"Paid until: {paid or '-'} (days_left: {dl if dl is not None else '-'})")
        self.lbl_pending.configure(text=f"Pending machine: {pending or '-'}")

        self.txt_machines.configure(state="normal")
        self.txt_machines.delete("1.0", tk.END)
        if machines:
            self.txt_machines.insert(tk.END, "Machines:\n")
            for m in machines:
                self.txt_machines.insert(tk.END, f" - {m}\n")
        else:
            self.txt_machines.insert(tk.END, "Machines: (none)\n")
        self.txt_machines.configure(state="disabled")

    def on_extend(self):
        uname = self.selected_user.get()
        if not uname:
            return
        try:
            days = int((self.ent_days.get() or "0").strip())
        except ValueError:
            messagebox.showerror("Lỗi", "Số ngày không hợp lệ.")
            return
        if days <= 0:
            messagebox.showerror("Lỗi", "Nhập số ngày > 0.")
            return
        base = self.api_url.get().rstrip("/")
        try:
            r = requests.post(
                f"{base}/admin/users/{uname}/set_paid",
                json={"days": days},
                headers=self._headers(),
                timeout=20
            )
            j = r.json()
        except Exception as e:
            messagebox.showerror("Lỗi", f"Không kết nối: {e}")
            return
        if not j.get("ok"):
            messagebox.showerror("Lỗi", j.get("message", "Gia hạn thất bại"))
            return
        messagebox.showinfo("OK", j.get("message", "Đã gia hạn"))
        self.refresh_users()

    def on_delete(self):
        uname = self.selected_user.get()
        if not uname:
            return
        if not messagebox.askyesno("Xác nhận", f"Xóa tài khoản '{uname}'?"):
            return
        base = self.api_url.get().rstrip("/")
        try:
            r = requests.delete(f"{base}/admin/users/{uname}",
                                headers=self._headers(), timeout=20)
            j = r.json()
        except Exception as e:
            messagebox.showerror("Lỗi", f"Không kết nối: {e}")
            return
        if not j.get("ok"):
            messagebox.showerror("Lỗi", j.get("message", "Xóa thất bại"))
            return
        messagebox.showinfo("OK", j.get("message", "Đã xóa"))
        self.refresh_users()

    def on_reset_password(self):
        uname = self.selected_user.get()
        if not uname:
            return
        new_pw = (self.ent_new_pw.get() or "").strip()
        if not new_pw:
            messagebox.showerror("Lỗi", "Nhập mật khẩu mới.")
            return
        base = self.api_url.get().rstrip("/")
        try:
            r = requests.post(f"{base}/admin/users/{uname}/reset_password",
                              json={"new_password": new_pw},
                              headers=self._headers(), timeout=20)
            j = r.json()
        except Exception as e:
            messagebox.showerror("Lỗi", f"Không kết nối: {e}")
            return
        if not j.get("ok"):
            messagebox.showerror("Lỗi", j.get("message", "Reset mật khẩu thất bại"))
            return
        messagebox.showinfo("OK", j.get("message", "Đã cập nhật mật khẩu"))

    def on_rename(self):
        uname = self.selected_user.get()
        if not uname:
            return
        new_name = (self.ent_new_name.get() or "").strip().lower()
        if not new_name:
            messagebox.showerror("Lỗi", "Nhập username mới.")
            return
        base = self.api_url.get().rstrip("/")
        try:
            r = requests.post(f"{base}/admin/users/{uname}/rename",
                              json={"new_username": new_name},
                              headers=self._headers(), timeout=20)
            j = r.json()
        except Exception as e:
            messagebox.showerror("Lỗi", f"Không kết nối: {e}")
            return
        if not j.get("ok"):
            messagebox.showerror("Lỗi", j.get("message", "Đổi tên thất bại"))
            return
        messagebox.showinfo("OK", j.get("message", "Đã đổi tên"))
        self.refresh_users()
        self.ent_new_name.delete(0, tk.END)

    def on_create_user(self):
        base = self.api_url.get().rstrip("/")
        username = (self.cr_username.get() or "").strip().lower()
        password = (self.cr_password.get() or "").strip()
        pending = (self.cr_pending.get() or "").strip().upper()
        paid_days = (self.cr_paid.get() or "").strip()
        try:
            paid_days = int(paid_days) if paid_days else 0
        except ValueError:
            messagebox.showerror("Lỗi", "Paid days không hợp lệ.")
            return
        if not username or not password:
            messagebox.showerror("Lỗi", "Nhập username và password.")
            return
        try:
            r = requests.post(f"{base}/admin/users/create",
                              json={
                                  "username": username,
                                  "password": password,
                                  "pending_machine": pending,
                                  "paid_days": paid_days
                              },
                              headers=self._headers(), timeout=20)
            j = r.json()
        except Exception as e:
            messagebox.showerror("Lỗi", f"Không kết nối: {e}")
            return
        if not j.get("ok"):
            messagebox.showerror("Lỗi", j.get("message", "Tạo tài khoản thất bại"))
            return
        messagebox.showinfo("OK", j.get("message", "Đã tạo"))
        self.cr_username.delete(0, tk.END)
        self.cr_password.delete(0, tk.END)
        self.cr_pending.delete(0, tk.END)
        self.cr_paid.delete(0, tk.END)
        self.refresh_users()

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    AdminApp().run()
