"""Settings UI for configuring LLM, directories, agents, roles, and users in PySide6."""

from __future__ import annotations

import json
import sqlite3
import re
import base64
from typing import List, Tuple, Any, Dict
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTabWidget, QLabel, 
    QLineEdit, QPushButton, QComboBox, QCheckBox, QTreeWidget, 
    QTreeWidgetItem, QScrollArea, QGroupBox, QFileDialog, QMessageBox,
    QGridLayout, QFrame, QSplitter, QTextEdit, QSizePolicy, QSlider,
    QDialog, QListWidget, QListWidgetItem, QHeaderView, QSpinBox
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap

from core.common_data_area import CommonDataArea
from core.scheduler_agent import validate_schedule_request, compute_next_run
from settings import config_loader
from agents.registry import list_agents, register_agent, get_agent, _get_db_path
from tools.tool_registry import list_tools, list_tool_metadata, sync_tools_to_db

class SettingsPanel(QWidget):
    def __init__(self, parent: QWidget | None = None, cda: CommonDataArea | None = None) -> None:
        super().__init__(parent)
        self.cda = cda or CommonDataArea()
        
        # --- WHITE THEME CONFIGURATION ---
        self.bg_color = '#ffffff'
        self.fg_color = '#333333'
        self.accent_color = '#005fb8'
        self.panel_bg = '#f9f9f9'
        self.border_color = '#e0e0e0'
        
        self.setStyleSheet(f"""
            QWidget {{ background-color: {self.bg_color}; color: {self.fg_color}; font-family: 'Segoe UI'; font-size: 13px; }}
            QTabWidget::pane {{ border: 1px solid {self.border_color}; background: {self.bg_color}; }}
            QTabBar::tab {{ background: {self.panel_bg}; border: 1px solid {self.border_color}; padding: 8px 15px; margin-right: 2px; }}
            QTabBar::tab:selected {{ background: {self.bg_color}; border-bottom-color: {self.bg_color}; font-weight: bold; color: {self.accent_color}; }}
            QGroupBox {{ font-weight: bold; border: 1px solid {self.border_color}; border-radius: 5px; margin-top: 15px; background-color: {self.panel_bg}; }}
            QGroupBox::title {{ subcontrol-origin: margin; left: 10px; padding: 0 5px; color: {self.accent_color}; }}
            QLineEdit, QComboBox, QSpinBox, QTextEdit {{ background: #ffffff; border: 1px solid {self.border_color}; border-radius: 4px; padding: 5px; }}
            QPushButton {{ background-color: {self.panel_bg}; border: 1px solid {self.border_color}; border-radius: 4px; padding: 6px 15px; }}
            QPushButton:hover {{ background-color: #ededed; }}
            QPushButton#primaryAction {{ background-color: {self.accent_color}; color: white; font-weight: bold; border: none; }}
            QPushButton#primaryAction:hover {{ background-color: #004488; }}
            QTreeWidget {{ border: 1px solid {self.border_color}; background-color: #ffffff; alternate-background-color: #fafafa; }}
            QHeaderView::section {{ background-color: {self.panel_bg}; border: 1px solid {self.border_color}; font-weight: bold; padding: 4px; }}
        """)
        
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

        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        
        self.notebook = QTabWidget()
        layout.addWidget(self.notebook)

        self._create_general_tab()
        self._create_ai_tab()
        self._create_agents_tab()
        self._create_roles_tab()
        self._create_users_tab()
        self._create_tools_tab()
        self._create_telegram_tab()
        self._create_whatsapp_tab()
        self._create_scheduler_tab()

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
            cur.execute("""
                CREATE TABLE IF NOT EXISTS AgentPromptVersion (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    agent_id INTEGER NOT NULL,
                    agent_name TEXT,
                    prompt_content TEXT,
                    version INTEGER NOT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cur.execute("PRAGMA table_info(AgentPromptVersion)")
            cols = {row[1] for row in cur.fetchall()}
            if 'agent_name' not in cols:
                cur.execute("ALTER TABLE AgentPromptVersion ADD COLUMN agent_name TEXT")
            conn.commit()
        finally:
            conn.close()

    # ==========================
    # GENERAL TAB
    # ==========================
    def _create_general_tab(self) -> None:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setAlignment(Qt.AlignTop)
        
        # Database Group
        db_group = QGroupBox("Data Storage")
        db_layout = QGridLayout(db_group)
        db_layout.addWidget(QLabel("SQLite Database Path:"), 0, 0)
        self.db_path_edit = QLineEdit(self.settings.get('sqlite_db_path', 'backend.db'))
        db_layout.addWidget(self.db_path_edit, 0, 1)
        btn_db = QPushButton("Browse...")
        btn_db.clicked.connect(lambda: self._browse_file(self.db_path_edit, "Select Database File", "SQLite DB (*.db);;All Files (*.*)"))
        db_layout.addWidget(btn_db, 0, 2)
        
        db_layout.addWidget(QLabel("File Storage Path:"), 1, 0)
        self.storage_path_edit = QLineEdit(self.settings.get('file_storage_path', 'storage/files'))
        db_layout.addWidget(self.storage_path_edit, 1, 1)
        btn_storage = QPushButton("Browse...")
        btn_storage.clicked.connect(lambda: self._browse_dir(self.storage_path_edit, "Select Storage Directory"))
        db_layout.addWidget(btn_storage, 1, 2)
        layout.addWidget(db_group)
        
        # Debug Group
        debug_group = QGroupBox("Execution Debugging")
        debug_layout = QVBoxLayout(debug_group)
        self.debug_mode_check = QCheckBox("Enable debug approvals (ask permission for each tool/LLM step)")
        self.debug_mode_check.setChecked(bool(self.settings.get('debug_mode', False)))
        debug_layout.addWidget(self.debug_mode_check)

        activity_row = QHBoxLayout()
        activity_row.addWidget(QLabel("Agent Activity Context:"))
        self.activity_level_combo = QComboBox()
        self.activity_level_combo.addItems(["Full Activity", "Partial Activity (save tokens)"])
        current_level = str(self.settings.get('agent_activity_level', 'full') or 'full').strip().lower()
        self.activity_level_combo.setCurrentIndex(1 if current_level == 'partial' else 0)
        activity_row.addWidget(self.activity_level_combo)
        activity_row.addStretch()
        debug_layout.addLayout(activity_row)

        partial_row = QHBoxLayout()
        self.partial_keep_steps_label = QLabel("Partial mode: keep full details for last N steps:")
        partial_row.addWidget(self.partial_keep_steps_label)
        self.partial_keep_steps_spin = QSpinBox()
        self.partial_keep_steps_spin.setRange(1, 200)
        self.partial_keep_steps_spin.setValue(int(self.settings.get('agent_activity_partial_keep_steps', 5) or 5))
        partial_row.addWidget(self.partial_keep_steps_spin)
        partial_row.addStretch()
        debug_layout.addLayout(partial_row)
        self.activity_level_combo.currentIndexChanged.connect(self._on_activity_level_changed)
        self._on_activity_level_changed()
        layout.addWidget(debug_group)
        
        # Environment Group
        env_group = QGroupBox("Environment Constraints")
        env_layout = QVBoxLayout(env_group)
        
        d_layout = QHBoxLayout()
        d_layout.addWidget(QLabel("Default Working Directory:"))
        self.default_dir_edit = QLineEdit(self.settings.get('default_directory', ''))
        d_layout.addWidget(self.default_dir_edit)
        env_layout.addLayout(d_layout)
        
        env_layout.addWidget(QLabel("Whitelisted Directories (Security Sandbox):"))
        self.accessible_text = QTextEdit()
        self.accessible_text.setFixedHeight(100)
        dirs = self.settings.get('accessible_directories', []) or []
        self.accessible_text.setPlainText('\n'.join(dirs))
        env_layout.addWidget(self.accessible_text)
        layout.addWidget(env_group)

        # Save Action
        layout.addStretch()
        action_layout = QHBoxLayout()
        action_layout.addStretch()
        btn_save = QPushButton("Save & Apply Changes")
        btn_save.setObjectName("primaryAction")
        btn_save.clicked.connect(self._save_general)
        action_layout.addWidget(btn_save)
        layout.addLayout(action_layout)
        
        self.notebook.addTab(tab, "System Settings")

    def _create_telegram_tab(self) -> None:
        tab = QWidget()
        layout = QVBoxLayout(tab)

        tg_group = QGroupBox("Telegram Channel Integration (Polling)")
        tg_layout = QVBoxLayout(tg_group)

        status_row = QHBoxLayout()
        self.telegram_status_label = QLabel("Status: unknown")
        status_row.addWidget(self.telegram_status_label, 1)

        btn_tg_status = QPushButton("Refresh Status")
        btn_tg_status.clicked.connect(self._tg_refresh_status)
        status_row.addWidget(btn_tg_status)

        btn_tg_restart = QPushButton("Restart Polling")
        btn_tg_restart.clicked.connect(self._tg_restart_polling)
        status_row.addWidget(btn_tg_restart)
        tg_layout.addLayout(status_row)

        adv_layout = QGridLayout()
        self.telegram_enabled_check = QCheckBox("Enable Telegram polling integration")
        self.telegram_enabled_check.setChecked(bool(self.settings.get('telegram_enabled', False)))
        adv_layout.addWidget(self.telegram_enabled_check, 0, 0, 1, 3)

        adv_layout.addWidget(QLabel("Bot Token:"), 1, 0)
        self.telegram_bot_token_edit = QLineEdit(self.settings.get('telegram_bot_token', ''))
        self.telegram_bot_token_edit.setEchoMode(QLineEdit.Password)
        adv_layout.addWidget(self.telegram_bot_token_edit, 1, 1, 1, 2)

        adv_layout.addWidget(QLabel("Poll Timeout (seconds):"), 2, 0)
        self.telegram_poll_timeout_edit = QLineEdit(str(self.settings.get('telegram_poll_timeout', 25)))
        adv_layout.addWidget(self.telegram_poll_timeout_edit, 2, 1, 1, 2)

        adv_layout.addWidget(QLabel("Retry Delay (seconds):"), 3, 0)
        self.telegram_poll_retry_edit = QLineEdit(str(self.settings.get('telegram_poll_retry_seconds', 2)))
        adv_layout.addWidget(self.telegram_poll_retry_edit, 3, 1, 1, 2)

        adv_layout.addWidget(QLabel("Test Chat ID:"), 4, 0)
        self.telegram_test_chat_id_edit = QLineEdit(self.settings.get('telegram_test_chat_id', ''))
        adv_layout.addWidget(self.telegram_test_chat_id_edit, 4, 1, 1, 2)

        adv_layout.addWidget(QLabel("Test Message:"), 5, 0)
        self.telegram_test_message_edit = QLineEdit(
            self.settings.get('telegram_test_message', 'Hello from Desktop Agentic System')
        )
        adv_layout.addWidget(self.telegram_test_message_edit, 5, 1)
        btn_tg_test_send = QPushButton("Send Test")
        btn_tg_test_send.clicked.connect(self._tg_send_test)
        adv_layout.addWidget(btn_tg_test_send, 5, 2)

        tg_layout.addLayout(adv_layout)
        layout.addWidget(tg_group)

        layout.addStretch()
        action_layout = QHBoxLayout()
        action_layout.addStretch()
        btn_save = QPushButton("Save & Apply Changes")
        btn_save.setObjectName("primaryAction")
        btn_save.clicked.connect(self._save_general)
        action_layout.addWidget(btn_save)
        layout.addLayout(action_layout)

        self.notebook.addTab(tab, "Telgram")

    def _create_whatsapp_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        # WhatsApp Channel Group
        wa_group = QGroupBox("WhatsApp Channel Integration")
        wa_layout = QVBoxLayout(wa_group)

        status_row = QHBoxLayout()
        self.whatsapp_status_label = QLabel("Status: unknown")
        status_row.addWidget(self.whatsapp_status_label, 1)
        btn_wa_status = QPushButton("Refresh Status")
        btn_wa_status.clicked.connect(self._wa_refresh_status)
        status_row.addWidget(btn_wa_status)

        btn_wa_qr = QPushButton("Show QR")
        btn_wa_qr.clicked.connect(self._wa_show_qr)
        status_row.addWidget(btn_wa_qr)

        btn_wa_disconnect = QPushButton("Disconnect")
        btn_wa_disconnect.clicked.connect(self._wa_disconnect)
        status_row.addWidget(btn_wa_disconnect)
        wa_layout.addLayout(status_row)

        self.whatsapp_qr_label = QLabel("QR not loaded")
        self.whatsapp_qr_label.setAlignment(Qt.AlignCenter)
        self.whatsapp_qr_label.setFixedSize(240, 240)
        self.whatsapp_qr_label.setStyleSheet("border: 1px solid #d0d0d0; background-color: #ffffff;")
        wa_layout.addWidget(self.whatsapp_qr_label, alignment=Qt.AlignLeft)

        self.wa_advanced_toggle = QPushButton("Advanced Settings")
        self.wa_advanced_toggle.setCheckable(True)
        self.wa_advanced_toggle.setChecked(False)
        self.wa_advanced_toggle.toggled.connect(self._wa_toggle_advanced)
        wa_layout.addWidget(self.wa_advanced_toggle, alignment=Qt.AlignLeft)

        self.wa_advanced_widget = QWidget()
        adv_layout = QGridLayout(self.wa_advanced_widget)
        adv_layout.setContentsMargins(0, 4, 0, 0)

        self.whatsapp_enabled_check = QCheckBox("Enable WhatsApp channel integration")
        self.whatsapp_enabled_check.setChecked(bool(self.settings.get('whatsapp_enabled', False)))
        adv_layout.addWidget(self.whatsapp_enabled_check, 0, 0, 1, 3)

        self.whatsapp_auto_start_check = QCheckBox("Auto-start local WhatsApp gateway process")
        self.whatsapp_auto_start_check.setChecked(bool(self.settings.get('whatsapp_auto_start_gateway', False)))
        adv_layout.addWidget(self.whatsapp_auto_start_check, 1, 0, 1, 3)

        adv_layout.addWidget(QLabel("Gateway URL:"), 2, 0)
        self.whatsapp_gateway_url_edit = QLineEdit(self.settings.get('whatsapp_gateway_url', 'http://127.0.0.1:5715'))
        adv_layout.addWidget(self.whatsapp_gateway_url_edit, 2, 1, 1, 2)

        adv_layout.addWidget(QLabel("Gateway Command:"), 3, 0)
        self.whatsapp_gateway_command_edit = QLineEdit(self.settings.get('whatsapp_gateway_command', 'node whatsapp-gateway/src/server.js'))
        adv_layout.addWidget(self.whatsapp_gateway_command_edit, 3, 1, 1, 2)

        adv_layout.addWidget(QLabel("Webhook Host:"), 4, 0)
        self.whatsapp_webhook_host_edit = QLineEdit(self.settings.get('whatsapp_webhook_host', '127.0.0.1'))
        adv_layout.addWidget(self.whatsapp_webhook_host_edit, 4, 1, 1, 2)

        adv_layout.addWidget(QLabel("Webhook Port:"), 5, 0)
        self.whatsapp_webhook_port_edit = QLineEdit(str(self.settings.get('whatsapp_webhook_port', 5716)))
        adv_layout.addWidget(self.whatsapp_webhook_port_edit, 5, 1, 1, 2)

        adv_layout.addWidget(QLabel("Webhook Secret:"), 6, 0)
        self.whatsapp_webhook_secret_edit = QLineEdit(self.settings.get('whatsapp_webhook_secret', 'change-me'))
        adv_layout.addWidget(self.whatsapp_webhook_secret_edit, 6, 1, 1, 2)

        adv_layout.addWidget(QLabel("Test To (JID):"), 7, 0)
        self.whatsapp_test_to_edit = QLineEdit(self.settings.get('whatsapp_test_to', ''))
        adv_layout.addWidget(self.whatsapp_test_to_edit, 7, 1, 1, 2)

        adv_layout.addWidget(QLabel("Test Message:"), 8, 0)
        self.whatsapp_test_message_edit = QLineEdit(self.settings.get('whatsapp_test_message', 'Hello from Desktop Agentic System'))
        adv_layout.addWidget(self.whatsapp_test_message_edit, 8, 1)
        btn_wa_test_send = QPushButton("Send Test")
        btn_wa_test_send.clicked.connect(self._wa_send_test)
        adv_layout.addWidget(btn_wa_test_send, 8, 2)

        self.wa_advanced_widget.setVisible(False)
        wa_layout.addWidget(self.wa_advanced_widget)

        layout.addWidget(wa_group)
        
        # Save Action
        layout.addStretch()
        action_layout = QHBoxLayout()
        action_layout.addStretch()
        btn_save = QPushButton("Save & Apply Changes")
        btn_save.setObjectName("primaryAction")
        btn_save.clicked.connect(self._save_general)
        action_layout.addWidget(btn_save)
        layout.addLayout(action_layout)
        
        self.notebook.addTab(tab, "WhatsApp")

    def _wa_toggle_advanced(self, visible: bool) -> None:
        self.wa_advanced_widget.setVisible(bool(visible))

    def _browse_file(self, edit_widget, title, filters):
        filename, _ = QFileDialog.getOpenFileName(self, title, "", filters)
        if filename:
            edit_widget.setText(filename)
            
    def _browse_dir(self, edit_widget, title):
        directory = QFileDialog.getExistingDirectory(self, title)
        if directory:
            edit_widget.setText(directory)

    def _refresh_embedding_status_label(self) -> None:
        model_name = self.embedding_model_name_edit.text().strip() or "jinaai/jina-embeddings-v3"
        text = f"Active model: {model_name} (fixed)"
        self.embedding_status_label.setText(text)

    def _on_activity_level_changed(self) -> None:
        partial_mode = self.activity_level_combo.currentIndex() == 1
        self.partial_keep_steps_label.setVisible(partial_mode)
        self.partial_keep_steps_spin.setVisible(partial_mode)

    def _wa_refresh_status(self) -> None:
        svc = self.cda.get_runtime('whatsapp_channel_service')
        if svc is None:
            self.whatsapp_status_label.setText("Status: service not initialized")
            return
        try:
            st = svc.get_gateway_status()
            connected = bool(st.get('connected', False))
            err = str(st.get('error', '') or '')
            if connected:
                self.whatsapp_status_label.setText("Status: connected")
            elif err:
                self.whatsapp_status_label.setText(f"Status: disconnected ({err})")
            else:
                self.whatsapp_status_label.setText("Status: disconnected")
        except Exception as e:
            self.whatsapp_status_label.setText(f"Status: error ({e})")

    def _wa_send_test(self) -> None:
        svc = self.cda.get_runtime('whatsapp_channel_service')
        if svc is None:
            QMessageBox.warning(self, "WhatsApp", "WhatsApp service not initialized.")
            return
        to = self.whatsapp_test_to_edit.text().strip()
        text = self.whatsapp_test_message_edit.text().strip()
        if not to or not text:
            QMessageBox.warning(self, "WhatsApp", "Provide both Test To and Test Message.")
            return
        result = svc.send_text(to, text)
        if bool(result.get('success', False)):
            QMessageBox.information(self, "WhatsApp", "Test message sent.")
        else:
            QMessageBox.warning(self, "WhatsApp", f"Send failed: {result.get('error', result)}")

    def _wa_show_qr(self) -> None:
        svc = self.cda.get_runtime('whatsapp_channel_service')
        if svc is None:
            QMessageBox.warning(self, "WhatsApp", "WhatsApp service not initialized.")
            return
        data = svc.get_gateway_qr()
        qr_data_url = str(data.get('qr_data_url', '') or '')
        has_qr = bool(data.get('has_qr', False))
        if not has_qr or not qr_data_url:
            self.whatsapp_qr_label.setText("No QR available\n(Already connected or gateway not ready)")
            return

        if "," not in qr_data_url:
            self.whatsapp_qr_label.setText("Invalid QR payload")
            return
        try:
            b64 = qr_data_url.split(",", 1)[1]
            raw = base64.b64decode(b64)
            pixmap = QPixmap()
            if not pixmap.loadFromData(raw):
                self.whatsapp_qr_label.setText("Failed to render QR")
                return
            self.whatsapp_qr_label.setPixmap(
                pixmap.scaled(
                    self.whatsapp_qr_label.width() - 8,
                    self.whatsapp_qr_label.height() - 8,
                    Qt.KeepAspectRatio,
                    Qt.SmoothTransformation,
                )
            )
        except Exception as e:
            self.whatsapp_qr_label.setText(f"QR error: {e}")

    def _wa_disconnect(self) -> None:
        svc = self.cda.get_runtime('whatsapp_channel_service')
        if svc is None:
            QMessageBox.warning(self, "WhatsApp", "WhatsApp service not initialized.")
            return
        result = svc.disconnect()
        if bool(result.get('success', False)):
            self.whatsapp_status_label.setText("Status: disconnected")
            self.whatsapp_qr_label.setText("Disconnected\nClick Show QR to pair again")
            self.whatsapp_qr_label.setPixmap(QPixmap())
            QMessageBox.information(self, "WhatsApp", "Disconnected successfully.")
        else:
            QMessageBox.warning(self, "WhatsApp", f"Disconnect failed: {result.get('error', result)}")

    def _tg_refresh_status(self) -> None:
        svc = self.cda.get_runtime('telegram_channel_service')
        if svc is None:
            self.telegram_status_label.setText("Status: service not initialized")
            return
        try:
            st = svc.get_status()
            running = bool(st.get('running', False))
            err = str(st.get('last_error', '') or '')
            if running:
                self.telegram_status_label.setText("Status: polling")
            elif err:
                self.telegram_status_label.setText(f"Status: stopped ({err})")
            else:
                self.telegram_status_label.setText("Status: stopped")
        except Exception as e:
            self.telegram_status_label.setText(f"Status: error ({e})")

    def _tg_restart_polling(self) -> None:
        svc = self.cda.get_runtime('telegram_channel_service')
        if svc is None:
            QMessageBox.warning(self, "Telegram", "Telegram service not initialized.")
            return
        try:
            svc.restart()
            self._tg_refresh_status()
            QMessageBox.information(self, "Telegram", "Polling restarted.")
        except Exception as e:
            QMessageBox.warning(self, "Telegram", f"Restart failed: {e}")

    def _tg_send_test(self) -> None:
        svc = self.cda.get_runtime('telegram_channel_service')
        if svc is None:
            QMessageBox.warning(self, "Telegram", "Telegram service not initialized.")
            return
        chat_id = self.telegram_test_chat_id_edit.text().strip()
        text = self.telegram_test_message_edit.text().strip()
        if not chat_id or not text:
            QMessageBox.warning(self, "Telegram", "Provide both Test Chat ID and Test Message.")
            return
        result = svc.send_text(chat_id, text)
        if bool(result.get('ok', False)):
            QMessageBox.information(self, "Telegram", "Test message sent.")
        else:
            QMessageBox.warning(self, "Telegram", f"Send failed: {result.get('error', result)}")

    # ==========================
    # SCHEDULER TAB
    # ==========================
    def _create_scheduler_tab(self) -> None:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        status_group = QGroupBox("Scheduler Service")
        status_layout = QHBoxLayout(status_group)
        self.scheduler_status_label = QLabel("Status: unknown")
        status_layout.addWidget(self.scheduler_status_label, 1)
        btn_status = QPushButton("Refresh Status")
        btn_status.clicked.connect(self._scheduler_refresh_status)
        status_layout.addWidget(btn_status)
        btn_restart = QPushButton("Restart Scheduler")
        btn_restart.clicked.connect(self._scheduler_restart)
        status_layout.addWidget(btn_restart)
        layout.addWidget(status_group)

        cfg_group = QGroupBox("Execution Settings")
        cfg_layout = QGridLayout(cfg_group)
        cfg_layout.setColumnStretch(1, 1)
        self.scheduler_enabled_check = QCheckBox("Enable scheduler service")
        self.scheduler_enabled_check.setChecked(bool(self.settings.get("scheduler_enabled", False)))
        cfg_layout.addWidget(self.scheduler_enabled_check, 0, 0, 1, 2)
        cfg_layout.addWidget(QLabel("Poll frequency (minutes):"), 1, 0)
        self.scheduler_poll_minutes_spin = QSpinBox()
        self.scheduler_poll_minutes_spin.setRange(1, 1440)
        self.scheduler_poll_minutes_spin.setValue(int(self.settings.get("scheduler_poll_minutes", 1) or 1))
        cfg_layout.addWidget(self.scheduler_poll_minutes_spin, 1, 1)
        layout.addWidget(cfg_group)

        self.scheduler_workspace_tabs = QTabWidget()
        self.scheduler_workspace_tabs.setDocumentMode(True)
        self.scheduler_workspace_tabs.setUsesScrollButtons(False)
        self.scheduler_workspace_tabs.setElideMode(Qt.ElideRight)
        self.scheduler_workspace_tabs.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        self.scheduler_list_tab_index = 0
        self.scheduler_create_tab_index = 1
        self.scheduler_editor_tab_index = 2

        list_tab = QWidget()
        list_layout_main = QVBoxLayout(list_tab)
        list_group = QGroupBox("Schedules")
        list_layout = QVBoxLayout(list_group)
        self.scheduler_tree = QTreeWidget()
        self.scheduler_tree.setHeaderLabels(["ID", "Title", "Type", "Next Run", "Enabled", "Task Prompt"])
        self.scheduler_tree.setAlternatingRowColors(True)
        self.scheduler_tree.itemSelectionChanged.connect(self._scheduler_on_select)
        self.scheduler_tree.header().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.scheduler_tree.header().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.scheduler_tree.header().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.scheduler_tree.header().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.scheduler_tree.header().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self.scheduler_tree.header().setSectionResizeMode(5, QHeaderView.Stretch)
        list_layout.addWidget(self.scheduler_tree)
        list_btns = QHBoxLayout()
        btn_refresh = QPushButton("Refresh List")
        btn_refresh.clicked.connect(self._scheduler_refresh_list)
        list_btns.addWidget(btn_refresh)
        btn_new_from_list = QPushButton("New Schedule")
        btn_new_from_list.clicked.connect(self._scheduler_new_from_list)
        list_btns.addWidget(btn_new_from_list)
        btn_delete = QPushButton("Delete")
        btn_delete.clicked.connect(self._scheduler_delete_schedule)
        list_btns.addWidget(btn_delete)
        list_btns.addStretch()
        list_layout.addLayout(list_btns)
        list_layout_main.addWidget(list_group)

        create_tab = QWidget()
        create_layout_main = QVBoxLayout(create_tab)
        create_layout_main.setContentsMargins(0, 0, 0, 0)
        create_layout_main.setSpacing(12)

        create_group = QGroupBox("Create From Natural Language")
        create_layout = QVBoxLayout(create_group)
        create_hint = QLabel("Describe the schedule in plain language. Validate fills the editor; Validate + Create saves it immediately.")
        create_hint.setWordWrap(True)
        create_layout.addWidget(create_hint)
        self.scheduler_nl_edit = QTextEdit()
        self.scheduler_nl_edit.setPlaceholderText(
            "Example:\n"
            "Schedule to send reminder for all users about their weekly tasks on Tuesday and Thursday.\n"
            "Also update task status every Monday morning at 9."
        )
        self.scheduler_nl_edit.setMinimumHeight(260)
        self.scheduler_nl_edit.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        create_layout.addWidget(self.scheduler_nl_edit, 1)

        create_actions = QHBoxLayout()
        btn_create_back = QPushButton("Back To List")
        btn_create_back.clicked.connect(self._scheduler_back_to_list)
        create_actions.addWidget(btn_create_back)
        create_actions.addStretch()
        btn_validate = QPushButton("Validate")
        btn_validate.clicked.connect(self._scheduler_validate_nl)
        create_actions.addWidget(btn_validate)
        btn_create_nl = QPushButton("Validate + Create")
        btn_create_nl.clicked.connect(self._scheduler_create_from_nl)
        create_actions.addWidget(btn_create_nl)
        create_layout.addLayout(create_actions)
        create_layout_main.addWidget(create_group)

        editor_tab = QWidget()
        editor_layout_main = QVBoxLayout(editor_tab)
        editor_layout_main.setContentsMargins(0, 0, 0, 0)
        editor_layout_main.setSpacing(12)

        editor_scroll = QScrollArea()
        editor_scroll.setWidgetResizable(True)
        editor_scroll.setFrameShape(QFrame.NoFrame)

        editor_scroll_widget = QWidget()
        editor_scroll_layout = QVBoxLayout(editor_scroll_widget)
        editor_scroll_layout.setContentsMargins(0, 0, 0, 0)

        editor_group = QGroupBox("Schedule Editor")
        editor_group.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.MinimumExpanding)
        editor_layout = QGridLayout(editor_group)
        editor_layout.setVerticalSpacing(12)
        editor_layout.setHorizontalSpacing(15)
        editor_layout.setColumnMinimumWidth(0, 160)
        editor_layout.setColumnMinimumWidth(2, 160)
        editor_layout.setColumnStretch(1, 1)
        editor_layout.setColumnStretch(3, 1)
        self.scheduler_id_label = QLabel("New")
        editor_layout.addWidget(QLabel("Schedule ID:"), 0, 0)
        editor_layout.addWidget(self.scheduler_id_label, 0, 1)

        editor_layout.addWidget(QLabel("Title:"), 1, 0)
        self.scheduler_title_edit = QLineEdit()
        editor_layout.addWidget(self.scheduler_title_edit, 1, 1, 1, 3)

        editor_layout.addWidget(QLabel("Task Prompt:"), 2, 0)
        self.scheduler_task_edit = QTextEdit()
        self.scheduler_task_edit.setMinimumHeight(120)
        self.scheduler_task_edit.setMaximumHeight(180)
        self.scheduler_task_edit.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.MinimumExpanding)
        editor_layout.addWidget(self.scheduler_task_edit, 2, 1, 1, 3)

        editor_layout.addWidget(QLabel("Type:"), 3, 0)
        self.scheduler_type_combo = QComboBox()
        self.scheduler_type_combo.addItems(["hourly", "daily", "weekly", "monthly", "other"])
        editor_layout.addWidget(self.scheduler_type_combo, 3, 1)

        editor_layout.addWidget(QLabel("Interval (minutes):"), 3, 2)
        self.scheduler_interval_spin = QSpinBox()
        self.scheduler_interval_spin.setRange(0, 100000)
        self.scheduler_interval_spin.setValue(60)
        editor_layout.addWidget(self.scheduler_interval_spin, 3, 3)

        editor_layout.addWidget(QLabel("Hour:"), 4, 0)
        self.scheduler_hour_spin = QSpinBox()
        self.scheduler_hour_spin.setRange(0, 23)
        self.scheduler_hour_spin.setValue(9)
        editor_layout.addWidget(self.scheduler_hour_spin, 4, 1)

        editor_layout.addWidget(QLabel("Minute:"), 4, 2)
        self.scheduler_minute_spin = QSpinBox()
        self.scheduler_minute_spin.setRange(0, 59)
        self.scheduler_minute_spin.setValue(0)
        editor_layout.addWidget(self.scheduler_minute_spin, 4, 3)

        editor_layout.addWidget(QLabel("Weekday (0=Mon):"), 5, 0)
        self.scheduler_dow_spin = QSpinBox()
        self.scheduler_dow_spin.setRange(0, 6)
        self.scheduler_dow_spin.setValue(0)
        editor_layout.addWidget(self.scheduler_dow_spin, 5, 1)

        editor_layout.addWidget(QLabel("Day of month:"), 5, 2)
        self.scheduler_dom_spin = QSpinBox()
        self.scheduler_dom_spin.setRange(1, 31)
        self.scheduler_dom_spin.setValue(1)
        editor_layout.addWidget(self.scheduler_dom_spin, 5, 3)

        self.scheduler_row_enabled_check = QCheckBox("Enabled")
        self.scheduler_row_enabled_check.setChecked(True)
        editor_layout.addWidget(self.scheduler_row_enabled_check, 6, 0, 1, 1)

        btn_run_now = QPushButton("Run Now")
        btn_run_now.clicked.connect(self._scheduler_run_now)
        editor_layout.addWidget(btn_run_now, 6, 1)

        btn_save = QPushButton("Save Schedule")
        btn_save.setObjectName("primaryAction")
        btn_save.clicked.connect(self._scheduler_save_schedule)
        editor_layout.addWidget(btn_save, 6, 2, 1, 2)

        editor_layout.addWidget(QLabel("Last Run:"), 7, 0)
        self.scheduler_last_run_label = QLabel("Never")
        self.scheduler_last_run_label.setWordWrap(True)
        editor_layout.addWidget(self.scheduler_last_run_label, 7, 1, 1, 3)

        editor_layout.addWidget(QLabel("Last Result:"), 8, 0)
        self.scheduler_last_result_edit = QTextEdit()
        self.scheduler_last_result_edit.setReadOnly(True)
        self.scheduler_last_result_edit.setMinimumHeight(120)
        self.scheduler_last_result_edit.setMaximumHeight(220)
        self.scheduler_last_result_edit.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.MinimumExpanding)
        editor_layout.addWidget(self.scheduler_last_result_edit, 8, 1, 1, 3)

        editor_actions = QHBoxLayout()
        btn_back_list = QPushButton("Back To List")
        btn_back_list.clicked.connect(self._scheduler_back_to_list)
        editor_actions.addWidget(btn_back_list)

        btn_new_schedule = QPushButton("New Schedule")
        btn_new_schedule.clicked.connect(self._scheduler_new_from_list)
        editor_actions.addWidget(btn_new_schedule)

        btn_delete_editor = QPushButton("Delete This Schedule")
        btn_delete_editor.clicked.connect(self._scheduler_delete_schedule)
        editor_actions.addWidget(btn_delete_editor)
        editor_actions.addStretch()

        editor_scroll_layout.addWidget(editor_group)
        editor_scroll_layout.addStretch()
        editor_scroll.setWidget(editor_scroll_widget)

        editor_layout_main.addWidget(editor_scroll, 1)
        editor_layout_main.addLayout(editor_actions)

        self.scheduler_workspace_tabs.addTab(list_tab, "Schedule List")
        self.scheduler_workspace_tabs.addTab(create_tab, "Create Schedule")
        self.scheduler_workspace_tabs.addTab(editor_tab, "Schedule Editor")
        self.scheduler_workspace_tabs.setCurrentIndex(self.scheduler_list_tab_index)
        layout.addWidget(self.scheduler_workspace_tabs, 1)

        action_layout = QHBoxLayout()
        action_layout.addStretch()
        btn_apply = QPushButton("Save & Apply Changes")
        btn_apply.setObjectName("primaryAction")
        btn_apply.clicked.connect(self._save_general)
        action_layout.addWidget(btn_apply)
        layout.addLayout(action_layout)

        self.notebook.addTab(tab, "Scheduler")
        self._scheduler_refresh_status()
        self._scheduler_refresh_list()
        self._scheduler_clear_form(clear_nl=True)

    def _scheduler_refresh_status(self) -> None:
        svc = self.cda.get_runtime("scheduler_service")
        if svc is None:
            self.scheduler_status_label.setText("Status: service not initialized")
            return
        try:
            st = svc.get_status()
            running = bool(st.get("running", False))
            err = str(st.get("last_error", "") or "")
            if running:
                self.scheduler_status_label.setText(f"Status: running (poll={st.get('poll_minutes', '?')}m)")
            elif err:
                self.scheduler_status_label.setText(f"Status: stopped ({err})")
            else:
                self.scheduler_status_label.setText("Status: stopped")
        except Exception as e:
            self.scheduler_status_label.setText(f"Status: error ({e})")

    def _scheduler_restart(self) -> None:
        svc = self.cda.get_runtime("scheduler_service")
        if svc is None:
            QMessageBox.warning(self, "Scheduler", "Scheduler service not initialized.")
            return
        try:
            svc.restart()
            self._scheduler_refresh_status()
            QMessageBox.information(self, "Scheduler", "Scheduler restarted.")
        except Exception as e:
            QMessageBox.warning(self, "Scheduler", f"Restart failed: {e}")

    def _scheduler_validate_nl(self) -> None:
        req = self.scheduler_nl_edit.toPlainText().strip()
        if not req:
            QMessageBox.warning(self, "Scheduler", "Enter a schedule request.")
            return
        parsed = validate_schedule_request(req, cda=self.cda)
        if not bool(parsed.get("is_valid", False)):
            QMessageBox.warning(self, "Scheduler Validation", f"Invalid schedule: {parsed.get('reason', 'Unknown reason')}")
            return
        self._scheduler_fill_from_parsed(parsed)
        self.scheduler_workspace_tabs.setCurrentIndex(self.scheduler_editor_tab_index)
        QMessageBox.information(self, "Scheduler Validation", "Schedule request is valid and form has been prefilled.")

    def _scheduler_create_from_nl(self) -> None:
        req = self.scheduler_nl_edit.toPlainText().strip()
        if not req:
            QMessageBox.warning(self, "Scheduler", "Enter a schedule request.")
            return
        parsed = validate_schedule_request(req, cda=self.cda)
        if not bool(parsed.get("is_valid", False)):
            QMessageBox.warning(self, "Scheduler Validation", f"Invalid schedule: {parsed.get('reason', 'Unknown reason')}")
            return
        self._scheduler_fill_from_parsed(parsed)
        confirm = QMessageBox.question(
            self,
            "Create Schedule",
            f"Create schedule '{parsed.get('title', 'Scheduled Task')}'?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes,
        )
        if confirm != QMessageBox.Yes:
            return
        self._scheduler_insert_row(nl_request=req)
        self._scheduler_refresh_list()
        self.scheduler_workspace_tabs.setCurrentIndex(self.scheduler_list_tab_index)
        QMessageBox.information(self, "Scheduler", "Schedule created.")

    def _scheduler_fill_from_parsed(self, parsed: Dict[str, Any]) -> None:
        self.scheduler_title_edit.setText(str(parsed.get("title", "") or "Scheduled Task"))
        self.scheduler_task_edit.setPlainText(str(parsed.get("task_prompt", "") or ""))
        stype = str(parsed.get("schedule_type", "other") or "other")
        idx = self.scheduler_type_combo.findText(stype)
        self.scheduler_type_combo.setCurrentIndex(idx if idx >= 0 else 4)
        self.scheduler_interval_spin.setValue(int(parsed.get("interval_minutes", 0) or 0))
        self.scheduler_hour_spin.setValue(int(parsed.get("run_hour", 9) or 9))
        self.scheduler_minute_spin.setValue(int(parsed.get("run_minute", 0) or 0))
        self.scheduler_dow_spin.setValue(int(parsed.get("run_day_of_week", 0) or 0))
        self.scheduler_dom_spin.setValue(int(parsed.get("run_day_of_month", 1) or 1))
        self.scheduler_row_enabled_check.setChecked(True)

    def _scheduler_insert_row(self, nl_request: str = "") -> None:
        title = self.scheduler_title_edit.text().strip() or "Scheduled Task"
        task_prompt = self.scheduler_task_edit.toPlainText().strip()
        if not task_prompt:
            QMessageBox.warning(self, "Scheduler", "Task prompt is required.")
            return
        payload = {
            "schedule_type": self.scheduler_type_combo.currentText().strip().lower(),
            "interval_minutes": int(self.scheduler_interval_spin.value()),
            "run_hour": int(self.scheduler_hour_spin.value()),
            "run_minute": int(self.scheduler_minute_spin.value()),
            "run_day_of_week": int(self.scheduler_dow_spin.value()),
            "run_day_of_month": int(self.scheduler_dom_spin.value()),
        }
        next_run = compute_next_run(payload, now=None).strftime("%Y-%m-%d %H:%M:%S")
        conn = self._get_conn()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO Schedules (
                    title, nl_request, task_prompt, schedule_type, interval_minutes,
                    run_hour, run_minute, run_day_of_week, run_day_of_month,
                    is_enabled, status, next_run_at, owner, created_by
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, ?, ?)
                """,
                (
                    title,
                    str(nl_request or "").strip(),
                    task_prompt,
                    payload["schedule_type"],
                    payload["interval_minutes"],
                    payload["run_hour"],
                    payload["run_minute"],
                    payload["run_day_of_week"],
                    payload["run_day_of_month"],
                    1 if self.scheduler_row_enabled_check.isChecked() else 0,
                    next_run,
                    str(self.settings.get("current_user_id", "") or ""),
                    str(self.settings.get("current_user_id", "") or ""),
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def _scheduler_update_row(self, schedule_id: int) -> None:
        title = self.scheduler_title_edit.text().strip() or "Scheduled Task"
        task_prompt = self.scheduler_task_edit.toPlainText().strip()
        if not task_prompt:
            QMessageBox.warning(self, "Scheduler", "Task prompt is required.")
            return
        payload = {
            "schedule_type": self.scheduler_type_combo.currentText().strip().lower(),
            "interval_minutes": int(self.scheduler_interval_spin.value()),
            "run_hour": int(self.scheduler_hour_spin.value()),
            "run_minute": int(self.scheduler_minute_spin.value()),
            "run_day_of_week": int(self.scheduler_dow_spin.value()),
            "run_day_of_month": int(self.scheduler_dom_spin.value()),
        }
        next_run = compute_next_run(payload, now=None).strftime("%Y-%m-%d %H:%M:%S")
        conn = self._get_conn()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                UPDATE Schedules
                SET title=?, task_prompt=?, schedule_type=?, interval_minutes=?, run_hour=?, run_minute=?,
                    run_day_of_week=?, run_day_of_month=?, is_enabled=?, next_run_at=?, updated_at=CURRENT_TIMESTAMP
                WHERE id=?
                """,
                (
                    title,
                    task_prompt,
                    payload["schedule_type"],
                    payload["interval_minutes"],
                    payload["run_hour"],
                    payload["run_minute"],
                    payload["run_day_of_week"],
                    payload["run_day_of_month"],
                    1 if self.scheduler_row_enabled_check.isChecked() else 0,
                    next_run,
                    str(self.settings.get("current_user_id", "") or ""),                    int(schedule_id),
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def _scheduler_refresh_list(self) -> None:
        self.scheduler_tree.clear()
        conn = self._get_conn()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT id, title, schedule_type, next_run_at, is_enabled, task_prompt, nl_request,
                       interval_minutes, run_hour, run_minute, run_day_of_week, run_day_of_month,
                       last_run_at, last_result
                FROM Schedules
                ORDER BY id DESC
                LIMIT 1000
                """
            )
            rows = cur.fetchall()
            for row in rows:
                sid = str(row[0])
                item = QTreeWidgetItem(
                    [
                        sid,
                        str(row[1] or ""),
                        str(row[2] or ""),
                        str(row[3] or ""),
                        "Yes" if int(row[4] or 0) else "No",
                        str(row[5] or ""),
                    ]
                )
                item.setData(0, Qt.UserRole, tuple(row))
                self.scheduler_tree.addTopLevelItem(item)
        except Exception as e:
            self.scheduler_tree.addTopLevelItem(
                QTreeWidgetItem(["", "Failed to load schedules", "", "", "", str(e)])
            )
        finally:
            conn.close()

    def _scheduler_on_select(self) -> None:
        items = self.scheduler_tree.selectedItems()
        if not items:
            return
        row = items[0].data(0, Qt.UserRole)
        if not row:
            return
        self.scheduler_id_label.setText(str(row[0]))
        self.scheduler_title_edit.setText(str(row[1] or ""))
        stype = str(row[2] or "other")
        idx = self.scheduler_type_combo.findText(stype)
        self.scheduler_type_combo.setCurrentIndex(idx if idx >= 0 else 4)
        self.scheduler_row_enabled_check.setChecked(bool(int(row[4] or 0)))
        self.scheduler_task_edit.setPlainText(str(row[5] or ""))
        self.scheduler_nl_edit.setPlainText(str(row[6] or ""))
        self.scheduler_interval_spin.setValue(int(row[7] or 0))
        self.scheduler_hour_spin.setValue(int(row[8] or 0))
        self.scheduler_minute_spin.setValue(int(row[9] or 0))
        self.scheduler_dow_spin.setValue(int(row[10] or 0))
        self.scheduler_dom_spin.setValue(int(row[11] or 1))
        self.scheduler_last_run_label.setText(str(row[12] or "Never"))
        self.scheduler_last_result_edit.setPlainText(str(row[13] or "No runs yet."))
        self.scheduler_workspace_tabs.setCurrentIndex(self.scheduler_editor_tab_index)

    def _scheduler_clear_form(self, clear_nl: bool = True) -> None:
        self.scheduler_id_label.setText("New")
        self.scheduler_title_edit.clear()
        self.scheduler_task_edit.clear()
        if clear_nl:
            self.scheduler_nl_edit.clear()
        self.scheduler_type_combo.setCurrentText("other")
        self.scheduler_interval_spin.setValue(60)
        self.scheduler_hour_spin.setValue(9)
        self.scheduler_minute_spin.setValue(0)
        self.scheduler_dow_spin.setValue(0)
        self.scheduler_dom_spin.setValue(1)
        self.scheduler_row_enabled_check.setChecked(True)
        self.scheduler_last_run_label.setText("Never")
        self.scheduler_last_result_edit.setPlainText("No runs yet.")
        self.scheduler_tree.clearSelection()

    def _scheduler_run_now(self) -> None:
        sid_text = self.scheduler_id_label.text().strip()
        if not sid_text or sid_text.lower() == "new":
            QMessageBox.warning(self, "Scheduler", "Save the schedule before running it.")
            return

        svc = self.cda.get_runtime("scheduler_service")
        if svc is None:
            QMessageBox.warning(self, "Scheduler", "Scheduler service not initialized.")
            return

        try:
            result = svc.run_schedule_now(int(sid_text))
        except Exception as e:
            QMessageBox.warning(self, "Scheduler", f"Run failed: {e}")
            return

        self.scheduler_last_run_label.setText(str(result.get("last_run_at") or "Never"))
        self.scheduler_last_result_edit.setPlainText(str(result.get("last_result") or ""))
        self._scheduler_refresh_list()
        QMessageBox.information(self, "Scheduler", "Schedule executed. Latest result loaded in the editor.")

    def _scheduler_save_schedule(self) -> None:
        sid_text = self.scheduler_id_label.text().strip()
        if sid_text and sid_text.lower() != "new":
            try:
                self._scheduler_update_row(int(sid_text))
            except Exception as e:
                QMessageBox.warning(self, "Scheduler", f"Update failed: {e}")
                return
        else:
            try:
                self._scheduler_insert_row(nl_request=self.scheduler_nl_edit.toPlainText().strip())
            except Exception as e:
                QMessageBox.warning(self, "Scheduler", f"Create failed: {e}")
                return
        self._scheduler_refresh_list()
        self.scheduler_workspace_tabs.setCurrentIndex(self.scheduler_list_tab_index)
        QMessageBox.information(self, "Scheduler", "Schedule saved.")

    def _scheduler_delete_schedule(self) -> None:
        sid_text = self.scheduler_id_label.text().strip()
        if not sid_text or sid_text.lower() == "new":
            selected = self.scheduler_tree.selectedItems()
            if not selected:
                QMessageBox.warning(self, "Scheduler", "Select a schedule to delete.")
                return
            row = selected[0].data(0, Qt.UserRole)
            if not row:
                QMessageBox.warning(self, "Scheduler", "Select a valid schedule to delete.")
                return
            sid_text = str(row[0])
        confirm = QMessageBox.question(
            self,
            "Delete Schedule",
            f"Delete schedule #{sid_text}?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if confirm != QMessageBox.Yes:
            return
        conn = self._get_conn()
        try:
            cur = conn.cursor()
            cur.execute("DELETE FROM Schedules WHERE id=?", (int(sid_text),))
            conn.commit()
        finally:
            conn.close()
        self._scheduler_clear_form(clear_nl=False)
        self._scheduler_refresh_list()
        self.scheduler_workspace_tabs.setCurrentIndex(self.scheduler_list_tab_index)
        QMessageBox.information(self, "Scheduler", "Schedule deleted.")

    def _scheduler_new_from_list(self) -> None:
        self._scheduler_clear_form(clear_nl=True)
        self.scheduler_workspace_tabs.setCurrentIndex(self.scheduler_create_tab_index)

    def _scheduler_back_to_list(self) -> None:
        self.scheduler_workspace_tabs.setCurrentIndex(self.scheduler_list_tab_index)

    # ==========================
    # AI TAB
    # ==========================
    def _create_ai_tab(self) -> None:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setAlignment(Qt.AlignTop)
        
        # Provider Group
        prov_group = QGroupBox("Active LLM Provider")
        prov_layout = QHBoxLayout(prov_group)
        
        self.provider_combo = QComboBox()
        self.provider_combo.addItems(["Google Gemini", "Local LLM (LM Studio/Ollama)", "OpenRouter"])
        
        current_prov = self.settings.get('llm_provider', 'gemini')
        if current_prov == 'local': self.provider_combo.setCurrentIndex(1)
        elif current_prov == 'openrouter': self.provider_combo.setCurrentIndex(2)
        else: self.provider_combo.setCurrentIndex(0)
        
        self.provider_combo.currentIndexChanged.connect(self._on_ai_provider_change)
        prov_layout.addWidget(QLabel("Select Provider:"))
        prov_layout.addWidget(self.provider_combo)
        prov_layout.addStretch()
        layout.addWidget(prov_group)
        
        # Stacked widgets for configs
        self.ai_configs_widget = QWidget()
        ai_configs_layout = QVBoxLayout(self.ai_configs_widget)
        ai_configs_layout.setContentsMargins(0,0,0,0)
        
        # Gemini
        self.gemini_group = QGroupBox("Google Gemini Settings")
        g_layout = QGridLayout(self.gemini_group)
        g_layout.addWidget(QLabel("API Key:"), 0, 0)
        self.gemini_api_edit = QLineEdit(self.settings.get('gemini_api_key', ''))
        self.gemini_api_edit.setEchoMode(QLineEdit.Password)
        g_layout.addWidget(self.gemini_api_edit, 0, 1)
        
        g_layout.addWidget(QLabel("Model Selection:"), 1, 0)
        self.gemini_model_combo = QComboBox()
        self.gemini_model_combo.setEditable(True)
        models = [
            'gemini-3-flash-preview', 'gemini-2.5-flash', 'gemini-2.5-flash-lite',
            'gemini-2.0-flash', 'gemini-2.0-flash-lite', 'Gemma 3'
        ]
        self.gemini_model_combo.addItems(models)
        self.gemini_model_combo.setCurrentText(self.settings.get('gemini_model', 'gemini-2.5-flash'))
        g_layout.addWidget(self.gemini_model_combo, 1, 1)
        
        g_layout.addWidget(QLabel("Temperature:"), 2, 0)
        self.gemini_temp_slider = QSlider(Qt.Horizontal)
        self.gemini_temp_slider.setRange(0, 100)
        self.gemini_temp_slider.setValue(int(self.settings.get('gemini_temperature', 0.0) * 100))
        g_layout.addWidget(self.gemini_temp_slider, 2, 1)
        
        ai_configs_layout.addWidget(self.gemini_group)
        
        # Local
        self.local_group = QGroupBox("Local LLM Settings")
        l_layout = QGridLayout(self.local_group)
        l_layout.addWidget(QLabel("Endpoint URL:"), 0, 0)
        self.local_url_edit = QLineEdit(self.settings.get('local_llm_url', 'http://127.0.0.1:1234/v1'))
        l_layout.addWidget(self.local_url_edit, 0, 1)
        l_layout.addWidget(QLabel("Model ID:"), 1, 0)
        self.local_model_edit = QComboBox()
        self.local_model_edit.setEditable(True)
        local_models = ["local-model", "qwen3-4b-instruct-2507", "step3-vl-10b", "qwen2.5-14b-instruct-1m", "gpt-oss-20b"]
        self.local_model_edit.addItems(local_models)
        
        current_model = self.settings.get('local_llm_model', 'local-model')
        if current_model and current_model not in local_models:
            self.local_model_edit.addItem(current_model)
        self.local_model_edit.setCurrentText(current_model)
        
        self.local_model_edit.setToolTip("e.g. qwen3-4b-instruct-2507 or local-model")
        l_layout.addWidget(self.local_model_edit, 1, 1)
        
        l_layout_hint = QLabel("(LM Studio uses the loaded model if 'local-model' is specified)")
        l_layout_hint.setStyleSheet("color: #666666; font-size: 11px;")
        l_layout.addWidget(l_layout_hint, 2, 1)
        
        ai_configs_layout.addWidget(self.local_group)
        
        # OpenRouter
        self.openrouter_group = QGroupBox("OpenRouter Settings")
        o_layout = QGridLayout(self.openrouter_group)
        o_layout.addWidget(QLabel("API Key:"), 0, 0)
        self.openrouter_api_edit = QLineEdit(self.settings.get('openrouter_api_key', ''))
        self.openrouter_api_edit.setEchoMode(QLineEdit.Password)
        o_layout.addWidget(self.openrouter_api_edit, 0, 1)
        o_layout.addWidget(QLabel("Model ID:"), 1, 0)
        self.openrouter_model_edit = QLineEdit(self.settings.get('openrouter_model', 'stepfun/step-3.5-flash'))
        o_layout.addWidget(self.openrouter_model_edit, 1, 1)
        ai_configs_layout.addWidget(self.openrouter_group)

        # Embeddings
        self.embedding_group = QGroupBox("Embeddings Settings")
        e_layout = QGridLayout(self.embedding_group)
        e_layout.addWidget(QLabel("Embedded Model:"), 0, 0)
        self.embedding_model_name_edit = QLineEdit('jinaai/jina-embeddings-v3')
        self.embedding_model_name_edit.setReadOnly(True)
        e_layout.addWidget(self.embedding_model_name_edit, 0, 1, 1, 2)
        fixed_label = QLabel("Embedding model/chunking are fixed to protect RAG consistency.")
        fixed_label.setWordWrap(True)
        e_layout.addWidget(fixed_label, 1, 0, 1, 3)
        cache_hint = str((Path.home() / ".cache" / "huggingface" / "hub").resolve())
        cache_label = QLabel(
            "Runtime may also use local cache path:\n"
            f"Default cache path: {cache_hint}"
        )
        cache_label.setWordWrap(True)
        e_layout.addWidget(cache_label, 2, 0, 1, 3)
        self.embedding_status_label = QLabel("")
        self.embedding_status_label.setWordWrap(True)
        e_layout.addWidget(self.embedding_status_label, 3, 0, 1, 3)
        self._refresh_embedding_status_label()
        ai_configs_layout.addWidget(self.embedding_group)
        
        layout.addWidget(self.ai_configs_widget)
        self._on_ai_provider_change()
        
        layout.addStretch()
        action_layout = QHBoxLayout()
        action_layout.addStretch()
        btn_save = QPushButton("Save AI Settings")
        btn_save.setObjectName("primaryAction")
        btn_save.clicked.connect(self._save_general)
        action_layout.addWidget(btn_save)
        layout.addLayout(action_layout)
        
        self.notebook.addTab(tab, "AI Config")

    def _on_ai_provider_change(self):
        idx = self.provider_combo.currentIndex()
        self.gemini_group.setVisible(idx == 0)
        self.local_group.setVisible(idx == 1)
        self.openrouter_group.setVisible(idx == 2)

    def _save_general(self):
        # Gather all
        idx = self.provider_combo.currentIndex()
        if idx == 0: prov = 'gemini'
        elif idx == 1: prov = 'local'
        else: prov = 'openrouter'
        
        self.settings['llm_provider'] = prov
        self.settings['gemini_api_key'] = self.gemini_api_edit.text().strip()
        self.settings['gemini_model'] = self.gemini_model_combo.currentText().strip()
        self.settings['gemini_temperature'] = self.gemini_temp_slider.value() / 100.0
        self.settings['local_llm_url'] = self.local_url_edit.text().strip()
        self.settings['local_llm_model'] = self.local_model_edit.currentText().strip()
        self.settings['openrouter_api_key'] = self.openrouter_api_edit.text().strip()
        self.settings['openrouter_model'] = self.openrouter_model_edit.text().strip()
        self.settings['embedding_model_name'] = 'jinaai/jina-embeddings-v3'
        self.settings.pop('embedding_model_path', None)
        self.settings.pop('embedding_max_tokens', None)
        self.settings.pop('embedding_chunk_overlap_tokens', None)
        self.settings.pop('embedding_local_files_only', None)
        self.settings['default_directory'] = self.default_dir_edit.text().strip()
        self.settings['sqlite_db_path'] = self.db_path_edit.text().strip()
        self.settings['file_storage_path'] = self.storage_path_edit.text().strip()
        self.settings['debug_mode'] = self.debug_mode_check.isChecked()
        activity_level = 'partial' if self.activity_level_combo.currentIndex() == 1 else 'full'
        self.settings['agent_activity_level'] = activity_level
        self.settings['agent_activity_partial_keep_steps'] = int(self.partial_keep_steps_spin.value())
        # Backward-compatibility mode switch retained in executor.
        self.settings['agent_activity_mode'] = 'structured' if activity_level == 'partial' else 'fast'
        self.settings['whatsapp_enabled'] = self.whatsapp_enabled_check.isChecked()
        self.settings['whatsapp_auto_start_gateway'] = self.whatsapp_auto_start_check.isChecked()
        self.settings['whatsapp_gateway_url'] = self.whatsapp_gateway_url_edit.text().strip()
        self.settings['whatsapp_gateway_command'] = self.whatsapp_gateway_command_edit.text().strip()
        self.settings['whatsapp_webhook_host'] = self.whatsapp_webhook_host_edit.text().strip()
        try:
            self.settings['whatsapp_webhook_port'] = int(self.whatsapp_webhook_port_edit.text().strip())
        except Exception:
            self.settings['whatsapp_webhook_port'] = 5716
        self.settings['whatsapp_webhook_secret'] = self.whatsapp_webhook_secret_edit.text().strip()
        self.settings['whatsapp_test_to'] = self.whatsapp_test_to_edit.text().strip()
        self.settings['whatsapp_test_message'] = self.whatsapp_test_message_edit.text().strip()
        self.settings['telegram_enabled'] = self.telegram_enabled_check.isChecked()
        self.settings['telegram_bot_token'] = self.telegram_bot_token_edit.text().strip()
        try:
            self.settings['telegram_poll_timeout'] = int(self.telegram_poll_timeout_edit.text().strip())
        except Exception:
            self.settings['telegram_poll_timeout'] = 25
        try:
            self.settings['telegram_poll_retry_seconds'] = float(self.telegram_poll_retry_edit.text().strip())
        except Exception:
            self.settings['telegram_poll_retry_seconds'] = 2
        self.settings['telegram_test_chat_id'] = self.telegram_test_chat_id_edit.text().strip()
        self.settings['telegram_test_message'] = self.telegram_test_message_edit.text().strip()
        self.settings['scheduler_enabled'] = self.scheduler_enabled_check.isChecked()
        self.settings['scheduler_poll_minutes'] = int(self.scheduler_poll_minutes_spin.value())
        
        raw_dirs = self.accessible_text.toPlainText().strip()
        self.settings['accessible_directories'] = [d.strip() for d in raw_dirs.splitlines() if d.strip()]
        
        config_loader.save_settings(self.settings)
        
        # Update CDA
        for k, v in self.settings.items():
            self.cda.set_setting(k, v)

        # Reinitialize WhatsApp channel service with latest settings.
        wa_svc = self.cda.get_runtime('whatsapp_channel_service')
        if wa_svc is not None:
            try:
                wa_svc.stop()
                wa_svc.start()
            except Exception as e:
                QMessageBox.warning(self, "WhatsApp Re-init Warning", f"Settings saved, but failed to restart WhatsApp service: {e}")
        tg_svc = self.cda.get_runtime('telegram_channel_service')
        if tg_svc is not None:
            try:
                tg_svc.stop()
                tg_svc.start()
            except Exception as e:
                QMessageBox.warning(self, "Telegram Re-init Warning", f"Settings saved, but failed to restart Telegram service: {e}")
        sch_svc = self.cda.get_runtime('scheduler_service')
        if sch_svc is not None:
            try:
                sch_svc.stop()
                sch_svc.start()
            except Exception as e:
                QMessageBox.warning(self, "Scheduler Re-init Warning", f"Settings saved, but failed to restart Scheduler service: {e}")
            
        try:
            from llm.factory import get_llm_client
            new_client = get_llm_client(self.cda)
            self.cda.set_runtime('llm_client', new_client)
        except Exception as e:
            QMessageBox.warning(self, "AI Re-init Warning", f"Settings saved, but failed to re-initialize AI client: {e}")

        QMessageBox.information(self, "Success", "Configuration Updated and applied.")

    # ==========================
    # AGENTS TAB
    # ==========================
    def _create_agents_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        top_bar = QHBoxLayout()
        btn_refresh = QPushButton("Refresh Agents")
        btn_refresh.clicked.connect(self._refresh_agents)
        top_bar.addStretch()
        top_bar.addWidget(btn_refresh)
        layout.addLayout(top_bar)
        
        splitter = QSplitter(Qt.Horizontal)
        
        # Left Panel
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        self.agent_tree = QTreeWidget()
        self.agent_tree.setHeaderLabels(["Agent Name"])
        self.agent_tree.setAlternatingRowColors(True)
        self.agent_tree.itemSelectionChanged.connect(self._on_agent_select)
        left_layout.addWidget(self.agent_tree)
        btn_row = QHBoxLayout()
        btn_new = QPushButton("+ New Agent")
        btn_new.clicked.connect(self._new_agent)
        btn_row.addWidget(btn_new)
        btn_delete = QPushButton("Delete Agent")
        btn_delete.clicked.connect(self._delete_agent)
        btn_row.addWidget(btn_delete)
        left_layout.addLayout(btn_row)
        splitter.addWidget(left_panel)
        
        # Right Panel
        right_panel = QGroupBox("Agent Configuration")
        right_layout = QVBoxLayout(right_panel)
        
        form_layout = QGridLayout()
        form_layout.addWidget(QLabel("Name:"), 0, 0)
        self.agent_name_edit = QLineEdit()
        form_layout.addWidget(self.agent_name_edit, 0, 1)
        form_layout.addWidget(QLabel("Description:"), 1, 0)
        self.agent_desc_edit = QLineEdit()
        form_layout.addWidget(self.agent_desc_edit, 1, 1)
        right_layout.addLayout(form_layout)
        
        prompt_top_layout = QHBoxLayout()
        prompt_top_layout.addWidget(QLabel("System Prompt:"))
        prompt_top_layout.addStretch()

        self.btn_restore_prompt = QPushButton("Restore Older Version")
        self.btn_restore_prompt.setEnabled(False) 
        self.btn_restore_prompt.clicked.connect(self._restore_prompt_version)
        prompt_top_layout.addWidget(self.btn_restore_prompt)
        
        btn_save_agent = QPushButton("Save Agent Configuration")
        btn_save_agent.setObjectName("primaryAction")
        btn_save_agent.clicked.connect(self._save_agent)
        prompt_top_layout.addWidget(btn_save_agent)
        
        right_layout.addLayout(prompt_top_layout)
        self.agent_prompt_edit = QTextEdit()
        self.agent_prompt_edit.setStyleSheet("font-family: Consolas;")
        right_layout.addWidget(self.agent_prompt_edit)
        
        right_layout.addWidget(QLabel("Assigned Tools:"))
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setMaximumHeight(150)
        self.agent_tools_widget = QWidget()
        self.agent_tools_layout = QGridLayout(self.agent_tools_widget)
        scroll.setWidget(self.agent_tools_widget)
        right_layout.addWidget(scroll)
        self.agent_tool_vars = {}
        self._refresh_agent_tools_panel()
        
        splitter.addWidget(right_panel)
        splitter.setSizes([200, 800])
        layout.addWidget(splitter)
        
        self.notebook.addTab(tab, "Agents")
        self._refresh_agents()
        
    def _refresh_agent_tools_panel(self) -> None:
        for i in reversed(range(self.agent_tools_layout.count())): 
            self.agent_tools_layout.itemAt(i).widget().setParent(None)
            
        self.agent_tool_vars = {}
        tool_names = list(list_tools().keys())
        
        conn = self._get_conn()
        try:
            cur = conn.cursor()
            cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='ToolList'")
            if cur.fetchone():
                cur.execute("SELECT name FROM ToolList ORDER BY name")
                db_tools = [row[0] for row in cur.fetchall()]
                if db_tools:
                    tool_names = db_tools
        except Exception:
            pass
        finally:
            conn.close()

        for i, t_name in enumerate(sorted(tool_names)):
            cb = QCheckBox(t_name)
            self.agent_tools_layout.addWidget(cb, i // 3, i % 3)
            self.agent_tool_vars[t_name] = cb

    def _refresh_agents(self):
        self.agent_tree.clear()
        agents = sorted(list_agents(return_all=True), key=lambda a: a.get('name', ''))
        for agent in agents:
            item = QTreeWidgetItem([agent['name']])
            self.agent_tree.addTopLevelItem(item)

    def _on_agent_select(self):
        items = self.agent_tree.selectedItems()
        if not items: return
        name = items[0].text(0)
        try:
            agent = get_agent(name)
            self.agent_name_edit.setText(agent['name'])
            self.agent_desc_edit.setText(agent.get('description', ''))
            self.agent_prompt_edit.setPlainText(agent.get('prompt_content', ''))
            self.btn_restore_prompt.setEnabled(True)
            self._load_agent_tool_assignments(name)
        except Exception as e:
            print(f"Agent load error: {e}")

    def _load_agent_tool_assignments(self, agent_name: str) -> None:
        for cb in self.agent_tool_vars.values(): cb.setChecked(False)
        conn = self._get_conn()
        try:
            cur = conn.cursor()
            cur.execute("SELECT id FROM Agents WHERE name=?", (agent_name,))
            row = cur.fetchone()
            if not row: return
            
            cur.execute("SELECT tool_name FROM AgentTools WHERE agent_id=?", (row[0],))
            assigned = {r[0] for r in cur.fetchall()}
            for t_name, cb in self.agent_tool_vars.items():
                if t_name in assigned: cb.setChecked(True)
        finally:
            conn.close()

    def _new_agent(self):
        self.agent_tree.clearSelection()
        self.agent_name_edit.clear()
        self.agent_desc_edit.clear()
        self.agent_prompt_edit.clear()
        self.btn_restore_prompt.setEnabled(False)
        for cb in self.agent_tool_vars.values(): cb.setChecked(False)

    def _save_agent(self):
        name = self.agent_name_edit.text().strip()
        desc = self.agent_desc_edit.text().strip()
        prompt = self.agent_prompt_edit.toPlainText().strip()
        if not name or not prompt:
            QMessageBox.warning(self, "Error", "Name and Prompt are required.")
            return

        try:
            conn = self._get_conn()
            cur = conn.cursor()
            cur.execute("SELECT id, prompt_content, version FROM Agents WHERE name=?", (name,))
            row = cur.fetchone()
            if row:
                agent_id = row[0]
                old_prompt = row[1]
                current_version = row[2] if len(row) > 2 and row[2] is not None else 1
                
                if old_prompt != prompt:
                    cur.execute(
                        "INSERT INTO AgentPromptVersion (agent_id, agent_name, prompt_content, version) VALUES (?, ?, ?, ?)",
                        (agent_id, name, old_prompt, current_version),
                    )
                    new_version = current_version + 1
                    cur.execute("UPDATE Agents SET description=?, prompt_content=?, version=?, is_active=1 WHERE id=?", (desc, prompt, new_version, agent_id))
                else:
                    cur.execute("UPDATE Agents SET description=?, is_active=1 WHERE id=?", (desc, agent_id))
            else:
                cur.execute("INSERT INTO Agents (name, description, prompt_content, version) VALUES (?, ?, ?, 1)", (name, desc, prompt))
                agent_id = cur.lastrowid

            cur.execute("DELETE FROM AgentTools WHERE agent_id=?", (agent_id,))
            selected_tools = [t_name for t_name, cb in self.agent_tool_vars.items() if cb.isChecked()]
            for t_name in selected_tools:
                cur.execute("INSERT INTO AgentTools (agent_id, tool_name) VALUES (?, ?)", (agent_id, t_name))
            
            conn.commit()
            conn.close()
            self._refresh_agents()
            QMessageBox.information(self, "Success", f"Agent '{name}' saved.")
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def _restore_prompt_version(self):
        name = self.agent_name_edit.text().strip()
        if not name: return
        
        conn = self._get_conn()
        cur = conn.cursor()
        cur.execute("SELECT id, version FROM Agents WHERE name=?", (name,))
        row = cur.fetchone()
        if not row:
            conn.close()
            return
            
        agent_id, active_version = row
        
        cur.execute("SELECT id, version, created_at, prompt_content FROM AgentPromptVersion WHERE agent_id=? OR agent_name=? ORDER BY version DESC", (agent_id, name))
        versions = cur.fetchall()
        
        if not versions:
            QMessageBox.information(self, "No History", "There are no previous versions saved for this agent.")
            conn.close()
            return

        dialog = QDialog(self)
        dialog.setWindowTitle(f"Restore Prompt: {name}")
        dialog.setMinimumSize(600, 450)
        
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel("Select a previous version to preview and restore:"))
        
        list_widget = QListWidget()
        for vid, version, created_at, content in versions:
            item = QListWidgetItem(f"Version {version} - {created_at}")
            item.setData(Qt.UserRole, (vid, content, version))
            list_widget.addItem(item)
            
        layout.addWidget(list_widget, 1)
        
        preview = QTextEdit()
        preview.setReadOnly(True)
        preview.setStyleSheet("font-family: Consolas;")
        layout.addWidget(preview, 2)
        
        def on_select():
            selected = list_widget.selectedItems()
            if selected:
                _, content, _ = selected[0].data(Qt.UserRole)
                preview.setPlainText(content)
        list_widget.itemSelectionChanged.connect(on_select)
        if list_widget.count() > 0:
            list_widget.setCurrentRow(0)
            
        btn_layout = QHBoxLayout()
        btn_cancel = QPushButton("Cancel")
        btn_cancel.clicked.connect(dialog.reject)
        
        btn_restore = QPushButton("Restore Selected Version")
        btn_restore.setObjectName("primaryAction")
        
        def do_restore():
            selected = list_widget.selectedItems()
            if not selected: return
            _, content, restore_ver_num = selected[0].data(Qt.UserRole)
            
            # Save the currently active prompt to history before replacement
            current_prompt = self.agent_prompt_edit.toPlainText().strip()
            if current_prompt and current_prompt != content:
                cur.execute(
                    "INSERT INTO AgentPromptVersion (agent_id, agent_name, prompt_content, version) VALUES (?, ?, ?, ?)",
                    (agent_id, name, current_prompt, active_version),
                )
            
            # Overwrite active prompt with the selected older version and bump the master version counter
            new_active_version = active_version + 1
            cur.execute("UPDATE Agents SET prompt_content=?, version=? WHERE id=?", (content, new_active_version, agent_id))
            conn.commit()
            
            self.agent_prompt_edit.setPlainText(content)
            QMessageBox.information(self, "Restored", f"Agent '{name}' prompt successfully restored to Version {restore_ver_num} (now saved as active Version {new_active_version}).")
            dialog.accept()
            
        btn_restore.clicked.connect(do_restore)
        btn_layout.addStretch()
        btn_layout.addWidget(btn_cancel)
        btn_layout.addWidget(btn_restore)
        layout.addLayout(btn_layout)
        
        dialog.exec()
        conn.close()

    def _delete_agent(self):
        items = self.agent_tree.selectedItems()
        if not items:
            QMessageBox.warning(self, "Delete Agent", "Select an agent to delete.")
            return

        name = items[0].text(0).strip()
        if not name:
            return
        reply = QMessageBox.question(
            self,
            "Confirm Delete",
            f"Delete agent '{name}'?\nA prompt backup will be saved to version history first.",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        try:
            conn = self._get_conn()
            cur = conn.cursor()
            cur.execute("SELECT id, prompt_content, version FROM Agents WHERE name=?", (name,))
            row = cur.fetchone()
            if not row:
                conn.close()
                QMessageBox.warning(self, "Delete Agent", f"Agent '{name}' not found.")
                return

            agent_id = int(row[0])
            prompt_content = str(row[1] or "")
            version = int(row[2] or 1)

            # Mandatory backup before deletion/deactivation.
            cur.execute(
                "INSERT INTO AgentPromptVersion (agent_id, agent_name, prompt_content, version) VALUES (?, ?, ?, ?)",
                (agent_id, name, prompt_content, version),
            )

            # Soft delete to preserve all historical references.
            cur.execute("UPDATE Agents SET is_active=0 WHERE id=?", (agent_id,))
            conn.commit()
            conn.close()

            self._new_agent()
            self._refresh_agents()
            QMessageBox.information(self, "Delete Agent", f"Agent '{name}' deleted (deactivated). Prompt backup saved.")
        except Exception as e:
            QMessageBox.critical(self, "Delete Agent Error", str(e))

    # ==========================
    # ROLES TAB
    # ==========================
    def _create_roles_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        top_bar = QHBoxLayout()
        btn_refresh = QPushButton("Refresh Roles")
        btn_refresh.clicked.connect(self._refresh_roles)
        top_bar.addStretch()
        top_bar.addWidget(btn_refresh)
        layout.addLayout(top_bar)
        
        splitter = QSplitter(Qt.Horizontal)
        
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        self.role_tree = QTreeWidget()
        self.role_tree.setHeaderLabels(["Role Name"])
        self.role_tree.itemSelectionChanged.connect(self._on_role_select)
        left_layout.addWidget(self.role_tree)
        
        btn_group = QHBoxLayout()
        btn_new = QPushButton("+ New Role")
        btn_new.clicked.connect(self._new_role)
        btn_del = QPushButton("Delete Role")
        btn_del.clicked.connect(self._delete_role)
        btn_group.addWidget(btn_new)
        btn_group.addWidget(btn_del)
        left_layout.addLayout(btn_group)
        splitter.addWidget(left_panel)
        
        right_panel = QGroupBox("Access Control Policy")
        right_layout = QVBoxLayout(right_panel)
        form_layout = QGridLayout()
        form_layout.addWidget(QLabel("Role Name:"), 0, 0)
        self.role_name_edit = QLineEdit()
        form_layout.addWidget(self.role_name_edit, 0, 1)
        form_layout.addWidget(QLabel("Description:"), 1, 0)
        self.role_desc_edit = QLineEdit()
        form_layout.addWidget(self.role_desc_edit, 1, 1)
        right_layout.addLayout(form_layout)
        
        right_layout.addWidget(QLabel("Authorized Agents:"))
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        self.role_agents_widget = QWidget()
        self.role_agents_layout = QGridLayout(self.role_agents_widget)
        self.role_agents_layout.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.role_agents_layout.setHorizontalSpacing(50)
        self.role_agents_layout.setVerticalSpacing(15)
        scroll.setWidget(self.role_agents_widget)
        right_layout.addWidget(scroll)
        self.role_agent_vars = {}
        
        btn_save_role = QPushButton("Save Policy Changes")
        btn_save_role.setObjectName("primaryAction")
        btn_save_role.clicked.connect(self._save_role)
        r_bottom = QHBoxLayout()
        r_bottom.addStretch()
        r_bottom.addWidget(btn_save_role)
        right_layout.addLayout(r_bottom)
        
        splitter.addWidget(right_panel)
        splitter.setSizes([200, 600])
        layout.addWidget(splitter)
        
        self.notebook.addTab(tab, "Roles")
        self._refresh_roles()

    def _refresh_roles(self):
        self.role_tree.clear()
        conn = self._get_conn()
        cur = conn.cursor()
        cur.execute("SELECT name FROM Roles")
        for row in cur.fetchall():
            item = QTreeWidgetItem([row[0]])
            self.role_tree.addTopLevelItem(item)
        conn.close()
        
        for i in reversed(range(self.role_agents_layout.count())): 
            self.role_agents_layout.itemAt(i).widget().setParent(None)
        self.role_agent_vars = {}
        agents = list_agents(return_all=True)
        for i, agent in enumerate(agents):
            cb = QCheckBox(agent['name'])
            self.role_agents_layout.addWidget(cb, i//3, i%3)
            self.role_agent_vars[agent['name']] = cb

    def _on_role_select(self):
        items = self.role_tree.selectedItems()
        if not items: return
        rname = items[0].text(0)
        
        conn = self._get_conn()
        cur = conn.cursor()
        cur.execute("SELECT id, name, description FROM Roles WHERE name=?", (rname,))
        row = cur.fetchone()
        if row:
            self.role_name_edit.setText(row[1])
            self.role_desc_edit.setText(row[2])
            
            cur.execute("SELECT A.name FROM RoleAgents RA JOIN Agents A ON RA.agent_id = A.id WHERE RA.role_id = ?", (row[0],))
            assigned = {r[0] for r in cur.fetchall()}
            for aname, cb in self.role_agent_vars.items():
                cb.setChecked(aname in assigned)
        conn.close()

    def _new_role(self):
        self.role_tree.clearSelection()
        self.role_name_edit.clear()
        self.role_desc_edit.clear()
        for cb in self.role_agent_vars.values(): cb.setChecked(False)

    def _save_role(self):
        rname = self.role_name_edit.text().strip()
        rdesc = self.role_desc_edit.text().strip()
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
            
            cur.execute("DELETE FROM RoleAgents WHERE role_id=?", (rid,))
            for aname, cb in self.role_agent_vars.items():
                if cb.isChecked():
                    cur.execute("SELECT id FROM Agents WHERE name=?", (aname,))
                    arow = cur.fetchone()
                    if arow:
                        cur.execute("INSERT INTO RoleAgents (role_id, agent_id) VALUES (?, ?)", (rid, arow[0]))
            conn.commit()
            conn.close()
            self._refresh_roles()
            QMessageBox.information(self, "Success", f"Role '{rname}' saved.")
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def _delete_role(self):
        items = self.role_tree.selectedItems()
        if not items: return
        rname = items[0].text(0)
        reply = QMessageBox.question(self, "Confirm", f"Delete role '{rname}'?", QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            conn = self._get_conn()
            conn.execute("DELETE FROM Roles WHERE name=?", (rname,))
            conn.commit()
            conn.close()
            self._refresh_roles()

    # ==========================
    # USERS TAB
    # ==========================
    def _create_users_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        b = QHBoxLayout()
        b.addStretch()
        btn = QPushButton("Refresh Directory")
        btn.clicked.connect(self._refresh_users)
        b.addWidget(btn)
        layout.addLayout(b)
        
        list_frame = QGroupBox("Directory")
        lf_layout = QVBoxLayout(list_frame)
        self.user_tree = QTreeWidget()
        self.user_tree.setHeaderLabels(["ID", "Full Name / Email", "Mobile", "WhatsApp", "Assigned Role"])
        self.user_tree.header().setSectionResizeMode(1, QHeaderView.Stretch)
        self.user_tree.header().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.user_tree.header().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.user_tree.header().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self.user_tree.itemSelectionChanged.connect(self._on_user_select)
        lf_layout.addWidget(self.user_tree)
        layout.addWidget(list_frame)
        
        assign_frame = QGroupBox("Role Assignment")
        af_layout = QHBoxLayout(assign_frame)
        af_layout.addWidget(QLabel("Assign Role to Selected User:"))
        self.assign_role_combo = QComboBox()
        af_layout.addWidget(self.assign_role_combo)
        btn_upd = QPushButton("Update Role")
        btn_upd.setObjectName("primaryAction")
        btn_upd.clicked.connect(self._update_user_role)
        af_layout.addWidget(btn_upd)
        af_layout.addStretch()
        layout.addWidget(assign_frame)
        
        session_frame = QGroupBox("Active Session Context")
        sf_layout = QHBoxLayout(session_frame)
        sf_layout.addWidget(QLabel("Current Active User:"))
        self.session_user_combo = QComboBox()
        sf_layout.addWidget(self.session_user_combo, 1)
        btn_set = QPushButton("Set Active User")
        btn_set.clicked.connect(self._set_active_user)
        sf_layout.addWidget(btn_set)
        layout.addWidget(session_frame)
        
        self.notebook.addTab(tab, "Users")
        self._refresh_users()

    def _refresh_users(self):
        self.user_tree.clear()
        self.all_users = []
        conn = self._get_conn()
        cur = conn.cursor()
        
        cur.execute("SELECT id, name FROM Roles")
        self.roles_map = {r[0]: r[1] for r in cur.fetchall()}
        self.assign_role_combo.clear()
        self.assign_role_combo.addItems(list(self.roles_map.values()))
        
        try:
            cur.execute("PRAGMA table_info(Users)")
            cols = [c[1] for c in cur.fetchall()]
            
            name_col = 'full_name' if 'full_name' in cols else ('FirstName' if 'FirstName' in cols else "''")
            email_col = 'email' if 'email' in cols else "''"
            mobile_col = 'mobile_number' if 'mobile_number' in cols else "''"
            whatsapp_col = 'whatsapp_number' if 'whatsapp_number' in cols else "''"
            role_expr = 'COALESCE(role_id, roleID)' if 'role_id' in cols and 'roleID' in cols else ('role_id' if 'role_id' in cols else ('roleID' if 'roleID' in cols else 'NULL'))
            
            cur.execute(f'SELECT id, "{name_col}", {role_expr}, {email_col}, {mobile_col}, {whatsapp_col} FROM Users')
            for row in cur.fetchall():
                uid, name, rid, email, mobile, whatsapp = row
                rname = self.roles_map.get(rid, 'Has No Role')
                display_name = f"{name} ({email})"
                item = QTreeWidgetItem([str(uid), display_name, str(mobile or ''), str(whatsapp or ''), rname])
                self.user_tree.addTopLevelItem(item)
                self.all_users.append((uid, display_name))
        except Exception as e:
            print(f"User refresh error: {e}")
            
        conn.close()
        
        self.session_user_combo.clear()
        session_values = [f"{u[1]} [ID:{u[0]}]" for u in self.all_users]
        self.session_user_combo.addItems(session_values)

    def _on_user_select(self):
        items = self.user_tree.selectedItems()
        if items:
            role_assigned = items[0].text(4)
            idx = self.assign_role_combo.findText(role_assigned)
            if idx >= 0:
                self.assign_role_combo.setCurrentIndex(idx)

    def _update_user_role(self):
        items = self.user_tree.selectedItems()
        if not items: return
        uid = items[0].text(0)
        role_name = self.assign_role_combo.currentText()
        role_id = next((k for k,v in self.roles_map.items() if v == role_name), None)
        
        if role_id is not None:
            conn = self._get_conn()
            try:
                cur = conn.cursor()
                cur.execute("PRAGMA table_info(Users)")
                cols = [c[1] for c in cur.fetchall()]
                r_col = 'role_id' if 'role_id' in cols else 'roleID'
                cur.execute(f"UPDATE Users SET {r_col}=? WHERE id=?", (role_id, uid))
                conn.commit()
                QMessageBox.information(self, "Success", "User role updated successfully.")
            except Exception as e:
                 QMessageBox.critical(self, "Error", f"Failed to update user role: {e}")
            finally:
                conn.close()
                self._refresh_users()

    def _set_active_user(self):
        selection = self.session_user_combo.currentText()
        if not selection: return
        
        try:
            uid_str = selection.split("[ID:")[1].replace("]", "")
            uid = int(uid_str)
            
            uname_raw = selection.split("[ID:")[0].strip()
            email_match = re.search(r'\(([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})\)', uname_raw)
            email = email_match.group(1) if email_match else ''
            pure_name = uname_raw.split("(")[0].strip()
            
            self.settings['current_user_id'] = uid
            self.settings['current_username'] = pure_name
            self.settings['current_user_email'] = email
            config_loader.save_settings(self.settings)
            
            self.cda.set_setting('current_user_id', str(uid))
            self.cda.set_setting('current_username', pure_name)
            self.cda.set_setting('current_user_email', email)
            
            QMessageBox.information(self, "Session Context", f"Active context set to user {pure_name} (ID: {uid}).")
            
            # Notify ChatUI if available by a method call (parent handles it in ChatUI's logic now via CDA changes)
            if hasattr(self.parent(), '_refresh_active_user_label'):
                self.parent()._refresh_active_user_label()
                
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to set user context: {e}")

    # ==========================
    # TOOLS TAB
    # ==========================
    def _create_tools_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)

        action_row = QHBoxLayout()
        action_row.addStretch()
        self.btn_refresh_tools = QPushButton("Refresh Tool Registry")
        self.btn_refresh_tools.clicked.connect(self._sync_and_refresh_tools)
        action_row.addWidget(self.btn_refresh_tools)
        layout.addLayout(action_row)

        splitter = QSplitter(Qt.Horizontal)

        self.tool_tree = QTreeWidget()
        self.tool_tree.setHeaderLabels(["Tool Name", "Status", "Description"])
        self.tool_tree.setAlternatingRowColors(True)
        self.tool_tree.setRootIsDecorated(False)
        self.tool_tree.setUniformRowHeights(True)
        self.tool_tree.itemSelectionChanged.connect(self._on_tool_select)
        self.tool_tree.header().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.tool_tree.header().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.tool_tree.header().setSectionResizeMode(2, QHeaderView.Stretch)
        splitter.addWidget(self.tool_tree)

        details = QWidget()
        details_layout = QVBoxLayout(details)
        details_layout.setContentsMargins(12, 12, 12, 12)

        self.tool_name_label = QLabel("Tool: (select a tool)")
        self.tool_name_label.setStyleSheet(f"font-weight: bold; color: {self.accent_color};")
        details_layout.addWidget(self.tool_name_label)

        self.tool_status_label = QLabel("Status: ")
        details_layout.addWidget(self.tool_status_label)

        desc_label = QLabel("Description")
        desc_label.setStyleSheet("font-weight: bold;")
        details_layout.addWidget(desc_label)

        self.tool_description_edit = QTextEdit()
        self.tool_description_edit.setMinimumHeight(120)
        details_layout.addWidget(self.tool_description_edit)

        schema_label = QLabel("Input Schema")
        schema_label.setStyleSheet("font-weight: bold;")
        details_layout.addWidget(schema_label)

        self.tool_input_schema_edit = QTextEdit()
        self.tool_input_schema_edit.setReadOnly(True)
        self.tool_input_schema_edit.setMinimumHeight(100)
        details_layout.addWidget(self.tool_input_schema_edit)

        output_label = QLabel("Output Schema")
        output_label.setStyleSheet("font-weight: bold;")
        details_layout.addWidget(output_label)

        self.tool_output_schema_edit = QTextEdit()
        self.tool_output_schema_edit.setReadOnly(True)
        self.tool_output_schema_edit.setMinimumHeight(80)
        details_layout.addWidget(self.tool_output_schema_edit)

        button_row = QHBoxLayout()
        button_row.addStretch()
        self.btn_save_tool_desc = QPushButton("Save Description")
        self.btn_save_tool_desc.setObjectName("primaryAction")
        self.btn_save_tool_desc.clicked.connect(self._save_tool_description)
        button_row.addWidget(self.btn_save_tool_desc)
        details_layout.addLayout(button_row)

        splitter.addWidget(details)
        splitter.setSizes([520, 560])
        layout.addWidget(splitter)

        self.notebook.addTab(tab, "System Tools")
        self._refresh_tools()

    def _sync_and_refresh_tools(self) -> None:
        try:
            count = sync_tools_to_db(self.cda)
            self._refresh_tools()
            QMessageBox.information(self, "System Tools", f"Refreshed {count} tools into ToolList.")
        except Exception as e:
            QMessageBox.critical(self, "System Tools", f"Failed to refresh tools: {e}")

    def _refresh_tools(self):
        self.tool_tree.clear()
        registry_names = set(list(list_tools().keys()))
        tool_status: Dict[str, str] = {}
        metadata_rows = {row["name"]: row for row in list_tool_metadata(self.cda)}

        conn = self._get_conn()
        try:
            cur = conn.cursor()
            cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='ToolList'")
            if cur.fetchone():
                cur.execute("PRAGMA table_info(ToolList)")
                cols = [str(c[1]) for c in cur.fetchall()]
                has_active = "is_active" in cols

                if has_active:
                    cur.execute("SELECT name, is_active FROM ToolList ORDER BY name")
                    for row in cur.fetchall():
                        nm = str(row[0])
                        active = bool(row[1])
                        if nm in registry_names:
                            tool_status[nm] = "Active" if active else "Disabled"
                        else:
                            tool_status[nm] = "DB only" if active else "Disabled (DB only)"
                else:
                    cur.execute("SELECT name FROM ToolList ORDER BY name")
                    for row in cur.fetchall():
                        nm = str(row[0])
                        tool_status[nm] = "Available" if nm in registry_names else "DB only"
        except Exception:
            pass
        finally:
            conn.close()

        for name in registry_names:
            tool_status.setdefault(name, "Code only")

        if not tool_status:
            self.tool_tree.addTopLevelItem(QTreeWidgetItem(["(No tools found)", "Unavailable", "Check tool registry import errors"]))
            return

        for name in sorted(tool_status.keys()):
            description = str(metadata_rows.get(name, {}).get("description", "") or "")
            item = QTreeWidgetItem([name, tool_status[name], description])
            item.setData(0, Qt.UserRole, metadata_rows.get(name, {}))
            self.tool_tree.addTopLevelItem(item)

        if self.tool_tree.topLevelItemCount() > 0:
            self.tool_tree.setCurrentItem(self.tool_tree.topLevelItem(0))

    def _on_tool_select(self) -> None:
        items = self.tool_tree.selectedItems()
        if not items:
            self.tool_name_label.setText("Tool: (select a tool)")
            self.tool_status_label.setText("Status: ")
            self.tool_description_edit.clear()
            self.tool_input_schema_edit.clear()
            self.tool_output_schema_edit.clear()
            return

        item = items[0]
        name = item.text(0)
        status = item.text(1)
        meta = item.data(0, Qt.UserRole) or {}

        self.tool_name_label.setText(f"Tool: {name}")
        self.tool_status_label.setText(f"Status: {status}")
        self.tool_description_edit.setPlainText(str(meta.get("description", "") or ""))
        self.tool_input_schema_edit.setPlainText(str(meta.get("input_schema", "") or ""))
        self.tool_output_schema_edit.setPlainText(str(meta.get("output_schema", "") or ""))

    def _save_tool_description(self) -> None:
        items = self.tool_tree.selectedItems()
        if not items:
            QMessageBox.warning(self, "System Tools", "Select a tool first.")
            return

        item = items[0]
        name = item.text(0)
        new_desc = self.tool_description_edit.toPlainText().strip()

        conn = self._get_conn()
        try:
            cur = conn.cursor()
            cur.execute("UPDATE ToolList SET description=? WHERE name=?", (new_desc, name))
            if int(cur.rowcount or 0) <= 0:
                raise ValueError(f"Tool '{name}' not found in ToolList.")
            conn.commit()
        except Exception as e:
            QMessageBox.critical(self, "System Tools", f"Failed to save description: {e}")
            return
        finally:
            conn.close()

        self._refresh_tools()
        matches = self.tool_tree.findItems(name, Qt.MatchExactly, 0)
        if matches:
            self.tool_tree.setCurrentItem(matches[0])
        QMessageBox.information(self, "System Tools", f"Updated description for '{name}'.")






