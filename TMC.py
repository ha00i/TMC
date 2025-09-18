import sys
import time
import json
import os
import shutil
import re

from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                             QPushButton, QTextEdit, QLabel, QComboBox, QDialog,
                             QFormLayout, QLineEdit, QDialogButtonBox,
                             QTabWidget, QCheckBox, QGroupBox, QListWidget,
                             QHBoxLayout, QListWidgetItem, QMessageBox, QInputDialog,
                             QFileDialog, QTableWidget, QTableWidgetItem,
                             QAbstractItemView, QHeaderView, QStyledItemDelegate,
                             QProgressBar, QSpacerItem, QSizePolicy, QStyle,
                             QMenuBar)
from PyQt6.QtCore import QObject, QThread, pyqtSignal, QSettings, Qt, QDir
from PyQt6.QtGui import QAction, QColor, QFont, QIcon, QPalette, QActionGroup, QPixmap

# Selenium Imports
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, InvalidArgumentException, WebDriverException
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.firefox.service import Service as FirefoxService
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.firefox.options import Options as FirefoxOptions
from webdriver_manager.chrome import ChromeDriverManager
from webdriver_manager.firefox import GeckoDriverManager

# --- Global Constants ---
FLOWS_CONFIG_FILE = "flows.json"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STYLE_DIR = os.path.join(BASE_DIR, "styles")


# --- Kelas Worker Selenium ---
class SeleniumWorker(QObject):
    finished = pyqtSignal(tuple)
    progress = pyqtSignal(str)

    BY_MAP = {
        "ID": By.ID, "XPath": By.XPATH, "Name": By.NAME, "Class Name": By.CLASS_NAME,
        "CSS Selector": By.CSS_SELECTOR, "Link Text": By.LINK_TEXT,
    }

    def __init__(self, browser, url, username, password, role, flow_settings, test_flows_data):
        super().__init__()
        self.browser = browser; self.url = url; self.username = username
        self.password = password; self.role = role
        self.flow_settings = flow_settings; self.test_flows_data = test_flows_data; self.driver = None
        self._is_stopped = False

    def stop(self):
        """Metode ini dipanggil dari thread utama untuk menandai bahwa worker harus berhenti."""
        self._is_stopped = True
        self.progress.emit(">>> Perintah berhenti diterima oleh worker...")

    def _replace_placeholders(self, value):
        if not isinstance(value, str): return value
        return value.replace("{URL}", self.url).replace("{USERNAME}", self.username).replace("{PASSWORD}", self.password).replace("{ROLE}", self.role)

    def _execute_action(self, action_data):
        # Pemeriksaan flag stop di awal setiap aksi.
        if self._is_stopped: return
        action = action_data.get("action")
        by_string = action_data.get("by")
        by = self.BY_MAP.get(by_string)
        selector = self._replace_placeholders(action_data.get("selector"))
        value = self._replace_placeholders(action_data.get("value"))

        self.progress.emit(f"  - Aksi: {action}, By: {by_string or 'N/A'}, Selector: {selector or 'N/A'}, Value: {value or 'N/A'}")

        if action not in ["Buka URL", "Tunggu URL Mengandung", "Tidur", "Beralih ke Konten Utama"] and (not by or not selector):
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
        elif action == "Beralih ke Iframe":
            self.progress.emit(f"    -> Beralih fokus ke iframe '{selector}'...")
            wait.until(EC.frame_to_be_available_and_switch_to_it((by, selector)))
            self.progress.emit("    -> Berhasil beralih ke iframe.")
        elif action == "Beralih ke Konten Utama":
            self.progress.emit("    -> Kembali ke konteks halaman utama...")
            self.driver.switch_to.default_content()
            self.progress.emit("    -> Berhasil kembali ke halaman utama.")
        elif action == "Tunggu Elemen Ada di DOM":
            wait.until(EC.presence_of_element_located((by, selector)))
            self.progress.emit("    -> Elemen ditemukan di dalam DOM.")
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
            self.progress.emit(f"  - Verifikasi: Memastikan elemen '{selector}' TIDAK muncul (max 5 detik)...")
            short_wait = WebDriverWait(self.driver, 5)
            try:
                short_wait.until(EC.visibility_of_element_located((by, selector)))
                raise AssertionError(f"Verifikasi Gagal! Elemen '{selector}' seharusnya TIDAK muncul, tapi ditemukan.")
            except TimeoutException:
                self.progress.emit("    -> Verifikasi Berhasil: Elemen tidak muncul seperti yang diharapkan.")
        elif action == "Tidur":
            duration = float(value) # Mengubah value dari string (misal "3") menjadi angka
            self.progress.emit(f"    -> Jeda selama {duration} detik...") # Memberi log
            time.sleep(duration) # Perintah untuk berhenti sejenak
        elif action == "Gulir ke Elemen":
            element = wait.until(EC.presence_of_element_located((by, selector)))
            self.driver.execute_script("arguments[0].scrollIntoView({block: 'center', inline: 'center'});", element)
            self.progress.emit(f"    -> Elemen '{selector}' digulir ke tengah layar.")
        elif action == "Klik Elemen via JS":
            element = wait.until(EC.presence_of_element_located((by, selector)))
            self.driver.execute_script("arguments[0].click();", element)
            self.progress.emit("    -> Elemen diklik menggunakan JavaScript.")
        elif action == "Tunggu Elemen Siap Diklik":
            wait.until(EC.element_to_be_clickable((by, selector)))
            self.progress.emit("    -> Elemen siap untuk diklik.")
        else:
            raise NotImplementedError(f"Aksi '{action}' tidak dikenali.")

    def run_tests(self):
        self.progress.emit("Memulai rangkaian pengujian...")
        if not all([self.url, self.username, self.password, self.test_flows_data]):
            self.finished.emit((False, "Pengujian dibatalkan. Data/alur tes tidak lengkap.", None)); return
        
        current_flow_name = "unknown_flow"
        try:
            # Pemeriksaan flag stop sebelum memulai proses berat (setup browser).
            if self._is_stopped: raise InterruptedError("Pengujian dihentikan oleh pengguna sebelum dimulai.")
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

            for flow_name, flow_data in self.test_flows_data.items():
                current_flow_name = flow_name
                # Pemeriksaan flag stop di antara setiap alur tes.
                if self._is_stopped: raise InterruptedError("Pengujian dihentikan oleh pengguna.")
                self.progress.emit(f"\n--- Menjalankan Alur: {flow_name} ---")
                
                actions = flow_data.get('actions', [])
                for action_data in actions:
                    # Pemeriksaan flag stop di antara setiap aksi dalam satu alur.
                    if self._is_stopped: raise InterruptedError("Pengujian dihentikan oleh pengguna.")
                    self._execute_action(action_data)
            self.finished.emit((True, "Semua alur tes berhasil diselesaikan.", None))
        except InterruptedError as e:
            # Blok ini khusus menangani penghentian oleh pengguna.
            error_message = f"Pengujian dihentikan: {str(e)}"
            self.progress.emit(error_message)
            self.finished.emit((False, error_message, None))
        except (InvalidArgumentException, ValueError) as e:
            error_message = f"Error Konfigurasi Aksi: {str(e)}"
            self.progress.emit(error_message)
            self.finished.emit((False, error_message, None))
        except WebDriverException as e:
            error_message = f"Error WebDriver: Browser mungkin ditutup atau terjadi masalah koneksi.\nDetail: {e.msg}"
            self.progress.emit(error_message)
            self.finished.emit((False, error_message, None))
        except Exception as e:
            error_message = f"Error pada rangkaian tes '{current_flow_name}': {type(e).__name__}: {str(e)}"
            self.progress.emit(error_message)

            screenshot_path = None
            if self.driver:
                try:
                    safe_flow_name = re.sub(r'[\\/*?:"<>|]', "", current_flow_name).replace(" ", "_")
                    timestamp = time.strftime("%Y%m%d-%H%M%S")
                    screenshot_path = f"error_{timestamp}_{safe_flow_name}.png"
                    self.driver.save_screenshot(screenshot_path)
                    self.progress.emit(f"Screenshot error disimpan di {screenshot_path}")
                except Exception as ss_e:
                    self.progress.emit(f"Gagal menyimpan screenshot: {ss_e}")
            
            self.finished.emit((False, error_message, screenshot_path))
        finally:
            if self.driver:
                self.progress.emit("Menutup browser...");
                try:
                    # Logika ini memastikan ada jeda singkat HANYA jika tes selesai normal (tidak di-stop)
                    if not self.flow_settings.get("headless") and not self._is_stopped: time.sleep(3)
                    self.driver.quit()
                except Exception as quit_e:
                    self.progress.emit(f"Error saat menutup browser: {quit_e}")


# --- Dialog untuk Menambah Aksi ---
class ActionDialog(QDialog):
    def __init__(self, action_data=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Tambah Aksi"); self.layout = QFormLayout(self)
        self.action_combo = QComboBox()
        self.action_combo.addItems([
            "Buka URL", "Klik Elemen", "Isi Teks",
            "Tunggu Elemen Muncul", "Tidur", "Tunggu Elemen Hilang", "Tunggu URL Mengandung",
            "Verifikasi Teks Elemen", "Verifikasi Elemen TIDAK Muncul",
            "Centang Checkbox (Ensure Checked)", "Hapus Centang Checkbox (Ensure Unchecked)",
            "Verifikasi Checkbox Tercentang", "Verifikasi Checkbox Tidak Tercentang", "Gulir ke Elemen", "Klik Elemen via JS", "Beralih ke Iframe", "Beralih ke Konten Utama" 
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
        needs_selector = action_text not in ["Buka URL", "Tunggu URL Mengandung"]
        needs_value = action_text in ["Buka URL", "Isi Teks", "Tunggu URL Mengandung", "Verifikasi Teks Elemen", "Tidur"]
        self.by_combo.setVisible(needs_selector)
        self.selector_input.setVisible(needs_selector)
        self.value_input.setVisible(needs_value)
        self.layout.labelForField(self.by_combo).setVisible(needs_selector)
        self.layout.labelForField(self.selector_input).setVisible(needs_selector)
        self.layout.labelForField(self.value_input).setVisible(needs_value)

    def get_data(self):
        return {
            "action": self.action_combo.currentText(),
            "by": self.by_combo.currentText() if self.by_combo.isVisible() else None,
            "selector": self.selector_input.text() if self.selector_input.isVisible() else None,
            "value": self.value_input.text() if self.value_input.isVisible() else None
        }


# --- Delegate untuk ComboBox di dalam Tabel ---
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
        if value in self.items: editor.setCurrentText(value)

    def setModelData(self, editor, model, index):
        model.setData(index, editor.currentText(), Qt.ItemDataRole.EditRole)

    def updateEditorGeometry(self, editor, option, index):
        editor.setGeometry(option.rect)


# --- Delegate Kredensial ---
class CredentialDelegate(QStyledItemDelegate):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_window = parent

    def createEditor(self, parent, option, index):
        editor = QComboBox(parent)
        return editor

    def setEditorData(self, editor, index):
        row = index.row()
        env_name = self.parent_window.drives_table.item(row, 0).text().strip()
        
        env_details = self.parent_window.environments_data.get(env_name, {})
        credentials = env_details.get("credentials", [])
        
        editor.clear()
        for cred in credentials:
            display_text = f"{cred['username']} ({cred.get('role', 'No Role')})"
            editor.addItem(display_text)
            
        current_active_user = env_details.get("active_credential", "")
        for i in range(editor.count()):
            if editor.itemText(i).startswith(current_active_user):
                editor.setCurrentIndex(i)
                break

    def setModelData(self, editor, model, index):
        new_display_text = editor.currentText()
        new_username = new_display_text.split(' (')[0]
        
        row = index.row()
        env_name = self.parent_window.drives_table.item(row, 0).text().strip()
        
        self.parent_window.environments_data[env_name]['active_credential'] = new_username
        self.parent_window.save_active_credential_change()

# --- Dialog Pengaturan ---
class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings"); self.setMinimumSize(950, 650)
        self.settings = QSettings("CVSuudRokok88", "TestRunnerApp")
        
        self.role_presets = json.loads(self.settings.value("role_flow_presets", "{}"))

        main_layout = QVBoxLayout(self); self.tabs = QTabWidget(); main_layout.addWidget(self.tabs)
        self.create_environment_tab(); self.create_credentials_tab(); self.create_flow_management_tab()
        self.button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        self.button_box.accepted.connect(self.accept); self.button_box.rejected.connect(self.reject)
        main_layout.addWidget(self.button_box)
        self.load_environments()
        self.environments_list.currentItemChanged.connect(self.on_environment_selected)
        self.credentials_list.currentItemChanged.connect(self.on_credential_selected_for_saving)

    def _refresh_environment_list_ui(self):
        current_selection_text = None
        if self.environments_list.currentItem():
            current_selection_text = self.environments_list.currentItem().text()
        self.environments_list.clear(); self.environments_list.addItems(sorted(self.environments_data.keys()))
        if current_selection_text:
            items = self.environments_list.findItems(current_selection_text, Qt.MatchFlag.MatchExactly)
            if items: self.environments_list.setCurrentItem(items[0])
        if not self.environments_list.currentItem() and self.environments_list.count() > 0:
            self.environments_list.setCurrentItem(self.environments_list.item(0))
        if self.environments_list.count() == 0: self.on_environment_selected(None)

    def load_environments(self):
        self.environments_data = json.loads(self.settings.value("environments", "{}"))
        self._refresh_environment_list_ui()
        active_env_name = self.settings.value("active_environment", "")
        items = self.environments_list.findItems(active_env_name, Qt.MatchFlag.MatchExactly)
        if items: self.environments_list.setCurrentItem(items[0])
        elif self.environments_list.count() > 0: self.environments_list.setCurrentItem(self.environments_list.item(0))

    def remove_environment(self):
        current_item = self.environments_list.currentItem()
        if not current_item: return
        env_name = current_item.text()
        reply = QMessageBox.question(self, "Hapus Environment", f"Anda yakin ingin menghapus '{env_name}'?")
        if reply == QMessageBox.StandardButton.Yes:
            del self.environments_data[env_name]; self._refresh_environment_list_ui()

    def create_environment_tab(self):
        env_widget=QWidget();main_layout=QHBoxLayout(env_widget);left_layout=QVBoxLayout();left_layout.addWidget(QLabel("Daftar Environment:"));self.environments_list=QListWidget();left_layout.addWidget(self.environments_list);btn_layout=QHBoxLayout();self.add_env_button=QPushButton("Tambah");self.add_env_button.clicked.connect(self.add_environment);self.remove_env_button=QPushButton("Hapus");self.remove_env_button.clicked.connect(self.remove_environment);btn_layout.addWidget(self.add_env_button);btn_layout.addWidget(self.remove_env_button);left_layout.addLayout(btn_layout);right_layout=QFormLayout();self.env_name_input=QLineEdit();self.env_name_input.setReadOnly(True);self.env_url_input=QLineEdit();self.save_env_button=QPushButton("Simpan Perubahan URL");self.save_env_button.clicked.connect(self.save_environment_details);right_layout.addRow("Nama Environment:",self.env_name_input);right_layout.addRow("URL:",self.env_url_input);right_layout.addRow(self.save_env_button);main_layout.addLayout(left_layout,1);main_layout.addLayout(right_layout,2);self.tabs.addTab(env_widget,"Environment")

    def create_credentials_tab(self):
        credentials_widget = QWidget()
        main_layout = QHBoxLayout(credentials_widget)
        left_layout = QVBoxLayout()
        self.credentials_label = QLabel("Kredensial untuk Environment:")
        left_layout.addWidget(self.credentials_label)
        self.credentials_list = QListWidget()
        self.credentials_list.itemClicked.connect(self.on_credential_item_clicked)
        left_layout.addWidget(self.credentials_list)
        self.remove_cred_button = QPushButton("Hapus Kredensial Terpilih")
        self.remove_cred_button.clicked.connect(self.remove_selected_credential)
        left_layout.addWidget(self.remove_cred_button)
        right_layout = QVBoxLayout()
        form_group = QGroupBox("Tambah / Edit Kredensial")
        form_layout = QFormLayout()
        self.username_input = QLineEdit()
        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.role_input = QLineEdit()
        form_layout.addRow("Username (Email):", self.username_input)
        form_layout.addRow("Password:", self.password_input)
        form_layout.addRow("Role:", self.role_input)
        form_group.setLayout(form_layout)
        self.add_save_button = QPushButton("Tambah / Simpan Perubahan")
        self.add_save_button.clicked.connect(self.add_or_update_credential)
        right_layout.addWidget(form_group)
        right_layout.addWidget(self.add_save_button)
        right_layout.addStretch()
        main_layout.addLayout(left_layout, 2)
        main_layout.addLayout(right_layout, 3)
        self.tabs.addTab(credentials_widget, "Kredensial")

    def on_environment_selected(self, current_item=None, _=None):
        if current_item is None: current_item = self.environments_list.currentItem()
        if not current_item:
            self.env_name_input.clear(); self.env_url_input.clear(); self.credentials_list.clear()
            self.username_input.clear(); self.password_input.clear(); self.role_input.clear()
            self.credentials_label.setText("Kredensial (Pilih Environment)")
            self.flow_role_combo.clear()
            return
            
        env_name = current_item.text()
        env_details = self.environments_data.get(env_name, {})
        self.env_name_input.setText(env_name); self.env_url_input.setText(env_details.get("url", ""))
        self.credentials_label.setText(f"Kredensial untuk: {env_name}"); self.credentials_list.clear()
        
        credentials = env_details.get("credentials", [])
        for cred in credentials:
            display_text = f"{cred['username']} ({cred.get('role', 'No Role')})"
            self.credentials_list.addItem(display_text)
            
        active_cred_user = env_details.get("active_credential", "")
        for i in range(self.credentials_list.count()):
            item = self.credentials_list.item(i)
            if item.text().startswith(active_cred_user):
                self.credentials_list.setCurrentItem(item)
                break
        else:
            if self.credentials_list.count() > 0:
                self.credentials_list.setCurrentItem(self.credentials_list.item(0))

        self.username_input.clear(); self.password_input.clear(); self.role_input.clear()
        
        self.flow_role_combo.blockSignals(True)
        self.flow_role_combo.clear()
        unique_roles = sorted(list(set(c.get("role", "") for c in credentials if c.get("role"))))
        self.flow_role_combo.addItems([""] + unique_roles)
        self.flow_role_combo.blockSignals(False)

    def on_credential_item_clicked(self, item):
        username = item.text().split(' (')[0]
        current_env_item = self.environments_list.currentItem()
        if not current_env_item: return
        env_name = current_env_item.text()
        credentials = self.environments_data[env_name].get("credentials", [])
        for cred in credentials:
            if cred['username'] == username:
                self.username_input.setText(cred['username'])
                self.password_input.setText(cred['password'])
                self.role_input.setText(cred.get('role', ''))
                break

    def add_environment(self):
        name, ok = QInputDialog.getText(self, "Tambah Environment", "Masukkan Nama Environment Baru:")
        if ok and name and name.strip() and name not in self.environments_data:
            self.environments_data[name] = {"url": "", "credentials": [], "active_credential": ""}
            self.environments_list.addItem(name)
            self.environments_list.setCurrentRow(self.environments_list.count() - 1)

    def save_environment_details(self):
        current_item = self.environments_list.currentItem()
        if not current_item: return
        env_name = current_item.text()
        self.environments_data[env_name]["url"] = self.env_url_input.text()
        QMessageBox.information(self, "Sukses", "Perubahan URL telah disimpan.")

    def add_or_update_credential(self):
        current_env_item = self.environments_list.currentItem()
        if not current_env_item: return
        env_name = current_env_item.text()
        username = self.username_input.text().strip()
        password = self.password_input.text()
        role = self.role_input.text().strip()
        if not username: return
        credentials = self.environments_data[env_name]["credentials"]
        existing_cred = next((cred for cred in credentials if cred['username'] == username), None)
        if existing_cred:
            existing_cred['password'] = password; existing_cred['role'] = role
        else:
            credentials.append({'username': username, 'password': password, 'role': role})
        self.on_environment_selected(current_env_item)
        for i in range(self.credentials_list.count()):
            item = self.credentials_list.item(i)
            if item.text().startswith(username):
                self.credentials_list.setCurrentItem(item)
                self.on_credential_item_clicked(item)
                break
        QMessageBox.information(self, "Sukses", f"Kredensial untuk '{username}' berhasil disimpan.")

    def remove_selected_credential(self):
        current_env_item = self.environments_list.currentItem(); current_cred_item = self.credentials_list.currentItem()
        if not current_env_item or not current_cred_item: return
        env_name = current_env_item.text()
        username_to_remove = current_cred_item.text().split(' (')[0]
        reply = QMessageBox.question(self, "Hapus Kredensial", f"Anda yakin ingin menghapus kredensial untuk '{username_to_remove}'?")
        if reply == QMessageBox.StandardButton.No: return
        credentials = self.environments_data[env_name]["credentials"]
        self.environments_data[env_name]["credentials"] = [c for c in credentials if c['username'] != username_to_remove]
        self.on_environment_selected(current_env_item)

    def on_credential_selected_for_saving(self, item, _):
        current_env_item = self.environments_list.currentItem()
        if not current_env_item or not item: return
        env_name = current_env_item.text()
        self.environments_data[env_name]["active_credential"] = item.text().split(' (')[0]

    def create_flow_management_tab(self):
        flow_widget = QWidget(); main_tab_layout = QVBoxLayout(flow_widget)
        top_panels_layout = QHBoxLayout(); main_tab_layout.addLayout(top_panels_layout, 1)

        flows_group_box = QGroupBox("Alur Tes & Preset Role")
        flows_layout = QVBoxLayout(flows_group_box)
        
        flows_layout.addWidget(QLabel("<b>Daftar Alur Tes:</b>"))
        self.flow_list = QListWidget()
        self.flow_list.currentItemChanged.connect(self.on_flow_selected)
        flows_layout.addWidget(self.flow_list)

        flow_button_layout = QHBoxLayout()
        add_flow_btn = QPushButton("Tambah"); add_flow_btn.clicked.connect(self.add_flow)
        remove_flow_btn = QPushButton("Hapus"); remove_flow_btn.clicked.connect(self.remove_flow)
        
        # --- PERUBAHAN DIMULAI DI SINI ---
        move_flow_up_btn = QPushButton("↑") # Ganti ikon dengan teks
        # BARIS DI BAWAH INI DIHAPUS: move_flow_up_btn.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_ArrowUp))
        move_flow_up_btn.clicked.connect(lambda: self.move_flow_item(-1))
        
        move_flow_down_btn = QPushButton("↓") # Ganti ikon dengan teks
        # BARIS DI BAWAH INI DIHAPUS: move_flow_down_btn.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_ArrowDown))
        move_flow_down_btn.clicked.connect(lambda: self.move_flow_item(1))
        # --- AKHIR DARI PERUBAHAN PERTAMA ---
        
        flow_button_layout.addWidget(add_flow_btn); flow_button_layout.addWidget(remove_flow_btn)
        flow_button_layout.addStretch()
        flow_button_layout.addWidget(move_flow_up_btn); flow_button_layout.addWidget(move_flow_down_btn)
        flows_layout.addLayout(flow_button_layout)

        preset_form_layout = QFormLayout()
        preset_form_layout.setContentsMargins(0, 10, 0, 5)
        self.flow_role_combo = QComboBox()
        self.flow_role_combo.currentTextChanged.connect(self.load_role_preset)
        preset_form_layout.addRow(QLabel("<b>Pilih/Simpan Preset Role:</b>"), self.flow_role_combo)
        flows_layout.addLayout(preset_form_layout)
        
        self.save_preset_button = QPushButton("Simpan Status Centang untuk Role Ini")
        self.save_preset_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_DialogSaveButton))
        self.save_preset_button.clicked.connect(self.save_role_preset)
        flows_layout.addWidget(self.save_preset_button)

        top_panels_layout.addWidget(flows_group_box, 1)

        self.actions_group_box = QGroupBox("Langkah/Aksi untuk Alur: -")
        actions_layout = QVBoxLayout(self.actions_group_box)
        
        self.actions_table = QTableWidget(); self.actions_table.setColumnCount(4); self.actions_table.setHorizontalHeaderLabels(["Aksi", "By", "Selector", "Data/Nilai"]); self.actions_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.actions_table.itemChanged.connect(self.on_action_type_changed)
        header = self.actions_table.horizontalHeader(); header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive); header.setStretchLastSection(True)
        self.actions_table.setColumnWidth(0, 180); self.actions_table.setColumnWidth(1, 100); self.actions_table.setColumnWidth(2, 250)
        action_items = ["Buka URL", "Klik Elemen", "Isi Teks", "Tunggu Elemen Muncul", "Tunggu Elemen Hilang", "Tunggu URL Mengandung", "Tidur", "Verifikasi Teks Elemen", "Verifikasi Elemen TIDAK Muncul", "Centang Checkbox (Ensure Checked)", "Hapus Centang Checkbox (Ensure Unchecked)", "Verifikasi Checkbox Tercentang", "Verifikasi Checkbox Tidak Tercentang", "Gulir ke Elemen", "Klik Elemen via JS"]
        by_items = ["", "ID", "XPath", "Name", "Class Name", "CSS Selector", "Link Text"]; self.action_delegate = ComboBoxDelegate(action_items, self); self.by_delegate = ComboBoxDelegate(by_items, self); self.actions_table.setItemDelegateForColumn(0, self.action_delegate); self.actions_table.setItemDelegateForColumn(1, self.by_delegate)
        actions_layout.addWidget(self.actions_table)
        
        action_button_layout = QHBoxLayout(); add_action_btn = QPushButton("Tambah Aksi"); add_action_btn.clicked.connect(self.add_action); remove_action_btn = QPushButton("Hapus Aksi"); remove_action_btn.clicked.connect(self.remove_action)

        # --- PERUBAHAN DIMULAI DI SINI ---
        move_action_up_btn = QPushButton("Atas")
        # BARIS DI BAWAH INI DIHAPUS: move_action_up_btn.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_ArrowUp))
        move_action_up_btn.clicked.connect(lambda: self.move_action(-1))
        
        move_action_down_btn = QPushButton("Bawah")
        # BARIS DI BAWAH INI DIHAPUS: move_action_down_btn.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_ArrowDown))
        move_action_down_btn.clicked.connect(lambda: self.move_action(1))
        # --- AKHIR DARI PERUBAHAN KEDUA ---

        action_button_layout.addWidget(add_action_btn); action_button_layout.addWidget(remove_action_btn); action_button_layout.addStretch(); action_button_layout.addWidget(move_action_up_btn); action_button_layout.addWidget(move_action_down_btn)
        actions_layout.addLayout(action_button_layout)
        
        self.save_actions_button = QPushButton("Simpan Perubahan Aksi Alur Ini")
        self.save_actions_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_DialogSaveButton))
        self.save_actions_button.clicked.connect(self.save_current_flow_actions)
        self.save_actions_button.setEnabled(False)
        actions_layout.addWidget(self.save_actions_button, 0, Qt.AlignmentFlag.AlignRight)

        top_panels_layout.addWidget(self.actions_group_box, 3)
        
        bottom_bar_layout = QHBoxLayout(); bottom_bar_layout.addStretch()
        self.headless_checkbox = QCheckBox("Jalankan Headless"); self.headless_checkbox.setChecked(self.settings.value("flow/headless", False, type=bool))
        bottom_bar_layout.addWidget(self.headless_checkbox)
        main_tab_layout.addLayout(bottom_bar_layout)
        
        self.tabs.addTab(flow_widget, "Management Flow (Codeless)")
        self.column_to_key_map = {0: "action", 1: "by", 2: "selector", 3: "value"}
        self.load_flows()

    def load_role_preset(self, role_name):
        if not role_name: return
        self.flow_list.blockSignals(True)
        flows_for_this_role = self.role_presets.get(role_name, [])
        for i in range(self.flow_list.count()):
            item = self.flow_list.item(i)
            if item.text() in flows_for_this_role:
                item.setCheckState(Qt.CheckState.Checked)
            else:
                item.setCheckState(Qt.CheckState.Unchecked)
        self.flow_list.blockSignals(False)

    def save_role_preset(self):
        selected_role = self.flow_role_combo.currentText()
        if not selected_role:
            QMessageBox.warning(self, "Tidak Ada Role Terpilih", "Pilih sebuah role dari dropdown untuk menyimpan preset.")
            return
        checked_flows = []
        for i in range(self.flow_list.count()):
            item = self.flow_list.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                checked_flows.append(item.text())
        self.role_presets[selected_role] = checked_flows
        QMessageBox.information(self, "Preset Disimpan", f"Status centang saat ini telah disimpan untuk role '{selected_role}'.")

    def save_current_flow_actions(self):
        current_flow_item = self.flow_list.currentItem()
        if not current_flow_item: return
        flow_name = current_flow_item.text()
        new_actions = []
        for row in range(self.actions_table.rowCount()):
            action_data = {}
            for col, key in self.column_to_key_map.items():
                item = self.actions_table.item(row, col)
                action_data[key] = item.text() if item else ""
            new_actions.append(action_data)
        self.flows_data[flow_name]['actions'] = new_actions
        self.save_flows_to_file()
        QMessageBox.information(self, "Aksi Disimpan", f"Perubahan aksi untuk alur '{flow_name}' telah disimpan.")

    def on_flow_selected(self, current_item, _=None):
        self.actions_table.blockSignals(True)
        self.actions_table.setRowCount(0)
        if not current_item:
            self.actions_group_box.setTitle("Langkah/Aksi untuk Alur: -")
            self.save_actions_button.setEnabled(False)
            self.actions_table.blockSignals(False)
            return
        self.save_actions_button.setEnabled(True)
        flow_name = current_item.text()
        self.actions_group_box.setTitle(f"Langkah/Aksi untuk Alur: {flow_name}")
        actions = self.flows_data.get(flow_name, {}).get('actions', [])
        self.actions_table.setRowCount(len(actions))
        for row, action_data in enumerate(actions):
            action_text = action_data.get("action", "")
            for col, key in self.column_to_key_map.items():
                value = action_data.get(key, ""); item = QTableWidgetItem(str(value if value is not None else ""))
                self.actions_table.setItem(row, col, item)
            self._update_row_editability(row, action_text)
        self.actions_table.blockSignals(False)

    def load_flows(self):
        try:
            with open(FLOWS_CONFIG_FILE, 'r') as f: self.flows_data = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            self.flows_data = self.add_default_login_flow_data(); self.save_flows_to_file()
        needs_resave = False
        if self.flows_data:
            for name, data in self.flows_data.items():
                if isinstance(data, dict) and 'role' in data:
                    self.flows_data[name] = {'actions': data.get('actions', [])}
                    needs_resave = True
        if needs_resave:
            self.save_flows_to_file()
            QMessageBox.information(self, "Struktur Data Dimigrasi", "Struktur file flows.json telah disederhanakan. Data role sekarang dikelola sebagai preset terpisah.")
        self._refresh_flow_list_ui()

    def accept(self):
        self.settings.setValue("role_flow_presets", json.dumps(self.role_presets))
        self.save_settings()
        super().accept()

    def _update_row_editability(self, row, action_text):
        selector_needed = action_text not in ["Buka URL", "Tunggu URL Mengandung", "Tidur"]
        value_needed = action_text in ["Buka URL", "Isi Teks", "Tunggu URL Mengandung", "Verifikasi Teks Elemen", "Tidur"]
        disabled_color = self.palette().color(QPalette.ColorRole.Window).lighter(110)
        base_color = self.palette().color(QPalette.ColorRole.Base)
        for col, item_key in [(1, "by"), (2, "selector"), (3, "value")]:
            item = self.actions_table.item(row, col)
            if not item: continue
            should_be_editable = (item_key in ["by", "selector"] and selector_needed) or (item_key == "value" and value_needed)
            if not should_be_editable:
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable); item.setBackground(disabled_color)
            else:
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable); item.setBackground(base_color)

    def on_action_type_changed(self, item):
        if item.column() == 0:
            action_text = item.text()
            self._update_row_editability(item.row(), action_text)
    
    def move_flow_item(self, direction):
        current_row = self.flow_list.currentRow();
        if current_row < 0: return
        new_row = current_row + direction
        if 0 <= new_row < self.flow_list.count():
            current_item = self.flow_list.takeItem(current_row); self.flow_list.insertItem(new_row, current_item)
            self.flow_list.setCurrentRow(new_row); keys = list(self.flows_data.keys())
            key_to_move = keys.pop(current_row); keys.insert(new_row, key_to_move)
            self.flows_data = {key: self.flows_data[key] for key in keys}

    def add_default_login_flow_data(self):
        return {'01.Test_login_akurat': {'actions': []}, '02.Master Barang - Input Sukses': {'actions': []}, '03.test_logout': {'actions': []}}

    def _refresh_flow_list_ui(self):
        self.active_flows = self.settings.value("active_flows", [], type=list)
        current_selection = self.flow_list.currentItem().text() if self.flow_list.currentItem() else None
        self.flow_list.blockSignals(True); self.flow_list.clear()
        new_selection_item = None
        for flow_name in self.flows_data.keys():
            item = QListWidgetItem(flow_name); item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if flow_name in self.active_flows else Qt.CheckState.Unchecked)
            self.flow_list.addItem(item)
            if flow_name == current_selection: new_selection_item = item
        self.flow_list.blockSignals(False)
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
        active_flows = []
        for i in range(self.flow_list.count()):
            item = self.flow_list.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                active_flows.append(item.text())
        self.settings.setValue("active_flows", active_flows)

    def add_flow(self):
        name, ok = QInputDialog.getText(self, "Tambah Alur Tes", "Masukkan Nama Alur Baru:")
        if ok and name and name.strip():
            name = name.strip()
            if name in self.flows_data: QMessageBox.warning(self, "Gagal", f"Alur dengan nama '{name}' sudah ada."); return
            self.flows_data[name] = {'actions': []}
            self.save_flows_to_file()
            self._refresh_flow_list_ui()
            items = self.flow_list.findItems(name, Qt.MatchFlag.MatchExactly)
            if items: self.flow_list.setCurrentItem(items[0])

    def remove_flow(self):
        current_item = self.flow_list.currentItem()
        if not current_item: return
        flow_name = current_item.text()
        reply = QMessageBox.question(self, "Hapus Alur", f"Anda yakin ingin menghapus alur '{flow_name}'?")
        if reply == QMessageBox.StandardButton.Yes:
            del self.flows_data[flow_name]; self.save_flows_to_file(); self._refresh_flow_list_ui()

    def add_action(self):
        current_flow_item = self.flow_list.currentItem()
        if not current_flow_item: QMessageBox.warning(self, "Peringatan", "Pilih alur tes terlebih dahulu."); return
        dialog = ActionDialog(parent=self)
        if dialog.exec():
            action_data = dialog.get_data()
            row_count = self.actions_table.rowCount()
            self.actions_table.insertRow(row_count)
            for col, key in self.column_to_key_map.items():
                value = action_data.get(key, "")
                self.actions_table.setItem(row_count, col, QTableWidgetItem(str(value if value is not None else "")))
            self._update_row_editability(row_count, action_data.get("action", ""))

    def remove_action(self):
        selected_rows = sorted([index.row() for index in self.actions_table.selectionModel().selectedRows()], reverse=True)
        if not selected_rows: QMessageBox.warning(self, "Peringatan", "Pilih satu atau lebih aksi untuk dihapus."); return
        for row in selected_rows:
            self.actions_table.removeRow(row)

    def move_action(self, direction):
        row = self.actions_table.currentRow()
        if row < 0:
            return

        new_row = row + direction
        if not (0 <= new_row < self.actions_table.rowCount()):
            return

        self.actions_table.blockSignals(True)

        taken_items = []
        for col in range(self.actions_table.columnCount()):
            taken_items.append(self.actions_table.takeItem(row, col))

        self.actions_table.removeRow(row)
        self.actions_table.insertRow(new_row)

        for col, item in enumerate(taken_items):
            self.actions_table.setItem(new_row, col, item)

        self.actions_table.blockSignals(False)
        self.actions_table.selectRow(new_row)


# --- Jendela Utama Aplikasi ---
class TestRunnerApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Test Automation Challenge"); self.setGeometry(100, 100, 850, 650)
        self.setMinimumSize(800, 600)
        self.settings = QSettings("CVSuudRokok88", "TestRunnerApp")
        self.environments_data = {}; self.worker = None; self.thread = None
        self.total_test_steps = 0; self.current_test_step = 0
        self.active_workers = []
        self.last_error_screenshot_path = None
        self._create_actions(); self._create_menu_bar(); self._create_central_widget()
        self._load_and_set_environments(); self._apply_theme_on_startup()
        
    def _create_central_widget(self):
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.main_layout = QVBoxLayout(self.central_widget)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)
        content_layout = QVBoxLayout(); content_layout.setContentsMargins(10, 10, 10, 10); content_layout.setSpacing(10)
        self._create_header(); self._create_main_toolbar(); self._create_drives_table(); self._create_log_area(); self._create_progress_bar()
        content_layout.addWidget(self.drives_group_box); content_layout.addWidget(self.analyzing_label)
        content_layout.addWidget(self.log_area, 1); content_layout.addWidget(self.legend_and_progress_widget)
        self.main_layout.addLayout(content_layout)

    def _create_actions(self):
        self.quit_action = QAction("&Quit", self); self.quit_action.triggered.connect(self.close)

    def _create_menu_bar(self):
        menu_bar = self.menuBar(); file_menu = menu_bar.addMenu("&File"); file_menu.addAction(self.quit_action)
        view_menu = menu_bar.addMenu("&View"); theme_menu = view_menu.addMenu("&Theme")
        self.theme_action_group = QActionGroup(self); self.theme_action_group.setExclusive(True); self.theme_action_group.triggered.connect(self._change_theme)
        if os.path.exists(STYLE_DIR):
            for style_file in os.listdir(STYLE_DIR):
                if style_file.endswith(".css"):
                    theme_name = os.path.splitext(style_file)[0].replace("_", " ").title()
                    action = QAction(theme_name, self, checkable=True); action.setData(os.path.join(STYLE_DIR, style_file))
                    self.theme_action_group.addAction(action); theme_menu.addAction(action)

    def _apply_stylesheet(self, path):
        try:
            with open(path, 'r') as f: self.setStyleSheet(f.read())
        except FileNotFoundError: self.log(f"Warning: Stylesheet not found at {path}")

    def _apply_theme_on_startup(self):
        saved_theme_path = self.settings.value("theme/path", "")
        found_action = next((action for action in self.theme_action_group.actions() if action.data() == saved_theme_path), None)
        if not found_action and self.theme_action_group.actions(): found_action = self.theme_action_group.actions()[0]
        if found_action:
            found_action.setChecked(True); self._apply_stylesheet(found_action.data())
        else: self.log("No themes found in the 'styles' directory.")

    def _change_theme(self, action):
        theme_path = action.data(); self.log(f"Changing theme to: {action.text()}")
        self._apply_stylesheet(theme_path); self.settings.setValue("theme/path", theme_path)

    def _create_header(self):
        header_widget = QWidget(); header_widget.setObjectName("HeaderWidget")
        header_layout = QHBoxLayout(header_widget); header_layout.setContentsMargins(10, 5, 10, 5)
        title_label = QLabel(); title_label.setObjectName("HeaderLabel"); pixmap = QPixmap("assets/header.png"); title_label.setFixedSize(80, 50); title_label.setPixmap(pixmap); title_label.setScaledContents(True)
        github_link = "<a href='https://github.com/ha00i/TMC' style='color: #0066cc; text-decoration: underline;'>👉 Updates?</a>"
        feedback_link = "<a href='mailto:cobaingatemailnya@gmail.com' style='color: #0066cc; text-decoration: underline;'>✉ Send Feedback</a>"
        rec_label = QLabel(github_link); rec_label.setOpenExternalLinks(True)
        send_label = QLabel(feedback_link); send_label.setOpenExternalLinks(True)
        header_layout.addWidget(title_label); header_layout.addStretch(); header_layout.addWidget(rec_label); header_layout.addWidget(send_label)
        self.main_layout.addWidget(header_widget)

    def _create_main_toolbar(self):
        toolbar_widget = QWidget(); toolbar_widget.setObjectName("MainToolBar"); self.main_layout.addWidget(toolbar_widget)
        toolbar_layout = QVBoxLayout(toolbar_widget); toolbar_layout.setContentsMargins(5, 0, 5, 0); self.tabs = QTabWidget(); toolbar_layout.addWidget(self.tabs)
        home_tab, home_layout = QWidget(), QHBoxLayout(); home_tab.setLayout(home_layout); home_layout.setContentsMargins(10, 15, 10, 15)
        def create_tool_button(text, icon_enum):
            button = QPushButton(f" {text}"); button.setObjectName("ToolBarButton"); button.setIcon(self.style().standardIcon(icon_enum)); button.setFlat(True); button.setLayoutDirection(Qt.LayoutDirection.LeftToRight); return button
        defrag_group = QGroupBox("Serangkaian Test"); defrag_layout = QHBoxLayout(defrag_group); self.analyze_button = create_tool_button("Jalankan", QStyle.StandardPixmap.SP_MediaPlay); defrag_layout.addWidget(self.analyze_button)
        process_group = QGroupBox("Process"); process_layout = QHBoxLayout(process_group); self.stop_button = create_tool_button("Stop", QStyle.StandardPixmap.SP_MediaStop); self.stop_button.setEnabled(False); process_layout.addWidget(self.stop_button)
        others_group = QGroupBox("Others Features"); others_layout = QHBoxLayout(others_group); self.settings_button_main = create_tool_button("Pengaturan", QStyle.StandardPixmap.SP_FileDialogDetailedView)
        self.export_log_button = create_tool_button("Export Log", QStyle.StandardPixmap.SP_DialogSaveButton)
        others_layout.addWidget(self.settings_button_main); others_layout.addWidget(self.export_log_button)
        home_layout.addWidget(defrag_group); home_layout.addWidget(process_group); home_layout.addWidget(others_group); home_layout.addStretch(); self.tabs.addTab(home_tab, "Home")
        options_tab = QWidget(); options_layout = QFormLayout(options_tab); options_layout.setContentsMargins(20, 20, 20, 20); self.browser_combo_options = QComboBox(); self.browser_combo_options.addItems(["chrome", "firefox"]); options_layout.addRow(QLabel("<b>Browser for testing:</b>"), self.browser_combo_options); self.tabs.addTab(options_tab, "Options")
        help_tab = QWidget(); help_layout = QVBoxLayout(help_tab); help_layout.addWidget(QLabel("Bantuan dan Informasi Aplikasi")); self.tabs.addTab(help_tab, "Help")
        self.analyze_button.clicked.connect(self.start_test); self.stop_button.clicked.connect(self.stop_test); self.settings_button_main.clicked.connect(self.open_settings_dialog)
        self.export_log_button.clicked.connect(self.export_log)

    def _create_drives_table(self):
        self.drives_group_box = QGroupBox("List Data"); layout = QVBoxLayout(self.drives_group_box); layout.setContentsMargins(5, 5, 5, 5)
        self.drives_table = QTableWidget(); self.drives_table.setColumnCount(3); self.drives_table.setHorizontalHeaderLabels(["Env", "Site URL", "Active User (Role)"]); self.drives_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows); self.drives_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.drives_table.setEditTriggers(QAbstractItemView.EditTrigger.DoubleClicked)
        self.credential_delegate = CredentialDelegate(self)
        self.drives_table.setItemDelegateForColumn(2, self.credential_delegate)
        self.drives_table.verticalHeader().setVisible(False); self.drives_table.setShowGrid(True)
        header = self.drives_table.horizontalHeader(); header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents); header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch); header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.drives_table); self.drives_table.currentItemChanged.connect(self.on_drive_selected)

    def _create_log_area(self):
        self.analyzing_label = QLabel("Select a drive and click Analyze or Defrag."); self.analyzing_label.setObjectName("AnalyzingLabel")
        self.log_area = QTextEdit(); self.log_area.setObjectName("LogArea"); self.log_area.setReadOnly(True)

    def _create_progress_bar(self):
        self.legend_and_progress_widget = QWidget(); layout = QHBoxLayout(self.legend_and_progress_widget); layout.setContentsMargins(0, 5, 0, 5)
        legend_widget = QWidget(); legend_widget.setObjectName("LegendWidget"); legend_layout = QHBoxLayout(legend_widget); legend_layout.setContentsMargins(5, 5, 5, 5)
        legend_layout.addWidget(QLabel("⬜")); legend_layout.addWidget(QLabel("🟩")); legend_layout.addWidget(QLabel("🟦"));legend_layout.addWidget(QLabel("Ngising Is the BEST!!")); legend_layout.addStretch()
        self.progress_bar = QProgressBar(); self.progress_bar.setTextVisible(True); self.progress_bar.setFormat("%p%")
        layout.addWidget(legend_widget, 1); layout.addWidget(self.progress_bar, 2)

    def _load_and_set_environments(self):
        self.environments_data = json.loads(self.settings.value("environments", "{}"))
        self.drives_table.setRowCount(0)
        self.analyze_button.setEnabled(bool(self.environments_data))
        if not self.environments_data: return
        
        self.drives_table.setRowCount(len(self.environments_data))
        active_env_name = self.settings.value("active_environment", "")
        row_to_select = 0
        for i, (name, details) in enumerate(self.environments_data.items()):
            active_user = details.get("active_credential", "N/A")
            credentials = details.get("credentials", [])
            active_cred_details = next((c for c in credentials if c.get("username") == active_user), None)
            role = active_cred_details.get('role', 'No Role') if active_cred_details else 'No Role'
            display_cred = f"{active_user} ({role})"
            
            item_drive = QTableWidgetItem(f" {name}"); item_drive.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_DriveHDIcon))
            self.drives_table.setItem(i, 0, item_drive)
            self.drives_table.setItem(i, 1, QTableWidgetItem(details.get("url", "No URL")))
            self.drives_table.setItem(i, 2, QTableWidgetItem(display_cred))
            if name == active_env_name: row_to_select = i
        
        if self.drives_table.rowCount() > 0: self.drives_table.selectRow(row_to_select)

    def on_drive_selected(self, current, previous):
        if not current: self.analyzing_label.setText("No drive selected."); return
        env_name = self.drives_table.item(current.row(), 0).text().strip()
        self.analyzing_label.setText(f"Ready to run tests on: {env_name}")

    def open_settings_dialog(self):
        dialog = SettingsDialog(self)
        if dialog.exec():
            self.log("Settings saved."); self._load_and_set_environments()
        else: self.log("Settings changes canceled.")
            
    def set_controls_enabled(self, enabled):
        self.analyze_button.setEnabled(enabled); self.tabs.setEnabled(enabled); self.settings_button_main.setEnabled(enabled); self.drives_table.setEnabled(enabled); self.stop_button.setEnabled(not enabled)

    def save_active_credential_change(self):
        self.settings.setValue("environments", json.dumps(self.environments_data))
        self._load_and_set_environments()

    def export_log(self):
        log_content = self.log_area.toPlainText()
        if not log_content.strip():
            QMessageBox.information(self, "Export Log", "Tidak ada log untuk di-export.")
            return

        timestamp = time.strftime("%Y%m%d-%H%M%S")
        default_filename = os.path.join(os.getcwd(), f"test_log_{timestamp}.txt")
        
        filePath, _ = QFileDialog.getSaveFileName(self, "Save Log File", default_filename, "Text Files (*.txt);;All Files (*)")

        if not filePath:
            return

        try:
            with open(filePath, 'w', encoding='utf-8') as f:
                f.write(log_content)
            
            if self.last_error_screenshot_path and os.path.exists(self.last_error_screenshot_path):
                dir_name = os.path.dirname(filePath)
                base_name = os.path.basename(self.last_error_screenshot_path)
                new_screenshot_path = os.path.join(dir_name, base_name)
                shutil.copy2(self.last_error_screenshot_path, new_screenshot_path)
                QMessageBox.information(self, "Export Successful", f"Log file dan screenshot error telah disimpan di:\n{dir_name}")
            else:
                QMessageBox.information(self, "Export Successful", f"Log file telah disimpan di:\n{filePath}")

        except Exception as e:
            QMessageBox.critical(self, "Export Error", f"Gagal menyimpan file: {e}")
    
    def start_test(self):
        self.last_error_screenshot_path = None
        selected_rows = self.drives_table.selectionModel().selectedRows()
        if not selected_rows:
            QMessageBox.warning(self, "No Environment Selected", "Please select an environment from the 'Drives Available' list to test."); return

        selected_row = selected_rows[0].row(); selected_env = self.drives_table.item(selected_row, 0).text().strip()
        self.set_controls_enabled(False); self.log_area.clear(); self.progress_bar.setValue(0)
        self.log(f"Preparing to test environment: '{selected_env}'..."); self.analyzing_label.setText(f"Analyzing {selected_env}...")
        
        env_details = self.environments_data.get(selected_env, {})
        url = env_details.get("url", "")
        
        try:
            with open(FLOWS_CONFIG_FILE, 'r') as f: all_flows = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
             QMessageBox.critical(self, "Error", f"Flow configuration file '{FLOWS_CONFIG_FILE}' not found or is corrupted."); self.set_controls_enabled(True); return

        active_flow_names = self.settings.value("active_flows", [], type=list)
        if not active_flow_names:
            QMessageBox.warning(self, "No Tests", "Tidak ada alur tes yang dicentang untuk dijalankan. Silakan aktifkan di Pengaturan."); self.set_controls_enabled(True); return
        
        self.log(f"Menggunakan kredensial yang aktif untuk environment '{selected_env}'...")
        credentials = env_details.get("credentials", [])
        active_user_name = env_details.get("active_credential", "")
        
        target_cred = next((c for c in credentials if c.get("username") == active_user_name), None)
        
        if not target_cred:
            QMessageBox.critical(self, "Error Kredensial", f"Kredensial aktif '{active_user_name}' tidak ditemukan di environment '{selected_env}'.\n\nSilakan periksa Pengaturan.")
            self.set_controls_enabled(True)
            return

        username = target_cred['username']
        password = target_cred['password']
        role = target_cred.get('role', '') # Role yang sebenarnya digunakan untuk tes
        self.log(f"Tes akan dijalankan menggunakan user: {username} (Role: {role or 'N/A'})")
        
        test_flows_to_run = {name: all_flows[name] for name in all_flows if name in active_flow_names}
            
        self.total_test_steps = sum(len(data.get('actions', [])) for data in test_flows_to_run.values())
        self.current_test_step = 0; self.progress_bar.setMaximum(self.total_test_steps if self.total_test_steps > 0 else 100)

        flow_settings = {"headless": self.settings.value("flow/headless", False, type=bool)}
        self.thread = QThread()
        self.worker = SeleniumWorker(browser=self.browser_combo_options.currentText(), url=url, 
                                     username=username, password=password, role=role, 
                                     flow_settings=flow_settings, test_flows_data=test_flows_to_run)
            
        self.worker.moveToThread(self.thread); self.thread.started.connect(self.worker.run_tests)
        self.worker.finished.connect(self.on_test_finished); self.worker.progress.connect(self.log)
        self.worker.finished.connect(self.thread.quit); self.worker.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)
        self.active_workers.append({'worker': self.worker, 'thread': self.thread})
        self.thread.start()

    def stop_test(self):
        """Metode ini memanggil `stop()` pada worker yang aktif dengan umpan balik yang lebih jelas."""
        if not self.active_workers:
            self.log("Tidak ada tes yang sedang berjalan untuk dihentikan.")
            return

        # Langsung berikan feedback di log utama
        self.log("\n>>> MENGIRIM PERINTAH BERHENTI...")
        for item in self.active_workers:
            if item.get('worker'):
                item['worker'].stop() # Ini akan memicu log 'Perintah berhenti diterima...' dari worker
        
        self.log(">>> Menunggu aksi yang sedang berjalan selesai sebelum berhenti sepenuhnya.")
        self.stop_button.setEnabled(False) # Nonaktifkan tombol agar tidak diklik lagi

    def log(self, message):
        self.log_area.append(message)
        if message.strip().startswith("- Aksi:"):
            self.current_test_step += 1
            if self.total_test_steps > 0: self.progress_bar.setValue(self.current_test_step)

    def on_test_finished(self, result):
        success, message, screenshot_path = result
        if not success and screenshot_path:
            self.last_error_screenshot_path = screenshot_path
        
        self.progress_bar.setValue(self.progress_bar.maximum())
        current_env_item = self.drives_table.currentItem()
        env_name = self.drives_table.item(current_env_item.row(), 0).text().strip() if current_env_item else "the operation"
        if success:
            final_message, color = "COMPLETED", "#27ae60"; self.analyzing_label.setText(f"Analysis of {env_name} completed.")
        else:
            final_message, color = "FAILED", "#c0392b"; self.analyzing_label.setText(f"Operation on {env_name} failed.")
        
        self.log_area.append(f"<br><font color='{color}'>--- <b>RESULT: {final_message}</b> ---</font>")
        self.log_area.append(f"<font color='{color}'>{message}</font>")

        if screenshot_path: self.log(f"Error screenshot: {os.path.abspath(screenshot_path)}")
        self.set_controls_enabled(True)
        self.active_workers.clear()

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = TestRunnerApp()
    window.show()
    sys.exit(app.exec())