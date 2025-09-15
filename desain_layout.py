import sys
from PyQt6.QtWidgets import QApplication, QMainWindow, QLabel, QPushButton, QLineEdit, QWidget, QVBoxLayout

class MainWindowLayout(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Desain GUI dengan Layout Manager")
        self.resize(400, 250) # Ukuran awal, bisa diubah oleh user

        # Layouts tidak bisa langsung ditaruh di QMainWindow.
        # Kita butuh 'central widget' sebagai alasnya.
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        # Buat layout vertikal
        # Semua yang dimasukkan ke layout ini akan diatur secara vertikal
        layout = QVBoxLayout()
        central_widget.setLayout(layout) # Terapkan layout ke central widget

        # --- Buat dan tambahkan widget ke layout ---
        # Perhatikan kita tidak lagi menggunakan .move() atau .setGeometry()!
        # Urutan penambahan widget sangat penting.

        self.label = QLabel("Masukkan Nama Anda:")
        layout.addWidget(self.label) # Tambahkan label ke layout

        self.input_nama = QLineEdit()
        layout.addWidget(self.input_nama) # Tambahkan input box ke layout

        self.tombol_sapa = QPushButton("Sapa!")
        layout.addWidget(self.tombol_sapa) # Tambahkan tombol ke layout
        
        self.label_hasil = QLabel("Hasil akan muncul di sini")
        layout.addWidget(self.label_hasil) # Tambahkan label hasil ke layout

        # Menghubungkan sinyal dan slot (sama seperti sebelumnya)
        self.tombol_sapa.clicked.connect(self.aksi_tombol_sapa)

    def aksi_tombol_sapa(self):
        nama = self.input_nama.text()
        if nama:
            self.label_hasil.setText(f"Halo, {nama}! Selamat datang di PyQt6.")
        else:
            self.label_hasil.setText("Tolong masukkan nama terlebih dahulu.")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindowLayout()
    window.show()
    sys.exit(app.exec())