import os
import json
import customtkinter as ctk
from PIL import Image
import tkinter as tk
import sys

# Windows Registry for Startup
if sys.platform == 'win32':
    import winreg

class SettingsGUI(ctk.CTk):
    def __init__(self, config_path="config.json"):
        super().__init__()

        self.config_path = config_path
        self.load_config()

        # Window Setup
        self.title("Privox Settings")
        self.geometry("800x600")
        
        # Monotone Theme Setup
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue") # Overridden by custom colors
        
        # Configure Grid
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # Sidebar Navigation
        self.sidebar_frame = ctk.CTkFrame(self, width=160, corner_radius=0, fg_color="#1a1a1a")
        self.sidebar_frame.grid(row=0, column=0, sticky="nsew")
        self.sidebar_frame.grid_rowconfigure(4, weight=1)

        self.logo_label = ctk.CTkLabel(self.sidebar_frame, text="PRIVOX", font=ctk.CTkFont(size=22, weight="bold"))
        self.logo_label.grid(row=0, column=0, padx=20, pady=(30, 20))

        # Models (Focus - Row 1)
        self.btn_models = ctk.CTkButton(self.sidebar_frame, text="AI Models", command=lambda: self.select_frame("models"),
                                        fg_color="transparent", text_color="#ffffff", hover_color="#333333")
        self.btn_models.grid(row=1, column=0, sticky="ew", padx=10, pady=5)

        self.btn_general = ctk.CTkButton(self.sidebar_frame, text="General", command=lambda: self.select_frame("general"), 
                                         fg_color="transparent", text_color="#aaaaaa", hover_color="#333333")
        self.btn_general.grid(row=2, column=0, sticky="ew", padx=10, pady=5)

        self.btn_dict = ctk.CTkButton(self.sidebar_frame, text="Dictionary", command=lambda: self.select_frame("dictionary"),
                                      fg_color="transparent", text_color="#aaaaaa", hover_color="#333333")
        self.btn_dict.grid(row=3, column=0, sticky="ew", padx=10, pady=5)

        self.btn_about = ctk.CTkButton(self.sidebar_frame, text="About", command=lambda: self.select_frame("about"),
                                       fg_color="transparent", text_color="#aaaaaa", hover_color="#333333")
        self.btn_about.grid(row=5, column=0, sticky="ew", padx=10, pady=10)

        # Main Content Area
        self.content_frame = ctk.CTkFrame(self, corner_radius=0, fg_color="#121212")
        self.content_frame.grid(row=0, column=1, sticky="nsew", padx=15, pady=15)
        self.content_frame.grid_columnconfigure(0, weight=1)

        # Footer Actions
        self.save_btn = ctk.CTkButton(self, text="Save Settings", command=self.save_config,
                                      fg_color="#ffffff", text_color="#000000", hover_color="#cccccc", height=32)
        self.save_btn.place(relx=0.97, rely=0.97, anchor="se")

        # Initial Tab
        self.select_frame("models")

    def load_config(self):
        if os.path.exists(self.config_path):
            with open(self.config_path, "r", encoding="utf-8") as f:
                self.config = json.load(f)
        else:
            self.config = {
                "hotkey": "f8",
                "sound_enabled": True,
                "vram_timeout": 60,
                "whisper_model": "distil-large-v3",
                "custom_dictionary": [],
                "character": "Writing Assistant",
                "tone": "Natural",
                "dictation_prompt": ""
            }

    def save_config(self):
        # Update General
        self.config["sound_enabled"] = self.sound_check.get() == 1
        
        # Update Startup
        if sys.platform == 'win32':
            self.set_startup(self.startup_check.get() == 1)

        # Update Models
        self.config["whisper_model"] = self.model_dropdown.get()
        self.config["character"] = self.char_dropdown.get()
        self.config["tone"] = self.tone_dropdown.get()
        self.config["dictation_prompt"] = self.prompt_textbox.get("1.0", "end").strip()
        
        # Update Dictionary
        raw_dict = self.dict_textbox.get("1.0", "end").strip()
        self.config["custom_dictionary"] = [w.strip() for w in raw_dict.split(",") if w.strip()]

        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump(self.config, f, indent=4)
        
        self.destroy()

    def set_startup(self, enabled):
        key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
        app_name = "Privox"
        exe_path = sys.executable 
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_ALL_ACCESS)
            if enabled:
                winreg.SetValueEx(key, app_name, 0, winreg.REG_SZ, exe_path)
            else:
                try: winreg.DeleteValue(key, app_name)
                except FileNotFoundError: pass
            winreg.CloseKey(key)
        except Exception as e:
            print(f"Startup toggle error: {e}")

    def is_startup_enabled(self):
        if sys.platform != 'win32': return False
        key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_READ)
            winreg.QueryValueEx(key, "Privox")
            winreg.CloseKey(key)
            return True
        except: return False

    def select_frame(self, name):
        # Update sidebar
        for btn in [self.btn_general, self.btn_models, self.btn_dict, self.btn_about]:
            btn.configure(text_color="#aaaaaa")
        
        # Clear main content
        for widget in self.content_frame.winfo_children():
            widget.pack_forget()

        if name == "models":
            self.btn_models.configure(text_color="#ffffff")
            self.setup_models_tab()
        elif name == "general":
            self.btn_general.configure(text_color="#ffffff")
            self.setup_general_tab()
        elif name == "dictionary":
            self.btn_dict.configure(text_color="#ffffff")
            self.setup_dict_tab()
        elif name == "about":
            self.btn_about.configure(text_color="#ffffff")
            self.setup_about_tab()

    def setup_models_tab(self):
        tab = self.content_frame
        
        ctk.CTkLabel(tab, text="AI BRAIN & PERSONALITY", font=ctk.CTkFont(size=16, weight="bold")).pack(pady=(10, 20), anchor="w", padx=20)
        
        grid = ctk.CTkFrame(tab, fg_color="transparent")
        grid.pack(fill="x", padx=20)
        grid.columnconfigure(0, weight=1)
        grid.columnconfigure(1, weight=1)

        # Column 1: Models
        col1 = ctk.CTkFrame(grid, fg_color="transparent")
        col1.grid(row=0, column=0, sticky="nw", padx=(0, 20))
        
        ctk.CTkLabel(col1, text="ASR Backend (Inference)", font=ctk.CTkFont(weight="bold")).pack(anchor="w", pady=5)
        self.model_dropdown = ctk.CTkOptionMenu(col1, values=["distil-large-v3", "large-v3", "medium", "SenseVoice"],
                                               fg_color="#2a2a2a", button_color="#333333", button_hover_color="#444444")
        self.model_dropdown.set(self.config.get("whisper_model", "distil-large-v3"))
        self.model_dropdown.pack(fill="x")

        ctk.CTkLabel(col1, text="Character / Persona", font=ctk.CTkFont(weight="bold")).pack(anchor="w", pady=(15, 5))
        self.char_dropdown = ctk.CTkOptionMenu(col1, values=["Writing Assistant", "Code Expert", "Philosopher", "Executive Secretary", "Personal Buddy"],
                                              fg_color="#2a2a2a", button_color="#333333", button_hover_color="#444444")
        self.char_dropdown.set(self.config.get("character", "Writing Assistant"))
        self.char_dropdown.pack(fill="x")

        # Column 2: Tone
        col2 = ctk.CTkFrame(grid, fg_color="transparent")
        col2.grid(row=0, column=1, sticky="nw")
        
        ctk.CTkLabel(col2, text="Voice Tone", font=ctk.CTkFont(weight="bold")).pack(anchor="w", pady=5)
        self.tone_dropdown = ctk.CTkOptionMenu(col2, values=["Professional", "Natural", "Polite", "Casual", "Aggressive", "Concise"],
                                              fg_color="#2a2a2a", button_color="#333333", button_hover_color="#444444")
        self.tone_dropdown.set(self.config.get("tone", "Natural"))
        self.tone_dropdown.pack(fill="x")

        # Prompt Editor (Focus)
        ctk.CTkLabel(tab, text="Custom System Prompt", font=ctk.CTkFont(weight="bold")).pack(anchor="w", pady=(30, 5), padx=20)
        self.prompt_textbox = ctk.CTkTextbox(tab, height=220, fg_color="#1a1a1a", border_color="#333333", border_width=1)
        self.prompt_textbox.pack(fill="both", expand=True, padx=20, pady=(0, 20))
        
        pText = self.config.get("dictation_prompt", "")
        if not pText:
            pText = "# Default behavior is used if left blank"
        self.prompt_textbox.insert("1.0", pText)

    def setup_general_tab(self):
        tab = self.content_frame
        ctk.CTkLabel(tab, text="GENERAL SETTINGS", font=ctk.CTkFont(size=16, weight="bold")).pack(pady=(10, 20), anchor="w", padx=20)

        # Hotkey Display
        hk_frame = ctk.CTkFrame(tab, fg_color="#1a1a1a", border_width=1, border_color="#333333")
        hk_frame.pack(fill="x", padx=20, pady=10)
        
        ctk.CTkLabel(hk_frame, text="Active Recording Hotkey:", font=ctk.CTkFont(weight="bold")).pack(side="left", padx=20, pady=20)
        
        self.hk_label = ctk.CTkLabel(hk_frame, text=self.config.get("hotkey", "F8").upper(), 
                                    font=ctk.CTkFont(size=18, weight="bold"), text_color="#ffffff")
        self.hk_label.pack(side="left", padx=10)

        self.hotkey_btn = ctk.CTkButton(hk_frame, text="Record New", command=self.record_hotkey, 
                                        fg_color="#333333", hover_color="#444444", width=120)
        self.hotkey_btn.pack(side="right", padx=20)

        # Options
        opt_frame = ctk.CTkFrame(tab, fg_color="transparent")
        opt_frame.pack(fill="x", padx=20, pady=20)

        self.sound_check = ctk.CTkSwitch(opt_frame, text="Play Sound Effects (Beeps)", progress_color="#ffffff")
        self.sound_check.pack(pady=10, anchor="w")
        if self.config.get("sound_enabled", True): self.sound_check.select()

        self.startup_check = ctk.CTkSwitch(opt_frame, text="Launch Privox at Startup", progress_color="#ffffff")
        self.startup_check.pack(pady=10, anchor="w")
        if self.is_startup_enabled(): self.startup_check.select()

    def record_hotkey(self):
        self.hotkey_btn.configure(text="Listening...", state="disabled", fg_color="#555555")
        from pynput import keyboard
        def on_press(key):
            try:
                k_str = key.name if hasattr(key, 'name') else key.char
                self.config["hotkey"] = str(k_str)
                self.after(0, lambda: self.hk_label.configure(text=str(k_str).upper()))
                self.after(0, lambda: self.hotkey_btn.configure(text="Record New", state="normal", fg_color="#333333"))
                return False
            except:
                self.after(0, lambda: self.hotkey_btn.configure(text="Record New", state="normal", fg_color="#333333"))
                return False
        keyboard.Listener(on_press=on_press).start()

    def setup_dict_tab(self):
        tab = self.content_frame
        ctk.CTkLabel(tab, text="CUSTOM DICTIONARY", font=ctk.CTkFont(size=16, weight="bold")).pack(pady=(10, 20), anchor="w", padx=20)
        
        ctk.CTkLabel(tab, text="Enhance AI accuracy for specific names, terms, or brands.\nFormat: Word1, Word2, Word3...", justify="left").pack(anchor="w", padx=20, pady=(0, 10))
        
        self.dict_textbox = ctk.CTkTextbox(tab, fg_color="#1a1a1a", border_color="#333333", border_width=1)
        self.dict_textbox.pack(fill="both", expand=True, padx=20, pady=(0, 20))
        self.dict_textbox.insert("1.0", ", ".join(self.config.get("custom_dictionary", [])))

    def setup_about_tab(self):
        tab = self.content_frame
        ctk.CTkLabel(tab, text="Privox v0.1.1", font=ctk.CTkFont(size=24, weight="bold")).pack(pady=(100, 10))
        ctk.CTkLabel(tab, text="Private Local Voice Assistant", font=ctk.CTkFont(size=16)).pack(pady=5)
        
        ctk.CTkLabel(tab, text="Built for absolute privacy. Your data stays on this machine.", text_color="#777777").pack(pady=30)
        ctk.CTkLabel(tab, text="© 2026 Mark Yip", font=ctk.CTkFont(size=10), text_color="#555555").pack(side="bottom", pady=20)

if __name__ == "__main__":
    app = SettingsGUI()
    app.mainloop()
