"""Chat UI using PySide6 with Professional White Theme Layout."""

from __future__ import annotations

import json
import os
import sqlite3
import threading
import uuid
import re
from datetime import datetime, timezone
from typing import Dict, Any, List, Tuple, Optional
from pathlib import Path

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
    QListWidget, QListWidgetItem, QStackedWidget, 
    QTextBrowser, QLineEdit, QPushButton, QLabel,
    QScrollArea, QFileDialog, QFrame, QSizePolicy, QTabWidget,
    QDialog, QTextEdit, QTreeWidget, QTreeWidgetItem, QSplitter, QHeaderView
)
from PySide6.QtCore import Qt, QTimer, Signal, QObject, QUrl
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPixmap, QDesktopServices

from core.common_data_area import CommonDataArea
from core.conversation_manager import ConversationManager
from core.inbound_request import InboundRequest
from ui.settings_ui import SettingsPanel
import execution_logger
from agents.registry import _get_db_path
from settings import config_loader
from ui.branding import BRAND_NAME, build_brand_icon, build_brand_pixmap


class Signals(QObject):
    # Signals for thread-safe UI updates
    append_message = Signal(str, str)
    append_log = Signal(str)
    update_status = Signal(str)
    request_permission = Signal(str, dict, threading.Event, dict)
    executor_status = Signal(str, str)
    execution_started = Signal()
    execution_ended = Signal()


class ExternalTextBrowser(QTextBrowser):
    """A QTextBrowser that explicitly refuses to navigate internally, forcing all links to the OS."""
    def __init__(self, parent=None):
        super().__init__(parent)
        # Disables entirely the internal engine attempting to resolve clicked URLs
        self.setOpenLinks(False)
        self.anchorClicked.connect(QDesktopServices.openUrl)


class CreateAgentDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Create or Modify Agent")
        if parent is not None and not parent.windowIcon().isNull():
            self.setWindowIcon(parent.windowIcon())
        self.resize(500, 400)
        
        # Consistent theme for dialog
        self.setStyleSheet("""
            QDialog { background-color: #ffffff; color: #333333; font-family: 'Segoe UI', Arial; font-size: 14px; }
            QTextEdit { background-color: #f9f9f9; border: 1px solid #e0e0e0; border-radius: 5px; padding: 10px; color: #333333; }
            QPushButton { background-color: #f5f5f5; border: 1px solid #e0e0e0; border-radius: 4px; padding: 6px 15px; color: #333333; }
            QPushButton:hover { background-color: #ededed; }
        """)
        
        layout = QVBoxLayout(self)
        
        self.label = QLabel(
            "Enter tasks and requirements for the new capability. "
            "This can be used to add new features into your system. For example, if you want "
            "to build an issue tracker, a task manager, research capabilities, etc."
        )
        self.label.setWordWrap(True)
        self.label.setStyleSheet("font-weight: bold; margin-bottom: 5px; color: #005fb8;")
        layout.addWidget(self.label)
        
        self.text_edit = QTextEdit()
        self.text_edit.setPlaceholderText("e.g. I need an agent to manage my expenses and read receipts from my inbox...")
        layout.addWidget(self.text_edit)
        
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        self.btn_save_draft = QPushButton("Save Draft")
        self.btn_save_draft.setCursor(Qt.PointingHandCursor)
        self.btn_save_draft.clicked.connect(self.save_draft)
        button_layout.addWidget(self.btn_save_draft)
        
        self.btn_submit = QPushButton("Submit")
        self.btn_submit.setStyleSheet("background-color: #005fb8; color: white; border: none; font-weight: bold;")
        self.btn_submit.setCursor(Qt.PointingHandCursor)
        self.btn_submit.clicked.connect(self.submit)
        button_layout.addWidget(self.btn_submit)
        
        layout.addLayout(button_layout)
        
        self.result_text = None
        self.is_draft = False
        
    def save_draft(self):
        self.is_draft = True
        self.result_text = self.text_edit.toPlainText().strip()
        self.accept()
        
    def submit(self):
        self.is_draft = False
        self.result_text = self.text_edit.toPlainText().strip()
        self.accept()


class ChatUI(QMainWindow):
    def __init__(self, conversation_manager: ConversationManager, cda: CommonDataArea | None = None) -> None:
        super().__init__()
        self.cda = cda or CommonDataArea()
        self.conversation_manager = conversation_manager
        self.selected_files: List[str] = []
        self._current_chat_id: Optional[int] = None
        self._conversation_id = self._new_ui_conversation_id()
        self._runtime_trace_file = self._init_runtime_trace_file()
        
        self.signals = Signals()
        self.signals.append_message.connect(self._safe_append_message)
        self.signals.append_log.connect(self._safe_append_log)
        self.signals.update_status.connect(self._safe_update_status)
        self.signals.executor_status.connect(self._safe_executor_status)
        self.signals.request_permission.connect(self._safe_request_permission)
        self.signals.execution_started.connect(self._on_execution_started)
        self.signals. execution_ended.connect(self._on_execution_ended)
        
        # --- THEME CONFIGURATION (Professional White Theme) ---
        self.bg_color = '#ffffff'
        self.sidebar_bg = '#f5f5f5'
        self.header_bg = '#ffffff'
        self.accent_color = '#005fb8'
        self.fg_color = '#333333'
        self.fg_muted = '#666666'
        self.border_color = '#e0e0e0'
        
        self.brand_icon = build_brand_icon()
        self.setWindowTitle(BRAND_NAME)
        self.setWindowIcon(self.brand_icon)
        self.resize(1100, 750)
        self.setStyleSheet(f"""
            QMainWindow {{ background-color: {self.bg_color}; }}
            QWidget {{ color: {self.fg_color}; font-family: 'Segoe UI', Arial; font-size: 14px; background-color: {self.bg_color}; }}
            QTextBrowser {{ background-color: {self.bg_color}; border: none; padding: 15px; selection-background-color: {self.accent_color}; selection-color: white; }}
            QLineEdit {{ background-color: #f9f9f9; border: 1px solid {self.border_color}; border-radius: 17px; padding: 8px 15px; color: {self.fg_color}; }}
            QPushButton[flat="true"] {{ background: none; border: none; font-weight: bold; color: {self.accent_color}; }}
            QPushButton[flat="true"]:hover {{ color: #004488; }}
            QPushButton#sendBtn {{ background-color: {self.accent_color}; border-radius: 17px; color: white; font-weight: bold; padding: 5px 20px; }}
            QPushButton#sendBtn:hover {{ background-color: #004488; }}
        """)
        
        # Build Central Widget
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        main_layout = QHBoxLayout(self.central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # 1. Sidebar
        self.sidebar = QWidget()
        self.sidebar.setFixedWidth(236)
        self.sidebar.setStyleSheet(f"QWidget {{ background-color: {self.sidebar_bg}; border-right: 1px solid {self.border_color}; }}")
        sidebar_layout = QVBoxLayout(self.sidebar)
        sidebar_layout.setContentsMargins(0, 0, 0, 0)
        sidebar_layout.setSpacing(0)
        
        brand_container = QWidget()
        brand_container_layout = QVBoxLayout(brand_container)
        brand_container_layout.setContentsMargins(12, 12, 12, 8)
        brand_container_layout.setSpacing(0)

        brand_card = QFrame()
        brand_card.setFixedHeight(132)
        brand_card.setObjectName("brandCard")
        brand_card.setStyleSheet("""
            QFrame#brandCard {
                background-color: qlineargradient(
                    x1:0, y1:0, x2:1, y2:1,
                    stop:0 #10253d,
                    stop:0.55 #005fb8,
                    stop:1 #14b8a6
                );
                border: 1px solid rgba(255, 255, 255, 28);
                border-radius: 18px;
            }
            QLabel { background: transparent; }
        """)

        brand_layout = QVBoxLayout(brand_card)
        brand_layout.setContentsMargins(14, 14, 14, 14)
        brand_layout.setSpacing(4)

        brand_logo = QLabel()
        brand_logo.setAlignment(Qt.AlignCenter)
        brand_logo.setPixmap(build_brand_pixmap(44, compact=False))
        brand_layout.addWidget(brand_logo)

        brand_title = QLabel(BRAND_NAME)
        brand_title.setAlignment(Qt.AlignCenter)
        brand_title.setWordWrap(True)
        brand_title.setStyleSheet("color: white; font-size: 15px; font-weight: 700;")
        brand_layout.addWidget(brand_title)

        brand_subtitle = QLabel("Agent Console")
        brand_subtitle.setAlignment(Qt.AlignCenter)
        brand_subtitle.setStyleSheet("color: rgba(255, 255, 255, 190); font-size: 11px; font-weight: 600;")
        brand_layout.addWidget(brand_subtitle)

        brand_container_layout.addWidget(brand_card)
        sidebar_layout.addWidget(brand_container)
        
        # Sidebar Navigation Buttons
        self.nav_buttons = {}
        nav_items = [
            ('interaction', '💬  Agent Console'),
            ('new_chat', '   ➕  New Chat'),
            ('history', '   🕰  History'),
            ('sessions', '   🧵  Sessions'),
            ('logs', '📋  System Logs'),
            ('spacer', ''),
            ('settings', '⚙️  Settings')
        ]
        
        for key, text in nav_items:
            if key == 'spacer':
                spacer = QFrame()
                spacer.setFrameShape(QFrame.HLine)
                spacer.setFrameShadow(QFrame.Sunken)
                spacer.setStyleSheet(f"background-color: {self.border_color}; margin: 15px 20px;")
                sidebar_layout.addWidget(spacer)
            else:
                btn = QPushButton(text)
                btn.setStyleSheet(f"""
                    QPushButton {{ 
                        text-align: left; padding: 12px 20px; border: none; background-color: transparent; 
                        color: {self.fg_muted}; font-size: 14px; 
                        border-left: 3px solid transparent;
                    }}
                    QPushButton:hover {{ background-color: #ededed; color: {self.fg_color}; }}
                    QPushButton:checked {{ background-color: #e5f1fb; color: {self.accent_color}; border-left: 3px solid {self.accent_color}; font-weight: bold; }}
                """)
                btn.setCheckable(True)
                btn.clicked.connect(lambda checked, k=key: self._handle_nav(k))
                self.nav_buttons[key] = btn
                sidebar_layout.addWidget(btn)
                
        sidebar_layout.addStretch()
        main_layout.addWidget(self.sidebar)
        
        # 2. Content Area
        self.stacked_widget = QStackedWidget()
        main_layout.addWidget(self.stacked_widget, 1)
        
        # -- CREATE PAGES --
        self.pages = {}
        
        # Page 1: Interaction
        interaction_page = QWidget()
        inter_layout = QVBoxLayout(interaction_page)
        inter_layout.setContentsMargins(0,0,0,0)
        
        # Header Info Bar
        info_header = QWidget()
        info_header.setStyleSheet(f"background-color: {self.header_bg}; border-bottom: 1px solid {self.border_color};")
        info_layout = QHBoxLayout(info_header)
        info_layout.setContentsMargins(25, 15, 25, 15)
        
        self.active_user_label = QLabel("Active User: (not set)")
        self.active_user_label.setStyleSheet(f"color: {self.fg_muted}; font-size: 16px;")
        self.debug_mode_label = QLabel("")
        self.debug_mode_label.setStyleSheet(f"color: #e65100; font-size: 12px; font-weight: bold;")
        
        info_layout.addWidget(self.active_user_label)
        info_layout.addStretch()
        info_layout.addWidget(self.debug_mode_label)
        inter_layout.addWidget(info_header)
        
        # Transcript & Trace Tabs
        self.inter_tabs = QTabWidget()
        inter_layout.addWidget(self.inter_tabs, 1)
        
        self.transcript = ExternalTextBrowser()
        self.inter_tabs.addTab(self.transcript, "Chat Transcript")
        
        self.trace_log = ExternalTextBrowser()
        self.trace_log.setStyleSheet(f"background-color: #f0f0f0; border: none; padding: 15px; font-family: Consolas, monospace; font-size: 12px; color: #444444;")
        self.inter_tabs.addTab(self.trace_log, "Runtime Trace")

        self.btn_clear_trace = QPushButton("Clear Trace")
        self.btn_clear_trace.setProperty("flat", "true")
        self.btn_clear_trace.setCursor(Qt.PointingHandCursor)
        self.btn_clear_trace.clicked.connect(self._clear_runtime_trace)
        self.inter_tabs.setCornerWidget(self.btn_clear_trace, Qt.TopRightCorner)
        
        # Status Label
        self.status_label = QLabel("")
        self.status_label.setStyleSheet(f"color: {self.fg_muted}; font-style: italic; padding: 0 20px;")
        inter_layout.addWidget(self.status_label)
        
        # File list frame (hidden initially)
        self.file_list_frame = QWidget()
        self.file_list_layout = QHBoxLayout(self.file_list_frame)
        self.file_list_layout.setContentsMargins(20, 0, 20, 0)
        self.file_list_frame.hide()
        inter_layout.addWidget(self.file_list_frame)
        
        # Tools / Action Bar above input
        self.action_bar = QWidget()
        action_layout = QHBoxLayout(self.action_bar)
        action_layout.setContentsMargins(30, 0, 30, 0)
        
        # Create Agent Button
        self.btn_create_agent = QPushButton("✨ Create an Agent")
        self.btn_create_agent.setProperty("flat", "true")
        self.btn_create_agent.setObjectName("createAgentBtn")
        self.btn_create_agent.setStyleSheet(f"background: none; border: 1px; color: {self.accent_color}; font-size: 14px; font-weight: bold; text-decoration: underline;")
        self.btn_create_agent.setCursor(Qt.PointingHandCursor)
        self.btn_create_agent.clicked.connect(self.open_create_agent_dialog)
        
        action_layout.addWidget(self.btn_create_agent)
        action_layout.addStretch()
        inter_layout.addWidget(self.action_bar)
        
        # Input Area Container
        input_container = QWidget()
        input_layout = QHBoxLayout(input_container)
        input_layout.setContentsMargins(20, 0, 20, 20)

        # Attach Button
        self.btn_attach = QPushButton("+")
        self.btn_attach.setProperty("flat", "true")
        self.btn_attach.setStyleSheet(f"font-size: 24px; color: {self.fg_muted};")
        self.btn_attach.setCursor(Qt.PointingHandCursor)
        self.btn_attach.clicked.connect(self.on_attach_file)
        input_layout.addWidget(self.btn_attach)
        
        # Input Field
        self.input_entry = QLineEdit()
        self.input_entry.setPlaceholderText("Message the agent...")
        self.input_entry.returnPressed.connect(self.on_send)
        input_layout.addWidget(self.input_entry, 1)
        

        # Send Button
        self.btn_send = QPushButton("Send")
        self.btn_send.setObjectName("sendBtn")
        self.btn_send.setStyleSheet(f"background-color: {self.accent_color}; color: white; border-radius: 20px; font-weight: bold; width: 60px; height: 35px;")
        self.btn_send.setCursor(Qt.PointingHandCursor)
        self.btn_send.clicked.connect(self.on_send)
        input_layout.addWidget(self.btn_send)
        
        # Stop Button
        self.btn_stop = QPushButton("Stop")
        self.btn_stop.setObjectName("stopBtn")
        self.btn_stop.setStyleSheet(f"background-color: #d32f2f; color: white; border-radius: 20px; font-weight: bold; width: 60px; height: 35px;")
        self.btn_stop.setCursor(Qt.PointingHandCursor)
        self.btn_stop.clicked.connect(self.on_stop)
        self.btn_stop.hide()
        input_layout.addWidget(self.btn_stop)
        
        inter_layout.addWidget(input_container)
        
        # Permission Frame (Hidden initially)
        self.permission_frame = QFrame()
        self.permission_frame.setStyleSheet(f"background-color: #fff8e1; border: 1px solid #ffe082; margin: 10px 20px; border-radius: 8px;")
        perm_layout = QVBoxLayout(self.permission_frame)
        self.permission_label = QLabel("Permission Required")
        self.permission_label.setWordWrap(True)
        self.permission_label.setStyleSheet("color: #ec407a;")
        perm_layout.addWidget(self.permission_label)
        
        btn_layout = QHBoxLayout()
        btn_yes = QPushButton("Approve")
        btn_yes.setStyleSheet(f"background-color: #4CAF50; color: white; border-radius: 4px; padding: 5px;")
        btn_yes.clicked.connect(lambda: self._resolve_permission(True))
        btn_no = QPushButton("Deny")
        btn_no.setStyleSheet(f"background-color: #f44336; color: white; border-radius: 4px; padding: 5px;")
        btn_no.clicked.connect(lambda: self._resolve_permission(False))
        btn_layout.addWidget(btn_yes)
        btn_layout.addWidget(btn_no)
        btn_layout.addStretch()
        perm_layout.addLayout(btn_layout)
        
        self.permission_frame.hide()
        inter_layout.insertWidget(2, self.permission_frame) # Above input area
        
        self.stacked_widget.addWidget(interaction_page)
        self.pages['interaction'] = interaction_page
        
        # Page 2: History
        history_page = QWidget()
        hist_layout = QVBoxLayout(history_page)
        hist_layout.setContentsMargins(20, 20, 20, 20)
        
        hist_header_layout = QHBoxLayout()
        hist_title = QLabel("Chat History")
        hist_title.setStyleSheet("font-size: 24px; font-weight: bold;")
        hist_btn_refresh = QPushButton("Refresh")
        hist_btn_refresh.clicked.connect(self._refresh_history_list)
        hist_header_layout.addWidget(hist_title)
        hist_header_layout.addStretch()
        hist_header_layout.addWidget(hist_btn_refresh)
        hist_layout.addLayout(hist_header_layout)
        
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; }")
        
        self.history_list_widget = QWidget()
        self.history_list_layout = QVBoxLayout(self.history_list_widget)
        self.history_list_layout.setAlignment(Qt.AlignTop)
        scroll.setWidget(self.history_list_widget)
        hist_layout.addWidget(scroll, 1)
        
        self.stacked_widget.addWidget(history_page)
        self.pages['history'] = history_page

        # Page 3: Sessions
        sessions_page = QWidget()
        sessions_layout = QVBoxLayout(sessions_page)
        sessions_layout.setContentsMargins(20, 20, 20, 20)

        sessions_header = QHBoxLayout()
        sessions_title = QLabel("Active Sessions")
        sessions_title.setStyleSheet("font-size: 24px; font-weight: bold;")
        sessions_header.addWidget(sessions_title)
        sessions_header.addStretch()
        sessions_refresh = QPushButton("Refresh")
        sessions_refresh.clicked.connect(self._refresh_sessions_list)
        sessions_header.addWidget(sessions_refresh)
        sessions_layout.addLayout(sessions_header)
        self.sessions_meta_label = QLabel("")
        self.sessions_meta_label.setStyleSheet(f"color: {self.fg_muted}; font-size: 12px;")
        sessions_layout.addWidget(self.sessions_meta_label)

        self.sessions_splitter = QSplitter(Qt.Horizontal)
        self.sessions_tree = QTreeWidget()
        self.sessions_tree.setHeaderLabels(["User", "Channel", "Last Message"])
        self.sessions_tree.setAlternatingRowColors(True)
        self.sessions_tree.setStyleSheet("QTreeWidget::item { padding: 8px; }")
        self.sessions_tree.header().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.sessions_tree.header().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.sessions_tree.header().setSectionResizeMode(2, QHeaderView.Stretch)
        self.sessions_tree.itemSelectionChanged.connect(self._on_session_select)
        self.sessions_splitter.addWidget(self.sessions_tree)

        self.session_chat_view = QTextBrowser()
        self.session_chat_view.setStyleSheet(
            f"background-color: #f9f9f9; border: 1px solid {self.border_color}; padding: 10px;"
        )
        self.sessions_splitter.addWidget(self.session_chat_view)
        self.sessions_splitter.setSizes([450, 450])
        sessions_layout.addWidget(self.sessions_splitter, 1)

        self.stacked_widget.addWidget(sessions_page)
        self.pages['sessions'] = sessions_page
        
        # Page 4: Logs
        logs_page = QWidget()
        logs_layout = QVBoxLayout(logs_page)
        logs_layout.setContentsMargins(20, 20, 20, 20)
        logs_title = QLabel("System Logs")
        logs_title.setStyleSheet("font-size: 24px; font-weight: bold;")
        logs_layout.addWidget(logs_title)
        self.log_display = QTextBrowser()
        logs_layout.addWidget(self.log_display, 1)
        self.stacked_widget.addWidget(logs_page)
        self.pages['logs'] = logs_page
        
        # Page 5: Settings
        self.settings_panel = SettingsPanel(self, self.cda)
        self.stacked_widget.addWidget(self.settings_panel)
        self.pages['settings'] = self.settings_panel
        
        # --- INIT TASKS ---
        self._refresh_active_user_label()
        self._refresh_debug_mode_label()
        self.nav_buttons['interaction'].setChecked(True)
        
        # Register Core Handlers
        execution_logger.register_log_callback(lambda msg: self.signals.append_log.emit(msg))
        self.cda.set_runtime('executor_trace_handler', self._executor_trace_threadsafe)
        self.cda.set_runtime('executor_permission_handler', self._request_permission_threadsafe)
        self.cda.set_runtime('tool_status_handler', lambda msg: self.signals.update_status.emit(msg))
        
        # Restore pending permission statics
        self._pending_permission_event = None
        self._pending_permission_decision = None
        self._pending_permission_action_type = ""
        self._sessions_timer = QTimer(self)
        self._sessions_timer.setInterval(2000)
        self._sessions_timer.timeout.connect(self._refresh_sessions_list)

    def _is_debug_mode_enabled(self) -> bool:
        settings = config_loader.load_settings()
        return settings.get('debug_mode', False)

    def _init_runtime_trace_file(self) -> str:
        log_dir = Path.cwd() / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        session_id = str(self.cda.get_setting('active_log_session', datetime.now().strftime('%Y%m%d_%H%M%S')))
        path = log_dir / f"runtime_trace_{session_id}.log"
        return str(path)

    def _append_runtime_trace_file(self, text: str) -> None:
        try:
            clean = str(text or "").strip()
            if not clean:
                return
            with open(self._runtime_trace_file, "a", encoding="utf-8") as f:
                f.write(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} {clean}\n")
        except Exception:
            return

    def _refresh_active_user_label(self):
        uid = self.cda.get_setting('current_user_id')
        uname = self.cda.get_setting('current_username')
        if uid and uname:
            self.active_user_label.setText(f"Active User: {uname} (ID: {uid})")
        else:
            self.active_user_label.setText("Active User: (not set)")

    def _refresh_debug_mode_label(self):
        if self._is_debug_mode_enabled():
            self.debug_mode_label.setText("DEBUG MODE ON")
            self.nav_buttons['logs'].show()
        else:
            self.debug_mode_label.setText("")
            self.nav_buttons['logs'].hide()

    def _active_user_id(self) -> str:
        return str(self.cda.get_setting('current_user_id', '') or '')

    def _new_ui_conversation_id(self, chat_id: Optional[int] = None) -> str:
        if chat_id is not None:
            return f"ui:chat:{int(chat_id)}"
        return f"ui:live:{uuid.uuid4().hex}"

    def _handle_ui_completion(self, result: Any) -> None:
        try:
            status = str(getattr(result, 'status', '') or '').strip().lower()
            content = str(getattr(result, 'content', '') or '').strip()
            if content:
                role = 'Error' if status == 'error' else 'Agent'
                self.signals.append_message.emit(role, content)
        finally:
            self.signals.execution_ended.emit()

    def _handle_nav(self, key: str):
        # Update button checks
        for k, btn in self.nav_buttons.items():
            btn.setChecked(k == key)
            
        if key == 'new_chat':
            self._start_new_chat()
        elif key in self.pages:
            self.stacked_widget.setCurrentWidget(self.pages[key])
            if key == 'history':
                self._refresh_history_list()
            elif key == 'sessions':
                self._refresh_sessions_list()
                self._sessions_timer.start()
            elif key == 'settings':
                self._refresh_active_user_label()
                self._refresh_debug_mode_label()
        else:
            self._sessions_timer.stop()

    def _start_new_chat(self) -> None:
        self._current_chat_id = None
        self._conversation_id = self._new_ui_conversation_id()
        self.transcript.clear()
        self._handle_nav('interaction')

    def append_message(self, sender: str, message: str) -> None:
        self.signals.append_message.emit(sender, message)
        
    def _safe_append_message(self, sender: str, message: str) -> None:
        agent_activity = ""
        if sender == 'Agent':
            agent_activity = self.conversation_manager.get_agent_activity(self._conversation_id)
            
        # Save raw message to database before prefixing
        self._save_to_chat_history(sender, message, agent_activity)
        
        color = self.fg_color
        weight = "normal"
        if sender == 'User':
            color = self.accent_color
            weight = "bold"
            message = f"You: {message}"
        elif sender == 'Error':
            color = "#d32f2f"
            message = f"Error: {message}"
        elif sender == 'Status':
            color = self.fg_muted
            message = f"<i>{message}</i>"
        else:
            message = f"<b>Agent:</b><br>{message}"
            
        html = f"<div style='color: {color}; font-weight: {weight}; margin-bottom: 10px;'>{message.replace(chr(10), '<br>')}</div><br>"
        self.transcript.append(html)
        
    def _safe_append_log(self, message: str) -> None:
        self.log_display.append(message)
        self._append_runtime_trace_file(f"[LOG] {message}")

    def _safe_update_status(self, message: str) -> None:
        if message:
            self.status_label.setText(f"? {message}")
        else:
            self.status_label.setText("")

    def _safe_executor_status(self, title: str, body: str) -> None:
        if not title:
            self.trace_log.append(body)
            plain = re.sub(r'<[^>]+>', '', body).replace('&lt;', '<').replace('&gt;', '>')
            self._append_runtime_trace_file(f"[TRACE] {plain}")
            return

        def repl(m):
            raw_path = m.group(1)
            clean_path = raw_path.replace('\\\\', '\\')
            
            # Trim trailing punctuation common in plain English sentences
            while clean_path and clean_path[-1] in '.,;:]}':
                raw_path = raw_path[:-1]
                clean_path = clean_path[:-1]
                
            uri = clean_path.replace('\\', '/')
            if not uri.startswith('/'): uri = '/' + uri
            return f'<a href="file://{uri}" style="color: #005fb8; text-decoration: underline;">{raw_path}</a>'
            
        # Match Windows paths
        body_linked = re.sub(r'([A-Za-z]:(?:\\\\|\\|/)[^\s"\'<>\n\t]+)', repl, body)
        body_linked = body_linked.replace('\n', '<br>')
            
        html = f"<div style='color: {self.fg_muted}; font-size: 12px;'><b>{title}</b><br>{body_linked}</div><br>"
        if 'error' in title.lower() or 'failed' in title.lower():
            html = f"<div style='color: #d32f2f; font-size: 12px;'><b>{title}</b><br>{body_linked}</div><br>"
        self.trace_log.append(html)
        plain = re.sub(r'<[^>]+>', '', f"{title}\n{body}")
        self._append_runtime_trace_file(f"[TRACE] {plain}")

    def _clear_runtime_trace(self) -> None:
        self.trace_log.clear()
        self._append_runtime_trace_file("[TRACE] Cleared from UI")

    def _refresh_sessions_list(self) -> None:
        sel_items = self.sessions_tree.selectedItems()
        selected_key = sel_items[0].text(0) + ":" + sel_items[0].text(1) if sel_items else None
        
        self.sessions_tree.blockSignals(True)
        self.sessions_tree.clear()
        
        raw = self.cda.get_setting('session_engine_enabled', True)
        if isinstance(raw, bool):
            session_engine = raw
        elif isinstance(raw, str):
            session_engine = raw.strip().lower() in ('1', 'true', 'yes', 'on')
        else:
            session_engine = bool(raw)
        try:
            sessions = self.conversation_manager.list_active_sessions()
        except Exception as e:
            self.sessions_meta_label.setText(f"Failed to load sessions: {e}")
            self.session_chat_view.setText(f"Failed to load sessions: {e}")
            self.sessions_tree.blockSignals(False)
            return

        store_count = len(sessions)
        try:
            store_count = int(self.conversation_manager.size())
        except Exception:
            pass
        self.sessions_meta_label.setText(
            f"Session engine: {'ON' if session_engine else 'OFF'} | Active in-memory sessions: {store_count}"
        )

        if not sessions:
            empty = QTreeWidgetItem(["(No active sessions)", "", "Send a message first to create one."])
            self.sessions_tree.addTopLevelItem(empty)
            self.session_chat_view.setText(
                "No active sessions found.\n\n"
                "Notes:\n"
                "- Sessions are in-memory (runtime), not loaded from DB history.\n"
                "- A session is created when a message is handled by Controller."
            )
            self.sessions_tree.blockSignals(False)
            return

        for sess in sessions:
            user = str(sess.get("user", "") or sess.get("user_id", "") or "unknown")
            channel = str(sess.get("channel", "") or "")
            last_msg = str(sess.get("last_message", "") or "")
            if len(last_msg) > 120:
                last_msg = last_msg[:117] + "..."
            item = QTreeWidgetItem([user, channel, last_msg])
            item.setData(0, Qt.UserRole, sess)
            self.sessions_tree.addTopLevelItem(item)
            
            if selected_key and (user + ":" + channel) == selected_key:
                item.setSelected(True)
                
        self.sessions_tree.blockSignals(False)
        self._on_session_select()

    def _on_session_select(self) -> None:
        items = self.sessions_tree.selectedItems()
        if not items:
            self.session_chat_view.clear()
            return
        sess = items[0].data(0, Qt.UserRole) or {}
        chat_history = str(sess.get("chat_history", "") or "")
        if not chat_history:
            self.session_chat_view.setText("(No chat history in this session)")
            return
            
        scrollbar = self.session_chat_view.verticalScrollBar()
        was_at_bottom = scrollbar.value() >= (scrollbar.maximum() - 5) if scrollbar else True
            
        self.session_chat_view.setText(chat_history)
        
        if was_at_bottom and scrollbar:
            scrollbar.setValue(scrollbar.maximum())

    def on_attach_file(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(self, "Attach Files", "", "All Files (*.*)")
        if files:
            self.selected_files.extend(files)
            self._refresh_file_list()

    def _refresh_file_list(self) -> None:
        # Clear existing
        while self.file_list_layout.count():
            child = self.file_list_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
                
        if not self.selected_files:
            self.file_list_frame.hide()
            return
            
        self.file_list_frame.show()
        
        for f in self.selected_files:
            chip = QFrame()
            chip.setStyleSheet(f"background-color: #e0e0e0; border-radius: 12px; padding: 2px 8px;")
            chip_layout = QHBoxLayout(chip)
            chip_layout.setContentsMargins(5,2,5,2)
            name = os.path.basename(f)
            lbl = QLabel(name)
            lbl.setStyleSheet(f"color: {self.fg_color}; font-size: 12px;")
            
            btn_x = QPushButton("x")
            btn_x.setStyleSheet(f"background: none; border: none; color: #d32f2f; font-weight: bold;")
            btn_x.setCursor(Qt.PointingHandCursor)
            btn_x.clicked.connect(lambda checked=False, target=f: self._remove_file(target))
            
            chip_layout.addWidget(lbl)
            chip_layout.addWidget(btn_x)
            self.file_list_layout.addWidget(chip)
            
        self.file_list_layout.addStretch()

    def _remove_file(self, target: str):
        if target in self.selected_files:
            self.selected_files.remove(target)
            self._refresh_file_list()

    def open_create_agent_dialog(self):
        dialog = CreateAgentDialog(self)
        
        # Load draft
        draft = self.cda.get_setting('create_agent_draft')
        if draft:
            dialog.text_edit.setPlainText(str(draft))
            
        if dialog.exec():
            if dialog.is_draft:
                self.cda.set_setting('create_agent_draft', dialog.result_text)
                self.append_message('Status', "<i>Agent requirements draft saved.</i>")
            else:
                self.cda.set_setting('create_agent_draft', "") # clear draft
                text = dialog.result_text
                if text:
                    prefix = "Create an agent or Modify an agent"
                    final_prompt = f"{prefix}:\\n{text}"
                    self.input_entry.setText(final_prompt)
                    self.on_send()

    def on_send(self) -> None:
        message = self.input_entry.text().strip()
        if not message and not self.selected_files:
            return

        self.input_entry.clear()

        if message:
            self.append_message('User', message)

        if self.selected_files:
            docs_msg = f"Attached {len(self.selected_files)} document(s)."
            if message:
                docs_msg += " " + message
            if not message:
                self.append_message('User', f"<i>Attached {len(self.selected_files)} document(s)</i>")
            message = docs_msg

        files_to_send = list(self.selected_files)
        self.selected_files.clear()
        self.file_list_frame.hide()

        self.signals.execution_started.emit()
        try:
            self.conversation_manager.submit(
                InboundRequest(
                    conversation_id=self._conversation_id,
                    interface='UI',
                    user_id=self._active_user_id(),
                    message=message,
                    files=files_to_send,
                    ui_callback=self._ui_feedback,
                    status_callback=lambda status: self.signals.update_status.emit(str(status or '')),
                    trace_callback=self._executor_trace_threadsafe,
                    permission_callback=self._request_permission_threadsafe,
                    completion_callback=self._handle_ui_completion,
                )
            )
        except Exception as e:
            execution_logger.log_exception('CONTROLLER_FAIL', e)
            self.append_message('Error', f"System error: {e}")
            self.signals.execution_ended.emit()

    def on_stop(self) -> None:
        if self.conversation_manager.cancel(self._conversation_id):
            self.append_message('Status', "<i>Cancellation requested...</i>")

    def closeEvent(self, event) -> None:  # noqa: N802
        try:
            wa_service = self.cda.get_runtime('whatsapp_channel_service')
            if wa_service:
                wa_service.stop()
                self.cda.set_runtime('whatsapp_channel_service', None)
            tg_service = self.cda.get_runtime('telegram_channel_service')
            if tg_service:
                tg_service.stop()
                self.cda.set_runtime('telegram_channel_service', None)
        except Exception:
            pass
        super().closeEvent(event)
            
    def _on_execution_started(self) -> None:
        self.btn_send.hide()
        self.btn_stop.show()
        self.input_entry.setEnabled(False)
        self.btn_attach.setEnabled(False)
        if hasattr(self, 'history_list_widget'):
            self.history_list_widget.setEnabled(False)

    def _on_execution_ended(self) -> None:
        self.btn_stop.hide()
        self.btn_send.show()
        self.input_entry.setEnabled(True)
        self.btn_attach.setEnabled(True)
        if hasattr(self, 'history_list_widget'):
            self.history_list_widget.setEnabled(True)
        self.input_entry.setFocus()

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

    def _insert_linked_trace_html(self, text: str, filepath: str = "", tag: str = 'default') -> None:
        colors = {
            'default': '#444444',
            'llm_input': '#005fb8',      # Blue
            'llm_output': '#2e7d32',     # Green
            'tool_call': '#e65100',      # Orange
            'tool_result': '#00838f',    # Teal
            'permission': '#f57f17',     # Yellow/Orange
            'error': '#d32f2f',          # Red
            'status': '#757575'          # Gray
        }
        color = colors.get(tag, colors['default'])
        
        # Escape HTML chars in text to prevent bleeding, except for BRs
        cleaned_text = text.replace('<', '&lt;').replace('>', '&gt;').replace('\n', '<br>')
        
        # Base formatting
        if tag == 'status':
            html_block = f"<div style='color: {color}; font-style: italic; margin-bottom: 2px;'>{cleaned_text}"
        elif tag == 'error':
            html_block = f"<div style='color: {color}; font-weight: bold; margin-bottom: 5px; background-color: #ffebee; padding: 5px;'>{cleaned_text}"
        else:
            html_block = f"<div style='color: {color}; font-weight: 500; margin-bottom: 5px;'>{cleaned_text}"
            
        # Add filepath if present
        if filepath:
            uri = filepath.replace('\\\\', '\\').replace('\\', '/')
            if not uri.startswith('/'): uri = '/' + uri
            
            import os
            display_name = os.path.basename(filepath)
            html_block += f" <a href='file://{uri}' style='color: #005fb8; text-decoration: underline;'>[Link: {display_name}]</a>"
            
        html_block += "</div>"
        self.signals.executor_status.emit("", html_block)

    def _executor_trace_threadsafe(self, event_type: str, payload: Dict[str, Any]) -> None:
        if not hasattr(self, '_trace_counter'):
            self._trace_counter = 1

        if event_type == 'user_input':
            self._trace_counter = 1
            self._insert_linked_trace_html(f"\n{'-'*60}\n1. User input received")
            self._trace_counter += 1

        elif event_type == 'llm_prepared_prompt':
            agent = payload.get('agent_name', 'Agent')
            fp = payload.get('filepath', '')
            self._insert_linked_trace_html(f"{self._trace_counter}. {agent} Prompt prepared", fp, 'llm_input')
            self._trace_counter += 1
            self._insert_linked_trace_html(f"{self._trace_counter}. LLM request in progress", tag='status')

        elif event_type == 'llm_response':
            tt = payload.get('time_taken', 0)
            tu = payload.get('tokens_used', 0)
            fp = payload.get('response_file', '')
            self._insert_linked_trace_html(f"  {self._trace_counter}.1. LLM call completed: Time {tt:.2f}s, Tokens used: {tu}", tag='status')
            self._trace_counter += 1
            self._insert_linked_trace_html(f"{self._trace_counter}. LLM response", fp, 'llm_output')
            self._trace_counter += 1

        elif event_type == 'plan_step':
            agent = payload.get('agent_name', 'Agent')
            step = str(payload.get('current_step', '')).strip()
            self._insert_linked_trace_html(f"{self._trace_counter}. {agent} executing step: {step}", tag='status')
            self._trace_counter += 1

        elif event_type == 'tool_prepared':
            tn = payload.get('tool_name', 'Unknown')
            fp = payload.get('param_file', '')
            self._insert_linked_trace_html(f"{self._trace_counter}. Tool call in progress: {tn}", fp, 'tool_call')
            self._trace_counter += 1
            
        elif event_type == 'tool_result':
            tn = payload.get('tool_name', 'Unknown')
            fp = payload.get('result_file', '')
            self._insert_linked_trace_html(f"{self._trace_counter}. Tool call completed results: {tn}", fp, 'tool_result')
            self._trace_counter += 1

        elif event_type == 'permission_required':
            ts = datetime.now().strftime('%H:%M:%S')
            title = f"[{ts}] PERMISSION REQUIRED"
            action_type = payload.get('action_type', 'unknown')
            body = f"Action: {action_type}"
            self._insert_linked_trace_html(f"{title}\n{body}", tag='permission')

        elif event_type == 'permission_decision':
            ts = datetime.now().strftime('%H:%M:%S')
            title = f"[{ts}] PERMISSION DECISION"
            body = f"Action: {payload.get('action_type', 'unknown')}\nApproved: {payload.get('approved', False)}"
            self._insert_linked_trace_html(f"{title}\n{body}", tag='permission')

        elif event_type == 'router_summary':
            selected = payload.get('selected_targets', [])
            selected_txt = ", ".join([str(x) for x in selected]) if selected else "(none)"
            self._insert_linked_trace_html(f"{self._trace_counter}. Router selected: {selected_txt}", tag='llm_output')
            self._trace_counter += 1

        elif event_type == 'router_decision':
            # Keep router decision concise
            selected = payload.get('selected_targets', [])
            types = payload.get('decision_types', [])
            selected_txt = ", ".join([str(x) for x in selected]) if selected else "(none)"
            types_txt = ", ".join([str(x) for x in types]) if types else "(unknown)"
            self._insert_linked_trace_html(f"{self._trace_counter}. Router decision: {types_txt} -> {selected_txt}", tag='llm_output')
            self._trace_counter += 1

        elif event_type == 'controller_task_queue':
            queue_size = payload.get('queue_size', 0)
            routes = payload.get('routes', [])
            targets = []
            for r in routes if isinstance(routes, list) else []:
                if not isinstance(r, dict): continue
                t = r.get('selected_agent') or r.get('tool_name') or r.get('type')
                if t: targets.append(str(t))
            targets_txt = ", ".join(targets) if targets else "(none)"
            self._insert_linked_trace_html(f"{self._trace_counter}. Controller queued {queue_size} task(s): {targets_txt}", tag='default')
            self._trace_counter += 1

        elif event_type == 'controller_delegate_agent':
            agent = payload.get('agent_name', 'unknown')
            self._insert_linked_trace_html(f"{self._trace_counter}. Delegating to agent: {agent}", tag='default')
            self._trace_counter += 1

        elif event_type == 'request_user_input':
            agent = payload.get('agent_name', 'Agent')
            content = str(payload.get('content', '')).strip()
            short = (content[:140] + '...') if len(content) > 140 else content
            self._insert_linked_trace_html(f"{self._trace_counter}. {agent} requested user input: {short}", tag='status')
            self._trace_counter += 1

        elif event_type == 'router_trace_file':
            phase = str(payload.get('phase', '')).strip().lower()
            fp = payload.get('filepath', '')
            label = "Router prompt file" if phase == 'prompt' else "Router response file"
            self._insert_linked_trace_html(f"{self._trace_counter}. {label}", fp, 'llm_input')
            self._trace_counter += 1

        elif 'error' in event_type.lower():
            ts = datetime.now().strftime('%H:%M:%S')
            title = f"[{ts}] ERROR: {event_type}"
            try:
                body = json.dumps(payload, indent=2, ensure_ascii=False)
            except:
                body = str(payload)
            self._insert_linked_trace_html(f"{title}\n{body}", tag='error')

        else:
            ts = datetime.now().strftime('%H:%M:%S')
            title = f"[{ts}] {event_type.upper()}"
            try:
                body = json.dumps(payload, indent=2, ensure_ascii=False)
            except:
                body = str(payload)
            self._insert_linked_trace_html(f"{title}\n{body}", tag='default')

    def _request_permission_threadsafe(self, action_type: str, payload: Dict[str, Any]) -> bool:
        if not self._is_debug_mode_enabled():
            return True

        decision = {'allow': False}
        event = threading.Event()
        
        self.signals.request_permission.emit(action_type, payload, event, decision)
        event.wait()
        return decision['allow']

    def _safe_request_permission(self, action_type, payload, event, decision):
        self._pending_permission_event = event
        self._pending_permission_decision = decision
        self._pending_permission_action_type = action_type
        
        params = ""
        if 'parameters' in payload:
             params = json.dumps(payload['parameters'], indent=2)
             
        self.permission_label.setText(f"<b>Approve Action: {action_type}</b><br><pre>{params}</pre>")
        self.permission_frame.show()
        self._handle_nav('interaction')
        self.append_message('Status', f"Approval required for {action_type}. Click Approve/Deny above input area.")

    def _resolve_permission(self, allow: bool) -> None:
        if self._pending_permission_decision is None or self._pending_permission_event is None:
            return
            
        self._pending_permission_decision['allow'] = bool(allow)
        self.append_message('Status', f"[debug] Action {self._pending_permission_action_type} {'approved' if allow else 'denied'}")
        
        self.permission_frame.hide()
        pending_event = self._pending_permission_event
        self._pending_permission_event = None
        self._pending_permission_decision = None
        self._pending_permission_action_type = ""
        pending_event.set()

    def _save_to_chat_history(self, role: str, content: str, agent_activity: str = "") -> None:
        if role == 'Status' or not content.strip():
            return
            
        db_path = _get_db_path()
        if not db_path or not os.path.exists(db_path):
            return
            
        try:
            conn = sqlite3.connect(db_path)
            cur = conn.cursor()
            user_id = str(self.cda.get_setting('current_user_id', '') or '')
            interface = 'UI'
            cur.execute("PRAGMA table_info(ChatHistory)")
            ch_cols = [row[1] for row in cur.fetchall()]
            cur.execute("PRAGMA table_info(ChatLog)")
            cl_cols = [row[1] for row in cur.fetchall()]
            
            if self._current_chat_id is None:
                title = content[:50].strip()
                if not title:
                    title = "New Chat"
                if 'user_id' in ch_cols and 'interface' in ch_cols:
                    cur.execute(
                        "INSERT INTO ChatHistory (title, agent_activity, user_id, interface) VALUES (?, ?, ?, ?)",
                        (title, agent_activity, user_id, interface),
                    )
                elif 'user_id' in ch_cols:
                    cur.execute(
                        "INSERT INTO ChatHistory (title, agent_activity, user_id) VALUES (?, ?, ?)",
                        (title, agent_activity, user_id),
                    )
                else:
                    cur.execute("INSERT INTO ChatHistory (title, agent_activity) VALUES (?, ?)", (title, agent_activity))
                self._current_chat_id = cur.lastrowid
            else:
                if agent_activity:
                    cur.execute("UPDATE ChatHistory SET agent_activity = ? WHERE id = ?", (agent_activity, self._current_chat_id))
                
            if 'user_id' in cl_cols and 'interface' in cl_cols:
                cur.execute(
                    "INSERT INTO ChatLog (chat_id, role, content, user_id, interface) VALUES (?, ?, ?, ?, ?)",
                    (self._current_chat_id, role, content, user_id, interface),
                )
            elif 'user_id' in cl_cols:
                cur.execute(
                    "INSERT INTO ChatLog (chat_id, role, content, user_id) VALUES (?, ?, ?, ?)",
                    (self._current_chat_id, role, content, user_id),
                )
            else:
                cur.execute("INSERT INTO ChatLog (chat_id, role, content) VALUES (?, ?, ?)", 
                            (self._current_chat_id, role, content))
            conn.commit()
            conn.close()
        except Exception as e:
            execution_logger.log_execution_step('CHAT_DB_ERROR', f"Failed to save chat: {e}")

    @staticmethod
    def _format_history_timestamp(created_at: Any) -> str:
        raw = str(created_at or "").strip()
        if not raw:
            return ""

        local_tz = datetime.now().astimezone().tzinfo
        candidates = [
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d %H:%M:%S.%f",
        ]

        for fmt in candidates:
            try:
                parsed = datetime.strptime(raw, fmt).replace(tzinfo=timezone.utc)
                return parsed.astimezone(local_tz).strftime("%Y-%m-%d %H:%M:%S")
            except ValueError:
                continue

        try:
            iso_value = raw.replace("Z", "+00:00")
            parsed = datetime.fromisoformat(iso_value)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(local_tz).strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            return raw

    def _refresh_history_list(self) -> None:
        # Clear specific layout
        while self.history_list_layout.count():
            child = self.history_list_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
                
        db_path = _get_db_path()
        if not db_path or not os.path.exists(db_path):
            lbl = QLabel("No Database Path Available.")
            self.history_list_layout.addWidget(lbl)
            self.history_list_layout.addStretch()
            return

        try:
            conn = sqlite3.connect(db_path)
            cur = conn.cursor()
            user_id = str(self.cda.get_setting('current_user_id', '') or '')
            cur.execute("PRAGMA table_info(ChatHistory)")
            ch_cols = [row[1] for row in cur.fetchall()]
            has_interface = 'interface' in ch_cols
            if 'user_id' in ch_cols and user_id:
                select_cols = "id, title, created_at, interface" if has_interface else "id, title, created_at, '' as interface"
                cur.execute(
                    f"SELECT {select_cols} FROM ChatHistory WHERE user_id = ? OR user_id IS NULL OR user_id = '' ORDER BY created_at DESC LIMIT 50",
                    (user_id,),
                )
            else:
                select_cols = "id, title, created_at, interface" if has_interface else "id, title, created_at, '' as interface"
                cur.execute(f"SELECT {select_cols} FROM ChatHistory ORDER BY created_at DESC LIMIT 50")
            rows = cur.fetchall()
            conn.close()
            
            for row in rows:
                chat_id, title, created_at, iface = row
                
                card = QPushButton()
                card.setStyleSheet(f"""
                    QPushButton {{
                        background-color: {self.bg_color};
                        border: 1px solid {self.border_color};
                        border-radius: 8px;
                        text-align: left;
                        padding: 15px;
                    }}
                    QPushButton:hover {{ background-color: {self.sidebar_bg}; }}
                """)
                card.setCursor(Qt.PointingHandCursor)
                
                # We can't use layout directly on QPushButton easily without breaking clicks in some configs,
                # so we use rich text or just text, or build a widget and handle mouse events.
                # In PySide6, QPushButton doesn't render HTML via setText, so we compose it with a layout:
                card_layout = QHBoxLayout(card)
                card_layout.setContentsMargins(15, 10, 15, 10)
                
                title_lbl = QLabel(f"<b>{title or 'New Chat'}</b>")
                title_lbl.setAttribute(Qt.WA_TransparentForMouseEvents)
                title_lbl.setStyleSheet("border: none; background: transparent; padding: 0;")
                
                channel = str(iface or "UI").strip() or "UI"
                display_created_at = self._format_history_timestamp(created_at)
                time_lbl = QLabel(f"{display_created_at}  [{channel}]")
                time_lbl.setAttribute(Qt.WA_TransparentForMouseEvents)
                time_lbl.setStyleSheet(f"color: {self.fg_muted}; font-size: 11px; border: none; background: transparent; padding: 0;")
                
                card_layout.addWidget(title_lbl)
                card_layout.addStretch()
                card_layout.addWidget(time_lbl)
                card.clicked.connect(lambda checked=False, cid=chat_id: self._load_history_chat(cid))
                
                self.history_list_layout.addWidget(card)
                
            self.history_list_layout.addStretch()
                
        except Exception as e:
            execution_logger.log_execution_step('HISTORY_ERROR', f"Failed to load history: {e}")
            lbl = QLabel(f"Error loading history: {e}")
            self.history_list_layout.addWidget(lbl)
            self.history_list_layout.addStretch()

    def _load_history_chat(self, chat_id: int) -> None:
        self._current_chat_id = chat_id
        self._conversation_id = self._new_ui_conversation_id(chat_id)
        self.transcript.clear()
        
        history_text = ""
        db_path = _get_db_path()
        if not db_path or not os.path.exists(db_path): return
        
        try:
            conn = sqlite3.connect(db_path)
            cur = conn.cursor()
            user_id = str(self.cda.get_setting('current_user_id', '') or '')
            res = None
            
            # Fetch agent_activity from parent ChatHistory record safely
            cur.execute("PRAGMA table_info(ChatHistory)")
            ch_cols = [col[1] for col in cur.fetchall()]
            latest_agent_activity = ""
            if 'agent_activity' in ch_cols and 'user_id' in ch_cols and user_id:
                cur.execute(
                    "SELECT agent_activity FROM ChatHistory WHERE id=? AND (user_id = ? OR user_id IS NULL OR user_id = '')",
                    (chat_id, user_id),
                )
                res = cur.fetchone()
                if not res:
                    conn.close()
                    execution_logger.log_execution_step('HISTORY_LOAD_DENY', f"Chat {chat_id} not accessible for user_id={user_id}")
                    return
            elif 'agent_activity' in ch_cols:
                cur.execute("SELECT agent_activity FROM ChatHistory WHERE id=?", (chat_id,))
                res = cur.fetchone()
                if res and res[0]:
                    latest_agent_activity = res[0]
            if 'agent_activity' in ch_cols and res and res[0]:
                latest_agent_activity = res[0]
            
            cur.execute("PRAGMA table_info(ChatLog)")
            cl_cols = [col[1] for col in cur.fetchall()]
            if 'user_id' in cl_cols and user_id:
                cur.execute(
                    "SELECT role, content FROM ChatLog WHERE chat_id=? AND (user_id = ? OR user_id IS NULL OR user_id = '') ORDER BY timestamp ASC",
                    (chat_id, user_id),
                )
            else:
                cur.execute("SELECT role, content FROM ChatLog WHERE chat_id=? ORDER BY timestamp ASC", (chat_id,))
            rows = cur.fetchall()
            conn.close()
            
            for role, content in rows:
                # Add to UI without triggering db save
                color = self.fg_color
                weight = "normal"
                if role == 'User':
                    color = self.accent_color
                    weight = "bold"
                    display_msg = f"You: {content}"
                elif role == 'Error':
                    color = "#d32f2f"
                    display_msg = f"Error: {content}"
                elif role == 'Status':
                    continue # Ignore status messages
                else:
                    display_msg = f"<b>Agent:</b><br>{content}"
                    
                html = f"<div style='color: {color}; font-weight: {weight}; margin-bottom: 10px;'>{display_msg.replace(chr(10), '<br>')}</div><br>"
                self.transcript.append(html)
                
                # Rebuild history context
                prefix = "User: " if role == 'User' else "Agent: "
                history_text += f"{prefix}{content}\n"
                
            self.conversation_manager.hydrate_ui_history(
                self._conversation_id,
                self._active_user_id(),
                history_text,
                latest_agent_activity,
                chat_id,
            )
            self._handle_nav('interaction')
                
        except Exception as e:
            execution_logger.log_execution_step('HISTORY_LOAD_ERROR', f"Failed to load chat {chat_id}: {e}")
            
        self._handle_nav('interaction')




