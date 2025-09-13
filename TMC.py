import sys
import time
import json
import os

from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                             QPushButton, QTextEdit, QLabel, QComboBox, QDialog,
                             QFormLayout, QLineEdit, QDialogButtonBox,
                             QTabWidget, QCheckBox, QGroupBox, QListWidget,
                             QHBoxLayout, QListWidgetItem, QMessageBox, QInputDialog,
                             QFileDialog, QTableWidget, QTableWidgetItem,
                             QAbstractItemView, QHeaderView, QStyledItemDelegate)
from PyQt6.QtCore import QObject, QThread, pyqtSignal, QSettings, Qt
from PyQt6.QtGui import QAction, QColor, QFont, QIcon

# Selenium Imports
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, InvalidArgumentException
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.firefox.service import Service as FirefoxService
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.firefox.options import Options as FirefoxOptions
from webdriver_manager.chrome import ChromeDriverManager
from webdriver_manager.firefox import GeckoDriverManager

# --- Variabel Global untuk path file konfigurasi ---
FLOWS_CONFIG_FILE = "flows.json"


# --- Stylesheet untuk Flat UI ---
STYLE_SHEET = """
    QWidget {
        background-color: #2c3e50; color: #ecf0f1; font-family: 'Segoe UI', Arial, sans-serif; font-size: 10pt;
    } QMainWindow { background-color: #2c3e50; } QDialog { background-color: #34495e; } QLabel { color: #ecf0f1; }
    QPushButton {
        background-color: #3498db; color: white; border: none; padding: 8px 16px; border-radius: 5px; font-weight: bold;
    } QPushButton:hover { background-color: #2980b9; }
    QPushButton:disabled { background-color: #566573; color: #95a5a6; }
    QTextEdit { background-color: #212f3d; color: #ecf0f1; border-radius: 5px; border: 1px solid #34495e; font-family: 'Consolas', 'Courier New', monospace; }
    QComboBox { background-color: #34495e; border: 1px solid #566573; border-radius: 5px; padding: 4px; min-width: 6em; }
    QComboBox::drop-down { subcontrol-origin: padding; subcontrol-position: top right; width: 20px; border-left-width: 1px; border-left-color: #566573; border-left-style: solid; border-top-right-radius: 3px; border-bottom-right-radius: 3px; }
    QComboBox QAbstractItemView { background-color: #34495e; border: 1px solid #566573; selection-background-color: #3498db; }
    QTabWidget::pane { border: 1px solid #34495e; border-radius: 5px; }
    QTabBar::tab { background: #34495e; color: #ecf0f1; border: 1px solid #566573; border-bottom: none; border-top-left-radius: 5px; border-top-right-radius: 5px; padding: 8px; margin-right: 2px; }
    QTabBar::tab:selected, QTabBar::tab:hover { background: #4e6a85; }
    QLineEdit { background-color: #212f3d; border: 1px solid #566573; border-radius: 5px; padding: 4px; color: #ecf0f1; }
    QListWidget { background-color: #212f3d; border: 1px solid #566573; border-radius: 5px; }
    QListWidget::item:hover { background-color: #34495e; }
    QListWidget::item:selected { background-color: #3498db; color: white; }
    QTableWidget { background-color: #212f3d; border: 1px solid #566573; border-radius: 5px; gridline-color: #34495e; }
    QTableWidget::item { padding: 5px; }
    QTableWidget::item:selected { background-color: #3498db; color: white; }
    QHeaderView::section { background-color: #34495e; padding: 4px; border: 1px solid #566573; font-weight: bold; }
    QGroupBox { border: 1px solid #566573; border-radius: 5px; margin-top: 1ex; }
    QGroupBox::title { subcontrol-origin: margin; subcontrol-position: top left; padding: 0 3px; }
    QMenuBar { background-color: #34495e; } QMenuBar::item { background: transparent; } QMenuBar::item:selected { background: #4e6a85; }
    QMenu { background-color: #34495e; border: 1px solid #566573; } QMenu::item:selected { background-color: #3498db; }
"""

# --- Kelas Worker Selenium --- (Tidak ada perubahan di sini)
class SeleniumWorker(QObject):
    finished = pyqtSignal(tuple)
    progress = pyqtSignal(str)

    BY_MAP = {
        "ID": By.ID, "XPath": By.XPATH, "Name": By.NAME, "Class Name": By.CLASS_NAME,
        "CSS Selector": By.CSS_SELECTOR, "Link Text": By.LINK_TEXT,
    }

    def __init__(self, browser, url, username, password, flow_settings, test_flows_data):
        super().__init__()
        self.browser = browser; self.url = url; self.username = username; self.password = password
        self.flow_settings = flow_settings; self.test_flows_data = test_flows_data; self.driver = None

    def _replace_placeholders(self, value):
        if not isinstance(value, str): return value
        return value.replace("{URL}", self.url).replace("{USERNAME}", self.username).replace("{PASSWORD}", self.password)

    def _execute_action(self, action_data):
        action = action_data.get("action")
        by_string = action_data.get("by")
        by = self.BY_MAP.get(by_string)
        selector = self._replace_placeholders(action_data.get("selector"))
        value = self._replace_placeholders(action_data.get("value"))

        self.progress.emit(f"  - Aksi: {action}, By: {by_string or 'N/A'}, Selector: {selector or 'N/A'}, Value: {value or 'N/A'}")

        if action not in ["Buka URL", "Tunggu URL Mengandung"] and (not by or not selector):
            raise ValueError(f"Aksi '{action}' memerlukan 'By' dan 'Selector' yang valid.")

        wait = WebDriverWait(self.driver, 10)

        if action == "Buka URL":
            url_to_open = self.url if value == "{URL}" or not value else value
            self.driver.get(url_to_open)
        elif action == "Klik Elemen":
            wait.until(EC.element_to_be_clickable((by, selector))).click()
        elif action == "Isi Teks":
            element = wait.until(EC.visibility_of_element_located((by, selector)))
            element.clear(); element.send_keys(value)
        elif action == "Centang Checkbox (Ensure Checked)":
            element = wait.until(EC.presence_of_element_located((by, selector)))
            if not element.is_selected(): element.click(); self.progress.emit("    -> Checkbox dicentang.")
            else: self.progress.emit("    -> Checkbox sudah dalam keadaan tercentang.")
        elif action == "Hapus Centang Checkbox (Ensure Unchecked)":
            element = wait.until(EC.presence_of_element_located((by, selector)))
            if element.is_selected(): element.click(); self.progress.emit("    -> Centang pada checkbox dihapus.")
            else: self.progress.emit("    -> Checkbox sudah dalam keadaan tidak tercentang.")
        elif action == "Verifikasi Checkbox Tercentang":
            element = wait.until(EC.presence_of_element_located((by, selector)))
            if not element.is_selected(): raise AssertionError(f"Verifikasi Gagal! Checkbox '{selector}' tidak tercentang.")
            self.progress.emit("    -> Verifikasi Berhasil: Checkbox tercentang.")
        elif action == "Verifikasi Checkbox Tidak Tercentang":
            element = wait.until(EC.presence_of_element_located((by, selector)))
            if element.is_selected(): raise AssertionError(f"Verifikasi Gagal! Checkbox '{selector}' seharusnya tidak tercentang.")
            self.progress.emit("    -> Verifikasi Berhasil: Checkbox tidak tercentang.")
        elif action == "Tunggu Elemen Muncul":
            wait.until(EC.visibility_of_element_located((by, selector)))
        elif action == "Tunggu URL Mengandung":
            wait.until(EC.url_contains(value))
        elif action == "Verifikasi Teks Elemen":
            element_text = wait.until(EC.visibility_of_element_located((by, selector))).text
            if value not in element_text:
                raise AssertionError(f"Verifikasi Gagal! Teks '{value}' tidak ditemukan di elemen. Teks aktual: '{element_text}'")
            self.progress.emit(f"  - Verifikasi Teks Berhasil!")
        elif action == "Tunggu Elemen Hilang":
            self.progress.emit(f"    -> Menunggu elemen '{selector}' untuk hilang...")
            long_wait = WebDriverWait(self.driver, 25)
            long_wait.until(EC.invisibility_of_element_located((by, selector)))
            self.progress.emit(f"    -> Elemen '{selector}' berhasil hilang.")
        elif action == "Verifikasi Elemen TIDAK Muncul":
            self.progress.emit(f"  - Verifikasi: Memastikan elemen '{selector}' TIDAK muncul (max 4 detik)...")
            short_wait = WebDriverWait(self.driver, 4)
            try:
                short_wait.until(EC.visibility_of_element_located((by, selector)))
                raise AssertionError(f"Verifikasi Gagal! Elemen '{selector}' seharusnya TIDAK muncul, tapi ditemukan.")
            except TimeoutException:
                self.progress.emit("    -> Verifikasi Berhasil: Elemen tidak muncul seperti yang diharapkan.")
        else:
            raise NotImplementedError(f"Aksi '{action}' tidak dikenali.")

    def run_tests(self):
        self.progress.emit("Memulai rangkaian pengujian...")
        if not all([self.url, self.username, self.password, self.test_flows_data]):
            self.finished.emit((False, "Pengujian dibatalkan. Data/alur tes tidak lengkap.", None)); return
        try:
            self.progress.emit(f"Menyiapkan driver untuk {self.browser}...")
            if self.browser == "chrome":
                options = ChromeOptions();
                if self.flow_settings.get("headless"): options.add_argument("--headless=new")
                service = ChromeService(ChromeDriverManager().install()); self.driver = webdriver.Chrome(service=service, options=options)
            elif self.browser == "firefox":
                options = FirefoxOptions()
                if self.flow_settings.get("headless"): options.add_argument("--headless")
                service = FirefoxService(GeckoDriverManager().install()); self.driver = webdriver.Firefox(service=service, options=options)
            self.driver.maximize_window()
            for flow_name, actions in self.test_flows_data.items():
                self.progress.emit(f"\n--- Menjalankan Alur: {flow_name} ---")
                for action_data in actions: self._execute_action(action_data)
            self.finished.emit((True, "Semua alur tes berhasil diselesaikan.", None))
        except (InvalidArgumentException, ValueError) as e:
            error_message = f"Error Konfigurasi Aksi: {str(e)}"
            self.progress.emit(error_message)
            self.finished.emit((False, error_message, None))
        except Exception as e:
            error_message = f"Error pada rangkaian tes: {type(e).__name__}: {str(e)}"
            self.progress.emit(error_message)
            screenshot_path = "flow_error.png"
            if self.driver:
                try: self.driver.save_screenshot(screenshot_path); self.progress.emit(f"Screenshot error disimpan di {screenshot_path}")
                except Exception as ss_e: self.progress.emit(f"Gagal menyimpan screenshot: {ss_e}")
            self.finished.emit((False, error_message, screenshot_path))
        finally:
            if self.driver:
                self.progress.emit("Menutup browser...");
                if not self.flow_settings.get("headless"): time.sleep(3)
                self.driver.quit()

# --- Dialog untuk Menambah/Edit Aksi --- (Hanya untuk menambah)
class ActionDialog(QDialog):
    def __init__(self, action_data=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Tambah Aksi"); self.layout = QFormLayout(self)
        self.action_combo = QComboBox()
        self.action_combo.addItems([
            "Buka URL", "Klik Elemen", "Isi Teks",
            "Tunggu Elemen Muncul", "Tunggu Elemen Hilang", "Tunggu URL Mengandung",
            "Verifikasi Teks Elemen", "Verifikasi Elemen TIDAK Muncul",
            "Centang Checkbox (Ensure Checked)", "Hapus Centang Checkbox (Ensure Unchecked)",
            "Verifikasi Checkbox Tercentang", "Verifikasi Checkbox Tidak Tercentang"
        ])
        self.by_combo = QComboBox(); self.by_combo.addItems(["ID", "XPath", "Name", "Class Name", "CSS Selector", "Link Text"])
        self.selector_input = QLineEdit(); self.value_input = QLineEdit()
        self.layout.addRow("Aksi:", self.action_combo)
        self.layout.addRow("Cari Elemen Dengan (By):", self.by_combo)
        self.layout.addRow("Selector:", self.selector_input)
        self.layout.addRow("Data/Nilai:", self.value_input)
        self.button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.button_box.accepted.connect(self.accept); self.button_box.rejected.connect(self.reject)
        self.layout.addWidget(self.button_box); self.action_combo.currentTextChanged.connect(self.update_ui_for_action)
        self.update_ui_for_action(self.action_combo.currentText())

    def update_ui_for_action(self, action_text):
        selector_is_needed = action_text not in ["Buka URL", "Tunggu URL Mengandung"]
        value_is_needed = action_text in ["Buka URL", "Isi Teks", "Tunggu URL Mengandung", "Verifikasi Teks Elemen"]
        self.by_combo.setVisible(selector_is_needed)
        self.selector_input.setVisible(selector_is_needed)
        self.value_input.setVisible(value_is_needed)
        self.layout.labelForField(self.by_combo).setVisible(selector_is_needed)
        self.layout.labelForField(self.selector_input).setVisible(selector_is_needed)
        self.layout.labelForField(self.value_input).setVisible(value_is_needed)

    def get_data(self):
        return {
            "action": self.action_combo.currentText(),
            "by": self.by_combo.currentText() if self.by_combo.isVisible() else None,
            "selector": self.selector_input.text() if self.selector_input.isVisible() else None,
            "value": self.value_input.text() if self.value_input.isVisible() else None
        }

# *** BARU: Delegate untuk ComboBox di dalam Tabel ***
class ComboBoxDelegate(QStyledItemDelegate):
    def __init__(self, items, parent=None):
        super().__init__(parent)
        self.items = items

    def createEditor(self, parent, option, index):
        editor = QComboBox(parent)
        editor.addItems(self.items)
        return editor

    def setEditorData(self, editor, index):
        value = index.model().data(index, Qt.ItemDataRole.EditRole)
        if value in self.items:
            editor.setCurrentText(value)

    def setModelData(self, editor, model, index):
        model.setData(index, editor.currentText(), Qt.ItemDataRole.EditRole)

    def updateEditorGeometry(self, editor, option, index):
        editor.setGeometry(option.rect)

# --- Dialog Pengaturan ---
class SettingsDialog(QDialog):
    # ... (Metode __init__ dan bagian Environment/Kredensial tidak berubah) ...
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings"); self.setMinimumSize(900, 600)
        self.settings = QSettings("CVSuudRokok88", "TestRunnerApp")
        main_layout = QVBoxLayout(self); self.tabs = QTabWidget(); main_layout.addWidget(self.tabs)
        self.create_environment_tab(); self.create_credentials_tab(); self.create_flow_management_tab()
        self.button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        self.button_box.accepted.connect(self.accept); self.button_box.rejected.connect(self.reject)
        main_layout.addWidget(self.button_box)
        self.load_environments()
        self.environments_list.currentItemChanged.connect(self.on_environment_selected)
        self.credentials_list.currentItemChanged.connect(self.on_credential_selected_for_saving)

    # --- Bagian Environment dan Kredensial tidak berubah ---
    def _refresh_environment_list_ui(self):
        current_selection_text=None;
        if self.environments_list.currentItem():current_selection_text=self.environments_list.currentItem().text();
        self.environments_list.clear();self.environments_list.addItems(sorted(self.environments_data.keys()));
        if current_selection_text:
            items=self.environments_list.findItems(current_selection_text,Qt.MatchFlag.MatchExactly);
            if items:self.environments_list.setCurrentItem(items[0]);
        if not self.environments_list.currentItem()and self.environments_list.count()>0:self.environments_list.setCurrentItem(self.environments_list.item(0));
        if self.environments_list.count()==0:self.on_environment_selected(None);
    def load_environments(self):
        self.environments_data=json.loads(self.settings.value("environments","{}"));self._refresh_environment_list_ui();active_env_name=self.settings.value("active_environment","");items=self.environments_list.findItems(active_env_name,Qt.MatchFlag.MatchExactly);
        if items:self.environments_list.setCurrentItem(items[0]);
        elif self.environments_list.count()>0:self.environments_list.setCurrentItem(self.environments_list.item(0));
    def remove_environment(self):
        current_item=self.environments_list.currentItem();
        if not current_item:return;env_name=current_item.text();reply=QMessageBox.question(self,"Hapus Environment",f"Anda yakin ingin menghapus '{env_name}'?");
        if reply==QMessageBox.StandardButton.Yes:del self.environments_data[env_name];self._refresh_environment_list_ui();
    def create_environment_tab(self):
        env_widget=QWidget();main_layout=QHBoxLayout(env_widget);left_layout=QVBoxLayout();left_layout.addWidget(QLabel("Daftar Environment:"));self.environments_list=QListWidget();left_layout.addWidget(self.environments_list);btn_layout=QHBoxLayout();self.add_env_button=QPushButton("Tambah");self.add_env_button.clicked.connect(self.add_environment);self.remove_env_button=QPushButton("Hapus");self.remove_env_button.clicked.connect(self.remove_environment);btn_layout.addWidget(self.add_env_button);btn_layout.addWidget(self.remove_env_button);left_layout.addLayout(btn_layout);right_layout=QFormLayout();self.env_name_input=QLineEdit();self.env_name_input.setReadOnly(True);self.env_url_input=QLineEdit();self.save_env_button=QPushButton("Simpan Perubahan URL");self.save_env_button.clicked.connect(self.save_environment_details);right_layout.addRow("Nama Environment:",self.env_name_input);right_layout.addRow("URL:",self.env_url_input);right_layout.addRow(self.save_env_button);main_layout.addLayout(left_layout,1);main_layout.addLayout(right_layout,2);self.tabs.addTab(env_widget,"Environment");
    def create_credentials_tab(self):
        credentials_widget=QWidget();main_layout=QHBoxLayout(credentials_widget);left_layout=QVBoxLayout();self.credentials_label=QLabel("Kredensial untuk Environment:");left_layout.addWidget(self.credentials_label);self.credentials_list=QListWidget();self.credentials_list.itemClicked.connect(self.on_credential_item_clicked);left_layout.addWidget(self.credentials_list);self.remove_button=QPushButton("Hapus Kredensial Terpilih");self.remove_button.clicked.connect(self.remove_selected_credential);left_layout.addWidget(self.remove_button);right_layout=QVBoxLayout();form_group=QGroupBox("Tambah / Edit Kredensial");form_layout=QFormLayout();self.username_input=QLineEdit();self.password_input=QLineEdit();self.password_input.setEchoMode(QLineEdit.EchoMode.Password);form_layout.addRow("Username (Email):",self.username_input);form_layout.addRow("Password:",self.password_input);form_group.setLayout(form_layout);self.add_save_button=QPushButton("Tambah / Simpan Perubahan");self.add_save_button.clicked.connect(self.add_or_update_credential);right_layout.addWidget(form_group);right_layout.addWidget(self.add_save_button);right_layout.addStretch();main_layout.addLayout(left_layout,2);main_layout.addLayout(right_layout,3);self.tabs.addTab(credentials_widget,"Kredensial");
    def on_environment_selected(self,current_item=None,_=None):
        if current_item is None:current_item=self.environments_list.currentItem();
        if not current_item:self.env_name_input.clear();self.env_url_input.clear();self.credentials_list.clear();self.username_input.clear();self.password_input.clear();self.credentials_label.setText("Kredensial (Pilih Environment)");return;
        env_name=current_item.text();env_details=self.environments_data.get(env_name,{});self.env_name_input.setText(env_name);self.env_url_input.setText(env_details.get("url",""));self.credentials_label.setText(f"Kredensial untuk: {env_name}");self.credentials_list.clear();credentials=env_details.get("credentials",[]);
        for cred in credentials:self.credentials_list.addItem(cred['username']);
        active_cred_user=env_details.get("active_credential","");items=self.credentials_list.findItems(active_cred_user,Qt.MatchFlag.MatchExactly);
        if items:self.credentials_list.setCurrentItem(items[0]);
        elif self.credentials_list.count()>0:self.credentials_list.setCurrentItem(self.credentials_list.item(0));
        self.username_input.clear();self.password_input.clear();
    def on_credential_item_clicked(self,item):
        username=item.text();current_env_item=self.environments_list.currentItem();
        if not current_env_item:return;env_name=current_env_item.text();credentials=self.environments_data[env_name].get("credentials",[]);
        for cred in credentials:
            if cred['username']==username:self.username_input.setText(cred['username']);self.password_input.setText(cred['password']);break;
    def add_environment(self):
        name,ok=QInputDialog.getText(self,"Tambah Environment","Masukkan Nama Environment Baru:");
        if ok and name and name.strip()and name not in self.environments_data:self.environments_data[name]={"url":"","credentials":[],"active_credential":""};self.environments_list.addItem(name);self.environments_list.setCurrentRow(self.environments_list.count()-1);
    def save_environment_details(self):
        current_item=self.environments_list.currentItem();
        if not current_item:return;
        env_name=current_item.text();self.environments_data[env_name]["url"]=self.env_url_input.text();QMessageBox.information(self,"Sukses","Perubahan URL telah disimpan.");
    def add_or_update_credential(self):
        current_env_item=self.environments_list.currentItem();
        if not current_env_item:return;
        env_name=current_env_item.text();username=self.username_input.text().strip();password=self.password_input.text();
        if not username:return;
        credentials=self.environments_data[env_name]["credentials"];existing_cred=next((cred for cred in credentials if cred['username']==username),None);
        if existing_cred:existing_cred['password']=password;
        else:credentials.append({'username':username,'password':password});
        self.on_environment_selected(current_env_item);items=self.credentials_list.findItems(username,Qt.MatchFlag.MatchExactly);
        if items:self.credentials_list.setCurrentItem(items[0]);
        self.username_input.setText(username);self.password_input.setText(password);QMessageBox.information(self,"Sukses",f"Kredensial untuk '{username}' berhasil disimpan.");
    def remove_selected_credential(self):
        current_env_item=self.environments_list.currentItem();current_cred_item=self.credentials_list.currentItem();
        if not current_env_item or not current_cred_item:return;
        env_name=current_env_item.text();username_to_remove=current_cred_item.text();reply=QMessageBox.question(self,"Hapus Kredensial",f"Anda yakin ingin menghapus kredensial untuk '{username_to_remove}'?");
        if reply==QMessageBox.StandardButton.No:return;
        credentials=self.environments_data[env_name]["credentials"];self.environments_data[env_name]["credentials"]=[c for c in credentials if c['username']!=username_to_remove];self.on_environment_selected(current_env_item);
    def on_credential_selected_for_saving(self, item, _):
        current_env_item=self.environments_list.currentItem();
        if not current_env_item or not item:return;
        env_name=current_env_item.text();self.environments_data[env_name]["active_credential"]=item.text();

    # --- PERUBAHAN BESAR DIMULAI DI SINI ---
    def create_flow_management_tab(self):
        flow_widget = QWidget()
        layout = QHBoxLayout(flow_widget)
        
        # Panel Kiri
        left_panel = QWidget(); left_layout = QVBoxLayout(left_panel)
        left_layout.addWidget(QLabel("<b>Daftar Alur Tes (Centang untuk diaktifkan):</b>"))
        self.flow_list = QListWidget()
        self.flow_list.currentItemChanged.connect(self.on_flow_selected)
        left_layout.addWidget(self.flow_list)
        flow_button_layout = QHBoxLayout()
        add_flow_btn = QPushButton("Tambah Alur"); add_flow_btn.clicked.connect(self.add_flow)
        remove_flow_btn = QPushButton("Hapus Alur"); remove_flow_btn.clicked.connect(self.remove_flow)
        flow_button_layout.addWidget(add_flow_btn); flow_button_layout.addWidget(remove_flow_btn)
        left_layout.addLayout(flow_button_layout)

        # Panel Kanan
        right_panel = QWidget(); right_layout = QVBoxLayout(right_panel)
        self.actions_label = QLabel("<b>Langkah/Aksi untuk Alur: -</b>")
        right_layout.addWidget(self.actions_label)
        self.actions_table = QTableWidget()
        self.actions_table.setColumnCount(4)
        self.actions_table.setHorizontalHeaderLabels(["Aksi", "By", "Selector", "Data/Nilai"])
        self.actions_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.actions_table.itemChanged.connect(self.on_action_item_changed) # Terhubung ke penyimpanan real-time
        right_layout.addWidget(self.actions_table)
        
        header = self.actions_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        
        # Setup delegates untuk ComboBox di dalam tabel
        action_items = [
            "Buka URL", "Klik Elemen", "Isi Teks", "Tunggu Elemen Muncul", 
            "Tunggu Elemen Hilang", "Tunggu URL Mengandung", "Verifikasi Teks Elemen", 
            "Verifikasi Elemen TIDAK Muncul", "Centang Checkbox (Ensure Checked)", 
            "Hapus Centang Checkbox (Ensure Unchecked)", "Verifikasi Checkbox Tercentang", 
            "Verifikasi Checkbox Tidak Tercentang"
        ]
        by_items = ["", "ID", "XPath", "Name", "Class Name", "CSS Selector", "Link Text"]
        self.action_delegate = ComboBoxDelegate(action_items, self)
        self.by_delegate = ComboBoxDelegate(by_items, self)
        self.actions_table.setItemDelegateForColumn(0, self.action_delegate)
        self.actions_table.setItemDelegateForColumn(1, self.by_delegate)
        
        # Layout Tombol Aksi (Tanpa tombol Edit)
        action_button_layout = QHBoxLayout()
        add_action_btn = QPushButton("Tambah Aksi"); add_action_btn.clicked.connect(self.add_action)
        remove_action_btn = QPushButton("Hapus Aksi"); remove_action_btn.clicked.connect(self.remove_action)
        action_button_layout.addWidget(add_action_btn); action_button_layout.addWidget(remove_action_btn)
        
        move_buttons_layout = QVBoxLayout()
        move_up_btn = QPushButton("↑ Atas"); move_up_btn.clicked.connect(lambda: self.move_action(-1))
        move_down_btn = QPushButton("↓ Bawah"); move_down_btn.clicked.connect(lambda: self.move_action(1))
        move_buttons_layout.addWidget(move_up_btn); move_buttons_layout.addWidget(move_down_btn)
        
        action_button_layout.addStretch()
        action_button_layout.addLayout(move_buttons_layout)
        right_layout.addLayout(action_button_layout)
        
        self.headless_checkbox = QCheckBox("Jalankan Headless")
        self.headless_checkbox.setChecked(self.settings.value("flow/headless", False, type=bool))
        right_layout.addWidget(self.headless_checkbox, 0, Qt.AlignmentFlag.AlignRight)
        
        layout.addWidget(left_panel, 1); layout.addWidget(right_panel, 3)
        self.tabs.addTab(flow_widget, "Management Flow (Codeless)")
        self.column_to_key_map = {0: "action", 1: "by", 2: "selector", 3: "value"}
        self.load_flows()

    def add_default_login_flow_data(self):
        return {
            'test_login': [
                {"action": "Buka URL", "by": None, "selector": None, "value": "{URL}"},
                {"action": "Isi Teks", "by": "ID", "selector": "email", "value": "{USERNAME}"},
                {"action": "Isi Teks", "by": "ID", "selector": "password", "value": "{PASSWORD}"},
                {"action": "Klik Elemen", "by": "XPath", "selector": "//label[@for='validation']", "value": ""},
                {"action": "Klik Elemen", "by": "ID", "selector": "login", "value": ""},
                {"action": "Tunggu URL Mengandung", "by": None, "selector": None, "value": "dashboard"}
            ]
        }
    
    def load_flows(self):
        try:
            with open(FLOWS_CONFIG_FILE, 'r') as f: self.flows_data = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            self.flows_data = self.add_default_login_flow_data()
            self.save_flows_to_file()
        
        self.active_flows = self.settings.value("active_flows", [], type=list)
        current_selection = self.flow_list.currentItem().text() if self.flow_list.currentItem() else None
        self.flow_list.clear()
        
        new_selection_item = None
        for flow_name in sorted(self.flows_data.keys()):
            item = QListWidgetItem(flow_name)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if flow_name in self.active_flows else Qt.CheckState.Unchecked)
            self.flow_list.addItem(item)
            if flow_name == current_selection: new_selection_item = item
        
        if new_selection_item: self.flow_list.setCurrentItem(new_selection_item)
        elif self.flow_list.count() > 0: self.flow_list.setCurrentRow(0)
        else: self.on_flow_selected(None)

    def save_flows_to_file(self):
        try:
            with open(FLOWS_CONFIG_FILE, 'w') as f: json.dump(self.flows_data, f, indent=4)
        except Exception as e:
            QMessageBox.critical(self, "Error Menyimpan Flow", f"Gagal menyimpan alur tes ke {FLOWS_CONFIG_FILE}:\n{e}")

    def save_settings(self):
        self.settings.setValue("environments", json.dumps(self.environments_data))
        active_env_item = self.environments_list.currentItem()
        self.settings.setValue("active_environment", active_env_item.text() if active_env_item else "")
        self.settings.setValue("flow/headless", self.headless_checkbox.isChecked())
        active_flows = [self.flow_list.item(i).text() for i in range(self.flow_list.count()) if self.flow_list.item(i).checkState() == Qt.CheckState.Checked]
        self.settings.setValue("active_flows", active_flows)
        self.save_flows_to_file()
    
    def on_flow_selected(self, current_item, _=None):
        self.actions_table.blockSignals(True)
        self.actions_table.setRowCount(0)
        if not current_item:
            self.actions_label.setText("<b>Langkah/Aksi untuk Alur: -</b>")
            self.actions_table.blockSignals(False)
            return
            
        flow_name = current_item.text()
        self.actions_label.setText(f"<b>Langkah/Aksi untuk Alur: {flow_name}</b>")
        actions = self.flows_data.get(flow_name, [])
        self.actions_table.setRowCount(len(actions))
        
        disabled_color = QColor(40, 52, 64) # Warna untuk sel non-aktif
        
        for row, action_data in enumerate(actions):
            action_text = action_data.get("action", "")
            
            for col, key in self.column_to_key_map.items():
                value = action_data.get(key, "")
                item = QTableWidgetItem(str(value if value is not None else ""))
                self.actions_table.setItem(row, col, item)
            
            # Atur sel mana yang bisa diedit berdasarkan Aksi
            selector_needed = action_text not in ["Buka URL", "Tunggu URL Mengandung"]
            value_needed = action_text in ["Buka URL", "Isi Teks", "Tunggu URL Mengandung", "Verifikasi Teks Elemen"]
            
            for col, item_key in [(1, "by"), (2, "selector"), (3, "value")]:
                item = self.actions_table.item(row, col)
                should_be_editable = (item_key in ["by", "selector"] and selector_needed) or (item_key == "value" and value_needed)
                if not should_be_editable:
                    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                    item.setBackground(disabled_color)
                else:
                    item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
                    item.setBackground(QColor("#212f3d")) # Warna default

        self.actions_table.blockSignals(False)

    def on_action_item_changed(self, item):
        current_flow_item = self.flow_list.currentItem()
        if not current_flow_item: return

        row, col = item.row(), item.column()
        flow_name = current_flow_item.text()
        
        if flow_name in self.flows_data and len(self.flows_data[flow_name]) > row:
            key_to_update = self.column_to_key_map.get(col)
            if key_to_update:
                new_value = item.text()
                # Jika 'By' dikosongkan, jadikan None di data
                if key_to_update == 'by' and not new_value:
                    self.flows_data[flow_name][row][key_to_update] = None
                else:
                    self.flows_data[flow_name][row][key_to_update] = new_value
            
            # Jika kolom Aksi yang berubah, refresh seluruh baris untuk update flag editable
            if col == 0:
                self.on_flow_selected(current_flow_item)
                self.actions_table.selectRow(row)


    def add_flow(self):
        name, ok = QInputDialog.getText(self, "Tambah Alur Tes", "Masukkan Nama Alur Baru:")
        if ok and name and name.strip():
            name = name.strip()
            if name in self.flows_data:
                QMessageBox.warning(self, "Gagal", f"Alur dengan nama '{name}' sudah ada."); return
            self.flows_data[name] = []
            self.load_flows()
            items = self.flow_list.findItems(name, Qt.MatchFlag.MatchExactly)
            if items: self.flow_list.setCurrentItem(items[0])

    def remove_flow(self):
        current_item = self.flow_list.currentItem()
        if not current_item: return
        flow_name = current_item.text()
        reply = QMessageBox.question(self, "Hapus Alur", f"Anda yakin ingin menghapus alur '{flow_name}'?")
        if reply == QMessageBox.StandardButton.Yes:
            del self.flows_data[flow_name]
            self.load_flows()

    def add_action(self):
        current_flow_item = self.flow_list.currentItem()
        if not current_flow_item:
            QMessageBox.warning(self, "Peringatan", "Pilih alur tes terlebih dahulu."); return
        dialog = ActionDialog(parent=self)
        if dialog.exec():
            flow_name = current_flow_item.text()
            self.flows_data[flow_name].append(dialog.get_data())
            self.on_flow_selected(current_flow_item)

    def remove_action(self):
        current_flow_item = self.flow_list.currentItem()
        selected_rows = sorted([index.row() for index in self.actions_table.selectionModel().selectedRows()], reverse=True)
        if not current_flow_item or not selected_rows:
            QMessageBox.warning(self, "Peringatan", "Pilih satu atau lebih aksi untuk dihapus."); return
        
        reply = QMessageBox.question(self, "Hapus Aksi", f"Anda yakin ingin menghapus {len(selected_rows)} aksi yang dipilih?")
        if reply == QMessageBox.StandardButton.Yes:
            flow_name = current_flow_item.text()
            for row in selected_rows:
                del self.flows_data[flow_name][row]
            self.on_flow_selected(current_flow_item)
    
    def move_action(self, direction):
        current_flow_item = self.flow_list.currentItem()
        row = self.actions_table.currentRow()
        if not current_flow_item or row < 0: return
        
        flow_name = current_flow_item.text()
        actions = self.flows_data[flow_name]
        new_row = row + direction
        
        if 0 <= new_row < len(actions):
            actions.insert(new_row, actions.pop(row))
            self.on_flow_selected(current_flow_item)
            self.actions_table.selectRow(new_row)
    
    def accept(self):
        self.save_settings()
        super().accept()

# --- Jendela Utama Aplikasi --- (Tidak ada perubahan di sini)
class TestRunnerApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Aplikasi Test Runner (Codeless Edition)"); self.setGeometry(100, 100, 950, 600)
        self.settings = QSettings("CVSuudRokok88", "TestRunnerApp"); self.environments_data = {}
        self.central_widget = QWidget(); self.setCentralWidget(self.central_widget)
        self.main_layout = QHBoxLayout(self.central_widget)
        self.main_layout.setContentsMargins(10, 10, 10, 10); self.main_layout.setSpacing(10)
        self._create_left_panel(); self._create_right_panel()
        self.main_layout.setStretch(0, 1); self.main_layout.setStretch(1, 3); self._load_and_set_environments()
    
    def _create_left_panel(self):
        left_widget=QWidget();left_layout=QVBoxLayout(left_widget);left_layout.setContentsMargins(0,0,0,0);left_layout.setSpacing(10);left_layout.addWidget(QLabel("<h3>Pengaturan Cepat</h3>"));left_layout.addWidget(QLabel("<b>Environment:</b>"));self.env_combo=QComboBox();self.env_combo.currentTextChanged.connect(self._populate_credentials_for_env);left_layout.addWidget(self.env_combo);left_layout.addWidget(QLabel("<b>Kredensial Aktif:</b>"));self.cred_combo=QComboBox();left_layout.addWidget(self.cred_combo);left_layout.addWidget(QLabel("<b>Browser:</b>"));self.browser_combo=QComboBox();self.browser_combo.addItems(["chrome","firefox"]);left_layout.addWidget(self.browser_combo);left_layout.addStretch();self.settings_button=QPushButton("Manage Settings");self.settings_button.clicked.connect(self.open_settings_dialog);left_layout.addWidget(self.settings_button);self.main_layout.addWidget(left_widget);
    def _create_right_panel(self):
        right_widget=QWidget();right_layout=QVBoxLayout(right_widget);right_layout.setContentsMargins(0,0,0,0);right_layout.setSpacing(10);self.run_button=QPushButton("Jalankan Rangkaian Tes");self.run_button.clicked.connect(self.start_test);self.tabs=QTabWidget();self.log_area=QTextEdit();self.log_area.setReadOnly(True);self.tabs.addTab(self.log_area,"Log Hasil");self.summary_area=QTextEdit();self.summary_area.setReadOnly(True);self.tabs.addTab(self.summary_area,"Ringkasan");self.export_button=QPushButton("Export Hasil Tes");self.export_button.clicked.connect(self.export_results);right_layout.addWidget(self.run_button);right_layout.addWidget(self.tabs);right_layout.addWidget(self.export_button);self.main_layout.addWidget(right_widget);
    def _load_and_set_environments(self):
        self.environments_data=json.loads(self.settings.value("environments","{}"));self.env_combo.blockSignals(True);self.env_combo.clear();
        if not self.environments_data: self.env_combo.addItem("Tidak ada environment");self.env_combo.setEnabled(False);self.cred_combo.setEnabled(False);self.run_button.setEnabled(False);
        else:
            self.env_combo.addItems(sorted(self.environments_data.keys()));self.env_combo.setEnabled(True);self.cred_combo.setEnabled(True);self.run_button.setEnabled(True);active_env=self.settings.value("active_environment","");
            if active_env in self.environments_data: self.env_combo.setCurrentText(active_env);
        self.env_combo.blockSignals(False);self._populate_credentials_for_env(self.env_combo.currentText());
    def _populate_credentials_for_env(self,env_name):
        self.cred_combo.clear();
        if env_name and env_name in self.environments_data:
            env_details=self.environments_data[env_name];credentials=env_details.get("credentials",[]);
            if not credentials: self.cred_combo.addItem("Tidak ada kredensial");self.cred_combo.setEnabled(False);
            else:
                usernames=[cred['username']for cred in credentials];self.cred_combo.addItems(usernames);self.cred_combo.setEnabled(True);active_cred=env_details.get("active_credential","");
                if active_cred in usernames: self.cred_combo.setCurrentText(active_cred);
    def open_settings_dialog(self):
        dialog=SettingsDialog(self);
        if dialog.exec(): self.log("Settings disimpan.");self._load_and_set_environments();
        else: self.log("Perubahan settings dibatalkan.");

    def start_test(self):
        self.run_button.setEnabled(False); self.log_area.clear(); self.summary_area.clear(); self.log("Mempersiapkan pengujian...")
        selected_env = self.env_combo.currentText(); selected_user = self.cred_combo.currentText()
        if not selected_env or not selected_user or "Tidak ada" in selected_env or "Tidak ada" in selected_user:
            QMessageBox.critical(self, "Error", "Environment atau Kredensial tidak valid. Mohon periksa di Settings.")
            self.run_button.setEnabled(True); return
        env_details = self.environments_data.get(selected_env, {}); url = env_details.get("url", "")
        credentials = env_details.get("credentials", [])
        active_cred_details = next((c for c in credentials if c.get("username") == selected_user), {})
        password = active_cred_details.get("password", "")
        
        try:
            with open(FLOWS_CONFIG_FILE, 'r') as f: all_flows = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
             QMessageBox.critical(self, "Error", f"File konfigurasi alur tes '{FLOWS_CONFIG_FILE}' tidak ditemukan atau rusak.")
             self.run_button.setEnabled(True); return

        active_flow_names = self.settings.value("active_flows", [], type=list)
        test_flows_to_run = {name: all_flows[name] for name in active_flow_names if name in all_flows}
        if not test_flows_to_run:
            QMessageBox.warning(self, "Tidak Ada Tes", "Tidak ada alur tes yang dipilih untuk dijalankan. Silakan aktifkan di Settings.")
            self.run_button.setEnabled(True); return
        flow_settings = {"headless": self.settings.value("flow/headless", False, type=bool)}
        self.thread = QThread()
        self.worker = SeleniumWorker(
            browser=self.browser_combo.currentText(), url=url, username=selected_user, password=password,
            flow_settings=flow_settings, test_flows_data=test_flows_to_run)
        self.worker.moveToThread(self.thread); self.thread.started.connect(self.worker.run_tests)
        self.worker.finished.connect(self.on_test_finished); self.worker.progress.connect(self.log)
        self.worker.finished.connect(self.thread.quit); self.worker.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater); self.thread.start()

    def log(self,message):self.log_area.append(message);
    def on_test_finished(self,result):
        success,message,screenshot_path=result;self.summary_area.clear();summary_text=f"Hasil Tes: {'SUKSES' if success else 'GAGAL'}\n";summary_text+=f"Pesan: {message}\n";original_color=self.log_area.textColor();
        if success: self.log_area.setTextColor(QColor("#2ecc71"));self.summary_area.setStyleSheet("color: #2ecc71;");
        else:
            self.log_area.setTextColor(QColor("#e74c3c"));self.summary_area.setStyleSheet("color: #e74c3c;");
            if screenshot_path:summary_text+=f"Screenshot Error: {os.path.abspath(screenshot_path)}\n";
        self.log(f"\n--- HASIL: {'RANGKAIAN TES SELESEI' if success else 'GAGAL'} ---");self.log(message);self.summary_area.setText(summary_text);self.log_area.setTextColor(original_color);self.run_button.setEnabled(True);
    def export_results(self):
        log_content=self.log_area.toPlainText();summary_content=self.summary_area.toPlainText();
        if not log_content and not summary_content: QMessageBox.warning(self,"Export Gagal","Tidak ada hasil tes untuk diexport.");return;
        file_path,_=QFileDialog.getSaveFileName(self,"Simpan Hasil Tes","","Text Files (*.txt);;All Files (*)");
        if file_path:
            try:
                with open(file_path,'w',encoding='utf-8')as f:
                    f.write("="*20+" RINGKASAN TES "+"="*20+"\n");f.write(summary_content);f.write("\n\n"+"="*20+" LOG LENGKAP "+"="*20+"\n");f.write(log_content);
                QMessageBox.information(self,"Sukses",f"Hasil tes berhasil diexport ke:\n{file_path}");
            except Exception as e: QMessageBox.critical(self,"Export Error",f"Terjadi kesalahan saat menyimpan file: {e}");


if __name__ == '__main__':
    app = QApplication(sys.argv)
    app.setStyleSheet(STYLE_SHEET)
    window = TestRunnerApp()
    window.show()
    sys.exit(app.exec())