"""Chat UI using Tkinter with Modern Sidebar Layout."""

from __future__ import annotations

import tkinter as tk
import tkinter.ttk as ttk
from tkinter.scrolledtext import ScrolledText
import tkinter.filedialog as filedialog
import threading
import json
import os
from datetime import datetime
from typing import Dict, Any, Tuple, List, Optional
from PIL import Image, ImageDraw, ImageTk

from core.controller import Controller
from core.common_data_area import CommonDataArea
from ui.settings_ui import SettingsPanel
import execution_logger
import sqlite3
from agents.registry import _get_db_path

class ChatUI:
    def __init__(self, controller: Controller, cda: CommonDataArea | None = None) -> None:
        self.cda = cda or CommonDataArea()
        self.controller = controller
        self.selected_files: List[str] = []
        self._current_chat_id: Optional[int] = None
        
        self.root = tk.Tk()
        self.root.title('Desktop Agentic System')
        self.root.geometry('1100x750')
        
        # --- THEME CONFIGURATION (Refined Dark Modern) ---
        bg_color = '#1e1e1e' # Slightly darker main background
        sidebar_bg = '#252526' # Standard VS Code-like sidebar
        header_bg = '#323233' 
        accent_color = '#007acc' # Clean blue accent
        fg_color = '#cccccc'
        
        style = ttk.Style(self.root)
        try:
            style.theme_use('clam')
        except:
            pass
        
        # Global Styles
        style.configure('.', background=bg_color, foreground=fg_color, font=('Segoe UI', 10))
        style.configure('TFrame', background=bg_color)
        style.configure('Sidebar.TFrame', background=sidebar_bg)
        
        # Notebook (Tab) Styling - Rounded/Modern feel via padding and fonts
        style.configure('TNotebook', background=bg_color, borderwidth=0, padding=0)
        
        # --- ROUNDED TABS IMPLEMENTATION ---
        # We generate images for the tabs to get truly rounded corners
        tab_radius = 10
        tab_height = 35
        tab_width = 120
        
        self.tab_img_unselected = self._create_rounded_rect_image(tab_width, tab_height, tab_radius, sidebar_bg, bg_color)
        self.tab_img_selected = self._create_rounded_rect_image(tab_width, tab_height, tab_radius, bg_color, bg_color)
        self.tab_img_active = self._create_rounded_rect_image(tab_width, tab_height, tab_radius, '#37373d', bg_color)
        
        # Use a unique name for the images in style
        style.element_create('RoundedTab.bg', 'image', self.tab_img_unselected,
                            ('selected', self.tab_img_selected),
                            ('active', self.tab_img_active),
                            border=tab_radius, sticky='nsew')
        
        style.layout('TNotebook.Tab', [
            ('RoundedTab.bg', {'sticky': 'nsew', 'children': [
                ('Notebook.padding', {'side': 'top', 'sticky': 'nsew', 'children': [
                    ('Notebook.label', {'sticky': 'ns'})
                ]})
            ]})
        ])
        
        style.configure('TNotebook.Tab', 
                        foreground=fg_color, 
                        padding=[15, 5], 
                        font=('Segoe UI', 10, 'bold'))
        style.map('TNotebook.Tab', 
                  foreground=[('selected', 'white')])
        
        # Sidebar Buttons - More spacing, cleaner hover
        style.configure('Sidebar.TButton', background=sidebar_bg, foreground='#cccccc', borderwidth=0, font=('Segoe UI', 10), anchor='w', padding=(15, 12))
        style.map('Sidebar.TButton', 
                  background=[('active', '#37373d'), ('pressed', accent_color)],
                  foreground=[('active', 'white')])
        
        self.root.configure(bg=bg_color)
        
        # --- MAIN LAYOUT ---
        # 1. Sidebar (Left) - Slightly wider for breathing room
        self.sidebar = ttk.Frame(self.root, style='Sidebar.TFrame', width=220)
        self.sidebar.pack(side='left', fill='y')
        self.sidebar.pack_propagate(False)
        
        # Sidebar Header
        lbl_title = tk.Label(self.sidebar, text="AGS CONSOLE", bg=sidebar_bg, fg='white', font=('Segoe UI', 11, 'bold'), pady=30)
        lbl_title.pack(anchor='center')

        # Navigation Buttons
        self.btn_chat = ttk.Button(self.sidebar, text="  💬  Agent Console", style='Sidebar.TButton', command=lambda: self.show_page('interaction'))
        self.btn_chat.pack(fill='x', pady=1)

        style.configure('SubSidebar.TButton', background=sidebar_bg, foreground='#93a1a1', borderwidth=0, font=('Segoe UI', 9), anchor='w', padding=(35, 8))
        style.map('SubSidebar.TButton', 
                  background=[('active', '#37373d'), ('pressed', accent_color)],
                  foreground=[('active', 'white')])

        self.btn_new_chat = ttk.Button(self.sidebar, text="  ➕  New Chat", style='SubSidebar.TButton', command=self._start_new_chat)
        self.btn_new_chat.pack(fill='x', pady=0)

        self.btn_history = ttk.Button(self.sidebar, text="  🕰  History", style='SubSidebar.TButton', command=lambda: self.show_page('history'))
        self.btn_history.pack(fill='x', pady=0)
        
        self.btn_logs = ttk.Button(self.sidebar, text="  📋  System Logs", style='Sidebar.TButton', command=lambda: self.show_page('logs'))
        self.btn_logs.pack(fill='x', pady=1)
        
        tk.Frame(self.sidebar, bg='#3c3f41', height=1).pack(fill='x', pady=15, padx=20) # Thinner separator
        
        self.btn_settings = ttk.Button(self.sidebar, text="  ⚙️  Settings", style='Sidebar.TButton', command=lambda: self.show_page('settings'))
        self.btn_settings.pack(fill='x', pady=1)

        # 2. Content Area (Right)
        self.content_area = ttk.Frame(self.root)
        self.content_area.pack(side='right', fill='both', expand=True)
        
        # --- PAGES ---
        self.pages = {}
        
        # -- Interaction Page (Consolidated Chat + Executor) --
        self.pages['interaction'] = ttk.Frame(self.content_area)
        
        # Top Info Bar - More defined, horizontal padding
        self.info_header = tk.Frame(self.pages['interaction'], bg=header_bg, height=75)
        self.info_header.pack(side='top', fill='x')
        self.info_header.pack_propagate(False)

        self.active_user_label = tk.Label(
            self.info_header,
            text="Active User: (not set)",
            bg=header_bg,
            fg='#93a1a1',
            font=('Segoe UI', 14),
            padx=25
        )
        self.active_user_label.pack(side='left')

        self.debug_mode_label = tk.Label(
            self.info_header,
            text="Debug Mode: OFF",
            bg=header_bg,
            fg='#ef476f',
            font=('Segoe UI', 12, 'bold'),
            padx=25
        )
        self.debug_mode_label.pack(side='right')
        
        # Subtle border between header and content
        tk.Frame(self.pages['interaction'], bg='#3c3f41', height=1).pack(side='top', fill='x')

        # Main Interaction Area with Generous Padding
        self.interaction_container = ttk.Frame(self.pages['interaction'], padding=(20, 15, 20, 20))
        self.interaction_container.pack(fill='both', expand=True)

        # Interaction Notebook
        self.nb = ttk.Notebook(self.interaction_container)
        self.nb.pack(fill='both', expand=True)

        # Tab 1: Chat
        self.chat_tab = ttk.Frame(self.nb)
        self.nb.add(self.chat_tab, text='  Interactions  ')

        # Chat History - Added spacing1, spacing2 for air
        self.transcript = ScrolledText(
            self.chat_tab, 
            state='disabled', 
            wrap='word', 
            font=('Segoe UI', 10), 
            bg=bg_color, 
            fg=fg_color, 
            insertbackground='white', 
            relief='flat', 
            padx=15, 
            pady=15,
            spacing1=5, 
            spacing3=5
        )
        self.transcript.grid(row=0, column=0, sticky='nsew')
        self.chat_tab.grid_rowconfigure(0, weight=1)
        self.chat_tab.grid_columnconfigure(0, weight=1)
        # Spacing configs (no pack here, moved below)
        self.transcript.tag_config('user', foreground='#4b6eaf', font=('Segoe UI', 10, 'bold'))
        self.transcript.tag_config('assistant', foreground='#cccccc')
        self.transcript.tag_config('error', foreground='#ef476f')
        self.transcript.tag_config('status', foreground='#606060', font=('Segoe UI', 9, 'italic'))

        # --- INPUT AREA (Row 2) ---
        # Container for Status and File List (Above input)
        # We'll use a frame for the status breadcrumb
        self.status_frame = tk.Frame(self.chat_tab, bg=bg_color)
        self.status_frame.grid(row=1, column=0, sticky='ew', padx=20)
        
        self.status_label = tk.Label(
            self.status_frame, 
            text="", 
            bg=bg_color, 
            fg='#999999', 
            font=('Segoe UI', 9, 'italic')
        )
        self.status_label.pack(side='left', pady=(5, 0))

        self.file_list_frame = tk.Frame(self.chat_tab, bg=bg_color)
        self.file_list_frame.grid(row=2, column=0, sticky='ew', padx=20)
        self.file_list_frame.grid_remove() # Hidden initially

        self.input_container = ttk.Frame(self.chat_tab, padding=(20, 5, 20, 20))
        self.input_container.grid(row=3, column=0, sticky='ew')
        
        # Pill-shaped container for input
        # We simulate a "pill" by using a rounded rect image on a Label background? 
        # Or just a Frame with rounded corners? 
        # Tkinter doesn't do rounded frames easily. 
        # Let's keep the dark bar but round the buttons inside or making the bar look cleaner.
        # User asked for "Prompt accepting bar to accept file by pressing + button and right end make button also rounded".
        # This implies a pill-shaped input field. 
        # To achieve a "Google Search" style pill bar, we need a Canvas or an image-based Frame container.
        # For simplicity and robustness, I will make the *inner* logic robust and buttons rounded.
        
        input_inner = tk.Frame(self.input_container, bg='#2d2d2d', pady=8, padx=10)
        # To make "input_inner" rounded, we'd need a Canvas.
        # Let's keep it simple rectangular for now but polished.
        input_inner.pack(fill='x', pady=(0, 5)) # Add some bottom spacing for the inner frame itself

        # 1. Attach Button (+)
        self.btn_attach = tk.Button(
            input_inner,
            text="+",
            command=self.on_attach_file,
            bg='#2d2d2d',
            fg='#cccccc',
            relief='flat',
            font=('Segoe UI', 14),
            bd=0,
            activebackground='#3c3c3c',
            activeforeground='white',
            cursor='hand2'
        )
        self.btn_attach.pack(side='left', padx=(5, 10))

        self.input_var = tk.StringVar()
        self.input_entry = tk.Entry(
            input_inner, 
            textvariable=self.input_var, 
            bg='#2d2d2d', 
            fg='white', 
            insertbackground='white', 
            relief='flat', 
            font=('Segoe UI', 10),
            highlightthickness=0
        )
        self.input_entry.pack(side='left', fill='x', expand=True, ipady=8)
        self.input_entry.bind('<Return>', self.on_send)
        
        # 2. Rounded Send Button
        # We'll use an image for the rounded effect
        # Create pill image for "Send"
        self.img_send_btn = self._create_rounded_rect_image(80, 34, 17, accent_color, '#2d2d2d') # Increased height slightly
        self.img_send_btn_hover = self._create_rounded_rect_image(80, 34, 17, '#006bb3', '#2d2d2d')
        
        # We can't easily put text ON TOP of an image in a standard tk.Button reliably cross-platform without tricks.
        # A Label with binding is often better for custom buttons.
        
        self.btn_send_lbl = tk.Label(
            input_inner,
            image=self.img_send_btn,
            bg='#2d2d2d',
            cursor='hand2',
            text="Send", # Text won't show with image usually unless compound set
            compound='center',
            fg='white',
            font=('Segoe UI', 9, 'bold')
        )
        self.btn_send_lbl.pack(side='right', padx=(10, 0))
        self.btn_send_lbl.bind('<Button-1>', self.on_send)
        self.btn_send_lbl.bind('<Enter>', lambda e: self.btn_send_lbl.configure(image=self.img_send_btn_hover))
        self.btn_send_lbl.bind('<Leave>', lambda e: self.btn_send_lbl.configure(image=self.img_send_btn))

        # --- PERMISSION FRAME (Packed Bottom Second, initially hidden) ---
        self.permission_frame = ttk.Frame(self.chat_tab, padding=(10, 10, 10, 10))
        self.permission_label = tk.Label(
            self.permission_frame,
            text="",
            bg=bg_color,
            fg='#f2c94c',
            justify='left',
            anchor='w',
            wraplength=800,
            font=('Segoe UI', 9, 'bold')
        )
        self.permission_label.pack(fill='x', pady=(0, 10))
        
        btn_row = ttk.Frame(self.permission_frame)
        btn_row.pack(anchor='w')
        
        self.permission_yes_btn = tk.Button(
            btn_row,
            text="ACCEPT",
            command=lambda: self._resolve_permission(True),
            bg='#2e7d32',
            fg='white',
            relief='flat',
            padx=25,
            pady=4,
            font=('Segoe UI', 9, 'bold'),
        )
        self.permission_yes_btn.pack(side='left', padx=(0, 10))
        
        self.permission_no_btn = tk.Button(
            btn_row,
            text="REJECT",
            command=lambda: self._resolve_permission(False),
            bg='#c62828',
            fg='white',
            relief='flat',
            padx=25,
            pady=4,
            font=('Segoe UI', 9, 'bold'),
        )
        self.permission_no_btn.pack(side='left')
        
        self.permission_frame.grid(row=1, column=0, sticky='ew')
        self.permission_frame.grid_remove() # Hide initially
        
        # -- Tab 2: Executor Status --
        self.executor_tab = ttk.Frame(self.nb)
        self.nb.add(self.executor_tab, text='  Runtime Trace  ')

        self.executor_status = ScrolledText(
            self.executor_tab,
            state='disabled',
            wrap='word',
            font=('Consolas', 10),
            bg='#1a1a1a',
            fg='#dcdcdc',
            insertbackground='white',
            relief='flat',
            padx=15,
            pady=15,
            spacing1=3
        )
        self.executor_status.pack(fill='both', expand=True)
        # (tag configs remain same as they are defined later or should be here)
        self.executor_status.tag_config('default', foreground='#dcdcdc')
        self.executor_status.tag_config('llm_input', foreground='#8ecae6')
        self.executor_status.tag_config('llm_output', foreground='#90be6d')
        self.executor_status.tag_config('tool_call', foreground='#f4a261')
        self.executor_status.tag_config('tool_result', foreground='#2a9d8f')
        self.executor_status.tag_config('permission', foreground='#f2c94c')
        self.executor_status.tag_config('error', foreground='#ef476f')

        # -- Logs Page -- 
        self.pages['logs'] = ttk.Frame(self.content_area, padding=20)
        ttk.Label(self.pages['logs'], text="System Activity Logs", font=('Segoe UI', 12, 'bold')).pack(anchor='w', pady=(0, 15))
        self.log_display = ScrolledText(self.pages['logs'], state='disabled', wrap='word', font=('Consolas', 9), bg='#1a1a1a', fg='#dcdcdc', insertbackground='white', relief='flat', padx=10, pady=10)
        self.log_display.pack(fill='both', expand=True)

        # -- History Page --
        self.pages['history'] = ttk.Frame(self.content_area, padding=20)
        
        hist_header = ttk.Frame(self.pages['history'])
        hist_header.pack(fill='x', pady=(0, 15))
        ttk.Label(hist_header, text="Chat History", font=('Segoe UI', 12, 'bold')).pack(side='left')
        ttk.Button(hist_header, text="Refresh", command=self._refresh_history_list).pack(side='right')
        
        self.history_list_frame = ttk.Frame(self.pages['history'])
        self.history_list_frame.pack(fill='both', expand=True)

        # -- Settings Page --
        self.pages['settings'] = SettingsPanel(self.content_area, self.cda)
        
        # -- Final Setup --
        self.show_page('interaction')
        self._refresh_active_user_label()
        self._refresh_debug_mode_label()
        
        execution_logger.register_log_callback(self.append_log)
        self.cda.set_runtime('executor_trace_handler', self._executor_trace_threadsafe)
        self.cda.set_runtime('executor_permission_handler', self._request_permission_threadsafe)
        self.cda.set_runtime('tool_status_handler', self._update_tool_status_threadsafe)

    def show_page(self, page_name: str):
        for page in self.pages.values():
            page.pack_forget()
        if page_name in self.pages:
            if page_name == 'history':
                self._refresh_history_list()
            self.pages[page_name].pack(fill='both', expand=True)

    def _start_new_chat(self) -> None:
        self._current_chat_id = None
        self.cda.set_memory('chat_history', '')
        self.transcript.configure(state='normal')
        self.transcript.delete('1.0', tk.END)
        self.transcript.configure(state='disabled')
        self.controller.clear_current_task()
        self.show_page('interaction')

    def _refresh_history_list(self) -> None:
        for widget in self.history_list_frame.winfo_children():
            widget.destroy()
            
        db_path = _get_db_path()
        if not db_path or not os.path.exists(db_path):
            return
            
        try:
            conn = sqlite3.connect(db_path)
            cur = conn.cursor()
            cur.execute("SELECT id, title, created_at FROM ChatHistory ORDER BY created_at DESC LIMIT 50")
            rows = cur.fetchall()
            conn.close()
            
            for row in rows:
                chat_id, title, created_at = row
                card = tk.Frame(self.history_list_frame, bg='#2d2d2d', cursor='hand2', pady=10, padx=15)
                card.pack(fill='x', pady=5)
                
                lbl_title = tk.Label(card, text=title or "New Chat", bg='#2d2d2d', fg='white', font=('Segoe UI', 10, 'bold'))
                lbl_title.pack(anchor='w')
                
                lbl_date = tk.Label(card, text=created_at, bg='#2d2d2d', fg='#999999', font=('Segoe UI', 9))
                lbl_date.pack(anchor='w')
                
                card.bind('<Button-1>', lambda e, cid=chat_id: self._load_history_chat(cid))
                lbl_title.bind('<Button-1>', lambda e, cid=chat_id: self._load_history_chat(cid))
                lbl_date.bind('<Button-1>', lambda e, cid=chat_id: self._load_history_chat(cid))
                
        except Exception as e:
            execution_logger.log_execution_step('HISTORY_ERROR', f"Failed to load history: {e}")

    def _load_history_chat(self, chat_id: int) -> None:
        self._current_chat_id = chat_id
        self.transcript.configure(state='normal')
        self.transcript.delete('1.0', tk.END)
        self.transcript.configure(state='disabled')
        
        history_text = ""
        
        db_path = _get_db_path()
        if not db_path or not os.path.exists(db_path): return
        
        try:
            conn = sqlite3.connect(db_path)
            cur = conn.cursor()
            cur.execute("SELECT role, content FROM ChatLog WHERE chat_id=? ORDER BY timestamp ASC", (chat_id,))
            rows = cur.fetchall()
            conn.close()
            
            for role, content in rows:
                self.transcript.configure(state='normal')
                
                tag = 'assistant'
                display_msg = content
                if role == 'User':
                    tag = 'user'
                    display_msg = f"You: {content}"
                elif role == 'Error':
                    tag = 'error'
                    display_msg = f"Error: {content}"
                elif role == 'Status':
                    tag = 'status'
                else:
                    display_msg = f"Agent: {content}"
                    
                self.transcript.insert('end', f"{display_msg}\n\n", tag)
                self.transcript.configure(state='disabled')
                
                # Rebuild history context
                if role != 'Status':
                    prefix = "User: " if role == 'User' else "Agent: "
                    history_text += f"{prefix}{content}\n"
                
        except Exception as e:
            execution_logger.log_execution_step('HISTORY_LOAD_ERROR', f"Failed to load chat {chat_id}: {e}")
            
        self.cda.set_memory('chat_history', history_text)
        self.transcript.see('end')
        self.show_page('interaction')
    def _save_to_chat_history(self, role: str, content: str) -> None:
        if role == 'Status' or not content.strip():
            return
            
        db_path = _get_db_path()
        if not db_path or not os.path.exists(db_path):
            return
            
        try:
            conn = sqlite3.connect(db_path)
            cur = conn.cursor()
            
            if self._current_chat_id is None:
                title = content[:50].strip()
                if not title:
                    title = "New Chat"
                cur.execute("INSERT INTO ChatHistory (title) VALUES (?)", (title,))
                self._current_chat_id = cur.lastrowid
                
            cur.execute("INSERT INTO ChatLog (chat_id, role, content) VALUES (?, ?, ?)", 
                        (self._current_chat_id, role, content))
            conn.commit()
            conn.close()
        except Exception as e:
            execution_logger.log_execution_step('CHAT_DB_ERROR', f"Failed to save chat: {e}")

    def append_message(self, sender: str, message: str) -> None:
        self.transcript.configure(state='normal')
        
        # Save raw message to database before prefixing
        self._save_to_chat_history(sender, message)
        
        tag = 'assistant'
        if sender == 'User':
            tag = 'user'
            message = f"You: {message}"
        elif sender == 'Error':
            tag = 'error'
            message = f"Error: {message}"
        elif sender == 'Status':
            tag = 'status'
        else:
            message = f"Agent: {message}"
            
        self.transcript.insert('end', f"{message}\n\n", tag)
        self.transcript.configure(state='disabled')
        self.transcript.see('end')

    def append_log(self, message: str) -> None:
        def _update():
            self.log_display.configure(state='normal')
            self.log_display.insert('end', f"{message}\n")
            self.log_display.configure(state='disabled')
            self.log_display.see('end')
        self.root.after(0, _update)

    def _ui_feedback(self, feedback: dict) -> None:
        if not feedback: return
        status = feedback.get('status', 'info')
        msg = feedback.get('message', '')
        hint = feedback.get('progress_hint', '')
        if msg or hint:
            composed = f"[{status}] {msg}".strip()
            if hint:
                composed = f"{composed} | {hint}" if composed else f"[{status}] {hint}"
            self.append_message('Status', composed)

    def on_attach_file(self) -> None:
        filenames = filedialog.askopenfilenames(
            title="Attach Files",
            filetypes=[("All Files", "*.*"), ("Documents", "*.pdf;*.docx;*.txt"), ("Images", "*.png;*.jpg;*.jpeg")]
        )
        if filenames:
            self.selected_files.extend(filenames)
            self._refresh_file_list()

    def _refresh_file_list(self) -> None:
        # Clear existing
        for widget in self.file_list_frame.winfo_children():
            widget.destroy()
            
        if not self.selected_files:
            self.file_list_frame.grid_remove()
            return

        self.file_list_frame.grid()
        
        # Add chips
        for f in self.selected_files:
            import os
            name = os.path.basename(f)
            # Chip Frame
            chip = tk.Frame(self.file_list_frame, bg='#3c3f41', padx=5, pady=2)
            chip.pack(side='left', padx=2, pady=5)
            
            lbl = tk.Label(chip, text=name, bg='#3c3f41', fg='white', font=('Segoe UI', 9))
            lbl.pack(side='left')
            
            # X button to remove
            # Using a closure to capture 'f' correctly? No, f changes. Use partial or default arg.
            def remove_cb(target=f):
                if target in self.selected_files:
                    self.selected_files.remove(target)
                    self._refresh_file_list()

            btn_x = tk.Label(chip, text=" ×", bg='#3c3f41', fg='#ff6b6b', cursor='hand2', font=('Segoe UI', 10, 'bold'))
            btn_x.pack(side='left')
            btn_x.bind('<Button-1>', lambda e, t=f: remove_cb(t))

    def on_send(self, event=None) -> None:
        text = self.input_var.get().strip()
        files = list(self.selected_files) # Copy
        
        if not text and not files: return
        
        self.input_var.set('')
        self.selected_files.clear()
        self._refresh_file_list()
        
        # Display logic
        display_msg = text
        if files:
            file_names = [os.path.basename(f) for f in files]
            display_msg += f"\n[Attached: {', '.join(file_names)}]"
            
        self.append_message('User', display_msg)
        
        # Ensure we have some text even if user only attached files
        if not text and files:
            text = "Process the attached files."

        # Pass files to process_message
        threading.Thread(target=self._process_message, args=(text, files), daemon=True).start()

    def _process_message(self, text: str, files: List[str] = None) -> None:
        try:
            # Pass files to handle_user_message
            response = self.controller.handle_user_message(text, files=files, ui_callback=self._thread_safe_feedback)
            def _finish():
                # We assume response.content is the final answer string
                # If response object has other fields, adpat here.
                # Assuming ExecutorResult with .content, .status
                if hasattr(response, 'status') and response.status == 'error':
                     self.append_message('Error', getattr(response, 'content', str(response)))
                else:
                     content = getattr(response, 'content', str(response))
                     self.append_message('Assistant', content)
            self.root.after(0, _finish)
        except Exception as e:
            self.root.after(0, lambda: self.append_message('Error', str(e)))

    def _thread_safe_feedback(self, feedback: dict) -> None:
        self.root.after(0, lambda: self._ui_feedback(feedback))

    def run(self) -> None:
        self.root.mainloop()

    def _refresh_active_user_label(self) -> None:
        uid = str(self.cda.get_setting('current_user_id', '') or '')
        uname = str(self.cda.get_setting('current_username', '') or '')
        uemail = str(self.cda.get_setting('current_user_email', '') or '')
        if uname:
            if uid and uemail:
                text = f"Active User: {uname}\nID: {uid} | {uemail}"
            elif uid:
                text = f"Active User: {uname}\nID: {uid}"
            else:
                text = f"Active User: {uname}"
        else:
            text = "Active User: (not set)"
        self.active_user_label.configure(text=text)
        self.root.after(1000, self._refresh_active_user_label)

    def _is_debug_mode_enabled(self) -> bool:
        raw = self.cda.get_setting('debug_mode', False)
        if isinstance(raw, bool):
            return raw
        if isinstance(raw, str):
            return raw.strip().lower() in ('1', 'true', 'yes', 'on')
        return bool(raw)

    def _refresh_debug_mode_label(self) -> None:
        enabled = self._is_debug_mode_enabled()
        self.debug_mode_label.configure(
            text=f"Debug Mode: {'ON' if enabled else 'OFF'}",
            fg=('#90be6d' if enabled else '#ef476f'),
        )
        self.root.after(1000, self._refresh_debug_mode_label)

    def _append_executor_status(self, message: str, tag: str = 'default') -> None:
        self.executor_status.configure(state='normal')
        self.executor_status.insert('end', f"{message}\n\n", tag)
        self.executor_status.configure(state='disabled')
        self.executor_status.see('end')

    def _insert_linked_trace(self, text: str, filepath: str = "", tag: str = 'default'):
        self.executor_status.configure(state='normal')
        self.executor_status.insert('end', text, tag)
        if filepath:
            import os
            import time
            link_tag = f"link_{int(time.time()*1000)}_{hash(text)}"
            self.executor_status.tag_config(link_tag, foreground='#8ecae6', underline=True)
            self.executor_status.tag_bind(link_tag, '<Button-1>', lambda e, fp=filepath: os.startfile(fp))
            self.executor_status.tag_bind(link_tag, '<Enter>', lambda e: self.executor_status.config(cursor="hand2"))
            self.executor_status.tag_bind(link_tag, '<Leave>', lambda e: self.executor_status.config(cursor=""))
            display_name = os.path.basename(filepath)
            self.executor_status.insert('end', f" [Link: {display_name}]\n", link_tag)
        else:
            self.executor_status.insert('end', "\n", tag)
        self.executor_status.configure(state='disabled')
        self.executor_status.see('end')

    def _executor_trace_threadsafe(self, event_type: str, payload: Dict[str, Any]) -> None:
        def _update():
            # Initialize turn counter if absent
            if not hasattr(self, '_trace_counter'):
                self._trace_counter = 1

            if event_type == 'user_input':
                self._trace_counter = 1
                self._insert_linked_trace(f"\n{'-'*60}\n1. User input received")
                self._trace_counter += 1

            elif event_type == 'llm_prepared_prompt':
                agent = payload.get('agent_name', 'Agent')
                fp = payload.get('filepath', '')
                self._insert_linked_trace(f"{self._trace_counter}. {agent} Prompt prepared", fp, 'llm_input')
                self._trace_counter += 1
                self._insert_linked_trace(f"{self._trace_counter}. LLM request in progress", tag='status')

            elif event_type == 'llm_response':
                tt = payload.get('time_taken', 0)
                tu = payload.get('tokens_used', 0)
                fp = payload.get('response_file', '')
                self._insert_linked_trace(f"  {self._trace_counter}.1. LLM call completed: Time {tt:.2f}s, Tokens used: {tu}", tag='status')
                self._trace_counter += 1
                self._insert_linked_trace(f"{self._trace_counter}. LLM response", fp, 'llm_output')
                self._trace_counter += 1

            elif event_type == 'plan_step':
                agent = payload.get('agent_name', 'Agent')
                step = str(payload.get('current_step', '')).strip()
                self._insert_linked_trace(f"{self._trace_counter}. {agent} executing step: {step}", tag='status')
                self._trace_counter += 1

            elif event_type == 'tool_prepared':
                tn = payload.get('tool_name', 'Unknown')
                fp = payload.get('param_file', '')
                self._insert_linked_trace(f"{self._trace_counter}. Tool call in progress: {tn}", fp, 'tool_call')
                self._trace_counter += 1
                
            elif event_type == 'tool_result':
                tn = payload.get('tool_name', 'Unknown')
                fp = payload.get('result_file', '')
                self._insert_linked_trace(f"{self._trace_counter}. Tool call completed results: {tn}", fp, 'tool_result')
                self._trace_counter += 1

            elif event_type == 'permission_required':
                ts = datetime.now().strftime('%H:%M:%S')
                title = f"[{ts}] PERMISSION REQUIRED"
                action_type = payload.get('action_type', 'unknown')
                action_payload = payload.get('payload', {})
                body = f"Action: {action_type}\nSummary: {self._format_permission_summary(action_type, action_payload)}"
                self._append_executor_status(f"{title}\n{body}", tag='permission')

            elif event_type == 'permission_decision':
                ts = datetime.now().strftime('%H:%M:%S')
                title = f"[{ts}] PERMISSION DECISION"
                body = f"Action: {payload.get('action_type', 'unknown')}\nApproved: {payload.get('approved', False)}"
                self._append_executor_status(f"{title}\n{body}", tag='permission')

            elif event_type == 'router_summary':
                selected = payload.get('selected_targets', [])
                selected_txt = ", ".join([str(x) for x in selected]) if selected else "(none)"
                self._insert_linked_trace(f"{self._trace_counter}. Router selected: {selected_txt}", tag='llm_output')
                self._trace_counter += 1

            elif event_type == 'router_decision':
                # Keep router decision concise; do not expose router response payload/file here.
                selected = payload.get('selected_targets', [])
                types = payload.get('decision_types', [])
                selected_txt = ", ".join([str(x) for x in selected]) if selected else "(none)"
                types_txt = ", ".join([str(x) for x in types]) if types else "(unknown)"
                self._insert_linked_trace(f"{self._trace_counter}. Router decision: {types_txt} -> {selected_txt}", tag='llm_output')
                self._trace_counter += 1

            elif event_type == 'controller_task_queue':
                queue_size = payload.get('queue_size', 0)
                routes = payload.get('routes', [])
                targets = []
                for r in routes if isinstance(routes, list) else []:
                    if not isinstance(r, dict):
                        continue
                    t = r.get('selected_agent') or r.get('tool_name') or r.get('type')
                    if t:
                        targets.append(str(t))
                targets_txt = ", ".join(targets) if targets else "(none)"
                self._insert_linked_trace(f"{self._trace_counter}. Controller queued {queue_size} task(s): {targets_txt}", tag='default')
                self._trace_counter += 1

            elif event_type == 'controller_delegate_agent':
                agent = payload.get('agent_name', 'unknown')
                self._insert_linked_trace(f"{self._trace_counter}. Delegating to agent: {agent}", tag='default')
                self._trace_counter += 1

            elif event_type == 'request_user_input':
                agent = payload.get('agent_name', 'Agent')
                content = str(payload.get('content', '')).strip()
                short = (content[:140] + '...') if len(content) > 140 else content
                self._insert_linked_trace(f"{self._trace_counter}. {agent} requested user input: {short}", tag='status')
                self._trace_counter += 1

            elif event_type == 'router_trace_file':
                phase = str(payload.get('phase', '')).strip().lower()
                fp = payload.get('filepath', '')
                label = "Router prompt file" if phase == 'prompt' else "Router response file"
                self._insert_linked_trace(f"{self._trace_counter}. {label}", fp, 'llm_input')
                self._trace_counter += 1

            elif 'error' in event_type.lower():
                ts = datetime.now().strftime('%H:%M:%S')
                title = f"[{ts}] ERROR: {event_type}"
                try:
                    body = json.dumps(payload, indent=2, ensure_ascii=False)
                except:
                    body = str(payload)
                self._append_executor_status(f"{title}\n{body}", tag='error')

            else:
                # Catch-all for unknown events
                ts = datetime.now().strftime('%H:%M:%S')
                title = f"[{ts}] {event_type.upper()}"
                try:
                    body = json.dumps(payload, indent=2, ensure_ascii=False)
                except:
                    body = str(payload)
                self._append_executor_status(f"{title}\n{body}", tag='default')

        self.root.after(0, _update)

    def _request_permission_threadsafe(self, action_type: str, payload: Dict[str, Any]) -> bool:
        if not self._is_debug_mode_enabled():
            return True

        decision = {'allow': False}
        event = threading.Event()

        def _ask_inline():
            # Mirror pending approval in Executor Status panel.
            self._executor_trace_threadsafe('permission_required', {'action_type': action_type, 'payload': payload})
            self.show_page('interaction')
            self.nb.select(self.chat_tab)
            self._pending_permission_event = event
            self._pending_permission_decision = decision
            self._pending_permission_action_type = action_type
            self.permission_label.configure(
                text=f"[Debug Approval] {self._format_permission_summary(action_type, payload)}\nProceed?"
            )
            # Use grid() instead of grid_remove() to show
            self.permission_frame.grid()
            self.append_message('Status', f"[debug] Approval required for {action_type}. Click Yes/No below.")

        self.root.after(0, _ask_inline)
        event.wait()
        return decision['allow']

    def _format_permission_summary(self, action_type: str, payload: Dict[str, Any]) -> str:
        if action_type == 'llm_call':
            return f"LLM Generation | Agent: {payload.get('agent_name', '')} | Loop: {payload.get('loop', '?')} | Attempt: {payload.get('attempt', '?')}"
        if action_type == 'tool_call':
            params = json.dumps(payload.get('parameters', {}), indent=2, ensure_ascii=False)
            return f"Tool Call | Tool: {payload.get('tool_name', '')}\nParameters:\n{params}"
        if action_type == 'request_user_input':
            return f"Request User Input | Content: {str(payload.get('content', ''))[:600]}"
        return f"{action_type} | {json.dumps(payload, ensure_ascii=False)[:300]}"

    def _resolve_permission(self, allow: bool) -> None:
        if self._pending_permission_decision is None or self._pending_permission_event is None:
            return
        self._pending_permission_decision['allow'] = bool(allow)
        self._executor_trace_threadsafe(
            'permission_decision',
            {'action_type': self._pending_permission_action_type, 'approved': bool(allow)}
        )
        self.append_message('Status', f"[debug] {self._pending_permission_action_type} approval: {'yes' if allow else 'no'}")
        self.permission_frame.grid_remove()
        pending_event = self._pending_permission_event
        self._pending_permission_event = None
        self._pending_permission_decision = None
        self._pending_permission_action_type = ""
        pending_event.set()

    def _update_tool_status_threadsafe(self, message: str) -> None:
        """Updates the transient status label and optionally logs to trace."""
        def _update():
            # 1. Update transient label
            if message:
                self.status_label.configure(text=f"⚡ {message}")
            else:
                self.status_label.configure(text="")
            
            # 2. If debug mode is on, log to runtime trace as well
            if self._is_debug_mode_enabled() and message:
                ts = datetime.now().strftime('%H:%M:%S')
                self._append_executor_status(f"[{ts}] [PROGRESS] {message}", tag='status')

        self.root.after(0, _update)

    def _create_rounded_rect_image(self, width: int, height: int, radius: int, color: str, bg_color: str) -> ImageTk.PhotoImage:
        """Creates a rounded rectangle image for use in ttk Styles."""
        # Create a larger image for antialiasing
        scale = 4
        img = Image.new('RGBA', (width * scale, height * scale), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        
        # Fill background color (for the corners that aren't part of the tab)
        # However, for tabs we usually want the background to be transparent or match the parent
        # For simplicity, we use bg_color
        
        r = radius * scale
        w = width * scale
        h = height * scale
        
        # Draw the rounded rectangle (only top corners are rounded for tabs)
        draw.pieslice([0, 0, r * 2, r * 2], 180, 270, fill=color) # Top Left
        draw.pieslice([w - r * 2, 0, w, r * 2], 270, 360, fill=color) # Top Right
        draw.rectangle([r, 0, w - r, h], fill=color) # Middle vertical
        draw.rectangle([0, r, w, h], fill=color) # Bottom part + middle horizontal
        
        # Downsample for antialiasing
        img = img.resize((width, height), Image.Resampling.LANCZOS)
        return ImageTk.PhotoImage(img)
