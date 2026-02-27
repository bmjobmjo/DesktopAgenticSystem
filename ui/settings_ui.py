"""Settings UI for configuring LLM, directories, agents, roles, and users in PySide6."""

from __future__ import annotations

import json
import sqlite3
import re
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

from core.common_data_area import CommonDataArea
from settings import config_loader
from agents.registry import list_agents, register_agent, get_agent, _get_db_path
from tools.tool_registry import list_tools

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
            QLineEdit, QComboBox {{ background: #ffffff; border: 1px solid {self.border_color}; border-radius: 4px; padding: 5px; }}
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

    def _browse_file(self, edit_widget, title, filters):
        filename, _ = QFileDialog.getOpenFileName(self, title, "", filters)
        if filename:
            edit_widget.setText(filename)
            
    def _browse_dir(self, edit_widget, title):
        directory = QFileDialog.getExistingDirectory(self, title)
        if directory:
            edit_widget.setText(directory)

    def _refresh_embedding_status_label(self) -> None:
        model_name = self.embedding_model_name_edit.text().strip() or "all-MiniLM-L6-v2"
        bundled_path = config_loader.find_bundled_embedding_model_path(model_name)
        if bundled_path:
            text = f"Bundled model active: {bundled_path}"
        else:
            text = "Bundled model not found in application package."
        self.embedding_status_label.setText(text)

    def _on_activity_level_changed(self) -> None:
        partial_mode = self.activity_level_combo.currentIndex() == 1
        self.partial_keep_steps_label.setVisible(partial_mode)
        self.partial_keep_steps_spin.setVisible(partial_mode)

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
        self.embedding_model_name_edit = QLineEdit('all-MiniLM-L6-v2')
        self.embedding_model_name_edit.setReadOnly(True)
        e_layout.addWidget(self.embedding_model_name_edit, 0, 1, 1, 2)
        fixed_label = QLabel("Embedding model is managed by the application and is not user-editable.")
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
        self.settings['embedding_model_name'] = 'all-MiniLM-L6-v2'
        self.settings['embedding_model_path'] = config_loader.find_bundled_embedding_model_path('all-MiniLM-L6-v2')
        self.settings['embedding_local_files_only'] = True
        self.settings['default_directory'] = self.default_dir_edit.text().strip()
        self.settings['sqlite_db_path'] = self.db_path_edit.text().strip()
        self.settings['file_storage_path'] = self.storage_path_edit.text().strip()
        self.settings['debug_mode'] = self.debug_mode_check.isChecked()
        activity_level = 'partial' if self.activity_level_combo.currentIndex() == 1 else 'full'
        self.settings['agent_activity_level'] = activity_level
        self.settings['agent_activity_partial_keep_steps'] = int(self.partial_keep_steps_spin.value())
        # Backward-compatibility mode switch retained in executor.
        self.settings['agent_activity_mode'] = 'structured' if activity_level == 'partial' else 'fast'
        
        raw_dirs = self.accessible_text.toPlainText().strip()
        self.settings['accessible_directories'] = [d.strip() for d in raw_dirs.splitlines() if d.strip()]
        
        config_loader.save_settings(self.settings)
        
        # Update CDA
        for k, v in self.settings.items():
            self.cda.set_setting(k, v)
            
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
        btn_new = QPushButton("+ New Agent")
        btn_new.clicked.connect(self._new_agent)
        left_layout.addWidget(btn_new)
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
                    cur.execute("INSERT INTO AgentPromptVersion (agent_id, prompt_content, version) VALUES (?, ?, ?)", (agent_id, old_prompt, current_version))
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
        
        cur.execute("SELECT id, version, created_at, prompt_content FROM AgentPromptVersion WHERE agent_id=? ORDER BY version DESC", (agent_id,))
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
                cur.execute("INSERT INTO AgentPromptVersion (agent_id, prompt_content, version) VALUES (?, ?, ?)", (agent_id, current_prompt, active_version))
            
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
        self.user_tree.setHeaderLabels(["ID", "Full Name / Email", "Assigned Role"])
        self.user_tree.header().setSectionResizeMode(1, QHeaderView.Stretch)
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
            role_expr = 'COALESCE(role_id, roleID)' if 'role_id' in cols and 'roleID' in cols else ('role_id' if 'role_id' in cols else ('roleID' if 'roleID' in cols else 'NULL'))
            
            cur.execute(f'SELECT id, "{name_col}", {role_expr}, {email_col} FROM Users')
            for row in cur.fetchall():
                uid, name, rid, email = row
                rname = self.roles_map.get(rid, 'Has No Role')
                display_name = f"{name} ({email})"
                item = QTreeWidgetItem([str(uid), display_name, rname])
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
            role_assigned = items[0].text(2)
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
        
        b = QHBoxLayout()
        b.addStretch()
        btn = QPushButton("Refresh Directory")
        btn.clicked.connect(self._refresh_tools)
        b.addWidget(btn)
        layout.addLayout(b)
        
        self.tool_tree = QTreeWidget()
        self.tool_tree.setHeaderLabels(["Tool Name", "Status"])
        layout.addWidget(self.tool_tree)
        
        self.notebook.addTab(tab, "System Tools")
        self._refresh_tools()

    def _refresh_tools(self):
        self.tool_tree.clear()
        conn = self._get_conn()
        try:
            cur = conn.cursor()
            cur.execute("SELECT name, is_active FROM ToolList ORDER BY name")
            for row in cur.fetchall():
                status = "Active" if row[1] else "Disabled"
                item = QTreeWidgetItem([row[0], status])
                self.tool_tree.addTopLevelItem(item)
        except Exception:
            pass
        finally:
            conn.close()
