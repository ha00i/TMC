import time
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException

def run(driver, worker, username, password, url):
    """
    Menjalankan alur login yang paling akurat:
    Login -> Klik Dashboard -> Tunggu 'Tab is loading' -> Tunggu 'Processing' -> Verifikasi Konten.
    """
    wait = WebDriverWait(driver, 25) 
    
    try:
        # ======================================================
        # LANGKAH 1: PROSES LOGIN
        # ======================================================
        worker.progress.emit(f'Membuka URL: {url}')
        driver.get(url)
        driver.maximize_window()

        worker.progress.emit('Mengisi form login...')
        wait.until(EC.visibility_of_element_located((By.ID, 'email'))).send_keys(username)
        wait.until(EC.visibility_of_element_located((By.ID, 'password'))).send_keys(password)
        wait.until(EC.element_to_be_clickable((By.XPATH, "//label[@for='validation']"))).click()
        wait.until(EC.element_to_be_clickable((By.ID, 'login'))).click()
        worker.progress.emit('Tombol login diklik. Memverifikasi hasil...')

        try:
            # DIUBAH: Waktu tunggu cek error menjadi 4 detik
            WebDriverWait(driver, 4).until(EC.visibility_of_element_located((By.ID, "swal2-content")))
            worker.progress.emit('Login Gagal! Terdeteksi pesan error.')
            return False
        except TimeoutException:
            worker.progress.emit('Tidak ada pesan error. Melanjutkan ke pemuatan dashboard...')

        # ======================================================
        # LANGKAH 2: MEMUAT KONTEN DASHBOARD (ALUR WAJIB)
        # ======================================================
        
        worker.progress.emit('Menunggu sidebar muncul...')
        sidebar_dashboard_link = wait.until(
            EC.element_to_be_clickable((By.XPATH, "//aside//p[text()='Dashboard']/ancestor::a[1]"))
        )
        worker.progress.emit('Login Berhasil! Sidebar ditemukan.')
        
        sidebar_dashboard_link.click()
        worker.progress.emit("Menu Dashboard diklik. Menunggu semua proses loading...")

        # --- REVISI UTAMA: MENUNGGU SEMUA SPINNER DALAM URUTAN YANG BENAR ---

        # 1. Tunggu sampai spinner "Tab is loading" HILANG. Ini event pertama.
        worker.progress.emit("Menunggu struktur tab dimuat ('Tab is loading')...")
        wait.until(EC.invisibility_of_element_located((By.XPATH, "//*[contains(text(), 'Tab is loading')]")))
        
        # 2. Tunggu sampai spinner "Processing" HILANG. Ini event kedua.
        #    `invisibility_of_element_located` akan langsung lolos jika elemen ini tidak pernah muncul,
        #    tetapi akan menunggu jika elemen ini muncul. Ini sangat aman.
        worker.progress.emit("Menunggu data diproses ('Processing')...")
        wait.until(EC.invisibility_of_element_located((By.XPATH, "//*[contains(text(), 'Processing')]")))
        worker.progress.emit('Konten Dashboard berhasil dimuat dan diverifikasi.')
        
        # --- AKHIR REVISI ---
        
        worker.progress.emit('Langkah test_login selesai dengan sukses. Siap untuk langkah selanjutnya.')
        return True

    except TimeoutException:
        worker.progress.emit('Error: Waktu tunggu habis. '
                              'Salah satu proses loading (Tab/Processing) terlalu lama atau konten tidak muncul.')
        driver.save_screenshot('login_error.png')
        return False
        
    except Exception as e:
        worker.progress.emit(f'Terjadi error yang tidak terduga saat login: {str(e)}')
        return False