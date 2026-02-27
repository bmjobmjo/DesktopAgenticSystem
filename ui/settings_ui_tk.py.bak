"""Settings UI for configuring LLM, directories, agents, roles, and users."""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, filedialog, ttk
from tkinter import scrolledtext
import json
import sqlite3
import re
from typing import List, Tuple, Any, Dict
from pathlib import Path

from core.common_data_area import CommonDataArea
from settings import config_loader
from agents.registry import list_agents, register_agent, get_agent, _get_db_path
from tools.tool_registry import list_tools

class SettingsPanel(ttk.Frame):
    def __init__(self, parent: tk.Widget, cda: CommonDataArea | None = None) -> None:
        super().__init__(parent)
        self.cda = cda or CommonDataArea()
        
        # --- DARK MODERN THEME CONFIGURATION ---
        bg_color = '#2b2b2b'
        fg_color = '#a9b7c6'
        accent_color = '#3c3f41'
        select_bg = '#4b6eaf'
        
        style = ttk.Style(self)
        try:
            style.theme_use('clam')
        except:
            pass
        
        # General Widget Styles (Re-applied for safety, though global)
        style.configure('.', background=bg_color, foreground=fg_color, font=('Segoe UI', 10))
        style.configure('TFrame', background=bg_color)
        style.configure('TLabel', background=bg_color, foreground=fg_color)
        style.configure('TLabelframe', background=bg_color, foreground=fg_color, relief='groove')
        style.configure('TLabelframe.Label', background=bg_color, foreground=fg_color, font=('Segoe UI', 10, 'bold'))
        
        # Button Styles
        style.configure('TButton', background=accent_color, foreground='white', borderwidth=0, focuscolor=select_bg)
        style.map('TButton', background=[('active', select_bg)], relief=[('pressed', 'sunken')])
        
        style.configure('Accent.TButton', background='#365880', font=('Segoe UI', 10, 'bold'))
        style.map('Accent.TButton', background=[('active', '#4b6eaf')])
        
        # Entry & Combobox
        style.configure('TEntry', fieldbackground=accent_color, foreground='white', insertcolor='white')
        style.configure('TCombobox', fieldbackground=accent_color, foreground='white', arrowcolor='white')
        
        # Notebook (Tabs)
        style.configure('TNotebook', background=bg_color, tabposition='nw')
        style.configure('TNotebook.Tab', background=accent_color, foreground='white', padding=[15, 5], font=('Segoe UI', 10))
        style.map('TNotebook.Tab', background=[('selected', select_bg)], expand=[('selected', [1, 1, 1, 0])])
        
        # Treeview
        style.configure('Treeview', background=accent_color, foreground=fg_color, fieldbackground=accent_color, rowheight=25, borderwidth=0)
        style.configure('Treeview.Heading', background='#323232', foreground='white', font=('Segoe UI', 10, 'bold'), relief='flat')
        style.map('Treeview.Heading', background=[('active', '#3c3f41')])
        style.map('Treeview', background=[('selected', select_bg)], foreground=[('selected', 'white')])
        
        self.settings = config_loader.load_settings()
        if 'debug_mode' not in self.settings:
            self.settings['debug_mode'] = False
            config_loader.save_settings(self.settings)
        # Ensure persisted active user context is present in CDA on panel load.
        if self.settings.get('current_user_id') is not None:
            self.cda.set_setting('current_user_id', str(self.settings.get('current_user_id')))
        if self.settings.get('current_username') is not None:
            self.cda.set_setting('current_username', self.settings.get('current_username'))
        if self.settings.get('current_user_email') is not None:
            self.cda.set_setting('current_user_email', self.settings.get('current_user_email'))
        self.db_path = _get_db_path()
        self._ensure_agent_tools_schema()

        # Layout (self is now the Frame)
        main_frame = ttk.Frame(self, padding=10)
        main_frame.pack(fill='both', expand=True)

        # Create Notebook for Tabs
        self.notebook = ttk.Notebook(main_frame)
        self.notebook.pack(fill='both', expand=True)

        self._create_general_tab()
        self._create_ai_tab()
        self._create_agents_tab()
        self._create_roles_tab()
        self._create_users_tab()
        self._create_tools_tab()

    def _get_conn(self):
        return sqlite3.connect(str(self.db_path))

    def _ensure_agent_tools_schema(self) -> None:
        conn = self._get_conn()
        try:
            cur = conn.cursor()
            cur.execute("""
                CREATE TABLE IF NOT EXISTS AgentTools (
                    agent_id INTEGER NOT NULL,
                    tool_name TEXT NOT NULL,
                    PRIMARY KEY (agent_id, tool_name)
                )
            """)
            conn.commit()
        finally:
            conn.close()

    # ==========================
    # GENERAL TAB
    # ==========================
    # ==========================
    # GENERAL TAB
    # ==========================
    def _create_general_tab(self) -> None:
        tab = ttk.Frame(self.notebook, padding=20)
        self.notebook.add(tab, text='System Settings')

        # Keep save actions always visible at the bottom.
        action_bar = ttk.Frame(tab)
        action_bar.pack(side='bottom', fill='x', pady=(10, 0))
        ttk.Button(action_bar, text='Save & Apply Changes', command=self._save_general, style='Accent.TButton').pack(anchor='e')

        # --- Database Configuration Section ---
        lbl = ttk.Label(tab, text="Data Storage", style='Heading.TLabel')
        lbl.pack(anchor='w', pady=(0, 10))
        
        frame_db = ttk.LabelFrame(tab, text="Database Connection", padding=15)
        frame_db.pack(fill='x', pady=5)
        
        ttk.Label(frame_db, text='SQLite Database Path:', font=('Segoe UI', 9, 'bold')).pack(anchor='w')
        db_frame = ttk.Frame(frame_db)
        db_frame.pack(fill='x', pady=5)
        
        self.db_path_var = tk.StringVar(value=self.settings.get('sqlite_db_path', 'backend.db'))
        ttk.Entry(db_frame, textvariable=self.db_path_var).pack(side='left', fill='x', expand=True)
        ttk.Button(db_frame, text="Browse...", command=self._browse_db).pack(side='left', padx=(5, 0))

        # File Storage
        frame_storage = ttk.LabelFrame(tab, text="Attachment Storage", padding=15)
        frame_storage.pack(fill='x', pady=5)
        ttk.Label(frame_storage, text='File Storage Path:', font=('Segoe UI', 9, 'bold')).pack(anchor='w')
        storage_inner = ttk.Frame(frame_storage)
        storage_inner.pack(fill='x', pady=5)
        self.storage_path_var = tk.StringVar(value=self.settings.get('file_storage_path', 'storage/files'))
        ttk.Entry(storage_inner, textvariable=self.storage_path_var).pack(side='left', fill='x', expand=True)
        ttk.Button(storage_inner, text="Browse...", command=self._browse_storage).pack(side='left', padx=(5, 0))
        ttk.Label(frame_storage, text='Uploaded/Ingested files will be moved to this folder.', font=('Segoe UI', 8), foreground='#666').pack(anchor='w')

        # --- Debug Controls ---
        lbl = ttk.Label(tab, text="Execution Debugging", style='Heading.TLabel')
        lbl.pack(anchor='w', pady=(20, 10))
        frame_debug = ttk.LabelFrame(tab, text="Step Approval Mode", padding=15)
        frame_debug.pack(fill='x', pady=5)
        self.debug_mode_var = tk.BooleanVar(value=bool(self.settings.get('debug_mode', False)))
        ttk.Checkbutton(
            frame_debug,
            text='Enable debug approvals (ask permission for each tool/LLM step)',
            variable=self.debug_mode_var,
            command=self._toggle_debug_mode
        ).pack(anchor='w')

        # --- Environment Section ---
        lbl = ttk.Label(tab, text="Environment Constraints", style='Heading.TLabel')
        lbl.pack(anchor='w', pady=(20, 10))
        
        frame_env = ttk.LabelFrame(tab, text="File System Access", padding=15)
        frame_env.pack(fill='both', expand=True, pady=5)

        ttk.Label(frame_env, text='Default Working Directory:', font=('Segoe UI', 9, 'bold')).pack(anchor='w')
        self.default_dir_var = tk.StringVar(value=self.settings.get('default_directory', ''))
        ttk.Entry(frame_env, textvariable=self.default_dir_var, width=60).pack(fill='x', pady=5)
        
        ttk.Label(frame_env, text='Whitelisted Directories (Security Sandbox):', font=('Segoe UI', 9, 'bold')).pack(anchor='w', pady=(10, 0))
        self.accessible_text = tk.Text(frame_env, height=6, font=('Consolas', 9), relief='flat', borderwidth=1, padx=5, pady=5)
        self.accessible_text.config(highlightbackground='#3c3f41', highlightthickness=1, bg='#2b2b2b', fg='#a9b7c6', insertbackground='white')
        self.accessible_text.pack(fill='both', expand=True, pady=5)
        dirs = self.settings.get('accessible_directories', []) or []
        self.accessible_text.insert('1.0', '\n'.join(dirs))

    # ==========================
    # AI CONFIGURATION TAB
    # ==========================
    def _create_ai_tab(self) -> None:
        tab = ttk.Frame(self.notebook, padding=20)
        self.notebook.add(tab, text='AI Configuration')

        # Provider Selection
        lbl = ttk.Label(tab, text="LLM Configuration", style='Heading.TLabel')
        lbl.pack(anchor='w', pady=(0, 10))
        
        frame_prov = ttk.LabelFrame(tab, text="Active LLM Provider", padding=15)
        frame_prov.pack(fill='x', pady=5)
        
        self.llm_provider_var = tk.StringVar(value=self.settings.get('llm_provider', 'gemini'))
        prov_frame = ttk.Frame(frame_prov)
        prov_frame.pack(fill='x')
        ttk.Radiobutton(prov_frame, text="Google Gemini", variable=self.llm_provider_var, value='gemini', command=self._on_provider_change).pack(side='left', padx=10)
        ttk.Radiobutton(prov_frame, text="Local LLM (LM Studio/Ollama)", variable=self.llm_provider_var, value='local', command=self._on_provider_change).pack(side='left', padx=10)
        ttk.Radiobutton(prov_frame, text="OpenRouter", variable=self.llm_provider_var, value='openrouter', command=self._on_provider_change).pack(side='left', padx=10)

        # Container for conditional frames
        self.ai_settings_container = ttk.Frame(tab)
        self.ai_settings_container.pack(fill='both', expand=True, pady=10)

        # --- Gemini Section ---
        self.gemini_subframe = ttk.LabelFrame(self.ai_settings_container, text="Google Gemini Settings", padding=15)
        
        ttk.Label(self.gemini_subframe, text='Gemini API Key:', font=('Segoe UI', 9, 'bold')).pack(anchor='w')
        self.api_key_var = tk.StringVar(value=self.settings.get('gemini_api_key', ''))
        ttk.Entry(self.gemini_subframe, textvariable=self.api_key_var, show='•', width=60).pack(fill='x', pady=(5, 10))
        
        ttk.Label(self.gemini_subframe, text='Model Selection:', font=('Segoe UI', 9, 'bold')).pack(anchor='w')
        self.gemini_model_var = tk.StringVar(value=self.settings.get('gemini_model', 'gemini-1.5-flash'))
        gemini_models = [
            'gemini-3-flash-preview',
            'gemini-2.5-flash',
            'gemini-2.5-flash-lite',
            'gemini-2.5-flash-lite-preview-09-2025',
            'gemini-2.0-flash',
            'gemini-2.0-flash-lite',
            'Gemma 3',
            'Gemma 3n'
        ]
        self.gemini_model_combo = ttk.Combobox(self.gemini_subframe, textvariable=self.gemini_model_var, values=gemini_models, state='readonly')
        self.gemini_model_combo.pack(fill='x', pady=(5, 10))

        ttk.Label(self.gemini_subframe, text='Temperature (0.0 = Precise, 1.0 = Creative):', font=('Segoe UI', 9, 'bold')).pack(anchor='w')
        self.temp_var = tk.DoubleVar(value=self.settings.get('gemini_temperature', 0.0))
        temp_scale = tk.Scale(self.gemini_subframe, from_=0.0, to=1.0, resolution=0.1, orient='horizontal', variable=self.temp_var, 
                              bg='#2b2b2b', fg='white', highlightthickness=0, troughcolor='#3c3f41', activebackground='#4b6eaf')
        temp_scale.pack(fill='x', pady=(0, 10))

        # --- Local LLM Section ---
        self.local_subframe = ttk.LabelFrame(self.ai_settings_container, text="Local LLM Settings (OpenAI Compatible)", padding=15)
        
        ttk.Label(self.local_subframe, text='Local LLM Endpoint URL:', font=('Segoe UI', 9, 'bold')).pack(anchor='w')
        self.local_url_var = tk.StringVar(value=self.settings.get('local_llm_url', 'http://127.0.0.1:1234/v1'))
        ttk.Entry(self.local_subframe, textvariable=self.local_url_var, width=60).pack(fill='x', pady=(5, 10))
        
        ttk.Label(self.local_subframe, text='Model ID:', font=('Segoe UI', 9, 'bold')).pack(anchor='w')
        self.local_model_var = tk.StringVar(value=self.settings.get('local_llm_model', 'qwen2.5-14b-instruct-1m'))
        ttk.Entry(self.local_subframe, textvariable=self.local_model_var, width=60).pack(fill='x', pady=(5, 10))

        # --- OpenRouter Section ---
        self.openrouter_subframe = ttk.LabelFrame(self.ai_settings_container, text="OpenRouter Settings", padding=15)
        
        ttk.Label(self.openrouter_subframe, text='OpenRouter API Key:', font=('Segoe UI', 9, 'bold')).pack(anchor='w')
        self.openrouter_api_key_var = tk.StringVar(value=self.settings.get('openrouter_api_key', ''))
        ttk.Entry(self.openrouter_subframe, textvariable=self.openrouter_api_key_var, show='•', width=60).pack(fill='x', pady=(5, 10))
        
        ttk.Label(self.openrouter_subframe, text='Model ID:', font=('Segoe UI', 9, 'bold')).pack(anchor='w')
        self.openrouter_model_var = tk.StringVar(value=self.settings.get('openrouter_model', 'stepfun/step-3.5-flash'))
        ttk.Entry(self.openrouter_subframe, textvariable=self.openrouter_model_var, width=60).pack(fill='x', pady=(5, 10))

        # Initial visibility
        self._on_provider_change()

        # Save Button for AI Tab
        btn_save = ttk.Button(tab, text='Save AI Settings', command=self._save_general, style='Accent.TButton')
        btn_save.pack(anchor='e', pady=10)

    def _on_provider_change(self):
        provider = self.llm_provider_var.get()
        if provider == 'gemini':
            self.gemini_subframe.pack(fill='x', pady=5)
            self.local_subframe.pack_forget()
            self.openrouter_subframe.pack_forget()
        elif provider == 'local':
            self.local_subframe.pack(fill='x', pady=5)
            self.gemini_subframe.pack_forget()
            self.openrouter_subframe.pack_forget()
        elif provider == 'openrouter':
            self.openrouter_subframe.pack(fill='x', pady=5)
            self.gemini_subframe.pack_forget()
            self.local_subframe.pack_forget()

    def _browse_db(self):
        filename = filedialog.askopenfilename(title="Select Database File", filetypes=[("SQLite DB", "*.db"), ("All Files", "*.*")])
        if filename:
            self.db_path_var.set(filename)

    def _browse_storage(self):
        directory = filedialog.askdirectory(title="Select Storage Directory")
        if directory:
            self.storage_path_var.set(directory)

    def _toggle_debug_mode(self):
        self.settings['debug_mode'] = bool(self.debug_mode_var.get())
        config_loader.save_settings(self.settings)
        self.cda.set_setting('debug_mode', self.settings['debug_mode'])

    def _save_general(self):
        self.settings['llm_provider'] = self.llm_provider_var.get()
        self.settings['gemini_api_key'] = self.api_key_var.get().strip()
        self.settings['gemini_model'] = self.gemini_model_var.get().strip()
        self.settings['gemini_temperature'] = float(self.temp_var.get())
        self.settings['local_llm_url'] = self.local_url_var.get().strip()
        self.settings['local_llm_model'] = self.local_model_var.get().strip()
        self.settings['openrouter_api_key'] = self.openrouter_api_key_var.get().strip()
        self.settings['openrouter_model'] = self.openrouter_model_var.get().strip()
        self.settings['default_directory'] = self.default_dir_var.get().strip()
        self.settings['sqlite_db_path'] = self.db_path_var.get().strip()
        self.settings['file_storage_path'] = self.storage_path_var.get().strip()
        self.settings['debug_mode'] = bool(self.debug_mode_var.get())
        
        raw_dirs = self.accessible_text.get('1.0', 'end').strip()
        self.settings['accessible_directories'] = [d.strip() for d in raw_dirs.splitlines() if d.strip()]
        
        config_loader.save_settings(self.settings)
        
        # 1. Update CDA settings
        for k, v in self.settings.items():
            self.cda.set_setting(k, v)
            
        # 2. SEAMLESS SWITCHING: Refresh the runtime LLM client
        try:
            from llm.factory import get_llm_client
            new_client = get_llm_client(self.cda)
            self.cda.set_runtime('llm_client', new_client)
            print(f"[SETTINGS] Refreshed LLM client to {self.settings['llm_provider']}")
        except Exception as e:
            messagebox.showwarning("AI Re-init Warning", f"Settings saved, but failed to re-initialize AI client: {e}")

        messagebox.showinfo("Configuration Updated", "System settings have been successfully applied.")

    # ==========================
    # AGENTS TAB
    # ==========================
    def _create_agents_tab(self):
        tab = ttk.Frame(self.notebook, padding=15)
        self.notebook.add(tab, text='Agent Management')

        header = ttk.Frame(tab)
        header.pack(fill='x', pady=(0, 10))
        ttk.Label(header, text="Agent Management", style='Heading.TLabel').pack(side='left')
        ttk.Button(header, text="Refresh", command=self._refresh_agents).pack(side='right')

        # Split: Left List, Right Details
        paned = ttk.PanedWindow(tab, orient='horizontal')
        paned.pack(fill='both', expand=True)

        # Left: List
        frame_list = ttk.Frame(paned, padding=(0,0,10,0))
        paned.add(frame_list, weight=1)
        
        ttk.Label(frame_list, text="Registered Agents", style='Heading.TLabel').pack(anchor='w', pady=(0, 5))
        
        columns = ('name',)
        self.agent_tree = ttk.Treeview(frame_list, columns=columns, show='headings', selectmode='browse', height=15)
        self.agent_tree.heading('name', text='Agent Name')
        self.agent_tree.pack(fill='both', expand=True)
        self.agent_tree.bind('<<TreeviewSelect>>', self._on_agent_select)
        
        btn_frame = ttk.Frame(frame_list)
        btn_frame.pack(fill='x', pady=10)
        ttk.Button(btn_frame, text="+ New Agent", command=self._new_agent).pack(side='left', fill='x', expand=True)

        # Right: Details
        frame_detail = ttk.LabelFrame(paned, text="Agent Configuration", padding=15)
        paned.add(frame_detail, weight=3)
        action_bar = ttk.Frame(frame_detail)
        action_bar.pack(side='bottom', fill='x', pady=(8, 0))
        ttk.Button(action_bar, text="Save Agent Configuration", command=self._save_agent, style='Accent.TButton').pack(anchor='e')

        ttk.Label(frame_detail, text="Agent Name:", font=('Segoe UI', 9, 'bold')).pack(anchor='w')
        self.agent_name_var = tk.StringVar()
        ttk.Entry(frame_detail, textvariable=self.agent_name_var, width=40).pack(fill='x', pady=(5, 15))

        ttk.Label(frame_detail, text="Functional Description:", font=('Segoe UI', 9, 'bold')).pack(anchor='w')
        self.agent_desc_var = tk.StringVar()
        ttk.Entry(frame_detail, textvariable=self.agent_desc_var, width=60).pack(fill='x', pady=(5, 15))

        ttk.Label(frame_detail, text="System Prompt (Defines Behavior):", font=('Segoe UI', 9, 'bold')).pack(anchor='w')
        self.agent_prompt_text = scrolledtext.ScrolledText(frame_detail, height=20, font=('Consolas', 10), state='normal', padx=5, pady=5)
        self.agent_prompt_text.config(bg='#2b2b2b', fg='#a9b7c6', insertbackground='white', relief='flat', highlightbackground='#3c3f41', highlightthickness=1)
        self.agent_prompt_text.pack(fill='both', expand=True, pady=(5, 15))

        ttk.Label(frame_detail, text="Assigned Tools (only these will be available to this agent):", font=('Segoe UI', 9, 'bold')).pack(anchor='w', pady=(0, 5))
        self.agent_tools_frame = ttk.Frame(frame_detail, relief='sunken', borderwidth=1)
        self.agent_tools_frame.pack(fill='both', expand=False, pady=(0, 15))
        self.agent_tools_canvas = tk.Canvas(self.agent_tools_frame, height=120, highlightthickness=0, bg='#2b2b2b')
        self.agent_tools_scrollbar = ttk.Scrollbar(self.agent_tools_frame, orient='vertical', command=self.agent_tools_canvas.yview)
        self.agent_tools_inner = ttk.Frame(self.agent_tools_canvas)
        self.agent_tools_inner.bind(
            "<Configure>",
            lambda e: self.agent_tools_canvas.configure(scrollregion=self.agent_tools_canvas.bbox("all"))
        )
        self.agent_tools_canvas.create_window((0, 0), window=self.agent_tools_inner, anchor='nw')
        self.agent_tools_canvas.configure(yscrollcommand=self.agent_tools_scrollbar.set)
        self.agent_tools_canvas.pack(side='left', fill='both', expand=True)
        self.agent_tools_scrollbar.pack(side='right', fill='y')
        self.agent_tool_vars: Dict[str, tk.IntVar] = {}
        self._refresh_agent_tools_panel()

        self._refresh_agents()

    def _refresh_agents(self):
        self.agent_tree.delete(*self.agent_tree.get_children())
        # Use registry to ensure built-ins are seeded before listing.
        agents = sorted(list_agents(return_all=True), key=lambda a: a.get('name', ''))
        for agent in agents:
            self.agent_tree.insert('', 'end', values=(agent['name'],))

    def _on_agent_select(self, event):
        sel = self.agent_tree.selection()
        if not sel: return
        name = self.agent_tree.item(sel[0])['values'][0]
        
        # Load from DB
        try:
            agent = get_agent(name)
            self.agent_name_var.set(agent['name'])
            self.agent_desc_var.set(agent['description'])
            self.agent_prompt_text.delete('1.0', 'end')
            if agent.get('prompt_content'):
                self.agent_prompt_text.insert('1.0', agent['prompt_content'])
            self._load_agent_tool_assignments(name)
        except Exception as e:
            print(f"Error loading agent: {e}")

    def _new_agent(self):
        self.agent_tree.selection_remove(self.agent_tree.selection())
        self.agent_name_var.set("")
        self.agent_desc_var.set("")
        self.agent_prompt_text.delete('1.0', 'end')
        for var in self.agent_tool_vars.values():
            var.set(0)

    def _refresh_agent_tools_panel(self) -> None:
        for w in self.agent_tools_inner.winfo_children():
            w.destroy()
        self.agent_tool_vars = {}

        tool_names: List[str] = []
        conn = self._get_conn()
        try:
            cur = conn.cursor()
            cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='ToolList'")
            if cur.fetchone():
                cur.execute("SELECT name FROM ToolList ORDER BY name")
                tool_names = [row[0] for row in cur.fetchall()]
        except Exception:
            tool_names = []
        finally:
            conn.close()

        if not tool_names:
            tool_names = sorted(list(list_tools().keys()))

        for i, tool_name in enumerate(tool_names):
            var = tk.IntVar(value=0)
            cb = ttk.Checkbutton(self.agent_tools_inner, text=tool_name, variable=var)
            cb.grid(row=i // 3, column=i % 3, sticky='w', padx=8, pady=3)
            self.agent_tool_vars[tool_name] = var

    def _load_agent_tool_assignments(self, agent_name: str) -> None:
        for var in self.agent_tool_vars.values():
            var.set(0)

        conn = self._get_conn()
        try:
            cur = conn.cursor()
            cur.execute("SELECT id FROM Agents WHERE name=?", (agent_name,))
            row = cur.fetchone()
            if not row:
                return
            agent_id = row[0]
            cur.execute("SELECT tool_name FROM AgentTools WHERE agent_id=?", (agent_id,))
            assigned = {r[0] for r in cur.fetchall()}
            for tool_name, var in self.agent_tool_vars.items():
                var.set(1 if tool_name in assigned else 0)
        finally:
            conn.close()

    def _save_agent(self):
        name = self.agent_name_var.get().strip()
        desc = self.agent_desc_var.get().strip()
        prompt = self.agent_prompt_text.get('1.0', 'end').strip()
        
        if not name or not prompt:
            messagebox.showerror("Error", "Name and Prompt are required.")
            return

        try:
            conn = self._get_conn()
            cur = conn.cursor()
            
            # Check ID
            cur.execute("SELECT id FROM Agents WHERE name=?", (name,))
            row = cur.fetchone()
            
            if row:
                agent_id = row[0]
                cur.execute("UPDATE Agents SET description=?, prompt_content=?, is_active=1 WHERE name=?", (desc, prompt, name))
            else:
                cur.execute("INSERT INTO Agents (name, description, prompt_content) VALUES (?, ?, ?)", (name, desc, prompt))
                agent_id = cur.lastrowid

            # Persist agent -> tools mapping
            cur.execute("DELETE FROM AgentTools WHERE agent_id=?", (agent_id,))
            selected_tools = [tool_name for tool_name, var in self.agent_tool_vars.items() if var.get() == 1]
            for tool_name in selected_tools:
                cur.execute("INSERT INTO AgentTools (agent_id, tool_name) VALUES (?, ?)", (agent_id, tool_name))
            
            conn.commit()
            conn.close()
            self._refresh_agents()
            messagebox.showinfo("Success", f"Agent '{name}' saved.")
        except Exception as e:
            messagebox.showerror("Error", str(e))


    # ==========================
    # ROLES TAB
    # ==========================
    def _create_roles_tab(self):
        tab = ttk.Frame(self.notebook, padding=15)
        self.notebook.add(tab, text='Role Management')

        header = ttk.Frame(tab)
        header.pack(fill='x', pady=(0, 10))
        ttk.Label(header, text="Role Management", style='Heading.TLabel').pack(side='left')
        ttk.Button(header, text="Refresh", command=self._refresh_roles).pack(side='right')
        
        paned = ttk.PanedWindow(tab, orient='horizontal')
        paned.pack(fill='both', expand=True)

        # Left: Roles List
        left = ttk.Frame(paned, padding=(0,0,10,0))
        paned.add(left, weight=1)
        
        ttk.Label(left, text="Defined Roles", style='Heading.TLabel').pack(anchor='w', pady=(0, 5))
        
        self.role_tree = ttk.Treeview(left, columns=('name',), show='headings', selectmode='browse', height=15)
        self.role_tree.heading('name', text='Role Name')
        self.role_tree.pack(fill='both', expand=True)
        self.role_tree.bind('<<TreeviewSelect>>', self._on_role_select)
        
        btn_frame = ttk.Frame(left)
        btn_frame.pack(fill='x', pady=10)
        ttk.Button(btn_frame, text="+ New Role", command=self._new_role).pack(side='left', fill='x', expand=True, padx=(0,5))
        ttk.Button(btn_frame, text="Delete Role", command=self._delete_role).pack(side='left', fill='x', expand=True)

        # Right: Details
        right = ttk.LabelFrame(paned, text="Access Control Policy", padding=15)
        paned.add(right, weight=3)
        
        ttk.Label(right, text="Role Name:", font=('Segoe UI', 9, 'bold')).pack(anchor='w')
        self.role_name_var = tk.StringVar()
        ttk.Entry(right, textvariable=self.role_name_var, width=40).pack(fill='x', pady=(5, 15))
        
        ttk.Label(right, text="Description:", font=('Segoe UI', 9, 'bold')).pack(anchor='w')
        self.role_desc_var = tk.StringVar()
        ttk.Entry(right, textvariable=self.role_desc_var, width=60).pack(fill='x', pady=(5, 15))
        
        ttk.Label(right, text="Authorized Agents (Check all that apply):", font=('Segoe UI', 9, 'bold')).pack(anchor='w', pady=(10,5))
        
        # Checkboxes for agents in a scrollable frame if needed (keeping simple for now)
        self.role_agents_frame = ttk.Frame(right, relief='sunken', borderwidth=1)
        self.role_agents_frame.pack(fill='both', expand=True, pady=5, padx=1)
        self.role_agent_vars = {} # name -> Int(0/1)

        ttk.Button(right, text="Save Policy Changes", command=self._save_role, style='Accent.TButton').pack(anchor='e', pady=10)
        
        self._refresh_roles()

    def _refresh_roles(self):
        self.role_tree.delete(*self.role_tree.get_children())
        conn = self._get_conn()
        cur = conn.cursor()
        cur.execute("SELECT name FROM Roles")
        for row in cur.fetchall():
            self.role_tree.insert('', 'end', values=(row[0],))
        conn.close()
        
        # Refresh agent checkboxes
        for widgets in self.role_agents_frame.winfo_children():
            widgets.destroy()
        
        self.role_agent_vars = {}
        # Admin UI needs to see ALL agents to assign them
        agents = list_agents(return_all=True)
        for i, agent in enumerate(agents):
            var = tk.IntVar()
            cb = ttk.Checkbutton(self.role_agents_frame, text=agent['name'], variable=var)
            cb.grid(row=i//3, column=i%3, sticky='w', padx=5, pady=2)
            self.role_agent_vars[agent['name']] = var

    def _on_role_select(self, event):
        sel = self.role_tree.selection()
        if not sel: return
        rname = self.role_tree.item(sel[0])['values'][0]
        
        conn = self._get_conn()
        cur = conn.cursor()
        cur.execute("SELECT id, name, description FROM Roles WHERE name=?", (rname,))
        row = cur.fetchone()
        if row:
            rid = row[0]
            self.role_name_var.set(row[1])
            self.role_desc_var.set(row[2])
            
            # Load mappings
            cur.execute("""
                SELECT A.name FROM RoleAgents RA 
                JOIN Agents A ON RA.agent_id = A.id 
                WHERE RA.role_id = ?
            """, (rid,))
            assigned = {r[0] for r in cur.fetchall()}
            
            for aname, var in self.role_agent_vars.items():
                var.set(1 if aname in assigned else 0)
        conn.close()

    def _new_role(self):
        self.role_tree.selection_remove(self.role_tree.selection())
        self.role_name_var.set("")
        self.role_desc_var.set("")
        for v in self.role_agent_vars.values(): v.set(0)

    def _save_role(self):
        rname = self.role_name_var.get().strip()
        rdesc = self.role_desc_var.get().strip()
        if not rname: return
        
        try:
            conn = self._get_conn()
            cur = conn.cursor()
            
            cur.execute("SELECT id FROM Roles WHERE name=?", (rname,))
            row = cur.fetchone()
            
            if row:
                rid = row[0]
                cur.execute("UPDATE Roles SET description=? WHERE id=?", (rdesc, rid))
            else:
                cur.execute("INSERT INTO Roles (name, description) VALUES (?, ?)", (rname, rdesc))
                rid = cur.lastrowid
            
            # Update agents
            cur.execute("DELETE FROM RoleAgents WHERE role_id=?", (rid,))
            for aname, var in self.role_agent_vars.items():
                if var.get() == 1:
                    cur.execute("SELECT id FROM Agents WHERE name=?", (aname,))
                    arow = cur.fetchone()
                    if arow:
                        cur.execute("INSERT INTO RoleAgents (role_id, agent_id) VALUES (?, ?)", (rid, arow[0]))
            
            conn.commit()
            conn.close()
            self._refresh_roles()
            messagebox.showinfo("Success", f"Role '{rname}' saved.")
        except Exception as e:
             messagebox.showerror("Error", str(e))

    def _delete_role(self):
        sel = self.role_tree.selection()
        if not sel: return
        rname = self.role_tree.item(sel[0])['values'][0]
        if messagebox.askyesno("Confirm", f"Delete role '{rname}'?"):
             conn = self._get_conn()
             conn.execute("DELETE FROM Roles WHERE name=?", (rname,))
             conn.commit()
             conn.close()
             self._refresh_roles()

    # ==========================
    # USERS TAB
    # ==========================
    def _create_users_tab(self):
        tab = ttk.Frame(self.notebook, padding=15)
        self.notebook.add(tab, text='User Management')

        header = ttk.Frame(tab)
        header.pack(fill='x', pady=(0, 10))
        ttk.Label(header, text="User Management", style='Heading.TLabel').pack(side='left')
        ttk.Button(header, text="Refresh", command=self._refresh_users).pack(side='right')
        
        # User List Section
        list_frame = ttk.LabelFrame(tab, text="Directory", padding=15)
        list_frame.pack(fill='both', expand=True, pady=(0, 15))
        
        btn_frame = ttk.Frame(list_frame)
        btn_frame.pack(fill='x', pady=(0, 10))
        ttk.Button(btn_frame, text="+ Create New User", command=self._create_user_dialog).pack(side='left')
        ttk.Button(btn_frame, text="Refresh Directory", command=self._refresh_users).pack(side='right')

        cols = ('id', 'name', 'role')
        self.user_tree = ttk.Treeview(list_frame, columns=cols, show='headings', height=10)
        self.user_tree.heading('id', text='ID')
        self.user_tree.heading('name', text='Full Name / Email')
        self.user_tree.heading('role', text='Assigned Role')
        self.user_tree.column('id', width=40, anchor='center')
        self.user_tree.column('name', width=250)
        self.user_tree.column('role', width=120)
        self.user_tree.pack(fill='both', expand=True)
        
        # Role Assignment Section
        assign_frame = ttk.LabelFrame(tab, text="Role Assignment", padding=15)
        assign_frame.pack(fill='x', pady=(0, 15))
        
        ttk.Label(assign_frame, text="Assign Role to Selected User:", font=('Segoe UI', 9)).pack(side='left', padx=(0, 10))
        self.assign_role_var = tk.StringVar()
        self.assign_role_combo = ttk.Combobox(assign_frame, textvariable=self.assign_role_var, state='readonly', width=25)
        self.assign_role_combo.pack(side='left', padx=(0, 10))
        ttk.Button(assign_frame, text="Update Role", command=self._update_user_role, style='Accent.TButton').pack(side='left')
        
        # Session Control Section
        session_frame = ttk.LabelFrame(tab, text="Active Session Context", padding=15)
        session_frame.pack(fill='x')
        
        ttk.Label(session_frame, text="Current Active User (For this Client Instance):", font=('Segoe UI', 9, 'bold')).pack(anchor='w', pady=(0, 5))
        
        hbox = ttk.Frame(session_frame)
        hbox.pack(fill='x')
        
        self.session_user_var = tk.StringVar()
        self.session_user_combo = ttk.Combobox(hbox, textvariable=self.session_user_var, state='readonly', width=40)
        self.session_user_combo.pack(side='left', fill='x', expand=True, padx=(0, 10))
        ttk.Button(hbox, text="Set Active User", command=self._set_active_user).pack(side='left')

        self.user_tree.bind('<<TreeviewSelect>>', self._on_user_select)
        self._refresh_users()

    def _refresh_users(self):
        self.user_tree.delete(*self.user_tree.get_children())
        self.all_users = [] # List of tuples
        
        conn = self._get_conn()
        cur = conn.cursor()
        
        # Get roles first
        cur.execute("SELECT id, name FROM Roles")
        self.roles_map = {r[0]: r[1] for r in cur.fetchall()}
        self.assign_role_combo['values'] = list(self.roles_map.values())
        
        # Get users
        try:
            # Inspection first to be safe
            cur.execute("PRAGMA table_info(Users)")
            cols = [c[1] for c in cur.fetchall()]
            
            # Determine name column
            name_col = 'full_name'
            if 'full_name' not in cols and 'FirstName' in cols:
                 name_col = 'FirstName'
            
            # Check if email exists
            email_col = 'email' if 'email' in cols else "''"
            
            if 'role_id' in cols and 'roleID' in cols:
                role_expr = 'COALESCE(role_id, roleID)'
            elif 'role_id' in cols:
                role_expr = 'role_id'
            elif 'roleID' in cols:
                role_expr = 'roleID'
            else:
                role_expr = 'NULL'
            query = f'SELECT id, "{name_col}", {role_expr}, {email_col} FROM Users'
            cur.execute(query)
            
            for row in cur.fetchall():
                uid, name, rid, email = row
                rname = self.roles_map.get(rid, 'Has No Role')
                display_name = f"{name} ({email})"
                self.user_tree.insert('', 'end', values=(uid, display_name, rname))
                self.all_users.append((uid, display_name))
        except Exception as e:
            print(f"User refresh error: {e}")
            messagebox.showerror("Refresh Error", f"Failed to refresh user list: {e}")
            
        conn.close()
        
        # Refresh session user combo
        session_values = [f"{u[1]} [ID:{u[0]}]" for u in self.all_users]
        self.session_user_combo['values'] = session_values

        # Restore persisted active user in UI and keep CDA synced.
        active_user_id = str(
            self.cda.get_setting(
                'current_user_id',
                self.settings.get('current_user_id', '')
            )
        )
        if active_user_id:
            selected_val = ""
            for uid, display_name in self.all_users:
                if str(uid) == active_user_id:
                    selected_val = f"{display_name} [ID:{uid}]"
                    break

            if selected_val:
                self.session_user_combo.set(selected_val)
                active_username = selected_val.split(" [ID:")[0]
                email_match = re.search(r'\(([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})\)', active_username)
                active_email = email_match.group(1) if email_match else self.settings.get('current_user_email', '')
                self.settings['current_user_id'] = active_user_id
                self.settings['current_username'] = active_username
                self.settings['current_user_email'] = active_email
                self.cda.set_setting('current_user_id', active_user_id)
                self.cda.set_setting('current_username', active_username)
                self.cda.set_setting('current_user_email', active_email)

    def _on_user_select(self, event):
        sel = self.user_tree.selection()
        if not sel: return
        item = self.user_tree.item(sel[0])
        role = item['values'][2]
        if role in self.assign_role_combo['values']:
            self.assign_role_combo.set(role)

    def _update_user_role(self):
        sel = self.user_tree.selection()
        if not sel: return
        uid = self.user_tree.item(sel[0])['values'][0]
        rname = self.assign_role_var.get()
        
        # find role id
        rid = None
        for k, v in self.roles_map.items():
            if v == rname:
                rid = k
                break
        
        if rid:
            conn = self._get_conn()
            conn.execute("UPDATE Users SET role_id=? WHERE id=?", (rid, uid))
            conn.commit()
            conn.close()
            
            # Repopulate
            self._refresh_users()
            self.update_idletasks() # Force redraw
            messagebox.showinfo("Success", "User role updated.")

    def _set_active_user(self):
        val = self.session_user_combo.get()
        if not val: return
        # Extract ID from "Name [ID:123]"
        match = re.search(r'\[ID:(\d+)\]', val)
        if match:
            uid = match.group(1)
            # Find name
            uname = val.split(" [ID:")[0]
            email_match = re.search(r'\(([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})\)', uname)
            uemail = email_match.group(1) if email_match else ""
            if not uemail:
                # Fallback query by user id if display text did not include email.
                conn = self._get_conn()
                cur = conn.cursor()
                cur.execute("SELECT email FROM Users WHERE id = ?", (uid,))
                row = cur.fetchone()
                conn.close()
                if row and row[0]:
                    uemail = row[0]

            self.settings['current_user_id'] = uid
            self.settings['current_username'] = uname
            self.settings['current_user_email'] = uemail
            config_loader.save_settings(self.settings)
            
            # CDA Update
            self.cda.set_setting('current_user_id', uid)
            self.cda.set_setting('current_username', uname)
            self.cda.set_setting('current_user_email', uemail)
            messagebox.showinfo("Saved", f"Active user set to: {uname}")

    def _create_user_dialog(self):
        # Custom Styled Dialog
        d = tk.Toplevel(self)
        d.title("Create New User")
        d.geometry("400x300")
        d.configure(bg='#2b2b2b')
        d.resizable(False, False)
        
        # Center the dialog
        root = self.winfo_toplevel()
        root.update_idletasks()
        x = root.winfo_x() + (root.winfo_width() // 2) - (400 // 2)
        y = root.winfo_y() + (root.winfo_height() // 2) - (300 // 2)
        d.geometry(f"+{x}+{y}")
        
        # Consistent Style
        lbl_style = {'bg': '#2b2b2b', 'fg': '#a9b7c6', 'font': ('Segoe UI', 10)}
        entry_bg = '#3c3f41'
        entry_fg = 'white'
        
        # Header
        header = tk.Label(d, text="User Registration", font=('Segoe UI', 12, 'bold'), bg='#2b2b2b', fg='white')
        header.pack(pady=(20, 20))
        
        # Content Frame
        content = tk.Frame(d, bg='#2b2b2b', padx=30)
        content.pack(fill='both', expand=True)

        tk.Label(content, text="Full Name", **lbl_style).pack(anchor='w')
        name_var = tk.StringVar()
        name_entry = tk.Entry(content, textvariable=name_var, bg=entry_bg, fg=entry_fg, insertbackground='white', relief='flat', font=('Segoe UI', 10))
        name_entry.pack(fill='x', pady=(5, 15), ipady=3)
        
        tk.Label(content, text="Email Address", **lbl_style).pack(anchor='w')
        email_var = tk.StringVar()
        email_entry = tk.Entry(content, textvariable=email_var, bg=entry_bg, fg=entry_fg, insertbackground='white', relief='flat', font=('Segoe UI', 10))
        email_entry.pack(fill='x', pady=(5, 15), ipady=3)
        
        # Error Label
        error_lbl = tk.Label(content, text="", fg='#ff6b6b', bg='#2b2b2b', font=('Segoe UI', 9))
        error_lbl.pack(pady=(0, 10))
        
        def create():
            n = name_var.get().strip()
            e = email_var.get().strip()
            
            # Validation
            if not n:
                error_lbl.config(text="Full Name is required.")
                name_entry.focus()
                return
            if not e:
                error_lbl.config(text="Email is required.")
                email_entry.focus()
                return
            if "@" not in e or "." not in e:
                error_lbl.config(text="Invalid email format.")
                email_entry.focus()
                return

            conn = self._get_conn()
            try:
                # Check for duplicate email
                cur = conn.cursor()
                cur.execute("SELECT id FROM Users WHERE email=?", (e,))
                if cur.fetchone():
                    error_lbl.config(text="Email already registered.")
                    return

                conn.execute('INSERT INTO Users (full_name, email) VALUES (?, ?)', (n, e))
                conn.commit()
                messagebox.showinfo("Success", f"User '{n}' created successfully.", parent=d)
                d.destroy()
                self._refresh_users()
            except Exception as ex:
                error_lbl.config(text=str(ex))
            finally:
                conn.close()
        
        # Buttons
        btn_frame = tk.Frame(d, bg='#2b2b2b', pady=20)
        btn_frame.pack(fill='x', padx=30)
        
        # Cancel Button
        cancel_btn = tk.Button(btn_frame, text="Cancel", command=d.destroy, 
                             bg='#3c3f41', fg='white', relief='flat', font=('Segoe UI', 9),
                             activebackground='#4b6eaf', activeforeground='white', width=10)
        cancel_btn.pack(side='left')
        
        # Create Button (Accent)
        create_btn = tk.Button(btn_frame, text="Create User", command=create, 
                             bg='#365880', fg='white', relief='flat', font=('Segoe UI', 9, 'bold'),
                             activebackground='#4b6eaf', activeforeground='white', width=15)
        create_btn.pack(side='right')
        
        # Bind validation logic on enter

    # ==========================
    # TOOLS TAB
    # ==========================
    def _create_tools_tab(self):
        tab = ttk.Frame(self.notebook, padding=15)
        self.notebook.add(tab, text='Available Tools')

        header = ttk.Frame(tab)
        header.pack(fill='x', pady=(0, 10))
        ttk.Label(header, text="Tools Management", style='Heading.TLabel').pack(side='left')
        ttk.Button(header, text="Refresh", command=self._refresh_tools).pack(side='right')
        
        # Split: Left List, Right Details
        paned = ttk.PanedWindow(tab, orient='horizontal')
        paned.pack(fill='both', expand=True)

        # Left: List
        frame_list = ttk.Frame(paned, padding=(0,0,10,0))
        paned.add(frame_list, weight=1)
        
        ttk.Label(frame_list, text="Tool Registry", style='Heading.TLabel').pack(anchor='w', pady=(0, 5))
        
        columns = ('name',)
        self.tool_tree = ttk.Treeview(frame_list, columns=columns, show='headings', selectmode='browse', height=15)
        self.tool_tree.heading('name', text='Tool Name')
        self.tool_tree.pack(fill='both', expand=True)
        self.tool_tree.bind('<<TreeviewSelect>>', self._on_tool_select)
        
        # Right: Details (Read Only)
        frame_detail = ttk.LabelFrame(paned, text="Tool Specification", padding=15)
        paned.add(frame_detail, weight=3)

        ttk.Label(frame_detail, text="Tool Name:", font=('Segoe UI', 9, 'bold')).pack(anchor='w')
        self.tool_name_var = tk.StringVar()
        ttk.Entry(frame_detail, textvariable=self.tool_name_var, width=40, state='readonly').pack(fill='x', pady=(5, 10))

        ttk.Label(frame_detail, text="Description:", font=('Segoe UI', 9, 'bold')).pack(anchor='w')
        self.tool_desc_text = scrolledtext.ScrolledText(frame_detail, height=4, font=('Segoe UI', 9), state='disabled', padx=5, pady=5)
        self.tool_desc_text.config(bg='#2b2b2b', fg='#a9b7c6', relief='flat', highlightbackground='#3c3f41', highlightthickness=1)
        self.tool_desc_text.pack(fill='x', pady=(5, 10))

        ttk.Label(frame_detail, text="Input Schema (Parameters):", font=('Segoe UI', 9, 'bold')).pack(anchor='w')
        self.tool_input_text = scrolledtext.ScrolledText(frame_detail, height=5, font=('Consolas', 9), state='disabled', padx=5, pady=5)
        self.tool_input_text.config(bg='#2b2b2b', fg='#a9b7c6', relief='flat', highlightbackground='#3c3f41', highlightthickness=1)
        self.tool_input_text.pack(fill='x', pady=(5, 10))

        ttk.Label(frame_detail, text="Output Schema (Return Type):", font=('Segoe UI', 9, 'bold')).pack(anchor='w')
        self.tool_output_var = tk.StringVar()
        ttk.Entry(frame_detail, textvariable=self.tool_output_var, width=60, state='readonly').pack(fill='x', pady=(5, 10))

        self._refresh_tools()

    def _refresh_tools(self):
        self.tool_tree.delete(*self.tool_tree.get_children())
        conn = self._get_conn()
        try:
            cur = conn.cursor()
            # Check if table exists
            cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='ToolList'")
            if cur.fetchone():
                cur.execute("SELECT name FROM ToolList ORDER BY name")
                for row in cur.fetchall():
                    self.tool_tree.insert('', 'end', values=(row[0],))
        except Exception as e:
            print(f"Error loading tools: {e}")
        finally:
            conn.close()

    def _on_tool_select(self, event):
        sel = self.tool_tree.selection()
        if not sel: return
        name = self.tool_tree.item(sel[0])['values'][0]
        
        conn = self._get_conn()
        try:
            cur = conn.cursor()
            cur.execute("SELECT name, description, input_schema, output_schema FROM ToolList WHERE name=?", (name,))
            row = cur.fetchone()
            if row:
                self.tool_name_var.set(row[0])
                
                self.tool_desc_text.config(state='normal')
                self.tool_desc_text.delete('1.0', 'end')
                self.tool_desc_text.insert('1.0', row[1] or "No description.")
                self.tool_desc_text.config(state='disabled')
                
                self.tool_input_text.config(state='normal')
                self.tool_input_text.delete('1.0', 'end')
                self.tool_input_text.insert('1.0', row[2] or "N/A")
                self.tool_input_text.config(state='disabled')
                
                self.tool_output_var.set(row[3] or "Any")
        except Exception as e:
            print(f"Error fetching tool details: {e}")
        finally:
            conn.close()
