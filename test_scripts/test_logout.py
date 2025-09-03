import time
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException

def run(driver, worker, username, password, url):
    """
    Menjalankan skenario logout dengan langkah stabilisasi untuk memastikan
    halaman dan sidebar dalam keadaan normal sebelum logout.
    """
    worker.progress.emit('Memulai skenario test_logout...')
    wait = WebDriverWait(driver, 25)

    try:
        # ======================================================
        # LANGKAH 1: STABILISASI HALAMAN
        # ======================================================
        worker.progress.emit('Menstabilkan halaman dengan memastikan sidebar ada...')
        
        # Langkah ini memaksa skrip untuk menunggu sampai sidebar benar-benar terlihat
        # sebelum mencoba tindakan apa pun. Ini sangat penting untuk stabilitas.
        wait.until(
            EC.visibility_of_element_located((By.XPATH, "//aside//p[text()='Dashboard']/ancestor::a[1]"))
        )
        worker.progress.emit('Sidebar terkonfirmasi ada. Halaman stabil.')
        time.sleep(1) # Jeda singkat untuk memastikan semua elemen siap

        # ======================================================
        # LANGKAH 2: PROSES LOGOUT
        # ======================================================
        worker.progress.emit('Mencari tombol logout di sidebar...')
        
        logout_link = wait.until(
            EC.element_to_be_clickable((By.ID, "logout"))
        )
        worker.progress.emit('Tombol Logout ditemukan. Mengklik tombol...')
        logout_link.click()
        
        # Penanganan popup konfirmasi (jika ada)
        try:
            confirm_button = WebDriverWait(driver, 3).until(
                EC.element_to_be_clickable((By.XPATH, "//button[contains(@class, 'swal2-confirm')]"))
            )
            worker.progress.emit("Popup konfirmasi ditemukan, mengklik 'Ya'.")
            confirm_button.click()
        except TimeoutException:
            worker.progress.emit("Tidak ada popup konfirmasi, proses logout langsung.")
            pass

        # ======================================================
        # LANGKAH 3: VERIFIKASI LOGOUT
        # ======================================================
        worker.progress.emit('Memverifikasi kembali ke halaman login...')
        wait.until(EC.visibility_of_element_located((By.ID, 'email')))
        
        worker.progress.emit('Logout Berhasil! Telah kembali ke halaman login.')
        return True

    except TimeoutException:
        worker.progress.emit('Error: Waktu tunggu habis saat proses logout.')
        worker.progress.emit('Gagal menemukan elemen sidebar atau logout. Pastikan "test_login" berhasil.')
        driver.save_screenshot('logout_error.png')
        return False
        
    except Exception as e:
        worker.progress.emit(f'Terjadi error yang tidak terduga saat logout: {str(e)}')
        return False