import os
import sys
import json
import shutil
import threading
import logging
from datetime import datetime
from functools import partial

# PyQt6 Modules
from PyQt6.QtWidgets import (
    QApplication, QWidget, QLabel, QLineEdit, QPushButton,
    QTextEdit, QFileDialog, QVBoxLayout, QHBoxLayout, QMessageBox, QFrame
)
from PyQt6.QtCore import Qt, QTimer, QMetaObject, Q_ARG, pyqtSlot, QDateTime
from PyQt6.QtGui import QPixmap, QColor, QIntValidator

# pyftpdlib Modules
from pyftpdlib.handlers import FTPHandler
from pyftpdlib.servers import FTPServer
from pyftpdlib.authorizers import DummyAuthorizer


# BASE_DIR: Determine the base directory for resources (for PyInstaller)
# PyInstaller로 패키징될 때 리소스 파일의 경로를 올바르게 찾기 위함
BASE_DIR = getattr(sys, "_MEIPASS", os.path.abspath("."))

# --- Constants for better readability and maintainability ---
# 가독성과 유지보수성을 위한 상수 정의
INACTIVE_THRESHOLD_MS = 60000  # 60초 (1분) 이상 데이터 미수신 시 오류 표시
ACTIVE_ICON_DURATION_MS = 500 # 1초 (아이콘 활성 상태 유지 시간)
DEFAULT_FTP_PORT = 21
DEFAULT_PASSIVE_PORT_START = 60000
DEFAULT_PASSIVE_PORT_END = 60010

# --- Global FTP Server Instance ---
# FTP 서버 인스턴스 (스레드에서 접근하기 위함)
ftp_server = None

# --- Logger Setup ---
# 로깅 설정을 위한 초기화 (파일 및 콘솔 출력)
log_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

# 파일 핸들러: UTF-8 인코딩 명시
file_handler = logging.FileHandler('ftp_server_log.log', encoding='utf-8')
file_handler.setFormatter(log_formatter)
file_handler.setLevel(logging.INFO) # INFO 레벨 이상의 로그를 파일에 기록

# 콘솔 핸들러: UTF-8 인코딩 명시 (sys.stdout을 직접 재설정하거나 스트림에 인코딩을 지정)
try:
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
except AttributeError:
    pass

console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(log_formatter)
console_handler.setLevel(logging.INFO) # INFO 레벨 이상의 로그를 콘솔에 기록

root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO) # 전체 로깅 레벨 설정
root_logger.addHandler(file_handler)
root_logger.addHandler(console_handler)


class Config:
    """
    Handles loading and saving of configuration settings from/to a JSON file.
    JSON 파일로부터 설정 값을 로드하고 저장하는 클래스.
    """
    def __init__(self, path="config.json"):
        self.path = path
        self.data = {
            "root_dir": os.path.join(os.path.expanduser("~"), "FTP_Data"), # 기본 저장 경로를 사용자 홈 디렉토리 내로 변경
            "username": "user",
            "password": "password",
            "auto_start": False, # 자동 시작 기본값을 False로 변경
            "ftp_port": DEFAULT_FTP_PORT,
            "passive_port_start": DEFAULT_PASSIVE_PORT_START,
            "passive_port_end": DEFAULT_PASSIVE_PORT_END,
            "device_names": ["Main FAN", "Rotary Motor", "Combustion FAN", "Purge FAN"] # 장치 이름 목록 추가
        }
        self.load()
        # 초기 root_dir이 존재하지 않으면 생성
        if not os.path.exists(self.data["root_dir"]):
            try:
                os.makedirs(self.data["root_dir"])
                root_logger.info(f"Created default root directory: {self.data['root_dir']}")
            except OSError as e:
                root_logger.error(f"Failed to create default root directory {self.data['root_dir']}: {e}")

    def load(self):
        """Loads configuration from the JSON file."""
        # JSON 파일에서 설정을 로드합니다.
        try:
            with open(self.path, 'r', encoding='utf-8') as f: # 인코딩 명시
                loaded_data = json.load(f)
                # 새로운 설정이 추가되어도 기존 설정이 유지되도록 업데이트
                self.data.update(loaded_data)
        except FileNotFoundError:
            root_logger.info(f"Config file '{self.path}' not found. Using default settings.")
            self.save() # 기본 설정으로 파일 생성
        except json.JSONDecodeError as e:
            root_logger.error(f"Error decoding config file '{self.path}': {e}. Using default settings.")
        except Exception as e:
            root_logger.error(f"Failed to load config from '{self.path}': {e}. Using default settings.")

    def save(self):
        """Saves current configuration to the JSON file."""
        # 현재 설정을 JSON 파일에 저장합니다.
        try:
            with open(self.path, 'w', encoding='utf-8') as f: # 인코딩 명시
                json.dump(self.data, f, indent=4, ensure_ascii=False) # 한글 깨짐 방지
            root_logger.info(f"Config saved to '{self.path}'.")
        except Exception as e:
            root_logger.error(f"Failed to save config to '{self.path}': {e}")

    def __getitem__(self, key):
        """Allows dictionary-like access to config data."""
        # 딕셔너리처럼 설정 데이터에 접근할 수 있도록 합니다.
        return self.data.get(key)

    def __setitem__(self, key, value):
        """Allows dictionary-like assignment to config data."""
        # 딕셔너리처럼 설정 데이터에 값을 할당할 수 있도록 합니다.
        self.data[key] = value


class CustomFTPHandler(FTPHandler):
    """
    Custom FTP handler to process file transfers and log events.
    This handler now uses class-level attributes for GUI callbacks and configuration,
    which are set by the run_ftp_server function before the server starts.
    파일 전송을 처리하고 이벤트를 로깅하는 사용자 정의 FTP 핸들러.
    이 핸들러는 이제 GUI 콜백 및 구성을 위한 클래스 레벨 속성을 사용하며,
    이는 서버가 시작하기 전에 run_ftp_server 함수에 의해 설정됩니다.
    """
    # Class-level attributes to be set by run_ftp_server
    # run_ftp_server 함수에 의해 설정될 클래스 레벨 속성
    log_method_class = None
    device_status_update_method_class = None
    root_dir_class = None
    device_names_config_class = None

    def __init__(self, conn, server, **kwargs):
        """
        Initializes the custom FTP handler.
        Any extra keyword arguments from pyftpdlib (like 'ioloop') are now accepted.
        사용자 정의 FTP 핸들러를 초기화합니다.
        pyftpdlib에서 전달되는 추가 키워드 인수('ioloop' 등)는 이제 허용됩니다.
        """
        super().__init__(conn, server, **kwargs)

    def log(self, *args, **kwargs): # <--- Modified to accept *args and **kwargs
        """
        Logs messages using the provided GUI logging method (accessed via class attribute).
        Handles any additional arguments from pyftpdlib's internal calls.
        제공된 GUI 로깅 메서드(클래스 속성을 통해 접근)를 사용하여 메시지를 로깅합니다.
        pyftpdlib 내부 호출에서 오는 추가 인수들을 처리합니다.
        """
        msg = args[0] if args else "" # Extract message from positional arguments
        
        if CustomFTPHandler.log_method_class:
            QMetaObject.invokeMethod(CustomFTPHandler.log_method_class.__self__, CustomFTPHandler.log_method_class.__name__,
                                     Qt.ConnectionType.QueuedConnection, Q_ARG(str, msg))
        
        # root_logger는 콘솔로도 출력되므로, 콘솔의 인코딩 문제 방지를 위해 이모지는 GUI 로그에만 표시
        clean_msg = msg.replace('⚠', '[WARN]').replace('✅', '[OK]').replace('🛑', '[STOP]').replace('❌', '[ERROR]')
        root_logger.info(clean_msg)


    def on_connect(self):
        """Called when a client connects."""
        self.log(f"[+] FTP CONNECTED from {self.remote_ip}:{self.remote_port}")

    def on_login(self, username):
        """Called when a user logs in successfully."""
        self.log(f"[+] LOGIN SUCCESS - Username: {username}")

    def on_login_failed(self, username, password):
        """Called when a user fails to log in."""
        self.log(f"[!] LOGIN FAILED - Username: {username}")

    def on_file_received(self, file_path):
        """
        Called when a file is successfully received.
        Processes the file, moves it to the categorized directory, and updates GUI.
        파일이 성공적으로 수신될 때 호출됩니다. 파일을 처리하고 분류된 디렉토리로 이동하며 GUI를 업데이트합니다.
        """
        filename = os.path.basename(file_path)
        prefix = "Unknown"
        channel_name = "Unknown"

        # Extract prefix (e.g., [Main FAN])
        if filename.startswith('[') and ']' in filename:
            try:
                prefix = filename.split(']')[0].strip('[]')
                # Check if the extracted prefix is one of the configured device names
                if prefix not in CustomFTPHandler.device_names_config_class: # Access class attribute
                    self.log(f"[!] Warning: Unknown device prefix '{prefix}' in filename: {filename}")
                    prefix = "Unknown Device" # 알 수 없는 장치 접두사에 대한 기본값 설정
            except Exception as e:
                self.log(f"[!] Error parsing prefix from '{filename}': {e}")
                prefix = "Parse Error" # 파싱 오류 시 기본값 설정

        # Extract channel name (e.g., CH0, CH1)
        if "_CH" in filename:
            try:
                channel_part = filename.split("_CH")[1]
                channel_name = "CH" + channel_part.split("_")[0]
            except Exception as e:
                self.log(f"[!] Error parsing channel name from '{filename}': {e}")
                channel_name = "Parse Error" # 파싱 오류 시 기본값 설정

        date_folder = datetime.now().strftime("%Y%m%d")
        # Construct the destination folder path
        dest_folder = os.path.join(CustomFTPHandler.root_dir_class, prefix, date_folder, channel_name) # Access class attribute
        dest_path = os.path.join(dest_folder, filename)

        try:
            # Create destination directories if they don't exist
            os.makedirs(dest_folder, exist_ok=True)
            # Move the received file to its final destination
            shutil.move(file_path, dest_path)
            self.log(f"[\u2713] FILE SAVED TO: {dest_path}")

            # Update GUI device status (on the main thread)
            if CustomFTPHandler.device_status_update_method_class: # Access class attribute
                # Corrected typo: CustomFTPHandler.device_method_class to CustomFTPHandler.device_status_update_method_class
                QMetaObject.invokeMethod(CustomFTPHandler.device_status_update_method_class.__self__, CustomFTPHandler.device_status_update_method_class.__name__,
                                         Qt.ConnectionType.QueuedConnection, Q_ARG(str, prefix))

        except OSError as e:
            self.log(f"[!] File system error saving '{filename}' to '{dest_path}': {e}. Check permissions or disk space.")
        except Exception as e:
            self.log(f"[!] Unexpected error saving file '{filename}': {e}")

    def on_disconnect(self):
        """Called when a client disconnects."""
        self.log(f"[-] FTP DISCONNECTED: {self.remote_ip}")


def run_ftp_server(ftp_port, passive_port_start, passive_port_end, root_dir, username, password, log_method, device_status_update_method, device_names_config, gui_ref):
    """
    Runs the FTP server in a separate thread.
    This function now sets class-level attributes on CustomFTPHandler.
    별도의 스레드에서 FTP 서버를 실행합니다.
    이 함수는 이제 CustomFTPHandler에 클래스 레벨 속성을 설정합니다.
    """
    global ftp_server
    try:
        authorizer = DummyAuthorizer()
        authorizer.add_user(username, password, root_dir, perm="elradfmw")

        # Set CustomFTPHandler class attributes before starting the server
        # 서버 시작 전에 CustomFTPHandler 클래스 속성 설정
        CustomFTPHandler.authorizer = authorizer
        CustomFTPHandler.banner = "Custom FTP Server Ready."
        CustomFTPHandler.passive_ports = range(passive_port_start, passive_port_end + 1)
        CustomFTPHandler.log_method_class = log_method
        CustomFTPHandler.device_status_update_method_class = device_status_update_method
        CustomFTPHandler.root_dir_class = root_dir
        CustomFTPHandler.device_names_config_class = device_names_config

        # FTPServer now directly uses the CustomFTPHandler class
        # FTPServer는 이제 CustomFTPHandler 클래스를 직접 사용합니다.
        ftp_server = FTPServer(("0.0.0.0", ftp_port), CustomFTPHandler)
        log_method(f"[\u26a0] FTP Server attempting to start on port {ftp_port} with root: {root_dir}")
        
        QMetaObject.invokeMethod(gui_ref, "handle_server_startup_success", Qt.ConnectionType.QueuedConnection)
        
        ftp_server.serve_forever()
    except OSError as e:
        error_msg = f"[FATAL] FTP Server failed to start. Port {ftp_port} might be in use or permissions issue: {e}"
        log_method(error_msg)
        root_logger.critical(error_msg) # root_logger는 이모지 없는 메시지를 받도록 CustomFTPHandler.log에서 처리됨
        QMetaObject.invokeMethod(gui_ref, "handle_server_startup_failure", Qt.ConnectionType.QueuedConnection, Q_ARG(str, str(e)))
    except Exception as e:
        error_msg = f"[FATAL] An unexpected error occurred in FTP server thread: {e}"
        log_method(error_msg)
        root_logger.critical(error_msg) # root_logger는 이모지 없는 메시지를 받도록 CustomFTPHandler.log에서 처리됨
        QMetaObject.invokeMethod(gui_ref, "handle_server_startup_failure", Qt.ConnectionType.QueuedConnection, Q_ARG(str, str(e)))


class FTPServerGUI(QWidget):
    """
    Main GUI application for the FTP Server Manager.
    FTP 서버 관리자를 위한 메인 GUI 애플리케이션.
    """
    def __init__(self):
        super().__init__()
        self.setWindowTitle("FTP 서버 관리자")
        self.resize(700, 550) # 창 크기 약간 증가

        self.server_thread = None # FTP 서버를 실행하는 스레드 인스턴스
        self.server_running = False
        self.device_labels = {}
        self.device_last_received_labels = {} # 장치별 최종 수신 시간 라벨 추가
        self.device_timers = {}
        self.device_last_received = {}

        self.config = CONFIG # 전역 CONFIG 객체 참조
        self.device_names = self.config["device_names"] # 설정에서 장치 이름 로드

        self.setup_ui()
        # self.setup_callbacks() # No longer needed as global log_callback is removed.

        # Check initial root_dir validity
        # 초기 root_dir 유효성 검사
        if not self._is_valid_directory(self.config["root_dir"]):
            self.append_log(f"[!] Warning: Configured root directory '{self.config['root_dir']}' is invalid. Please select a valid directory.")
            self.dir_input.setStyleSheet("border: 1px solid red;") # 유효하지 않으면 빨간 테두리

        if self.config["auto_start"]:
            self.toggle_server() # 설정값이 true일 때만 자동 시작

        self.error_check_timer = QTimer(self)
        self.error_check_timer.timeout.connect(self.check_device_errors)
        self.error_check_timer.start(1000) # 매 1초마다 상태 확인 (데이터 미수신 여부)
        
        # 서버 상태 표시 업데이트를 위한 타이머 (선택 사항, 즉각적 업데이트는 슬롯으로)
        self.server_status_update_timer = QTimer(self)
        self.server_status_update_timer.timeout.connect(self._update_server_status_display)
        self.server_status_update_timer.start(500) # 0.5초마다 서버 상태 텍스트 업데이트

    def setup_callbacks(self):
        """Sets up any necessary callbacks. (Now mostly handled by direct arg passing)"""
        # 필요한 콜백을 설정합니다. (이제 대부분 직접 인수 전달로 처리됩니다)
        pass # 콜백을 직접 전달하는 방식으로 변경되어 전역 log_callback은 더 이상 필요 없음

    def setup_ui(self):
        """Configures the main user interface layout and widgets."""
        # 주요 사용자 인터페이스 레이아웃 및 위젯을 구성합니다.
        layout = QVBoxLayout()

        # --- Server Settings Layout ---
        # 서버 설정 레이아웃
        settings_group = QFrame(self)
        settings_group.setFrameShape(QFrame.Shape.Box)
        settings_group.setLineWidth(1)
        settings_layout = QVBoxLayout(settings_group)
        settings_layout.addWidget(QLabel("<b>서버 설정</b>"))

        # Root Directory
        dir_layout = QHBoxLayout()
        dir_layout.addWidget(QLabel("저장 경로:"))
        self.dir_input = QLineEdit(self.config["root_dir"])
        self.dir_input.textChanged.connect(self._validate_dir_input) # 입력 시 유효성 검사
        dir_layout.addWidget(self.dir_input)
        browse_btn = QPushButton("폴더 선택")
        browse_btn.clicked.connect(self.select_folder)
        dir_layout.addWidget(browse_btn)
        settings_layout.addLayout(dir_layout)

        # User Credentials
        acc_layout = QHBoxLayout()
        acc_layout.addWidget(QLabel("ID:"))
        self.user_input = QLineEdit(self.config["username"])
        acc_layout.addWidget(self.user_input)
        acc_layout.addWidget(QLabel("PW:"))
        self.pass_input = QLineEdit(self.config["password"])
        self.pass_input.setEchoMode(QLineEdit.EchoMode.Password)
        acc_layout.addWidget(self.pass_input)
        settings_layout.addLayout(acc_layout)

        # Port Settings
        port_layout = QHBoxLayout()
        port_layout.addWidget(QLabel("FTP 포트:"))
        self.ftp_port_input = QLineEdit(str(self.config["ftp_port"]))
        self.ftp_port_input.setFixedWidth(50)
        self.ftp_port_input.setValidator(QIntValidator(1, 65535, self))
        port_layout.addWidget(self.ftp_port_input)
        port_layout.addSpacing(20)
        port_layout.addWidget(QLabel("패시브 포트 범위:"))
        self.passive_start_input = QLineEdit(str(self.config["passive_port_start"]))
        self.passive_start_input.setFixedWidth(50)
        self.passive_start_input.setValidator(QIntValidator(1, 65535, self))
        port_layout.addWidget(self.passive_start_input)
        port_layout.addWidget(QLabel("~"))
        self.passive_end_input = QLineEdit(str(self.config["passive_port_end"]))
        self.passive_end_input.setFixedWidth(50)
        self.passive_end_input.setValidator(QIntValidator(1, 65535, self))
        port_layout.addWidget(self.passive_end_input)
        port_layout.addStretch(1) # 우측 정렬
        settings_layout.addLayout(port_layout)

        layout.addWidget(settings_group)

        # --- Server Control Buttons ---
        # 서버 제어 버튼
        button_layout = QHBoxLayout()
        self.toggle_btn = QPushButton("FTP 서버 시작")
        self.toggle_btn.clicked.connect(self.toggle_server)
        self.stop_btn = QPushButton("FTP 서버 중지")
        self.stop_btn.clicked.connect(self.stop_server)
        self.stop_btn.setEnabled(False) # 초기에는 중지 버튼 비활성화

        button_layout.addWidget(self.toggle_btn)
        button_layout.addWidget(self.stop_btn)
        layout.addLayout(button_layout)
        
        # Server Status Indicator
        # 서버 상태 표시기
        server_status_layout = QHBoxLayout()
        server_status_layout.addWidget(QLabel("서버 상태:"))
        self.server_status_label = QLabel("중지됨")
        self.server_status_label.setStyleSheet("color: gray;")
        self.server_status_indicator = QLabel()
        self.server_status_indicator.setFixedSize(16, 16)
        self.server_status_indicator.setPixmap(QPixmap(os.path.join(BASE_DIR, "idle.png")).scaled(16, 16, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        server_status_layout.addWidget(self.server_status_indicator)
        server_status_layout.addWidget(self.server_status_label)
        server_status_layout.addStretch(1)
        layout.addLayout(server_status_layout)


        # --- Server Log Output ---
        # 서버 로그 출력
        layout.addWidget(QLabel("<b>서버 로그</b>"))
        self.log_output = QTextEdit()
        self.log_output.setReadOnly(True)
        self.log_output.document().setMaximumBlockCount(1000) # 로그 최대 1000줄 제한
        layout.addWidget(self.log_output)

        # --- Device Status Monitoring ---
        # 장치 수신 현황 모니터링
        layout.addWidget(QLabel("<b>장치 수신 현황</b>"))
        device_layout = QHBoxLayout()
        device_layout.setSpacing(10) # 간격 좁게 조정

        for name in self.device_names:
            vbox = QVBoxLayout()
            vbox.setAlignment(Qt.AlignmentFlag.AlignCenter)

            # Device Name Label
            name_label = QLabel(name)
            name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            vbox.addWidget(name_label)

            # Icon Label
            icon_label = QLabel()
            icon_label.setFixedSize(32, 32) # 아이콘 크기 키움
            icon_label.setPixmap(QPixmap(os.path.join(BASE_DIR, "idle.png")).scaled(
                32, 32, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
            ))
            icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            vbox.addWidget(icon_label)

            # Last Received Time Label
            last_received_label = QLabel("미수신")
            last_received_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            last_received_label.setStyleSheet("font-size: 10px; color: gray;")
            vbox.addWidget(last_received_label)


            container = QFrame(self) # 각 장치별 컨테이너 프레임
            container.setFrameShape(QFrame.Shape.Box)
            container.setLineWidth(1)
            container.setLayout(vbox)
            device_layout.addWidget(container)

            self.device_labels[name] = icon_label
            self.device_last_received_labels[name] = last_received_label
            self.device_last_received[name] = QDateTime.currentDateTime() # 초기값을 현재 시간으로 설정

        layout.addLayout(device_layout)
        layout.addStretch(1) # 하단 공간 채우기

        self.setLayout(layout)

    def _is_valid_directory(self, path):
        """Checks if a given path is a valid and accessible directory."""
        # 주어진 경로가 유효하고 접근 가능한 디렉토리인지 확인합니다.
        return os.path.isdir(path) and os.access(path, os.W_OK | os.X_OK)

    def _validate_dir_input(self, text):
        """Validates the directory input field and updates its style."""
        # 디렉토리 입력 필드를 유효성 검사하고 스타일을 업데이트합니다.
        if self._is_valid_directory(text):
            self.dir_input.setStyleSheet("") # 정상
        else:
            self.dir_input.setStyleSheet("border: 1px solid red;") # 오류

    def select_folder(self):
        """Opens a file dialog to select the root directory."""
        # 루트 디렉토리를 선택하기 위한 파일 대화 상자를 엽니다.
        folder = QFileDialog.getExistingDirectory(self, "폴더 선택", self.dir_input.text())
        if folder:
            self.dir_input.setText(folder)

    def toggle_server(self):
        """Starts or stops the FTP server based on its current state."""
        # 현재 상태에 따라 FTP 서버를 시작하거나 중지합니다.
        if not self.server_running:
            root_dir = self.dir_input.text()
            username = self.user_input.text()
            password = self.pass_input.text()
            # Ensure port inputs are valid integers before converting
            try:
                ftp_port = int(self.ftp_port_input.text())
                passive_start = int(self.passive_start_input.text())
                passive_end = int(self.passive_end_input.text())
            except ValueError:
                self.show_message_box("Error", "포트 번호는 유효한 정수여야 합니다.")
                return

            # Basic validation (already handled by QIntValidator but good for robustness)
            if not self._is_valid_directory(root_dir):
                self.show_message_box("Error", f"유효하지 않거나 접근할 수 없는 저장 경로입니다: '{root_dir}'")
                self.append_log(f"[!] Error: Invalid root directory: {root_dir}")
                return
            if not (1 <= ftp_port <= 65535):
                self.show_message_box("Error", "FTP 포트가 유효한 범위(1-65535)를 벗어났습니다.")
                return
            if not (1 <= passive_start <= passive_end <= 65535):
                self.show_message_box("Error", "패시브 포트 범위가 유효하지 않습니다.")
                return

            # Save current settings to config
            self.config["root_dir"] = root_dir
            self.config["username"] = username
            self.config["password"] = password
            self.config["ftp_port"] = ftp_port
            self.config["passive_port_start"] = passive_start
            self.config["passive_port_end"] = passive_end
            self.config.save()

            self.server_thread = threading.Thread(target=run_ftp_server, daemon=True,
                                                  args=(ftp_port, passive_start, passive_end,
                                                        root_dir, username, password,
                                                        self.append_log, self.update_device_status,
                                                        self.device_names, self))
            self.server_thread.start()
            
            self.toggle_btn.setText("FTP 서버 시작 중...")
            self.toggle_btn.setEnabled(False)
            self.stop_btn.setEnabled(True)
            self.server_status_label.setText("시작 중...")
            self.server_status_label.setStyleSheet("color: orange;")
            self.server_status_indicator.setPixmap(QPixmap(os.path.join(BASE_DIR, "idle.png")).scaled(16, 16, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))

        else:
            self.stop_server()

    @pyqtSlot()
    def handle_server_startup_success(self):
        """Slot called when FTP server successfully starts."""
        self.server_running = True
        self.toggle_btn.setText("FTP 서버 실행 중")
        self.toggle_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.server_status_label.setText("실행 중")
        self.server_status_label.setStyleSheet("color: green;")
        self.server_status_indicator.setPixmap(QPixmap(os.path.join(BASE_DIR, "active.png")).scaled(16, 16, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        self.append_log("✅ FTP 서버가 성공적으로 시작되었습니다.")

    @pyqtSlot(str)
    def handle_server_startup_failure(self, error_message):
        """Slot called when FTP server fails to start."""
        self.server_running = False
        self.toggle_btn.setText("FTP 서버 시작")
        self.toggle_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.server_status_label.setText("오류 발생")
        self.server_status_label.setStyleSheet("color: red;")
        self.server_status_indicator.setPixmap(QPixmap(os.path.join(BASE_DIR, "error.png")).scaled(16, 16, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        self.append_log(f"❌ FTP 서버 시작 실패: {error_message}")
        self.show_message_box("FTP 서버 시작 실패", f"서버 시작 중 오류가 발생했습니다: {error_message}\n\n다른 프로그램이 포트 21을 사용 중이거나, 관리자 권한이 부족할 수 있습니다.")


    def stop_server(self):
        """Stops the running FTP server."""
        global ftp_server
        if self.server_running and ftp_server:
            try:
                ftp_server.close_all()
                self.server_running = False
                self.toggle_btn.setText("FTP 서버 시작")
                self.toggle_btn.setEnabled(True)
                self.stop_btn.setEnabled(False)
                self.server_status_label.setText("중지됨")
                self.server_status_label.setStyleSheet("color: gray;")
                self.server_status_indicator.setPixmap(QPixmap(os.path.join(BASE_DIR, "idle.png")).scaled(16, 16, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
                self.append_log("🛑 FTP 서버가 중지되었습니다.")
                root_logger.info("FTP server stopped.")
            except Exception as e:
                self.append_log(f"[!] 서버 중지 실패: {e}")
                root_logger.error(f"Failed to stop FTP server: {e}")
                self.show_message_box("서버 중지 실패", f"FTP 서버 중지 중 오류가 발생했습니다: {e}")
        else:
            self.append_log("[!] FTP 서버가 이미 중지 상태입니다.")

    @pyqtSlot(str) # <--- Added pyqtSlot decorator
    def append_log(self, msg):
        """Appends a message to the log output QTextEdit."""
        QMetaObject.invokeMethod(self.log_output, "append",
                                 Qt.ConnectionType.QueuedConnection, Q_ARG(str, msg))
        # Ensure that the message logged to file/console doesn't cause encoding errors
        # Remove emojis for console/file logging, as QTextEdit handles them fine but console might not
        clean_msg_for_logger = msg.replace('⚠', '[WARN]').replace('✅', '[OK]').replace('🛑', '[STOP]').replace('❌', '[ERROR]')
        root_logger.info(clean_msg_for_logger)

    @pyqtSlot(str)
    def update_device_status(self, device_prefix):
        """
        Updates the status of a specific device in the GUI.
        """
        device_name_map = {
            "Main FAN": "Main FAN",
            "Rotary Motor": "Rotary Motor",
            "Combustion FAN": "Combustion FAN",
            "Purge FAN": "Purge FAN"
        }
        
        display_name = device_name_map.get(device_prefix, device_prefix)

        if display_name not in self.device_labels:
            self.append_log(f"[!] Unknown device prefix received: {device_prefix}. Not updating status.")
            return

        now = QDateTime.currentDateTime()
        self.device_last_received[display_name] = now
        
        label = self.device_labels[display_name]
        last_received_label = self.device_last_received_labels[display_name]

        label.setPixmap(QPixmap(os.path.join(BASE_DIR, "active.png")).scaled(
            32, 32, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
        ))
        last_received_label.setText(now.toString("hh:mm:ss"))
        last_received_label.setStyleSheet("font-size: 10px; color: blue;")

        if display_name in self.device_timers:
            self.device_timers[display_name].stop()

        timer = QTimer(self)
        timer.setSingleShot(True)
        timer.timeout.connect(partial(self.reset_device_icon, display_name))
        timer.start(ACTIVE_ICON_DURATION_MS)
        self.device_timers[display_name] = timer

    def reset_device_icon(self, device_name):
        """Resets a device icon to idle state after an active period."""
        if device_name in self.device_labels:
            label = self.device_labels[device_name]
            label.setPixmap(QPixmap(os.path.join(BASE_DIR, "idle.png")).scaled(
                32, 32, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
            ))

    def check_device_errors(self):
        """
        Periodically checks for devices that haven't received data within a threshold
        and updates their icon to error state.
        """
        now = QDateTime.currentDateTime()
        for name in self.device_names:
            if name not in self.device_labels:
                continue

            last_time = self.device_last_received.get(name, now)
            label = self.device_labels[name]
            last_received_label = self.device_last_received_labels[name]

            if last_time.msecsTo(now) > INACTIVE_THRESHOLD_MS:
                # Check if the current pixmap is not already the error icon to avoid unnecessary updates
                if label.pixmap().toImage() != QPixmap(os.path.join(BASE_DIR, "error.png")).toImage():
                    label.setPixmap(QPixmap(os.path.join(BASE_DIR, "error.png")).scaled(
                        32, 32, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
                    ))
                    last_received_label.setStyleSheet("font-size: 10px; color: red;")
                    # Log only if the status actually changed to error from idle/active
                    if last_received_label.text() != "미수신" and "오류" not in last_received_label.text():
                         self.append_log(f"[!] Warning: '{name}' has not received data for {INACTIVE_THRESHOLD_MS/1000} seconds. Last received: {last_time.toString('hh:mm:ss')}")
            else:
                # If it was in error state but now within threshold, reset color to gray (unless active)
                if last_received_label.styleSheet() == "font-size: 10px; color: red;" and \
                   label.pixmap().toImage() != QPixmap(os.path.join(BASE_DIR, "active.png")).toImage():
                    last_received_label.setStyleSheet("font-size: 10px; color: gray;")

    def _update_server_status_display(self):
        """Periodically updates the textual server status to reflect actual state."""
        # Use self.server_thread to check if the thread is alive
        if self.server_running and self.server_thread and self.server_thread.is_alive():
            if self.server_status_label.text() != "실행 중":
                self.server_status_label.setText("실행 중")
                self.server_status_label.setStyleSheet("color: green;")
                self.server_status_indicator.setPixmap(QPixmap(os.path.join(BASE_DIR, "active.png")).scaled(16, 16, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        elif not self.server_running:
            if self.server_status_label.text() != "중지됨" and self.server_status_label.text() != "오류 발생":
                self.server_status_label.setText("중지됨")
                self.server_status_label.setStyleSheet("color: gray;")
                self.server_status_indicator.setPixmap(QPixmap(os.path.join(BASE_DIR, "idle.png")).scaled(16, 16, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))


    def show_message_box(self, title, message, icon=QMessageBox.Icon.Warning):
        """
        Displays a custom message box instead of alert().
        """
        msg_box = QMessageBox(self)
        msg_box.setIcon(icon)
        msg_box.setWindowTitle(title)
        msg_box.setText(message)
        msg_box.setStandardButtons(QMessageBox.StandardButton.Ok)
        msg_box.exec()


if __name__ == "__main__":
    CONFIG = Config()

    app = QApplication(sys.argv)
    window = FTPServerGUI()
    window.show()
    sys.exit(app.exec())
