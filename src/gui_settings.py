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
        
        # Monotone Theme Setup (MUST BE FIRST)
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.config_path = config_path
        self.load_config()

        # Window Setup
        self.title("Privox Settings")
        self.geometry("850x680")
        self.resizable(False, False)  # Show window controls in title bar
        
        # Ensure native title bar consistency
        self.configure(fg_color="#121212")
        # Transparency (Blur effect simulation via alpha)
        self.attributes("-alpha", 0.95)

        self.is_dirty = False
        self.custom_prompts = self.config.get("custom_prompts", {})
        self.last_prompt_key = f"{self.config.get('character', 'Writing Assistant')}|{self.config.get('tone', 'Natural')}"
        
        # Set Icon
        try:
            icon_path = os.path.join(os.path.dirname(self.config_path), "assets", "app_icon.ico")
            if os.path.exists(icon_path):
                self.iconbitmap(icon_path)
        except:
            pass

        self.protocol("WM_DELETE_WINDOW", self.on_closing)
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


        # Main Content Area
        self.content_frame = ctk.CTkFrame(self, corner_radius=0, fg_color="#121212")
        self.content_frame.grid(row=0, column=1, sticky="nsew", padx=15, pady=15)
        self.content_frame.grid_columnconfigure(0, weight=1)

        # Footer Actions
        # No explicit save button - using save-on-close logic

        # Version Label (lower right)
        self.version_label = ctk.CTkLabel(self, text="v1.0", font=ctk.CTkFont(size=10), text_color="#555555")
        self.version_label.place(relx=1.0, rely=1.0, anchor="se", x=-10, y=-10)
        
        # Initial Tab
        self.select_frame("models")

    def load_config(self):
        """Load from public config and hidden preferences."""
        self.config_path = os.path.join(os.path.dirname(self.config_path), "config.json")
        self.prefs_path = os.path.join(os.path.dirname(self.config_path), ".user_prefs.json")
        
        # Load Tech Config
        self.tech_config = {}
        if os.path.exists(self.config_path):
            with open(self.config_path, "r", encoding="utf-8") as f:
                self.tech_config = json.load(f)
        
        # Load User Prefs
        self.prefs = {}
        if os.path.exists(self.prefs_path):
            with open(self.prefs_path, "r", encoding="utf-8") as f:
                self.prefs = json.load(f)
        
        # Unified dictionary for GUI binding
        self.config = {**self.tech_config, **self.prefs}
        
        # Load custom_dictionary from config if not in prefs (backwards compatibility)
        if "custom_dictionary" not in self.prefs and "custom_dictionary" in self.config:
            self.prefs["custom_dictionary"] = self.config["custom_dictionary"]
        elif "custom_dictionary" not in self.prefs:
            self.prefs["custom_dictionary"] = []
        
        # Ensure libraries exist
        self.asr_library = self.tech_config.get("asr_library", [])
        self.llm_library = self.tech_config.get("llm_library", [])
        self.custom_prompts = self.prefs.get("custom_prompts", {})
        
        # Initialize prompt tracking
        char = self.config.get("character", "Writing Assistant")
        tone = self.config.get("tone", "Natural")
        self.last_prompt_key = f"{char}|{tone}"

    def save_config(self):
        """Split and save back to relevant files."""
        # Update Prefs from GUI
        self.prefs["sound_enabled"] = self.sound_check.get() == 1
        
        # Update Startup
        if sys.platform == 'win32':
            self.set_startup(self.startup_check.get() == 1)

        # Update Models/Prompts
        current_key = f"{self.char_dropdown.get()}|{self.tone_dropdown.get()}"
        self.custom_prompts[current_key] = self.prompt_textbox.get("1.0", "end").strip()
        
        # Save model selections from dropdowns
        if hasattr(self, 'asr_dropdown') and self.asr_dropdown.winfo_exists():
            self.prefs["whisper_model"] = self.asr_dropdown.get()
        if hasattr(self, 'refiner_dropdown') and self.refiner_dropdown.winfo_exists():
            self.prefs["current_refiner"] = self.refiner_dropdown.get()
        
        self.prefs["character"] = self.char_dropdown.get()
        self.prefs["tone"] = self.tone_dropdown.get()
        self.prefs["custom_prompts"] = self.custom_prompts
        
        # Dictionary is already managed by add_dict_word() and remove_dict_word()

        # Update Timeouts (with clamping and minimum values)
        try:
            v_val = int(self.vram_entry.get().strip())
            self.prefs["vram_timeout"] = max(1, min(600, v_val))  # Minimum 1
        except (ValueError, AttributeError): pass
        
        try:
            s_val = int(self.silence_entry.get().strip())
            clamped_s = max(1, min(600, s_val))  # Minimum 1 second
            self.prefs["silence_timeout_ms"] = clamped_s * 1000
        except (ValueError, AttributeError): 
            # If parsing fails, ensure we have a valid default
            if "silence_timeout_ms" not in self.prefs or self.prefs["silence_timeout_ms"] == 0:
                self.prefs["silence_timeout_ms"] = 10000  # Default 10 seconds

        # Save Hidden Prefs
        with open(self.prefs_path, "w", encoding="utf-8") as f:
            json.dump(self.prefs, f, indent=4)
            
        # Optional: update tech_config if library was modified 
        # (Though current GUI doesn't have library editor, we preserve it)
        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump(self.tech_config, f, indent=4)
        
        self.destroy()

    def set_startup(self, enabled):
        key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
        app_name = "Privox"
        exe_path = sys.executable
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_ALL_ACCESS)
            if enabled:
                # Add --autostart flag so it silently launches at Windows startup
                startup_command = f'"{exe_path}" --autostart'
                winreg.SetValueEx(key, app_name, 0, winreg.REG_SZ, startup_command)
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

    def capture_current_values(self):
        """Capture values from current tab before switching to preserve changes."""
        try:
            # Check if widgets exist before trying to get their values
            if hasattr(self, 'asr_dropdown') and self.asr_dropdown.winfo_exists():
                self.prefs["whisper_model"] = self.asr_dropdown.get()
            if hasattr(self, 'refiner_dropdown') and self.refiner_dropdown.winfo_exists():
                self.prefs["current_refiner"] = self.refiner_dropdown.get()
            if hasattr(self, 'char_dropdown') and self.char_dropdown.winfo_exists():
                self.prefs["character"] = self.char_dropdown.get()
            if hasattr(self, 'tone_dropdown') and self.tone_dropdown.winfo_exists():
                self.prefs["tone"] = self.tone_dropdown.get()
            if hasattr(self, 'prompt_textbox') and self.prompt_textbox.winfo_exists():
                # Save custom prompt for current character/tone combo
                current_text = self.prompt_textbox.get("1.0", "end-1c").strip()
                if current_text:
                    self.custom_prompts[self.last_prompt_key] = current_text
            if hasattr(self, 'vram_entry') and self.vram_entry.winfo_exists():
                try:
                    self.prefs["vram_timeout"] = max(1, int(self.vram_entry.get()))
                except: pass
            if hasattr(self, 'silence_entry') and self.silence_entry.winfo_exists():
                try:
                    # Convert seconds to milliseconds
                    s_val = int(self.silence_entry.get())
                    self.prefs["silence_timeout_ms"] = max(1000, s_val * 1000)
                except: pass
        except:
            pass  # Ignore errors during capture

    def select_frame(self, name):
        # Capture current tab values before switching
        self.capture_current_values()
        
        # Update sidebar
        for btn in [self.btn_general, self.btn_models, self.btn_dict]:
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

    def setup_models_tab(self):
        tab = self.content_frame
        
        ctk.CTkLabel(tab, text="AI MODELS", font=ctk.CTkFont(size=16, weight="bold")).pack(pady=(10, 10), anchor="w", padx=20)
        
        # 1. ASR MODEL (Voice to Text) - FIRST
        ctk.CTkLabel(tab, text="VOICE TO TEXT", font=ctk.CTkFont(size=14, weight="bold")).pack(pady=(10, 5), anchor="w", padx=20)
        
        asr_frame = ctk.CTkFrame(tab, fg_color="#1a1a1a", border_width=1, border_color="#333333")
        asr_frame.pack(fill="x", padx=20, pady=(0, 20))
        
        ctk.CTkLabel(asr_frame, text="ASR MODEL", font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=15, pady=(15, 5))
        
        asr_names = [m["name"] for m in self.asr_library]
        self.asr_dropdown = ctk.CTkOptionMenu(asr_frame, values=asr_names,
                                               fg_color="#2a2a2a", button_color="#333333", button_hover_color="#444444",
                                               command=self.on_model_change)
        self.asr_dropdown.set(self.prefs.get("whisper_model", "Premium (Distil Large v3)"))
        self.asr_dropdown.pack(fill="x", padx=15, pady=(0, 10))

        self.model_info = ctk.CTkLabel(asr_frame, text="", font=ctk.CTkFont(size=12, slant="italic"), text_color="#aaaaaa")
        self.model_info.pack(anchor="w", padx=15, pady=(0, 10))
        self.update_model_description()
        
        # 2. LLM REFINER MODEL - SECOND
        ctk.CTkLabel(tab, text="LLM REFINER", font=ctk.CTkFont(size=14, weight="bold")).pack(pady=(10, 5), anchor="w", padx=20)
        
        refiner_frame = ctk.CTkFrame(tab, fg_color="#1a1a1a", border_width=1, border_color="#333333")
        refiner_frame.pack(fill="x", padx=20, pady=(0, 20))
        
        ctk.CTkLabel(refiner_frame, text="LLM MODEL", font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=15, pady=(15, 5))
        
        # Populate from Library
        llm_names = [m["name"] for m in self.llm_library]
        self.refiner_dropdown = ctk.CTkOptionMenu(refiner_frame, values=llm_names,
                                                 fg_color="#2a2a2a", button_color="#333333", button_hover_color="#444444",
                                                 command=self.on_refiner_change)
        self.refiner_dropdown.set(self.prefs.get("current_refiner", "English Specialist (CoEdit)"))
        self.refiner_dropdown.pack(fill="x", padx=15, pady=(0, 10))
        
        self.refiner_info = ctk.CTkLabel(refiner_frame, text="", font=ctk.CTkFont(size=12, slant="italic"), text_color="#aaaaaa")
        self.refiner_info.pack(anchor="w", padx=15, pady=(0, 10))
        self.update_refiner_description()

        # 3. PERSONA & TONE - THIRD
        ctk.CTkLabel(tab, text="PERSONA & TONE", font=ctk.CTkFont(size=14, weight="bold")).pack(pady=(10, 5), anchor="w", padx=20)
        
        grid = ctk.CTkFrame(tab, fg_color="transparent")
        grid.pack(fill="x", padx=20, pady=(0, 20))
        grid.columnconfigure(0, weight=1)
        grid.columnconfigure(1, weight=1)

        # Column 1: Persona
        col1 = ctk.CTkFrame(grid, fg_color="transparent")
        col1.grid(row=0, column=0, sticky="nw", padx=(0, 20))
        
        ctk.CTkLabel(col1, text="Persona", font=ctk.CTkFont(weight="bold")).pack(anchor="w", pady=5)
        self.char_dropdown = ctk.CTkOptionMenu(col1, values=["Writing Assistant", "Code Expert", "Philosopher", "Executive Secretary", "Personal Buddy", "Custom"],
                                              fg_color="#2a2a2a", button_color="#333333", button_hover_color="#444444",
                                              command=self.on_character_tone_change)
        self.char_dropdown.set(self.config.get("character", "Writing Assistant"))
        self.char_dropdown.pack(fill="x")

        # Column 2: Tone
        col2 = ctk.CTkFrame(grid, fg_color="transparent")
        col2.grid(row=0, column=1, sticky="nw")
        
        ctk.CTkLabel(col2, text="Tone", font=ctk.CTkFont(weight="bold")).pack(anchor="w", pady=5)
        self.tone_dropdown = ctk.CTkOptionMenu(col2, values=["Professional", "Natural", "Polite", "Casual", "Aggressive", "Concise", "Custom"],
                                              fg_color="#2a2a2a", button_color="#333333", button_hover_color="#444444",
                                              command=self.on_character_tone_change)
        self.tone_dropdown.set(self.config.get("tone", "Natural"))
        self.tone_dropdown.pack(fill="x")

        # 4. CUSTOM PROMPTS - FOURTH
        ctk.CTkLabel(tab, text="CUSTOM INSTRUCTIONS", font=ctk.CTkFont(size=14, weight="bold")).pack(pady=(10, 5), anchor="w", padx=20)
        
        self.prompt_info = ctk.CTkLabel(tab, text="Persona and Tone presets are applied automatically and are hidden.", font=ctk.CTkFont(size=12, slant="italic"), text_color="#aaaaaa")
        self.prompt_info.pack(anchor="w", padx=20, pady=(0, 5))

        self.prompt_textbox = ctk.CTkTextbox(tab, height=220, fg_color="#1a1a1a", border_color="#333333", border_width=1)
        self.prompt_textbox.pack(fill="both", expand=True, padx=20, pady=(0, 20))
        self.prompt_textbox.bind("<<Modified>>", self.mark_dirty)
        
        # Load initial prompt for current combination
        self.refresh_prompt_editor()

    def on_character_tone_change(self, choice):
        self.mark_dirty()
        
        # Save current text to the last known key
        if hasattr(self, 'prompt_textbox'):
            current_text = self.prompt_textbox.get("1.0", "end").strip()
            # Only save if it's not the generic placeholder or default
            if current_text and not current_text.startswith("#"):
                self.custom_prompts[self.last_prompt_key] = current_text
            
            # Update key and refresh
            self.last_prompt_key = f"{self.char_dropdown.get()}|{self.tone_dropdown.get()}"
            self.refresh_prompt_editor()

    def refresh_prompt_editor(self):
        if not hasattr(self, 'prompt_textbox'):
            return
            
        self.prompt_textbox.delete("1.0", "end")
        
        char = self.char_dropdown.get()
        tone = self.tone_dropdown.get()
        key = f"{char}|{tone}"
        
        # Show status info
        if char == "Custom" or tone == "Custom":
            self.prompt_info.configure(text="CLEAN SLATE: System presets are bypassed for 'Custom' selections.")
        else:
            self.prompt_info.configure(text=f"HYBRID: System '{char}' and '{tone}' rules are active but hidden.")

        # Load user rules
        pText = self.custom_prompts.get(key, "")
        if not pText:
            pText = "" # Start empty for user rules
            
        self.prompt_textbox.insert("1.0", pText)
        self.prompt_textbox.edit_modified(False)

    def on_refiner_change(self, choice):
        self.mark_dirty()
        self.update_refiner_description()
    
    def on_model_change(self, choice):
        self.mark_dirty()
        self.update_model_description()

    def update_refiner_description(self):
        choice = self.refiner_dropdown.get()
        desc = None
        for m in self.llm_library:
            if m["name"] == choice:
                desc = m.get("description", None)
                break
        
        if desc:
            self.refiner_info.configure(text=desc)
            self.refiner_info.pack(anchor="w", padx=15, pady=(0, 10))
        else:
            self.refiner_info.pack_forget()

    def update_model_description(self):
        """Update ASR model description label."""
        if not hasattr(self, 'asr_dropdown'):
            return
        selected_name = self.asr_dropdown.get()
        for model in self.asr_library:
            if model["name"] == selected_name:
                desc = model.get("description", "").strip()
                if desc:
                    self.model_info.configure(text=desc)
                    self.model_info.pack(anchor="w", padx=15, pady=(0, 10))
                else:
                    self.model_info.pack_forget()
                return
        # If not found, hide
        self.model_info.pack_forget()

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

        self.sound_check = ctk.CTkSwitch(opt_frame, text="Play Sound Effects (Beeps)", progress_color="#ffffff", command=self.mark_dirty)
        self.sound_check.pack(pady=10, anchor="w")
        if self.config.get("sound_enabled", True): self.sound_check.select()

        self.startup_check = ctk.CTkSwitch(opt_frame, text="Launch Privox at Startup", progress_color="#ffffff", command=self.mark_dirty)
        self.startup_check.pack(pady=10, anchor="w")
        if self.is_startup_enabled(): self.startup_check.select()

        # Advanced Timeouts
        ctk.CTkLabel(tab, text="ADVANCED TIMEOUTS", font=ctk.CTkFont(size=14, weight="bold")).pack(pady=(30, 5), anchor="w", padx=20)
        
        timeout_grid = ctk.CTkFrame(tab, fg_color="transparent")
        timeout_grid.pack(fill="x", padx=20)
        timeout_grid.columnconfigure(0, weight=1)
        timeout_grid.columnconfigure(1, weight=1)
        
        # Validation for numeric input
        vcmd = (self.register(self.validate_int), '%P')

        # VRAM Timeout
        vt_frame = ctk.CTkFrame(timeout_grid, fg_color="transparent")
        vt_frame.grid(row=0, column=0, sticky="nw", padx=(0, 10))
        ctk.CTkLabel(vt_frame, text="VRAM Saver (Seconds):", font=ctk.CTkFont(size=12)).pack(anchor="w")
        self.vram_entry = ctk.CTkEntry(vt_frame, width=120, fg_color="#1a1a1a", border_color="#333333", validate="key", validatecommand=vcmd)
        self.vram_entry.pack(anchor="w", pady=5)
        self.vram_entry.insert(0, str(self.config.get("vram_timeout", 60)))
        
        # Silence Timeout
        st_frame = ctk.CTkFrame(timeout_grid, fg_color="transparent")
        st_frame.grid(row=0, column=1, sticky="nw", padx=(10, 0))
        ctk.CTkLabel(st_frame, text="Silence Auto-Stop (Seconds):", font=ctk.CTkFont(size=12)).pack(anchor="w")
        self.silence_entry = ctk.CTkEntry(st_frame, width=120, fg_color="#1a1a1a", border_color="#333333", validate="key", validatecommand=vcmd)
        self.silence_entry.pack(anchor="w", pady=5)
        
        # Load from prefs (stored as ms, show as seconds)
        # Use self.prefs instead of self.config to preserve tab-switching changes
        s_ms = self.prefs.get("silence_timeout_ms", self.config.get("silence_timeout_ms", 10000))
        self.silence_entry.insert(0, str(int(s_ms / 1000)))

    def validate_int(self, p):
        if p == "" or p.isdigit():
            self.mark_dirty()
            return True
        return False


    def mark_dirty(self, *args):
        self.is_dirty = True

    def on_closing(self):
        """Handle window close event - only show dialog if changes exist."""
        if self.is_dirty:
            # Capture any unsaved values from current tab
            self.capture_current_values()
            
            # Minimalistic monotone dialog
            dialog = ctk.CTkToplevel(self)
            dialog.title("Privox Settings")
            dialog.geometry("400x160")
            dialog.resizable(False, False)
            dialog.transient(self)
            dialog.grab_set()
            dialog.configure(fg_color="#1a1a1a")
            
            # Set dialog icon
            try:
                icon_path = os.path.join(os.path.dirname(self.config_path), "assets", "app_icon.ico")
                if os.path.exists(icon_path):
                    dialog.iconbitmap(icon_path)
            except:
                pass
            
            # Center on parent
            dialog.update_idletasks()
            x = self.winfo_x() + (self.winfo_width() // 2) - (dialog.winfo_width() // 2)
            y = self.winfo_y() + (self.winfo_height() // 2) - (dialog.winfo_height() // 2)
            dialog.geometry(f"+{x}+{y}")
            
            # Monotone design with consistent spacing
            ctk.CTkLabel(dialog, text="Unsaved Changes", 
                        font=ctk.CTkFont(size=14, weight="bold"),
                        text_color="#ffffff").pack(pady=(25, 10))
            ctk.CTkLabel(dialog, text="Save changes before closing?", 
                        font=ctk.CTkFont(size=11), 
                        text_color="#888888").pack(pady=(0, 20))
            
            btn_frame = ctk.CTkFrame(dialog, fg_color="transparent")
            btn_frame.pack(pady=10)
            
            def confirm_save():
                dialog.destroy()
                self.save_config()
                self.destroy()  # Only close settings window
            
            def leave_without_saving():
                dialog.destroy()
                self.destroy()  # Only close settings window
            
            def continue_editing():
                dialog.destroy()
            
            # Monotone button design
            ctk.CTkButton(btn_frame, text="Save", width=100, command=confirm_save,
                         fg_color="#333333", hover_color="#444444",
                         border_width=1, border_color="#555555").pack(side="left", padx=5)
            ctk.CTkButton(btn_frame, text="Don't Save", width=100, command=leave_without_saving,
                         fg_color="#2a2a2a", hover_color="#333333",
                         border_width=1, border_color="#444444").pack(side="left", padx=5)
            ctk.CTkButton(btn_frame, text="Cancel", width=100, command=continue_editing,
                         fg_color="#2a2a2a", hover_color="#333333",
                         border_width=1, border_color="#444444").pack(side="left", padx=5)
            
            dialog.wait_window()
        else:
            # No changes, close directly
            self.destroy()  # Only close settings window, not the main app

    def record_hotkey(self):
        self.hotkey_btn.configure(text="Press Key Combo...", state="disabled", fg_color="#555555")
        
        from pynput import keyboard
        current_keys = set()
        pressed_keys_order = []
        
        def on_press(key):
            try:
                # Get clean name
                k_name = key.name if hasattr(key, 'name') else key.char
                if k_name and k_name not in current_keys:
                    current_keys.add(k_name.lower())
                    pressed_keys_order.append(k_name.lower())
            except:
                pass
                
        def on_release(key):
            try:
                if current_keys:
                    # Build combo string
                    combo_str = "+".join(pressed_keys_order).upper()
                    self.prefs["hotkey"] = combo_str.lower()
                    self.after(0, lambda: self.hk_label.configure(text=combo_str))
                    self.after(0, lambda: self.hotkey_btn.configure(text="Record New", state="normal", fg_color="#333333"))
                    self.mark_dirty()
                    return False  # Stop listener
            except:
                self.after(0, lambda: self.hotkey_btn.configure(text="Record New", state="normal", fg_color="#333333"))
                return False

        listener = keyboard.Listener(on_press=on_press, on_release=on_release)
        listener.start()


    def setup_dict_tab(self):
        tab = self.content_frame
        ctk.CTkLabel(tab, text="CUSTOM DICTIONARY", font=ctk.CTkFont(size=16, weight="bold")).pack(pady=(10, 20), anchor="w", padx=20)
        
        ctk.CTkLabel(tab, text="Enhance AI accuracy for specific names, terms, or brands.", justify="left").pack(anchor="w", padx=20, pady=(0, 10))
        
        # Add Input
        add_frame = ctk.CTkFrame(tab, fg_color="transparent")
        add_frame.pack(fill="x", padx=20, pady=10)
        
        self.new_word_entry = ctk.CTkEntry(add_frame, placeholder_text="Enter new word...", fg_color="#1a1a1a", border_color="#333333")
        self.new_word_entry.pack(side="left", fill="x", expand=True, padx=(0, 10))
        # Bind Enter key to add action
        self.new_word_entry.bind("<Return>", lambda e: self.add_dict_word())
        
        ctk.CTkButton(add_frame, text="Add", width=60, fg_color="#333333", hover_color="#444444", command=self.add_dict_word).pack(side="right")

        # Word List Scrollable Frame
        self.dict_frame = ctk.CTkScrollableFrame(tab, fg_color="#1a1a1a", border_color="#333333", border_width=1,
                                                 scrollbar_button_color="transparent", scrollbar_button_hover_color="transparent")
        self.dict_frame.pack(fill="both", expand=True, padx=20, pady=(10, 20))
        
        self.refresh_dict_list()

    def add_dict_word(self):
        word = self.new_word_entry.get().strip()
        if word:
            words = self.prefs.get("custom_dictionary", [])
            if word not in words:
                words.append(word)
                self.prefs["custom_dictionary"] = words
                self.new_word_entry.delete(0, 'end')
                self.refresh_dict_list()
                self.mark_dirty()

    def remove_dict_word(self, word):
        words = self.prefs.get("custom_dictionary", [])
        if word in words:
            words.remove(word)
            self.prefs["custom_dictionary"] = words
            self.refresh_dict_list()
            self.mark_dirty()

    def refresh_dict_list(self):
        for widget in self.dict_frame.winfo_children():
            widget.destroy()
            
        words = self.prefs.get("custom_dictionary", [])
        for word in words:
            row = ctk.CTkFrame(self.dict_frame, fg_color="transparent")
            row.pack(fill="x", pady=2)
            
            ctk.CTkLabel(row, text=word, text_color="#ffffff").pack(side="left", padx=10)
            ctk.CTkButton(row, text="×", width=20, height=20, fg_color="transparent", text_color="#ff5555", hover_color="#333333", 
                          command=lambda w=word: self.remove_dict_word(w)).pack(side="right", padx=5)

    def setup_about_tab(self):
        tab = self.content_frame
        ctk.CTkLabel(tab, text="Privox v0.1.1", font=ctk.CTkFont(size=24, weight="bold")).pack(pady=(50, 10))
        ctk.CTkLabel(tab, text="Private Local Voice Assistant", font=ctk.CTkFont(size=16)).pack(pady=5)
        
        ctk.CTkLabel(tab, text="Built for absolute privacy. Your data stays on this machine.", text_color="#777777").pack(pady=20)
        
        # Advertisement Placeholder
        ad_frame = ctk.CTkFrame(tab, fg_color="#1a1a1a", border_width=1, border_color="#333333")
        ad_frame.pack(fill="x", padx=40, pady=20)
        
        ctk.CTkLabel(ad_frame, text="Privacy is a right, not a luxury.", font=ctk.CTkFont(slant="italic")).pack(pady=(15, 5))
        ctk.CTkLabel(ad_frame, text="Check out Privox Mobile on the App Store", text_color="#3a86ff").pack(pady=(0, 15))
        
        ctk.CTkLabel(tab, text="© 2026 Mark Yip", font=ctk.CTkFont(size=10), text_color="#555555").pack(side="bottom", pady=20)

if __name__ == "__main__":
    app = SettingsGUI()
    app.mainloop()
