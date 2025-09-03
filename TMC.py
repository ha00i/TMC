import sys
import time
import json
import os
import importlib.util

from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                             QPushButton, QTextEdit, QLabel, QComboBox, QDialog,
                             QFormLayout, QLineEdit, QDialogButtonBox, QMenuBar,
                             QTabWidget, QCheckBox, QGroupBox, QListWidget,
                             QHBoxLayout, QListWidgetItem, QMessageBox, QInputDialog,
                             QFileDialog)
from PyQt6.QtCore import QObject, QThread, pyqtSignal, QSettings, Qt, QRegularExpression
from PyQt6.QtGui import QAction, QColor, QFont, QSyntaxHighlighter, QTextCharFormat

# Selenium Imports
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.firefox.service import Service as FirefoxService
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.firefox.options import Options as FirefoxOptions
from webdriver_manager.chrome import ChromeDriverManager
from webdriver_manager.firefox import GeckoDriverManager

# --- Variabel Global untuk Path Skrip ---
SCRIPT_DIR = "test_scripts"

# --- Kelas untuk Syntax Highlighting ---
class PythonHighlighter(QSyntaxHighlighter):
    """Memberikan pewarnaan sintaks dasar Python pada QTextEdit."""
    def __init__(self, parent):
        super().__init__(parent)
        self.highlighting_rules = []

        keyword_format = QTextCharFormat()
        keyword_format.setForeground(QColor("#569CD6"))
        keyword_format.setFontWeight(QFont.Weight.Bold)
        keywords = [
            "\\bdef\\b", "\\bclass\\b", "\\bimport\\b", "\\bfrom\\b", "\\breturn\\b",
            "\\bif\\b", "\\belse\\b", "\\belif\\b", "\\bfor\\b", "\\bwhile\\b",
            "\\btry\\b", "\\bexcept\\b", "\\bfinally\\b", "\\bwith\\b", "\\bas\\b",
            "\\bpass\\b", "\\bTrue\\b", "\\bFalse\\b", "\\bNone\\b", "\\band\\b",
            "\\bor\\b", "\\bnot\\b", "\\bin\\b", "\\bis\\b"
        ]
        for word in keywords:
            self.highlighting_rules.append((QRegularExpression(word), keyword_format))

        self_format = QTextCharFormat()
        self_format.setForeground(QColor("#9CDCFE"))
        self.highlighting_rules.append((QRegularExpression("\\bself\\b"), self_format))

        string_format = QTextCharFormat()
        string_format.setForeground(QColor("#CE9178"))
        self.highlighting_rules.append((QRegularExpression("\".*\""), string_format))
        self.highlighting_rules.append((QRegularExpression("'.*'"), string_format))

        comment_format = QTextCharFormat()
        comment_format.setForeground(QColor("#6A9955"))
        comment_format.setFontItalic(True)
        self.highlighting_rules.append((QRegularExpression("#[^\n]*"), comment_format))

        number_format = QTextCharFormat()
        number_format.setForeground(QColor("#B5CEA8"))
        self.highlighting_rules.append((QRegularExpression("\\b[0-9]+\\.?[0-9]*\\b"), number_format))

    def highlightBlock(self, text):
        for pattern, format in self.highlighting_rules:
            match_iterator = pattern.globalMatch(text)
            while match_iterator.hasNext():
                match = match_iterator.next()
                self.setFormat(match.capturedStart(), match.capturedLength(), format)

# --- Worker untuk Menjalankan Selenium di Thread Terpisah ---
class SeleniumWorker(QObject):
    """Menjalankan tugas Selenium di background thread agar UI tidak freeze."""
    finished = pyqtSignal(tuple)
    progress = pyqtSignal(str)

    def __init__(self, browser, url, username, password, flow_settings, test_flow_steps):
        super().__init__()
        self.browser = browser
        self.url = url
        self.username = username
        self.password = password
        self.flow_settings = flow_settings
        self.test_flow_steps = test_flow_steps
        self.driver = None

    def run_tests(self):
        self.progress.emit("Memulai rangkaian pengujian...")
        if not all([self.url, self.username, self.password, self.test_flow_steps]):
            self.finished.emit((False, "Pengujian dibatalkan. Data/alur tes tidak lengkap.", None))
            return
        
        try:
            self.progress.emit(f"Menyiapkan driver untuk {self.browser}...")
            if self.browser == "chrome":
                options = ChromeOptions()
                if self.flow_settings.get("headless"):
                    options.add_argument("--headless=new")
                service = ChromeService(ChromeDriverManager().install())
                self.driver = webdriver.Chrome(service=service, options=options)
            elif self.browser == "firefox":
                options = FirefoxOptions()
                if self.flow_settings.get("headless"):
                    options.add_argument("--headless")
                service = FirefoxService(GeckoDriverManager().install())
                self.driver = webdriver.Firefox(service=service, options=options)
            
            self.driver.maximize_window()

            for step_name in self.test_flow_steps:
                self.progress.emit(f"\n--- Menjalankan Langkah: {step_name} ---")
                script_path = os.path.join(SCRIPT_DIR, f"{step_name}.py")

                if not os.path.exists(script_path):
                    self.progress.emit(f"Peringatan: File skrip '{script_path}' tidak ditemukan. Dilewati.")
                    continue

                spec = importlib.util.spec_from_file_location(step_name, script_path)
                test_module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(test_module)

                if hasattr(test_module, 'run'):
                    func_to_call = getattr(test_module, 'run')
                    # Panggil fungsi run dan periksa hasilnya
                    success = func_to_call(
                        driver=self.driver, 
                        worker=self, 
                        username=self.username, 
                        password=self.password, 
                        url=self.url
                    )
                    if not success:
                        # Jika langkah gagal, hentikan seluruh alur tes
                        raise Exception(f"Langkah '{step_name}' gagal dieksekusi.")
                else:
                    self.progress.emit(f"Peringatan: Fungsi 'run' tidak ditemukan di '{script_path}'.")

            self.finished.emit((True, "Semua langkah tes berhasil diselesaikan.", None))

        except Exception as e:
            error_message = f"Error pada rangkaian tes: {str(e)}"
            self.progress.emit(error_message)
            screenshot_path = "flow_error.png"
            if self.driver:
                self.driver.save_screenshot(screenshot_path)
                self.progress.emit(f"Screenshot error disimpan di {screenshot_path}")
            self.finished.emit((False, error_message, screenshot_path))

        finally:
            if self.driver:
                self.progress.emit("Menutup browser...")
                # Beri jeda sedikit agar pengguna bisa melihat hasil akhir jika tidak headless
                if not self.flow_settings.get("headless"):
                    time.sleep(3)
                self.driver.quit()

# --- Dialog Pengaturan ---
class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setMinimumSize(700, 500)
        self.settings = QSettings("CVSuudRokok88", "TestRunnerApp")
        self.current_editing_file = None

        main_layout = QVBoxLayout(self)
        self.tabs = QTabWidget()
        main_layout.addWidget(self.tabs)

        self.create_environment_tab()
        self.create_credentials_tab()
        self.create_flow_management_tab()

        self.button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        main_layout.addWidget(self.button_box)

        self.load_environments()
        self.environments_list.currentItemChanged.connect(self.on_environment_selected)
        self.credentials_list.currentItemChanged.connect(self.on_credential_selected_for_saving)

    def create_flow_management_tab(self):
        flow_widget = QWidget()
        layout = QHBoxLayout(flow_widget)

        # Kiri: Daftar langkah tes
        left_layout = QVBoxLayout()
        left_layout.addWidget(QLabel("Daftar Alur Tes (Centang untuk diaktifkan):"))
        self.flow_list = QListWidget()
        self.flow_list.itemClicked.connect(self.on_flow_step_selected)
        left_layout.addWidget(self.flow_list)

        flow_button_layout = QHBoxLayout()
        self.add_step_button = QPushButton("Tambah")
        self.add_step_button.clicked.connect(self.add_flow_step)
        self.edit_script_button = QPushButton("Edit")
        self.edit_script_button.clicked.connect(self.edit_selected_script)
        self.save_script_button = QPushButton("Simpan")
        self.save_script_button.clicked.connect(self.save_current_script)
        self.remove_step_button = QPushButton("Hapus")
        self.remove_step_button.clicked.connect(self.remove_flow_step)

        flow_button_layout.addWidget(self.add_step_button)
        flow_button_layout.addWidget(self.edit_script_button)
        flow_button_layout.addWidget(self.save_script_button)
        flow_button_layout.addWidget(self.remove_step_button)
        left_layout.addLayout(flow_button_layout)

        # Kanan: Editor kode
        right_layout = QVBoxLayout()
        self.code_preview_label = QLabel("Kode Skrip: (Pilih langkah untuk melihat/edit)")
        right_layout.addWidget(self.code_preview_label)
        self.code_preview = QTextEdit()
        self.code_preview.setReadOnly(True)
        self.code_preview.setFont(QFont("Consolas", 10))
        self.highlighter = PythonHighlighter(self.code_preview.document())
        right_layout.addWidget(self.code_preview)

        self.headless_checkbox = QCheckBox("Jalankan Headless")
        right_layout.addWidget(self.headless_checkbox)

        layout.addLayout(left_layout, 2)
        layout.addLayout(right_layout, 3)
        self.tabs.addTab(flow_widget, "Management Flow")

        self.headless_checkbox.setChecked(self.settings.value("flow/headless", False, type=bool))
        self.load_flow_steps()

    def on_flow_step_selected(self, item):
        step_name = item.text()
        file_path = os.path.join(SCRIPT_DIR, f"{step_name}.py")
        self.current_editing_file = file_path
        self.code_preview_label.setText(f"Kode Skrip: {step_name}.py")
        if os.path.exists(file_path):
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    self.code_preview.setPlainText(f.read())
            except Exception as e:
                self.code_preview.setPlainText(f"# Error membaca file: {e}")
        else:
            self.code_preview.setPlainText(f"# File untuk '{step_name}' tidak ditemukan.")
        self.code_preview.setReadOnly(True)

    def edit_selected_script(self):
        if not self.flow_list.currentItem():
            QMessageBox.warning(self, "Peringatan", "Pilih langkah tes yang ingin di-edit.")
            return
        self.code_preview.setReadOnly(False)
        self.code_preview.setFocus()
        QMessageBox.information(self, "Mode Edit", "Editor kode sekarang aktif.\nKlik 'Simpan' untuk menyimpan perubahan Anda.")

    def save_current_script(self):
        if not self.current_editing_file:
            QMessageBox.warning(self, "Error", "Tidak ada file yang sedang dipilih untuk disimpan.")
            return
        try:
            with open(self.current_editing_file, 'w', encoding='utf-8') as f:
                f.write(self.code_preview.toPlainText())
            QMessageBox.information(self, "Sukses", f"Perubahan berhasil disimpan ke:\n{os.path.basename(self.current_editing_file)}")
            self.code_preview.setReadOnly(True)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Gagal menyimpan file:\n{e}")

    def add_flow_step(self):
        step_name, ok = QInputDialog.getText(self, "Tambah Langkah Tes", "Masukkan Nama Langkah Tes (contoh: test_logout):")
        if ok and step_name and step_name.strip():
            step_name = step_name.strip().replace(" ", "_")
            file_path = os.path.join(SCRIPT_DIR, f"{step_name}.py")
            if os.path.exists(file_path):
                QMessageBox.warning(self, "Gagal", f"File dengan nama '{step_name}.py' sudah ada.")
                return
            
            # Template yang lebih robust
            template = (
                "from selenium.webdriver.common.by import By\n"
                "from selenium.webdriver.support.ui import WebDriverWait\n"
                "from selenium.webdriver.support import expected_conditions as EC\n"
                "from selenium.common.exceptions import TimeoutException\n\n"
                "# Fungsi harus mengembalikan True jika berhasil, False jika gagal.\n"
                "def run(driver, worker, username, password, url):\n"
                f"    worker.progress.emit('Menjalankan {step_name}...')\n"
                "    wait = WebDriverWait(driver, 10)\n"
                "    try:\n"
                "        # Tulis kode tes Anda di sini\n"
                "        # Contoh:\n"
                "        # element = wait.until(EC.element_to_be_clickable((By.ID, 'some_id')))\n"
                "        # element.click()\n"
                "        worker.progress.emit('Langkah berhasil dieksekusi.')\n"
                "        return True\n"
                "    except TimeoutException:\n"
                "        worker.progress.emit('Error: Elemen tidak ditemukan atau waktu tunggu habis.')\n"
                "        return False\n"
                "    except Exception as e:\n"
                "        worker.progress.emit(f'Error tidak terduga: {e}')\n"
                "        return False\n"
            )
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(template)
            self.load_flow_steps()
            items = self.flow_list.findItems(step_name, Qt.MatchFlag.MatchExactly)
            if items:
                self.flow_list.setCurrentItem(items[0])

    def remove_flow_step(self):
        current_item = self.flow_list.currentItem()
        if not current_item:
            QMessageBox.warning(self, "Peringatan", "Pilih langkah tes yang ingin dihapus.")
            return
        step_name = current_item.text()
        reply = QMessageBox.question(self, "Hapus Langkah", f"Anda yakin ingin menghapus langkah DAN file skrip '{step_name}.py'?")
        if reply == QMessageBox.StandardButton.Yes:
            file_path = os.path.join(SCRIPT_DIR, f"{step_name}.py")
            if os.path.exists(file_path):
                os.remove(file_path)
            self.flow_list.takeItem(self.flow_list.row(current_item))
            self.code_preview.clear()
            self.code_preview_label.setText("Kode Skrip:")

    def load_flow_steps(self):
        self.flow_list.clear()
        if not os.path.exists(SCRIPT_DIR):
            os.makedirs(SCRIPT_DIR)
        
        # Tambahkan skrip login default jika tidak ada skrip sama sekali
        if not any(fname.endswith('.py') for fname in os.listdir(SCRIPT_DIR)):
            self.add_default_login_script()

        files = [f.replace(".py", "") for f in os.listdir(SCRIPT_DIR) if f.endswith(".py")]
        checked_steps = self.settings.value("flow/checked_steps", ["test_login"], type=list)
        
        for step_name in sorted(files):
            item = QListWidgetItem(step_name)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if step_name in checked_steps else Qt.CheckState.Unchecked)
            self.flow_list.addItem(item)
        
        if self.flow_list.count() > 0:
            self.flow_list.setCurrentRow(0)

    def add_default_login_script(self):
        step_name = "test_login"
        file_path = os.path.join(SCRIPT_DIR, f"{step_name}.py")
        if os.path.exists(file_path):
            return
        
        # Template login yang lebih baik dan tangguh
        template = (
            "from selenium.webdriver.common.by import By\n"
            "from selenium.webdriver.support.ui import WebDriverWait\n"
            "from selenium.webdriver.support import expected_conditions as EC\n"
            "from selenium.common.exceptions import TimeoutException\n\n"
            "def run(driver, worker, username, password, url):\n"
            "    wait = WebDriverWait(driver, 10)\n"
            "    try:\n"
            "        worker.progress.emit('Membuka URL...')\n"
            "        driver.get(url)\n\n"
            "        worker.progress.emit('Mengisi form login...')\n"
            "        wait.until(EC.visibility_of_element_located((By.ID, 'email'))).send_keys(username)\n"
            "        wait.until(EC.visibility_of_element_located((By.ID, 'password'))).send_keys(password)\n"
            "        wait.until(EC.element_to_be_clickable((By.XPATH, \"//label[@for='validation']\"))).click()\n"
            "        wait.until(EC.element_to_be_clickable((By.ID, 'login'))).click()\n\n"
            "        worker.progress.emit('Memverifikasi login...')\n"
            "        wait.until(EC.url_contains('dashboard'))\n"
            "        worker.progress.emit('Login Berhasil!')\n"
            "        return True\n"
            "    except TimeoutException:\n"
            "        worker.progress.emit('Error Login: Elemen tidak ditemukan atau halaman dashboard tidak muncul.')\n"
            "        return False\n"
            "    except Exception as e:\n"
            "        worker.progress.emit(f'Error tidak terduga saat login: {e}')\n"
            "        return False\n"
        )
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(template)

    def save_settings(self):
        self.settings.setValue("environments", json.dumps(self.environments_data))
        active_env_item = self.environments_list.currentItem()
        self.settings.setValue("active_environment", active_env_item.text() if active_env_item else "")
        self.settings.setValue("flow/headless", self.headless_checkbox.isChecked())
        
        checked_steps = [
            self.flow_list.item(i).text() for i in range(self.flow_list.count()) 
            if self.flow_list.item(i).checkState() == Qt.CheckState.Checked
        ]
        self.settings.setValue("flow/checked_steps", checked_steps)
        
    def accept(self):
        self.save_settings()
        super().accept()

    # Sisa fungsi SettingsDialog (tidak perlu diubah, hanya diformat ulang)
    def create_environment_tab(self):
        env_widget = QWidget()
        main_layout = QHBoxLayout(env_widget)
        left_layout = QVBoxLayout()
        left_layout.addWidget(QLabel("Daftar Environment:"))
        self.environments_list = QListWidget()
        left_layout.addWidget(self.environments_list)
        btn_layout = QHBoxLayout()
        self.add_env_button = QPushButton("Tambah")
        self.add_env_button.clicked.connect(self.add_environment)
        self.remove_env_button = QPushButton("Hapus")
        self.remove_env_button.clicked.connect(self.remove_environment)
        btn_layout.addWidget(self.add_env_button)
        btn_layout.addWidget(self.remove_env_button)
        left_layout.addLayout(btn_layout)
        right_layout = QFormLayout()
        self.env_name_input = QLineEdit()
        self.env_name_input.setReadOnly(True)
        self.env_url_input = QLineEdit()
        self.save_env_button = QPushButton("Simpan Perubahan URL")
        self.save_env_button.clicked.connect(self.save_environment_details)
        right_layout.addRow("Nama Environment:", self.env_name_input)
        right_layout.addRow("URL:", self.env_url_input)
        right_layout.addRow(self.save_env_button)
        main_layout.addLayout(left_layout, 1)
        main_layout.addLayout(right_layout, 2)
        self.tabs.addTab(env_widget, "Environment")

    def create_credentials_tab(self):
        credentials_widget = QWidget()
        main_layout = QHBoxLayout(credentials_widget)
        left_layout = QVBoxLayout()
        self.credentials_label = QLabel("Kredensial untuk Environment:")
        left_layout.addWidget(self.credentials_label)
        self.credentials_list = QListWidget()
        self.credentials_list.itemClicked.connect(self.on_credential_item_clicked)
        left_layout.addWidget(self.credentials_list)
        self.remove_button = QPushButton("Hapus Kredensial Terpilih")
        self.remove_button.clicked.connect(self.remove_selected_credential)
        left_layout.addWidget(self.remove_button)
        right_layout = QVBoxLayout()
        form_group = QGroupBox("Tambah / Edit Kredensial")
        form_layout = QFormLayout()
        self.username_input = QLineEdit()
        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        form_layout.addRow("Username (Email):", self.username_input)
        form_layout.addRow("Password:", self.password_input)
        form_group.setLayout(form_layout)
        self.add_save_button = QPushButton("Tambah / Simpan Perubahan")
        self.add_save_button.clicked.connect(self.add_or_update_credential)
        right_layout.addWidget(form_group)
        right_layout.addWidget(self.add_save_button)
        right_layout.addStretch()
        main_layout.addLayout(left_layout, 2)
        main_layout.addLayout(right_layout, 3)
        self.tabs.addTab(credentials_widget, "Kredensial")

    def load_environments(self):
        self.environments_data = json.loads(self.settings.value("environments", "{}"))
        self.environments_list.clear()
        self.environments_list.addItems(self.environments_data.keys())
        active_env_name = self.settings.value("active_environment", "")
        items = self.environments_list.findItems(active_env_name, Qt.MatchFlag.MatchExactly)
        if items:
            self.environments_list.setCurrentItem(items[0])
        elif self.environments_list.count() > 0:
            self.environments_list.setCurrentItem(self.environments_list.item(0))

    def on_environment_selected(self, current_item=None, _=None):
        if current_item is None:
            current_item = self.environments_list.currentItem()
        if not current_item:
            self.env_name_input.clear()
            self.env_url_input.clear()
            self.credentials_list.clear()
            self.username_input.clear()
            self.password_input.clear()
            self.credentials_label.setText("Kredensial (Pilih Environment)")
            return
        env_name = current_item.text()
        env_details = self.environments_data.get(env_name, {})
        self.env_name_input.setText(env_name)
        self.env_url_input.setText(env_details.get("url", ""))
        self.credentials_label.setText(f"Kredensial untuk: {env_name}")
        self.credentials_list.clear()
        credentials = env_details.get("credentials", [])
        for cred in credentials:
            self.credentials_list.addItem(cred['username'])
        active_cred_user = env_details.get("active_credential", "")
        items = self.credentials_list.findItems(active_cred_user, Qt.MatchFlag.MatchExactly)
        if items:
            self.credentials_list.setCurrentItem(items[0])
        elif self.credentials_list.count() > 0:
            self.credentials_list.setCurrentItem(self.credentials_list.item(0))
        self.username_input.clear()
        self.password_input.clear()

    def on_credential_item_clicked(self, item):
        username = item.text()
        current_env_item = self.environments_list.currentItem()
        if not current_env_item:
            return
        env_name = current_env_item.text()
        credentials = self.environments_data[env_name].get("credentials", [])
        for cred in credentials:
            if cred['username'] == username:
                self.username_input.setText(cred['username'])
                self.password_input.setText(cred['password'])
                break

    def add_environment(self):
        name, ok = QInputDialog.getText(self, "Tambah Environment", "Masukkan Nama Environment Baru:")
        if ok and name and name.strip() and name not in self.environments_data:
            self.environments_data[name] = {"url": "", "credentials": [], "active_credential": ""}
            self.environments_list.addItem(name)
            self.environments_list.setCurrentRow(self.environments_list.count() - 1)

    def remove_environment(self):
        current_item = self.environments_list.currentItem()
        if not current_item:
            return
        env_name = current_item.text()
        reply = QMessageBox.question(self, "Hapus Environment", f"Anda yakin ingin menghapus '{env_name}'?")
        if reply == QMessageBox.StandardButton.Yes:
            del self.environments_data[env_name]
            self.load_environments()

    def save_environment_details(self):
        current_item = self.environments_list.currentItem()
        if not current_item:
            return
        env_name = current_item.text()
        self.environments_data[env_name]["url"] = self.env_url_input.text()
        QMessageBox.information(self, "Sukses", "Perubahan URL telah disimpan.")

    def add_or_update_credential(self):
        current_env_item = self.environments_list.currentItem()
        if not current_env_item:
            return
        env_name = current_env_item.text()
        username = self.username_input.text().strip()
        password = self.password_input.text()
        if not username:
            return
        credentials = self.environments_data[env_name]["credentials"]
        existing_cred = next((cred for cred in credentials if cred['username'] == username), None)
        if existing_cred:
            existing_cred['password'] = password
        else:
            credentials.append({'username': username, 'password': password})
        self.on_environment_selected(current_env_item)
        items = self.credentials_list.findItems(username, Qt.MatchFlag.MatchExactly)
        if items:
            self.credentials_list.setCurrentItem(items[0])

    def remove_selected_credential(self):
        current_env_item = self.environments_list.currentItem()
        current_cred_item = self.credentials_list.currentItem()
        if not current_env_item or not current_cred_item:
            return
        env_name = current_env_item.text()
        username_to_remove = current_cred_item.text()
        credentials = self.environments_data[env_name]["credentials"]
        self.environments_data[env_name]["credentials"] = [c for c in credentials if c['username'] != username_to_remove]
        self.on_environment_selected(current_env_item)

    def on_credential_selected_for_saving(self, item):
        current_env_item = self.environments_list.currentItem()
        if not current_env_item or not item:
            return
        env_name = current_env_item.text()
        self.environments_data[env_name]["active_credential"] = item.text()

# --- Jendela Utama Aplikasi ---
class TestRunnerApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Aplikasi Test Runner")
        self.setGeometry(100, 100, 800, 600)
        self.settings = QSettings("CVSuudRokok88", "TestRunnerApp")
        
        self._create_menu_bar()
        
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.layout = QVBoxLayout(self.central_widget)
        
        self.browser_label = QLabel("Pilih Browser:")
        self.browser_combo = QComboBox()
        self.browser_combo.addItems(["chrome", "firefox"])
        
        self.run_button = QPushButton("Jalankan Rangkaian Tes")
        self.run_button.clicked.connect(self.start_test)
        
        self.tabs = QTabWidget()
        self.log_area = QTextEdit()
        self.log_area.setReadOnly(True)
        self.log_area.setStyleSheet("background-color: #2b2b2b; color: #f0f0f0; font-family: Consolas;")
        self.tabs.addTab(self.log_area, "Log Hasil")
        
        self.summary_area = QTextEdit()
        self.summary_area.setReadOnly(True)
        self.tabs.addTab(self.summary_area, "Ringkasan")

        self.export_button = QPushButton("Export Hasil Tes")
        self.export_button.clicked.connect(self.export_results)

        self.layout.addWidget(self.browser_label)
        self.layout.addWidget(self.browser_combo)
        self.layout.addWidget(self.run_button)
        self.layout.addWidget(self.tabs)
        self.layout.addWidget(self.export_button)

    def start_test(self):
        self.run_button.setEnabled(False)
        self.log_area.clear()
        self.summary_area.clear()
        self.log("Mempersiapkan pengujian...")

        selected_browser = self.browser_combo.currentText()
        environments_data = json.loads(self.settings.value("environments", "{}"))
        active_env_name = self.settings.value("active_environment", "")
        active_env_details = environments_data.get(active_env_name, {})
        url = active_env_details.get("url", "")
        active_cred_user = active_env_details.get("active_credential", "")
        credentials = active_env_details.get("credentials", [])
        active_cred_details = next((c for c in credentials if c.get("username") == active_cred_user), None)
        username = active_cred_details.get("username", "") if active_cred_details else ""
        password = active_cred_details.get("password", "") if active_cred_details else ""
        test_flow_steps = self.settings.value("flow/checked_steps", [])
        flow_settings = {"headless": self.settings.value("flow/headless", False, type=bool)}

        # Inisialisasi thread dan worker
        self.thread = QThread()
        self.worker = SeleniumWorker(
            browser=selected_browser,
            url=url,
            username=username,
            password=password,
            flow_settings=flow_settings,
            test_flow_steps=test_flow_steps
        )
        self.worker.moveToThread(self.thread)

        # Hubungkan sinyal
        self.thread.started.connect(self.worker.run_tests)
        self.worker.finished.connect(self.on_test_finished)
        self.worker.progress.connect(self.log)
        self.worker.finished.connect(self.thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)

        self.thread.start()

    def _create_menu_bar(self):
        menu_bar = self.menuBar()
        file_menu = menu_bar.addMenu("&File")
        
        settings_action = QAction("&Settings", self)
        settings_action.triggered.connect(self.open_settings_dialog)
        file_menu.addAction(settings_action)
        
        exit_action = QAction("&Exit", self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

    def open_settings_dialog(self):
        dialog = SettingsDialog(self)
        if dialog.exec():
            self.log("Settings disimpan.")
        else:
            self.log("Perubahan settings dibatalkan.")

    def log(self, message):
        self.log_area.append(message)

    def on_test_finished(self, result):
        success, message, screenshot_path = result
        self.summary_area.clear()
        
        summary_text = f"Hasil Tes: {'SUKSES' if success else 'GAGAL'}\n"
        summary_text += f"Pesan: {message}\n"
        
        if success:
            self.log_area.setTextColor(QColor("lime"))
            self.log("\n--- HASIL: RANGKAIAN TES SELESAI ---")
            self.summary_area.setTextColor(QColor("green"))
        else:
            self.log_area.setTextColor(QColor("red"))
            self.log("\n--- HASIL: GAGAL ---")
            self.summary_area.setTextColor(QColor("red"))
            if screenshot_path:
                summary_text += f"Screenshot Error: {os.path.abspath(screenshot_path)}\n"
        
        self.log(message)
        self.summary_area.setText(summary_text)
        self.log_area.setTextColor(QColor("white")) # Kembalikan warna default
        self.run_button.setEnabled(True)

    def export_results(self):
        log_content = self.log_area.toPlainText()
        summary_content = self.summary_area.toPlainText()
        
        if not log_content and not summary_content:
            QMessageBox.warning(self, "Export Gagal", "Tidak ada hasil tes untuk diexport.")
            return
            
        file_path, _ = QFileDialog.getSaveFileName(self, "Simpan Hasil Tes", "", "Text Files (*.txt);;All Files (*)")
        if file_path:
            try:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write("="*20 + " RINGKASAN TES " + "="*20 + "\n")
                    f.write(summary_content)
                    f.write("\n\n" + "="*20 + " LOG LENGKAP " + "="*20 + "\n")
                    f.write(log_content)
                QMessageBox.information(self, "Sukses", f"Hasil tes berhasil diexport ke:\n{file_path}")
            except Exception as e:
                QMessageBox.critical(self, "Export Error", f"Terjadi kesalahan saat menyimpan file: {e}")

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = TestRunnerApp()
    window.show()
    sys.exit(app.exec())