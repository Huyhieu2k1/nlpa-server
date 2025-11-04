# admin_gui.py
import tkinter as tk
from tkinter import messagebox
import customtkinter as ctk
import requests
from datetime import datetime, timezone

# =============== helpers ===============
def iso_to_dt(value):
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    try:
        # cho cả dạng "...Z" hoặc có offset
        if value.endswith("Z"):
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

# =============== app ===============
class AdminApp:
    def __init__(self):
        ctk.set_appearance_mode("light")
        ctk.set_default_color_theme("green")

        self.root = ctk.CTk()
        self.root.title("NLPA Admin")
        self.root.geometry("900x560")
        self.root.minsize(900, 560)

        # state
        self.api_url = tk.StringVar(value="https://nlpa-server-2.onrender.com")
        self.admin_user = tk.StringVar(value="")
        self.admin_pass = tk.StringVar(value="")
        self.admin_token = None

        # selected user
        self.selected_user = tk.StringVar(value="")
        self.users_cache = {}  # username -> details

        self._build_ui()

    def _build_ui(self):
        # top bar
        top = ctk.CTkFrame(self.root, corner_radius=10)
        top.pack(fill="x", padx=12, pady=(12, 8))

        ctk.CTkLabel(top, text="API URL").grid(row=0, column=0, padx=(12, 6), pady=10, sticky="w")
        self.ent_api = ctk.CTkEntry(top, width=360, textvariable=self.api_url)
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

        # main content split
        body = ctk.CTkFrame(self.root, corner_radius=10)
        body.pack(fill="both", expand=True, padx=12, pady=(0, 12))

        body.grid_columnconfigure(0, weight=1, uniform="cols")
        body.grid_columnconfigure(1, weight=2, uniform="cols")
        body.grid_rowconfigure(0, weight=1)

        # left: user list
        left = ctk.CTkFrame(body, corner_radius=10)
        left.grid(row=0, column=0, sticky="nsew", padx=(12, 8), pady=12)

        ctk.CTkLabel(left, text="Danh sách người dùng", font=("Arial", 14, "bold")).pack(padx=12, pady=(12, 6), anchor="w")
        self.listbox = tk.Listbox(left, height=20)
        self.listbox.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        self.listbox.bind("<<ListboxSelect>>", self.on_select_user)

        # right: user details + actions
        right = ctk.CTkFrame(body, corner_radius=10)
        right.grid(row=0, column=1, sticky="nsew", padx=(8, 12), pady=12)

        ctk.CTkLabel(right, text="Chi tiết tài khoản", font=("Arial", 14, "bold")).grid(row=0, column=0, columnspan=4, sticky="w", padx=12, pady=(12, 8))

        # info labels
        self.lbl_user = ctk.CTkLabel(right, text="User: -", font=("Arial", 12))
        self.lbl_user.grid(row=1, column=0, columnspan=4, sticky="w", padx=12, pady=4)

        self.lbl_paid = ctk.CTkLabel(right, text="Paid until: -  (days_left: -)", font=("Arial", 12))
        self.lbl_paid.grid(row=2, column=0, columnspan=4, sticky="w", padx=12, pady=4)

        self.lbl_pending = ctk.CTkLabel(right, text="Pending machine: -", font=("Arial", 12))
        self.lbl_pending.grid(row=3, column=0, columnspan=4, sticky="w", padx=12, pady=4)

        self.txt_machines = ctk.CTkTextbox(right, height=140)
        self.txt_machines.grid(row=4, column=0, columnspan=4, sticky="nsew", padx=12, pady=(6, 12))
        right.grid_rowconfigure(4, weight=1)

        # actions
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

        self.lbl_hint = ctk.CTkLabel(right, text="* Reset mật khẩu cần endpoint /admin/users/<u>/reset_password", text_color="#7a7a7a")
        self.lbl_hint.grid(row=7, column=0, columnspan=4, sticky="w", padx=12, pady=(0, 12))

    # =============== actions ===============
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
        self.refresh_users()

    def refresh_users(self):
        if not self.admin_token:
            return
        base = self.api_url.get().rstrip("/")
        try:
            r = requests.get(f"{base}/admin/users", headers={"Authorization": f"Bearer {self.admin_token}"}, timeout=20)
            j = r.json()
        except Exception as e:
            messagebox.showerror("Lỗi", f"Không tải danh sách: {e}")
            return

        if not j.get("ok"):
            messagebox.showerror("Lỗi", j.get("message", "Không tải được users"))
            return

        users = j.get("users", {})
        self.users_cache = users

        self.listbox.delete(0, tk.END)
        for uname in sorted(users.keys(), key=str.lower):
            self.listbox.insert(tk.END, uname)

        # clear details
        self.selected_user.set("")
        self._show_user_details(None)
        self.btn_extend.configure(state="disabled")
        self.btn_delete.configure(state="disabled")
        self.btn_reset_pw.configure(state="disabled")

    def on_select_user(self, _evt):
        try:
            sel = self.listbox.get(self.listbox.curselection())
        except Exception:
            sel = None
        self.selected_user.set(sel or "")
        self._show_user_details(sel)
        have = bool(sel)
        self.btn_extend.configure(state="normal" if have else "disabled")
        self.btn_delete.configure(state="normal" if have else "disabled")
        self.btn_reset_pw.configure(state="normal" if have else "disabled")

    def _show_user_details(self, uname):
        if not uname or uname not in self.users_cache:
            self.lbl_user.configure(text="User: -")
            self.lbl_paid.configure(text="Paid until: -  (days_left: -)")
            self.lbl_pending.configure(text="Pending machine: -")
            self.txt_machines.configure(state="normal")
            self.txt_machines.delete("1.0", tk.END)
            self.txt_machines.configure(state="disabled")
            return

        info = self.users_cache[uname]
        paid = info.get("paid_until")
        pending = info.get("pending_machine")
        machines = info.get("machines") or []

        # days left
        dl = days_left_from_iso(paid) if paid else None
        self.lbl_user.configure(text=f"User: {uname}")
        self.lbl_paid.configure(text=f"Paid until: {paid or '-'}  (days_left: {dl if dl is not None else '-'})")
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
        days_str = self.ent_days.get().strip() or "0"
        try:
            days = int(days_str)
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
                headers={"Authorization": f"Bearer {self.admin_token}"},
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
            r = requests.delete(
                f"{base}/admin/users/{uname}",
                headers={"Authorization": f"Bearer {self.admin_token}"},
                timeout=20
            )
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
        new_pw = self.ent_new_pw.get().strip()
        if not new_pw:
            messagebox.showerror("Lỗi", "Nhập mật khẩu mới.")
            return

        base = self.api_url.get().rstrip("/")
        try:
            r = requests.post(
                f"{base}/admin/users/{uname}/reset_password",
                json={"new_password": new_pw},
                headers={"Authorization": f"Bearer {self.admin_token}"},
                timeout=20
            )
            j = r.json()
        except Exception as e:
            messagebox.showerror("Lỗi", f"Không kết nối: {e}")
            return

        if not j.get("ok"):
            messagebox.showerror("Lỗi", j.get("message", "Reset mật khẩu thất bại"))
            return

        messagebox.showinfo("OK", j.get("message", "Đã cập nhật mật khẩu"))

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    AdminApp().run()
