import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import json
import os
import subprocess
import threading
import sys

class CopyTradeApp:
    def __init__(self, root):
        self.root = root
        self.root.title("MT5 CopyTrade Dashboard")
        self.root.geometry("680x750")
        self.root.minsize(600, 600)
        
        self.master_process = None
        self.client_process = None
        self.running = False
        
        self.config_file = "config.json"
        self.load_config()
        self.setup_ui()
        self.check_processes()

    def load_config(self):
        default_config = {
            "redis": {
                "host": "localhost",
                "port": 6379,
                "db": 0,
                "channel": "copy_trade_gold"
            },
            "master": {
                "terminal_path": r"C:\Program Files\MetaTrader 5 - Copy (2)\terminal64.exe",
                "poll_interval_seconds": 0.05
            },
            "client": {
                "terminal_path": r"C:\Program Files\MetaTrader 5\terminal64.exe",
                "gold_symbol": "XAUUSD-ECN",
                "lot_multiplier": 0.5,
                "lot_minimum": 0.01,
                "magic_number": 999999,
                "deviation": 20
            }
        }
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, "r", encoding="utf-8") as f:
                    self.config = json.load(f)
            except Exception as e:
                messagebox.showerror("Error", f"Failed to load config: {e}")
                self.config = default_config
        else:
            self.config = default_config
            self.save_config_to_file()

    def save_config_to_file(self):
        try:
            with open(self.config_file, "w", encoding="utf-8") as f:
                json.dump(self.config, f, indent=4, ensure_ascii=False)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save config: {e}")

    def setup_ui(self):
        # Apply clean theme
        style = ttk.Style()
        style.theme_use('clam')
        
        # Configure styles
        style.configure('TLabel', font=('Segoe UI', 9))
        style.configure('TEntry', font=('Segoe UI', 9))
        style.configure('TButton', font=('Segoe UI', 9, 'bold'), padding=5)
        style.configure('TLabelframe', padding=10)
        style.configure('TLabelframe.Label', font=('Segoe UI', 10, 'bold'), foreground='#0052cc')
        
        # Main Scrollable / Padded Frame
        main_frame = ttk.Frame(self.root, padding="15")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Title Label
        title_label = tk.Label(main_frame, text="MT5 Investor CopyTrade Controller", font=('Segoe UI', 14, 'bold'), fg="#0052cc")
        title_label.pack(anchor=tk.W, pady=(0, 10))
        
        # --- Section 1: Terminals ---
        terminals_frame = ttk.LabelFrame(main_frame, text=" MetaTrader 5 Terminals Configuration ")
        terminals_frame.pack(fill=tk.X, pady=(0, 10))
        
        # Master Terminal Path
        ttk.Label(terminals_frame, text="Master Terminal (.exe):").grid(row=0, column=0, sticky=tk.W, pady=5)
        self.master_path_var = tk.StringVar(value=self.config["master"]["terminal_path"])
        self.master_entry = ttk.Entry(terminals_frame, textvariable=self.master_path_var, width=50)
        self.master_entry.grid(row=0, column=1, padx=5, pady=5, sticky=tk.EW)
        ttk.Button(terminals_frame, text="Browse...", command=self.browse_master).grid(row=0, column=2, padx=5, pady=5)
        
        # Client Terminal Path
        ttk.Label(terminals_frame, text="Client Terminal (.exe):").grid(row=1, column=0, sticky=tk.W, pady=5)
        self.client_path_var = tk.StringVar(value=self.config["client"]["terminal_path"])
        self.client_entry = ttk.Entry(terminals_frame, textvariable=self.client_path_var, width=50)
        self.client_entry.grid(row=1, column=1, padx=5, pady=5, sticky=tk.EW)
        ttk.Button(terminals_frame, text="Browse...", command=self.browse_client).grid(row=1, column=2, padx=5, pady=5)
        
        terminals_frame.columnconfigure(1, weight=1)
        
        # --- Section 2: Two Column settings ---
        settings_frame = ttk.Frame(main_frame)
        settings_frame.pack(fill=tk.X, pady=(0, 10))
        
        # Redis Connection Frame
        redis_frame = ttk.LabelFrame(settings_frame, text=" Redis Connection ")
        redis_frame.grid(row=0, column=0, sticky=tk.NSEW, padx=(0, 5))
        
        ttk.Label(redis_frame, text="Redis Host:").grid(row=0, column=0, sticky=tk.W, pady=4)
        self.redis_host_var = tk.StringVar(value=self.config["redis"]["host"])
        ttk.Entry(redis_frame, textvariable=self.redis_host_var, width=15).grid(row=0, column=1, sticky=tk.W, pady=4)
        
        ttk.Label(redis_frame, text="Redis Port:").grid(row=1, column=0, sticky=tk.W, pady=4)
        self.redis_port_var = tk.StringVar(value=str(self.config["redis"]["port"]))
        ttk.Entry(redis_frame, textvariable=self.redis_port_var, width=15).grid(row=1, column=1, sticky=tk.W, pady=4)
        
        ttk.Label(redis_frame, text="Redis DB:").grid(row=2, column=0, sticky=tk.W, pady=4)
        self.redis_db_var = tk.StringVar(value=str(self.config["redis"]["db"]))
        ttk.Entry(redis_frame, textvariable=self.redis_db_var, width=15).grid(row=2, column=1, sticky=tk.W, pady=4)
        
        ttk.Label(redis_frame, text="Channel Name:").grid(row=3, column=0, sticky=tk.W, pady=4)
        self.redis_channel_var = tk.StringVar(value=self.config["redis"]["channel"])
        ttk.Entry(redis_frame, textvariable=self.redis_channel_var, width=15).grid(row=3, column=1, sticky=tk.W, pady=4)
        
        # Copy Parameters Frame
        copy_frame = ttk.LabelFrame(settings_frame, text=" Copy Trade Settings ")
        copy_frame.grid(row=0, column=1, sticky=tk.NSEW, padx=(5, 0))
        
        ttk.Label(copy_frame, text="Gold Symbol:").grid(row=0, column=0, sticky=tk.W, pady=4)
        self.gold_symbol_var = tk.StringVar(value=self.config["client"]["gold_symbol"])
        ttk.Entry(copy_frame, textvariable=self.gold_symbol_var, width=15).grid(row=0, column=1, sticky=tk.W, pady=4)
        
        ttk.Label(copy_frame, text="Lot Multiplier:").grid(row=1, column=0, sticky=tk.W, pady=4)
        self.lot_multiplier_var = tk.StringVar(value=str(self.config["client"]["lot_multiplier"]))
        ttk.Entry(copy_frame, textvariable=self.lot_multiplier_var, width=15).grid(row=1, column=1, sticky=tk.W, pady=4)
        
        ttk.Label(copy_frame, text="Min Lot Limit:").grid(row=2, column=0, sticky=tk.W, pady=4)
        self.lot_min_var = tk.StringVar(value=str(self.config["client"]["lot_minimum"]))
        ttk.Entry(copy_frame, textvariable=self.lot_min_var, width=15).grid(row=2, column=1, sticky=tk.W, pady=4)
        
        ttk.Label(copy_frame, text="Poll Interval (s):").grid(row=3, column=0, sticky=tk.W, pady=4)
        self.poll_interval_var = tk.StringVar(value=str(self.config["master"]["poll_interval_seconds"]))
        ttk.Entry(copy_frame, textvariable=self.poll_interval_var, width=15).grid(row=3, column=1, sticky=tk.W, pady=4)

        ttk.Label(copy_frame, text="Magic Number:").grid(row=4, column=0, sticky=tk.W, pady=4)
        self.magic_var = tk.StringVar(value=str(self.config["client"]["magic_number"]))
        ttk.Entry(copy_frame, textvariable=self.magic_var, width=15).grid(row=4, column=1, sticky=tk.W, pady=4)

        ttk.Label(copy_frame, text="Max Deviation:").grid(row=5, column=0, sticky=tk.W, pady=4)
        self.deviation_var = tk.StringVar(value=str(self.config["client"]["deviation"]))
        ttk.Entry(copy_frame, textvariable=self.deviation_var, width=15).grid(row=5, column=1, sticky=tk.W, pady=4)
        
        settings_frame.columnconfigure(0, weight=1)
        settings_frame.columnconfigure(1, weight=1)
        
        # --- Section 3: Control Buttons & Status ---
        control_frame = ttk.Frame(main_frame, padding="5")
        control_frame.pack(fill=tk.X, pady=10)
        
        self.save_button = ttk.Button(control_frame, text="💾 Save Config", command=self.save_settings)
        self.save_button.pack(side=tk.LEFT, padx=5)
        
        self.start_button = ttk.Button(control_frame, text="▶ Start CopyTrade", command=self.start_copytrade)
        self.start_button.pack(side=tk.LEFT, padx=5)
        
        self.stop_button = ttk.Button(control_frame, text="■ Stop CopyTrade", command=self.stop_copytrade, state=tk.DISABLED)
        self.stop_button.pack(side=tk.LEFT, padx=5)
        
        self.status_label = tk.Label(control_frame, text="STATUS: STOPPED", font=('Segoe UI', 10, 'bold'), fg="red")
        self.status_label.pack(side=tk.RIGHT, padx=10)
        
        # --- Section 4: Output Log ---
        log_frame = ttk.LabelFrame(main_frame, text=" Real-time Logs & Activity ")
        log_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 5))
        
        self.log_text = tk.Text(log_frame, wrap=tk.WORD, height=15, state=tk.DISABLED, bg="#1e1e1e", fg="#d4d4d4", font=('Consolas', 9.5))
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        scrollbar = ttk.Scrollbar(log_frame, command=self.log_text.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.log_text.config(yscrollcommand=scrollbar.set)

    def browse_master(self):
        filename = filedialog.askopenfilename(
            title="Select Master terminal64.exe",
            filetypes=[("Executable files", "*.exe"), ("All files", "*.*")]
        )
        if filename:
            self.master_path_var.set(os.path.normpath(filename))
            
    def browse_client(self):
        filename = filedialog.askopenfilename(
            title="Select Client terminal64.exe",
            filetypes=[("Executable files", "*.exe"), ("All files", "*.*")]
        )
        if filename:
            self.client_path_var.set(os.path.normpath(filename))

    def save_settings(self):
        try:
            self.config["redis"]["host"] = self.redis_host_var.get()
            self.config["redis"]["port"] = int(self.redis_port_var.get())
            self.config["redis"]["db"] = int(self.redis_db_var.get())
            self.config["redis"]["channel"] = self.redis_channel_var.get()
            
            self.config["master"]["terminal_path"] = self.master_path_var.get()
            self.config["master"]["poll_interval_seconds"] = float(self.poll_interval_var.get())
            
            self.config["client"]["terminal_path"] = self.client_path_var.get()
            self.config["client"]["gold_symbol"] = self.gold_symbol_var.get()
            self.config["client"]["lot_multiplier"] = float(self.lot_multiplier_var.get())
            self.config["client"]["lot_minimum"] = float(self.lot_min_var.get())
            self.config["client"]["magic_number"] = int(self.magic_var.get())
            self.config["client"]["deviation"] = int(self.deviation_var.get())
            
            self.save_config_to_file()
            self.log("Settings saved successfully.\n")
            return True
        except ValueError as e:
            messagebox.showerror("Error", f"Invalid input format: {e}")
            return False

    def log(self, message):
        self.log_text.config(state=tk.NORMAL)
        self.log_text.insert(tk.END, message)
        self.log_text.see(tk.END)
        self.log_text.config(state=tk.DISABLED)

    def start_copytrade(self):
        if self.running:
            return
        
        # Save before running
        if not self.save_settings():
            return
        
        self.log("--- Starting Copy Trade System ---\n")
        self.running = True
        
        # Update UI state
        self.start_button.config(state=tk.DISABLED)
        self.save_button.config(state=tk.DISABLED)
        self.stop_button.config(state=tk.NORMAL)
        self.status_label.config(text="STATUS: RUNNING", fg="green")
        
        # Clear log box
        self.log_text.config(state=tk.NORMAL)
        self.log_text.delete('1.0', tk.END)
        self.log_text.config(state=tk.DISABLED)
        
        # Run master.py and client.py in background threads
        self.master_thread = threading.Thread(target=self.run_process, args=("master.py", "Master"), daemon=True)
        self.master_thread.start()
        
        self.client_thread = threading.Thread(target=self.run_process, args=("client.py", "Client"), daemon=True)
        self.client_thread.start()

    def stop_copytrade(self):
        if not self.running:
            return
            
        self.log("\n--- Stopping Copy Trade System ---\n")
        self.running = False
        
        # Terminate processes
        if self.master_process:
            try:
                self.master_process.terminate()
            except Exception:
                pass
        if self.client_process:
            try:
                self.client_process.terminate()
            except Exception:
                pass
            
        # Update UI state
        self.start_button.config(state=tk.NORMAL)
        self.save_button.config(state=tk.NORMAL)
        self.stop_button.config(state=tk.DISABLED)
        self.status_label.config(text="STATUS: STOPPED", fg="red")
        self.log("Copy trade processes terminated.\n")

    def run_process(self, script_name, prefix):
        cmd = [sys.executable, script_name]
        try:
            # Run python script in unbuffered mode (python -u) to stream logs instantly
            process = subprocess.Popen(
                [sys.executable, "-u", script_name],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                universal_newlines=True
            )
            
            if prefix == "Master":
                self.master_process = process
            else:
                self.client_process = process
                
            # Stream logs to the text widget
            for line in iter(process.stdout.readline, ''):
                if not self.running:
                    break
                self.log(f"[{prefix}] {line}")
                
            process.stdout.close()
            process.wait()
            
        except Exception as e:
            self.log(f"[{prefix}] Failed to run process: {e}\n")

    def check_processes(self):
        if self.running:
            master_alive = self.master_process and self.master_process.poll() is None
            client_alive = self.client_process and self.client_process.poll() is None
            
            if not master_alive and not client_alive:
                self.log("Both Master and Client have stopped.\n")
                self.stop_copytrade()
            elif not master_alive:
                self.log("Warning: Master monitor process stopped.\n")
            elif not client_alive:
                self.log("Warning: Client executor process stopped.\n")
                
        # Check every 1000ms (uses almost 0% CPU)
        self.root.after(1000, self.check_processes)

if __name__ == "__main__":
    root = tk.Tk()
    app = CopyTradeApp(root)
    root.mainloop()
