import customtkinter as ctk
import tkinter as tk
from tkinter import filedialog
import os, subprocess, threading, shutil, re, string, requests, zipfile
from bs4 import BeautifulSoup

# ----------------------------
# CONFIG
# ----------------------------
APP_NAME = "Dev Server Installer"

ARTIFACT_PAGE = "https://runtime.fivem.net/artifacts/fivem/build_server_windows/master/"

MAIN_REPO = "https://github.com/RoleplayOrginization/DevServer"

REPOS = {
    "Weapons": {"url": "https://github.com/RoleplayOrginization/Weapons", "path": "txData/ServerFiles/resources/[Weapons]"},
    "MLOS": {"url": "https://github.com/RoleplayOrginization/MLOS", "path": "txData/ServerFiles/resources/[MLOS]"},
    "Clothing": {"url": "https://github.com/RoleplayOrginization/Clothing2", "path": "txData/ServerFiles/resources/[Clothing]"},
    "Cars": {"url": "https://github.com/RoleplayOrginization/Cars", "path": "txData/ServerFiles/resources/[Cars]"},
    "Props": {"url": "https://github.com/RoleplayOrginization/Props", "path": "txData/ServerFiles/resources/[Dependencies]/[Props]"},
    "DevTools": {"url": "https://github.com/RoleplayOrginization/Dev_Tools", "path": "txData/ServerFiles/resources/[Dependencies]/[DevTools]"}
}

# ----------------------------
# XAMPP MYSQL DETECT
# ----------------------------

def detect_xampp_mysql():
    possible = [
        r"C:\xampp\mysql\bin\mysql.exe",
        r"C:\xampp\mysql\bin\mariadb.exe",
        r"D:\xampp\mysql\bin\mysql.exe",
        r"D:\xampp\mysql\bin\mariadb.exe"
    ]

    # Check common paths first
    for path in possible:
        if os.path.exists(path):
            return path

    # Scan drives (limited depth)
    for drive in string.ascii_uppercase:
        base = f"{drive}:\\xampp\\mysql\\bin\\"
        if os.path.exists(base):
            for exe in ["mysql.exe", "mariadb.exe"]:
                full = os.path.join(base, exe)
                if os.path.exists(full):
                    return full

    return None

# ----------------------------
# SQL PATCH
# ----------------------------
def patch_sql(file, db, log):
    log("[STEP] Patching SQL...")

    with open(file, "r", encoding="utf-8", errors="ignore") as f:
        c = f.read()

    c = re.sub(r"CREATE\s+DATABASE\s+IF\s+NOT\s+EXISTS\s+`?\w+`?",
               f"CREATE DATABASE IF NOT EXISTS `{db}`", c, flags=re.I)

    c = re.sub(r"USE\s+`?\w+`?", f"USE `{db}`", c, flags=re.I)

    out = file.replace(".sql", "_patched.sql")

    with open(out, "w", encoding="utf-8") as f:
        f.write(c)

    return out

# ----------------------------
# SQL EXEC (NON FATAL)
# ----------------------------
def run_sql(mysql, db, user, pw, file, log, errors):
    pw_part = f"-p{pw}" if pw else ""

    log("[STEP] Creating database...")

    subprocess.run(
        f'"{mysql}" -u{user} {pw_part} -e "CREATE DATABASE IF NOT EXISTS `{db}`;"',
        shell=True
    )

    result = subprocess.run(
        f'"{mysql}" -u{user} {pw_part} {db} < "{file}"',
        shell=True,
        capture_output=True,
        text=True
    )

    if result.returncode != 0:
        errors.append(result.stderr)
        log("[WARN] SQL failed (non-fatal)")
    else:
        log("[OK] SQL imported")

# ----------------------------
# SERVER CFG PATCH
# ----------------------------
def patch_cfg(path, db, log):
    if not os.path.exists(path):
        return

    log("[STEP] Patching server.cfg...")

    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        c = f.read()

    c = re.sub(
        r"(mysql:\/\/[^\/]+@[^\/]+\/)([^?]+)(\?charset=.*)",
        rf"\1{db}\3",
        c
    )

    with open(path, "w", encoding="utf-8") as f:
        f.write(c)

# ---------------------------
# FETCH LATEST ARTIFACT
# ---------------------------
def get_latest_artifact():
    print("[*] Fetching latest FiveM build...")

    r = requests.get(ARTIFACT_PAGE)
    soup = BeautifulSoup(r.text, "html.parser")

    links = soup.find_all("a")
    for link in links[::-1]:  # reverse for newest
        href = link.get("href")
        if href and "server.zip" in href:
            return ARTIFACT_PAGE + href

    raise Exception("No artifact found")


# ---------------------------
# DOWNLOAD + EXTRACT
# ---------------------------
def download_and_extract(url, unzip_path):
    print("[*] Downloading artifacts...")
    zip_path = "server.zip"

    with requests.get(url, stream=True) as r:
        with open(zip_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)

    print("[*] Extracting...")
    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
        zip_ref.extractall(unzip_path)

# ----------------------------
# APP  
# ----------------------------
class App(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title(APP_NAME)
        self.geometry("600x500")

        # State
        self.install_dir = tk.StringVar()
        self.db_name = tk.StringVar(value="fivemdev")
        self.db_user = tk.StringVar(value="root")
        self.db_pass = tk.StringVar()
        self.sql_file = tk.StringVar()
        self.mysql_path = tk.StringVar()

        self.repos = {k: tk.BooleanVar(value=False) for k in REPOS}

        self.errors = []

        self.frames = {}
        for F in (Welcome, RepoSelect, Database, Install, Finish):
            f = F(self)
            self.frames[F] = f
            f.place(relwidth=1, relheight=1)

        self.show(Welcome)

    def show(self, page):
        frame = self.frames[page]
        frame.tkraise()
        if hasattr(frame, "load"):
            frame.load()


# ----------------------------
# WELCOME
# ----------------------------
class Welcome(ctk.CTkFrame):
    def __init__(self, p):
        super().__init__(p)

        ctk.CTkLabel(self,text="Dev Server Installer",
                     font=ctk.CTkFont(size=28,weight="bold")).pack(pady=20)

        ctk.CTkLabel(self,text="Install Folder").pack()
        ctk.CTkEntry(self,textvariable=p.install_dir,width=500).pack()

        ctk.CTkButton(self,text="Browse",
                      command=self.browse).pack(pady=5)

        ctk.CTkButton(self,text="Next",
                      command=lambda:p.show(RepoSelect)).pack(pady=20)

    def browse(self):
        d = filedialog.askdirectory()
        if d:
            self.master.install_dir.set(d)

# ----------------------------
# REPO SELECT
# ----------------------------
class RepoSelect(ctk.CTkFrame):
    def __init__(self,p):
        super().__init__(p)

        self.p = p

        ctk.CTkLabel(self,text="Select Resources",
                     font=ctk.CTkFont(size=20)).pack(pady=10)

        for k,v in p.repos.items():
            ctk.CTkCheckBox(self,text=k,variable=v).pack(anchor="w",padx=40, pady=5)

        ctk.CTkButton(self,text="Next",
                      command=lambda:p.show(Database)).pack(pady=20)


# ----------------------------
# DATABASE
# ----------------------------
class Database(ctk.CTkFrame):
    def __init__(self,p):
        super().__init__(p)

        self.p = p

        self.check_mysql()

        ctk.CTkLabel(self,text="Database Setup",
                     font=ctk.CTkFont(size=20)).pack(pady=10)

        ctk.CTkLabel(self,text="Database Name").pack()
        ctk.CTkEntry(self,textvariable=p.db_name).pack() 

        ctk.CTkLabel(self,text="Database User").pack()
        ctk.CTkEntry(self,textvariable=p.db_user).pack()

        ctk.CTkLabel(self,text="Database Password").pack()
        ctk.CTkEntry(self,textvariable=p.db_pass, show="*").pack()

        ctk.CTkLabel(self,text="SQL File").pack(pady=5)
        ctk.CTkEntry(self,textvariable=p.sql_file, width=400).pack()
        ctk.CTkButton(self,text="Browse",
                      command=self.browse).pack(pady=5)


        ctk.CTkEntry(self,textvariable=p.mysql_path, width=400).pack()
        ctk.CTkButton(self,text="Browse MySQL", command=self.browseMySQL).pack(pady=5)

        ctk.CTkButton(self,text="Test MySQL",
                      command=lambda:self.testMySQL()).pack(pady=5)

        ctk.CTkButton(self,text="Next",
                      command=lambda:p.show(Install)).pack(pady=20)

    def browse(self):
        f = filedialog.askopenfilename(filetypes=[("SQL Files", "*.sql")])
        if f:
            self.p.sql_file.set(f)
    
    def browseMySQL(self):
        f = filedialog.askopenfilename(filetypes=[("MySQL Executable", "mysql.exe; mariadb.exe")])
        if f and os.path.basename(f).lower() in ["mysql.exe", "mariadb.exe"]:
            self.p.mysql_path.set(f)
        else:
            tk.messagebox.showerror("Invalid File", "Please select a valid MySQL executable (mysql.exe or mariadb.exe).")

    def check_mysql(self):
        path = detect_xampp_mysql()
        if path:
            self.p.mysql_path.set(path)

    def testMySQL(self):
        mysql = self.p.mysql_path.get()
        user = self.p.db_user.get()
        pw = self.p.db_pass.get()

        if not mysql:
            tk.messagebox.showerror("MySQL Path Required", "Please specify the path to your MySQL executable.")
            return

        pw_part = f"-p{pw}" if pw else ""

        result = subprocess.run(
            f'"{mysql}" -u{user} {pw_part} -e "SELECT VERSION();"',
            shell=True,
            capture_output=True,
            text=True
        )

        if result.returncode == 0:
            tk.messagebox.showinfo("MySQL Connection Successful", f"Successfully connected to MySQL.\nVersion: {result.stdout.strip()}")
        else:
            tk.messagebox.showerror("MySQL Connection Failed", f"Failed to connect to MySQL.\nError: {result.stderr.strip()}")

# ----------------------------
# INSTALL
# ----------------------------
class Install(ctk.CTkFrame):
    def __init__(self,p):
        super().__init__(p)

        self.p = p

        ctk.CTkLabel(self,text="Installing...", font=ctk.CTkFont(size=20)).pack(pady=10)

        self.log_box = ctk.CTkTextbox(self, state="disabled")
        self.log_box.pack(fill="both", expand=True, padx=20, pady=40)

        self.install_thread = None

        ctk.CTkButton(self,text="Start Install",
                      command=self.start).pack()
    
    def start(self):
        if self.install_thread and self.install_thread.is_alive():
            return

        self.install_thread = threading.Thread(target=self.run_install)
        self.install_thread.start()

    def run_install(self):
        p = self.p
        base = p.install_dir.get()

        # 1. Clone main repo
        self.log("[STEP] Cloning main repository...")
        main_path = os.path.join(p.install_dir.get())
        if os.path.exists(main_path):
            shutil.rmtree(main_path)
        subprocess.run(f'git clone {MAIN_REPO} "{main_path}"', shell=True)

        # 2. Clone selected repos
        for name, var in p.repos.items():
            if not var.get():
                continue

            repo_info = REPOS[name]
            repo_path = os.path.join(p.install_dir.get(), repo_info["path"])

            try:
                self.log(f"[STEP] Cloning {name}...")

                # Remove existing folder safely
                if os.path.exists(repo_path):
                    shutil.rmtree(repo_path)

                result = subprocess.run(
                    ["git", "clone", repo_info["url"], repo_path],
                    capture_output=True,
                    text=True
                )

                if result.returncode != 0:
                    error_msg = f"{name} clone failed:\n{result.stderr}"
                    self.log(f"[WARN] {error_msg}")
                    self.p.errors.append(error_msg)
                else:
                    self.log(f"[OK] {name} cloned successfully")

            except Exception as e:
                error_msg = f"{name} clone exception: {str(e)}"
                self.log(f"[ERROR] {error_msg}")
                self.p.errors.append(error_msg)

        # 3. Patch SQL
        patched_sql = patch_sql(p.sql_file.get(), p.db_name.get(), self.log)

        # 4. Run SQL
        self.log(f"[INFO] Using MySQL at: {p.mysql_path.get()}")
        self.log(f"[INFO] Database: {p.db_name.get()}, User: {p.db_user.get()}")
        self.log("[INFO] Running SQL... This may take a moment.")
        run_sql(p.mysql_path.get(), p.db_name.get(), p.db_user.get(), p.db_pass.get(), patched_sql, self.log, p.errors)

        # 5. Patch server.cfg
        self.log("[STEP] Patching server.cfg with database name...")
        cfg_path = os.path.join(base,"SetupFiles","server.cfg")
        patch_cfg(cfg_path, p.db_name.get(), self.log)

        # 6. Moving configs
        self.log("[STEP] Moving configuration files...")
        configs = ["server.cfg", "misc.cfg", "ox.cfg", "voice.cfg"]
        for cfg in configs:
            self.log(f"[STEP] Moving {cfg}...")
            src = os.path.join(base,"SetupFiles",cfg)
            dst = os.path.join(base,"txData","ServerFiles",cfg)
            if os.path.exists(src):
                shutil.move(src, dst)
            else:
                self.log(f"[WARN] {cfg} not found at expected location")

        # 7. Set up artifacts
        self.log("[STEP] Setting up artifacts...")
        os.makedirs(os.path.join(base,"server1"),exist_ok=True)
        download_and_extract(get_latest_artifact(), os.path.join(base,"server1"))

        # 8. Finish
        self.log("[OK] Installation complete!")
        p.show(Finish)

    def log(self, msg):
        self.log_box.configure(state="normal")
        self.log_box.insert("end", msg + "\n")
        self.log_box.configure(state="disabled")
        self.log_box.see("end")

# ----------------------------
# FINISH   
# ----------------------------
class Finish(ctk.CTkFrame):
    def __init__(self,p):
        super().__init__(p)

        self.p = p

        ctk.CTkLabel(self,text="Installation Complete!", font=ctk.CTkFont(size=20)).pack(pady=20)

        self.error_label = ctk.CTkLabel(self,text="However, some errors were encountered:", text_color="red")
        self.box = ctk.CTkTextbox(self, width=700, height=200)
        self.success_label = ctk.CTkLabel(self,text="No errors encountered!", text_color="green")

        self.open_folder_button = ctk.CTkButton(self, text="Open Folder",
                      command=lambda: os.startfile(p.install_dir.get()))
        self.exit_button = ctk.CTkButton(self, text="Exit",
                      command=p.destroy)

    def load(self):
        self.error_label.pack_forget()
        self.box.pack_forget()
        self.success_label.pack_forget()
        self.open_folder_button.pack_forget()
        self.exit_button.pack_forget()

        if self.p.errors:
            self.error_label.pack(pady=10)

            self.box.pack(pady=10)
            self.box.configure(state="normal")
            self.box.delete("1.0", "end")

            for err in self.p.errors:
                self.box.insert("end", f"- {err}\n")

            self.box.configure(state="disabled")
        else:
            self.success_label.pack(pady=10)

        self.open_folder_button.pack(pady=5)
        self.exit_button.pack(pady=5)

# ----------------------------
# MAIN
# ----------------------------
if __name__ == "__main__":
    p = App()
    p.mainloop()
