import wx
import wx.adv
import os
import configparser
import multiprocessing
import subprocess
import threading
import urllib.request
import zipfile
import io
from pathlib import Path

FISHTEST_URL = "https://github.com/glinscott/fishtest/archive/refs/heads/master.zip"
STORAGE_DIR = Path(os.environ.get("LocalAppData")) / "Fishtest"
WORKER_DIR = Path(STORAGE_DIR) / "fishtest-master" / "worker"
CONFIG_PATH = Path(STORAGE_DIR) / "config.cfg"
MSYS_DIR = Path(STORAGE_DIR) / "msys64"
# So no window shows when packaged in pyinstaller
STARTUPINFO = subprocess.STARTUPINFO()
STARTUPINFO.dwFlags |= subprocess.STARTF_USESHOWWINDOW

STORAGE_DIR.mkdir(parents=True, exist_ok=True)
if not CONFIG_PATH.is_file():
    CONFIG_PATH.write_text(
        "[Settings]\n"
        "msys_path =\n\n"
        "[Fishtest]\n"
        "username =\n"
        "password =\n"
        "concurrency = 1"
        )


config = configparser.ConfigParser()
config.read(CONFIG_PATH)

def save_config():
    with open(CONFIG_PATH, 'w') as f:
        config.write(f)

def find_msys2():
    def save_path(pth):
        config['Settings']['msys_path'] = pth
        save_config()
    msys_config_path = config['Settings']['msys_path']
    if os.path.isdir(msys_config_path):
        return msys_config_path
    elif os.path.isdir("C:\\tools\\msys64"):
        save_path("C:\\tools\\msys64")
        return "C:\\tools\\msys64"

def download_chocolatey():
    olddir = os.getcwd()
    os.chdir(STORAGE_DIR)

    # Set choco installation dir
    os.environ["ChocolateyInstall"] = str(STORAGE_DIR / "chocoportable")
    # Install chocolatey
    try:
        return subprocess.Popen([
            os.environ['SystemRoot']+"/System32/WindowsPowerShell/v1.0/powershell.exe",
            "-ExecutionPolicy", "Bypass",
            "-Command",
            "iex ((New-Object System.Net.WebClient).DownloadString('https://community.chocolatey.org/install.ps1'))"
            ],
            stdout=subprocess.PIPE,
            stdin=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=0,
            text=True,
            startupinfo=STARTUPINFO)
    finally:
        os.chdir(olddir)


def download_msys2():
    olddir = os.getcwd()
    os.chdir(STORAGE_DIR)

    # Install msys2 to MSYS_DIR
    try:
        return subprocess.Popen([
            "choco",
            "install",
            "msys2",
            "-y",
            "--params",
            "/InstallDir:"+str(MSYS_DIR).replace("\\", "/")
            ], text=True,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=0,
            startupinfo=STARTUPINFO)
    finally:
        os.chdir(olddir)    

def install_packages():
    olddir = os.getcwd()
    os.chdir(STORAGE_DIR)
    (STORAGE_DIR / "install_packages.sh").write_text(
        "pacman -S --noconfirm unzip make mingw-w64-x86_64-gcc mingw-w64-x86_64-python3"
     )
    try:
        return subprocess.Popen([
            str(MSYS_DIR / "usr/bin/bash.exe"),
            "-l",
            "-c",
            str(STORAGE_DIR / "install_packages.sh").replace("\\", "/")
            ],
            stdout=subprocess.PIPE,
            stdin=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=0,
            text=True,
            startupinfo=STARTUPINFO)
    finally:
        config["Settings"]["msys_path"] = str(MSYS_DIR)
        save_config()

        os.chdir(olddir)

def download_fishtest():
    with urllib.request.urlopen(FISHTEST_URL) as f:
        data = f.read()

    zipf = zipfile.ZipFile(io.BytesIO(data))
    del data
    zipf.extractall(path=STORAGE_DIR)
    zipf.close()

def run_fishtest():
    os.chdir(STORAGE_DIR)
    msys_path = Path(config["Settings"]["msys_path"])
    os.environ["PATH"] = str(msys_path / "mingw64/bin")+";"+str(msys_path / "usr/bin")+";"+os.environ["PATH"]
    return subprocess.Popen([
        "python3.exe",
        "-u",
        "fishtest-master/worker/worker.py",
        config['Fishtest']['username'],
        config['Fishtest']['password'],
        "--concurrency",
        config['Fishtest']['concurrency']
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        stdin=subprocess.PIPE,
        text=True,
        bufsize=0,
        startupinfo=STARTUPINFO)



class MonitorThread(threading.Thread):
    def __init__(self, text_ctrl, st, callback, plcallback=None):
        super().__init__()
        self.plcallback = plcallback
        self.callback = callback
        self.text_ctrl = text_ctrl
        self.st = st
        self.do_run = True
        self.start()

    def run(self):            
        while self.do_run:
            try:
                line = self.st.readline()
            except (ValueError, OSError):
                break
            if not line.strip() == "":
                wx.CallAfter(self.text_ctrl.write, line)
                if self.plcallback:
                    wx.CallAfter(self.plcallback, line)
            if not line: break
        try:
            self.callback("")
        except:
            pass


class MainFrame(wx.Frame):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.monitor_thread = None
        self.monitor_thread_error = None
        self.proc = None
        self.games_played = 0
        self.tests_completed = 0
        self.session_games = 0
        self.session_tasks = 0
        self.padding = wx.EXPAND|wx.ALL

        self.panel = wx.Panel(self)
        self.vbox = wx.BoxSizer(wx.VERTICAL)

        self.create_help()
        self.create_msys_settings()
        self.create_fishtest_settings()
        self.create_test_data()
    
        self.panel.SetSizer(self.vbox)
        self.Bind(wx.EVT_CLOSE, self.on_close)
        self.SetMinSize((400, 600))

    def create_help(self):
        self.help_sizer = wx.BoxSizer(wx.HORIZONTAL)
        
        self.help_label = wx.StaticText(self.panel, label="Don't know what do do?")

        self.help_url = wx.adv.HyperlinkCtrl(self.panel,
                                         label="Look at the wiki.",
                                         url="https://github.com/Dark42ed/fishtest-gui/wiki/Quickstart")

        self.help_sizer.Add(self.help_label, 0, wx.ALL, 5)
        self.help_sizer.Add(self.help_url, 0, wx.ALL, 5)

        self.vbox.Add(self.help_sizer, 0, wx.ALIGN_CENTER_HORIZONTAL)

    def create_msys_settings(self):
        self.msys_box = wx.StaticBox(self.panel, label="MSYS2")
        self.msys_sizer = wx.StaticBoxSizer(self.msys_box, wx.HORIZONTAL)
        
        self.msys_input_field = wx.TextCtrl(self.panel)
        self.msys_input_field.SetValue(find_msys2())

        self.msys_label = wx.StaticText(self.panel)
        self.msys_label.Label = "Path"
        
        self.msys_download = wx.Button(self.panel)
        self.msys_download.Label = "Download MSYS2"
        self.msys_download.Bind(wx.EVT_BUTTON, self.do_download_msys)

        # Until we get a stable solution in place
        self.msys_download.Enable()
        
        self.msys_sizer.Add(self.msys_label, 0, wx.ALL|wx.ALIGN_CENTER_VERTICAL, 5)
        self.msys_sizer.Add(self.msys_input_field, 1, self.padding, 5)
        self.msys_sizer.Add(self.msys_download, 0, self.padding, 5)
        
        self.vbox.Add(self.msys_sizer, 0, self.padding, 5)

    def create_fishtest_settings(self):
        max_concurrency = multiprocessing.cpu_count()-1
        self.fishtest_box = wx.StaticBox(self.panel, label="Fishtest")
        self.fishtest_sizer = wx.StaticBoxSizer(self.fishtest_box, wx.VERTICAL)

        self.fishtest_settings = wx.BoxSizer(wx.HORIZONTAL)

        # Username stuff ---

        self.username_sizer = wx.BoxSizer(wx.VERTICAL)

        self.username_label = wx.StaticText(self.panel)
        self.username_label.Label = "Username"

        self.username_input = wx.TextCtrl(self.panel)
        self.username_input.SetValue(config["Fishtest"]["username"])

        self.username_sizer.Add(self.username_label, 0, wx.TOP|wx.LEFT|wx.RIGHT, 5)
        self.username_sizer.Add(self.username_input, 1, wx.LEFT|wx.BOTTOM|wx.RIGHT|wx.EXPAND, 5)

        # Password stuff ---

        self.password_sizer = wx.BoxSizer(wx.VERTICAL)

        self.password_label = wx.StaticText(self.panel)
        self.password_label.Label = "Password"

        self.password_input = wx.TextCtrl(self.panel)
        self.password_input.SetValue(config["Fishtest"]["password"])

        self.password_sizer.Add(self.password_label, 0, wx.TOP|wx.LEFT|wx.RIGHT, 5)
        self.password_sizer.Add(self.password_input, 1, wx.LEFT|wx.BOTTOM|wx.RIGHT|wx.EXPAND, 5)

        # Concurrency stuff ---

        self.concurrency_label = wx.StaticText(self.panel)
        self.concurrency_label.Label = "Concurrency (1 - "+str(max_concurrency)+")"

        self.concurrency_input = wx.SpinCtrl(self.panel, style=wx.SP_ARROW_KEYS|wx.SP_WRAP, min=1, max=max_concurrency)
        self.concurrency_input.SetMaxSize((-1, 23))

        # Start stop

        self.button_sizer = wx.BoxSizer(wx.HORIZONTAL)

        self.start_button = wx.Button(self.panel, label="Start")
        self.start_button.Bind(wx.EVT_BUTTON, self.start_fishtest)
        
        self.stop_button = wx.Button(self.panel, label="Stop")
        self.stop_button.Bind(wx.EVT_BUTTON, self.stop_fishtest)
        self.stop_button.Disable()

        self.button_sizer.AddStretchSpacer(1)
        self.button_sizer.Add(self.start_button, 1, self.padding, 5)
        self.button_sizer.AddStretchSpacer(1)
        self.button_sizer.Add(self.stop_button, 1, self.padding, 5)
        self.button_sizer.AddStretchSpacer(1)

        self.fishtest_settings.Add(self.username_sizer, 1, self.padding, 0)
        self.fishtest_settings.Add(self.password_sizer, 1, self.padding, 0)
        self.fishtest_sizer.Add(self.fishtest_settings, 1, wx.EXPAND)

        self.fishtest_sizer.Add(self.concurrency_label, 0, wx.TOP|wx.LEFT|wx.RIGHT, 5)
        self.fishtest_sizer.Add(self.concurrency_input, 1, wx.LEFT|wx.RIGHT|wx.BOTTOM|wx.EXPAND, 5)
        self.fishtest_sizer.Add(self.button_sizer, 1, self.padding, 5)

        self.vbox.Add(self.fishtest_sizer, 0, self.padding, 5)

    def create_test_data(self):
        self.test_stats_box = wx.StaticBox(self.panel, label="Test Stats")
        self.test_stats_sizer = wx.StaticBoxSizer(self.test_stats_box, wx.VERTICAL)

        self.test_stats = wx.BoxSizer(wx.HORIZONTAL)

        self.session_tests_label = wx.StaticText(self.panel)
        self.session_tests_label.Label = "Tests completed this session: 0"

        self.session_games_label = wx.StaticText(self.panel)
        self.session_games_label.Label = "Games played this session: 0"

        self.test_stats.AddStretchSpacer(1)
        self.test_stats.Add(self.session_tests_label, 1, wx.ALL|wx.ALIGN_CENTER, 5)
        self.test_stats.AddStretchSpacer(1)
        self.test_stats.Add(self.session_games_label, 1, wx.ALL|wx.ALIGN_CENTER, 5)
        self.test_stats.AddStretchSpacer(1)
        
        self.log_label = wx.StaticText(self.panel, label="Log")
        self.log = wx.TextCtrl(self.panel, style=wx.TE_READONLY|wx.TE_MULTILINE)

        self.test_stats_sizer.Add(self.test_stats, 0, self.padding, 5)
        self.test_stats_sizer.Add(self.log_label, 0, wx.LEFT, 5)
        self.test_stats_sizer.Add(self.log, 1, self.padding, 5)

        self.vbox.Add(self.test_stats_sizer, 1, self.padding, 5)
        
    def start_fishtest(self, event):
        if self.monitor_thread is not None:
            self.log.write("\n")
        self.start_button.Disable()
        self.stop_button.Enable()
        
        config["Settings"]["msys_path"] = self.msys_input_field.GetValue()
        config["Fishtest"]["username"] = self.username_input.GetValue()
        config["Fishtest"]["password"] = self.password_input.GetValue()
        config["Fishtest"]["concurrency"] = str(self.concurrency_input.GetValue())
        save_config()

        if not os.path.exists(WORKER_DIR):
            self.log.write("Downloading Fishtest...")
            download_fishtest()
            self.log.write("done\n")

        self.proc = run_fishtest()
        self.monitor_thread = MonitorThread(self.log, self.proc.stdout, self.stop_fishtest, self.update_stats)
        self.monitor_thread_error = MonitorThread(self.log, self.proc.stderr, lambda x: None)

    
    def stop_fishtest(self, event):
        self.monitor_thread.do_run = False
        self.proc.kill()
        self.stop_button.Disable()
        self.start_button.Enable()

    def on_close(self, event):
        if self.monitor_thread:
            self.monitor_thread.do_run = False
        if self.monitor_thread_error:
            self.monitor_thread_error.do_run = False
        if self.proc:
            self.proc.kill()
        self.Destroy()
        
    def do_download_msys(self, event):
        dlg = wx.MessageDialog(None, "This process may take 5-10 minutes. Continue?", style=wx.OK|wx.CANCEL)
        if dlg.ShowModal() == wx.ID_OK:
            self.start_button.Disable()
            self.stop_button.Disable()
            self.msys_download.Disable()
            # Download chocolatey
            # There are 2 more functions because this relies on a callback system
            self.proc = download_chocolatey()
            self.monitor_thread = MonitorThread(self.log, self.proc.stdout, self.start_download_msys)
            self.monitor_thread_error = MonitorThread(self.log, self.proc.stderr, lambda x: None)

    def start_download_msys(self, *a, **k):
        # Download msys via chocolatey
        self.proc = download_msys2()
        self.monitor_thread = MonitorThread(self.log, self.proc.stdout, self.install_packages)
        self.monitor_thread_error = MonitorThread(self.log, self.proc.stderr, lambda x: None)
        # Bypass 20 wait for non-admin
        self.proc.communicate(input="Y\n")

    def install_packages(self, *a, **k):
        # Install packages (gcc, python, unzip, wget)
        self.proc = install_packages()
        self.monitor_thread = MonitorThread(self.log, self.proc.stdout, self.done_msys)
        self.monitor_thread_error = MonitorThread(self.log, self.proc.stderr, lambda x: None)

    def done_msys(self, *a, **k):
        self.msys_input_field.SetValue(config["Settings"]["msys_path"])
        self.start_button.Enable()
        self.msys_download.Enable()

    def update_stats(self, line):
        if "Finished game " in line:
            self.session_games += 1
        if "Task exited" in line:
            self.session_tasks += 1
            
        self.session_tests_label.Label = "Tests completed this session: "+str(self.session_tasks)
        self.session_games_label.Label = "Games played this session: "+str(self.session_games)



if __name__ == "__main__":
    app = wx.App()
    MainFrame(None, title="Fishtest").Show()
    app.MainLoop()
