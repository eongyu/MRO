import sys
import os
import json
import numpy as np
import pandas as pd
import nidaqmx
from nidaqmx.system import System
from datetime import datetime
from scipy.fft import rfft, rfftfreq
from scipy.signal import butter, filtfilt
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QFileDialog, QMessageBox
)
from PyQt6.QtCore import QTimer
from PyQt6.uic import loadUi
from PyQt6.QtWidgets import QSizePolicy
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

CONFIG_FILE = "iepe_config.json"
SENSITIVITY_FILE = "sensitivity_config.json"
CAL_RESISTOR = 230.9
DEFAULT_FILTER_CUTOFF = 5000.0
DEFAULT_FILTER_ORDER = 4
DEFAULT_AI3_SCALE = {"offset": 4.0, "gain": 16.0, "range": 10.0}
DEFAULT_INITIAL_CHANNELS = {"ai0": True, "ai1": True, "ai2": True, "ai3": True}
DEFAULT_COMBO_INDEX = 2

def butter_lowpass_filter(data, cutoff, fs, order=DEFAULT_FILTER_ORDER):
    nyq = 0.5 * fs
    normal_cutoff = cutoff / nyq
    b, a = butter(order, normal_cutoff, btype='low', analog=False)
    return filtfilt(b, a, data)

class IEPEWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        ui_path = os.path.join(os.path.dirname(__file__), "iepe_gui_with_calibration.ui")
        loadUi(ui_path, self)

        self.task = None
        self.measure_count = 0
        self.is_csv_mode = False
        self.last_csv_data = None
        self.last_csv_time = None
        self.auto_measuring = False

        data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
        os.makedirs(data_dir, exist_ok=True)
        self.save_directory = data_dir
        self.lblDirectory.setText(f"📁 저장 경로: {self.save_directory}")

        self.config = self.load_config()
        self.sensitivity_per_channel = self.load_sensitivity_config()

        self.spinCutoffFrequency.setValue(self.config.get("filter_cutoff", DEFAULT_FILTER_CUTOFF))

        self.figure = Figure(figsize=(10, 6))
        self.canvas = FigureCanvas(self.figure)
        self.canvas.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.canvas.updateGeometry()
        self.plotLayout.addWidget(self.canvas)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.start_measurement)

        self.btnStart.clicked.connect(self.start_auto_measurement)
        self.btnStop.clicked.connect(self.stop_auto_measurement)
        self.actionSelect_Directory.triggered.connect(self.select_directory)
        self.actionExit.triggered.connect(self.close)
        self.actionOpen_CSV.triggered.connect(self.open_csv_file)
        self.actionCalibrate_Channel.triggered.connect(self.calibrate_channel)

        initial_channels = self.config.get("initial_channels", DEFAULT_INITIAL_CHANNELS)
        self.chkAi0.setChecked(initial_channels.get("ai0", True))
        self.chkAi1.setChecked(initial_channels.get("ai1", True))
        self.chkAi2.setChecked(initial_channels.get("ai2", True))
        self.chkAi3.setChecked(initial_channels.get("ai3", True))

        initial_combo_index = self.config.get("combo_index", DEFAULT_COMBO_INDEX)
        self.comboChannelSelect.setCurrentIndex(initial_combo_index)

        for chk in [self.chkAi0, self.chkAi1, self.chkAi2, self.chkAi3]:
            chk.stateChanged.connect(self.update_plot)
        self.spinCutoffFrequency.valueChanged.connect(self.update_plot)

    def load_config(self):
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, 'r') as f:
                return json.load(f)
        return {
            "filter_cutoff": DEFAULT_FILTER_CUTOFF,
            "initial_channels": DEFAULT_INITIAL_CHANNELS,
            "combo_index": DEFAULT_COMBO_INDEX,
            "ai3_scale": DEFAULT_AI3_SCALE
        }

    def save_config(self):
        config_data = {
            "filter_cutoff": self.spinCutoffFrequency.value(),
            "initial_channels": {
                "ai0": self.chkAi0.isChecked(),
                "ai1": self.chkAi1.isChecked(),
                "ai2": self.chkAi2.isChecked(),
                "ai3": self.chkAi3.isChecked()
            },
            "combo_index": self.comboChannelSelect.currentIndex(),
            "ai3_scale": self.config.get("ai3_scale", DEFAULT_AI3_SCALE)
        }
        with open(CONFIG_FILE, 'w') as f:
            json.dump(config_data, f, indent=4)

    def open_csv_file(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "CSV 파일 열기", "", "CSV Files (*.csv)")
        if not file_path:
            return
        try:
            df = pd.read_csv(file_path)
            if "Time(s)" not in df.columns or df.shape[1] < 2:
                raise ValueError("CSV에 Time(s) 열과 하나 이상의 데이터 열이 필요합니다.")

            t = df["Time(s)"].values
            data_dict = {}
            sampling_rate = None
            if "Sampling Rate (Hz)" in df.columns:
                sampling_rate = df["Sampling Rate (Hz)"].iloc[0]
                df = df.drop(columns=["Sampling Rate (Hz)"])

            for col in df.columns[1:]:
                ch_name = col.replace(" (g)", "").strip()
                data_dict[ch_name] = df[col].values

            self.last_csv_time = t
            self.last_csv_data = data_dict
            self.csv_sampling_rate = sampling_rate
            self.is_csv_mode = True

            self.update_plot()
            self.lblStatus.setText("✅ CSV 파일 로드 완료")
        except Exception as e:
            QMessageBox.critical(self, "파일 읽기 오류", str(e))
            self.lblStatus.setText("❌ CSV 파일 로드 실패")

    def update_plot(self):
        try:
            if self.is_csv_mode and self.last_csv_data and self.last_csv_time is not None:
                t = self.last_csv_time
                data_dict = self.last_csv_data
                sampling_rate = self.csv_sampling_rate

                self.figure.clear()
                ax1 = self.figure.add_subplot(211)
                ax2 = self.figure.add_subplot(212)

                for ch, chk in zip(["ai0", "ai1", "ai2", "ai3"],
                                    [self.chkAi0, self.chkAi1, self.chkAi2, self.chkAi3]):
                    if chk.isChecked() and ch in data_dict:
                        y = data_dict[ch]
                        if sampling_rate is not None:
                            cutoff = self.spinCutoffFrequency.value()
                            y_filtered = butter_lowpass_filter(y, cutoff, sampling_rate)
                            ax1.plot(t, y_filtered, label=ch)
                            fft_vals = np.abs(rfft(y_filtered)) / len(y_filtered)
                            freqs = rfftfreq(len(y_filtered), 1 / sampling_rate)
                            ax2.plot(freqs, fft_vals, label=ch)
                        elif len(t) >= 2:
                            fs = 1 / (t[1] - t[0])
                            cutoff = self.spinCutoffFrequency.value()
                            y_filtered = butter_lowpass_filter(y, cutoff, fs)
                            ax1.plot(t, y_filtered, label=ch)
                            fft_vals = np.abs(rfft(y_filtered)) / len(y_filtered)
                            freqs = rfftfreq(len(y_filtered), 1 / fs)
                            ax2.plot(freqs, fft_vals, label=ch)
                        else:
                            ax1.plot(t, y, label=ch)
                            fft_vals = np.abs(rfft(y)) / len(y)
                            freqs = rfftfreq(len(y), 1.0) # Default frequency if no time info
                            ax2.plot(freqs, fft_vals, label=ch)

                ax1.set_title("Time Domain")
                ax1.set_ylabel("Acceleration (g) / Other Units")
                ax1.grid(True)
                ax1.legend()

                ax2.set_title("Frequency Domain")
                ax2.set_xlabel("Frequency (Hz)")
                ax2.set_ylabel("Amplitude")
                ax2.grid(True)
                ax2.legend()

                self.figure.tight_layout()
                self.canvas.draw()

                self.update_statistics(data_dict, t, sampling_rate)

                return

        except Exception as e:
            QMessageBox.critical(self, "CSV 업데이트 오류", str(e))

    def update_statistics(self, data_dict, t, sample_rate):
        ref_ch = self.comboChannelSelect.currentText().strip()
        enabled_channels = [ch for ch, chk in zip(["ai0", "ai1", "ai2", "ai3"],
                                                    [self.chkAi0, self.chkAi1, self.chkAi2, self.chkAi3]) if chk.isChecked()]
        if ref_ch not in enabled_channels and enabled_channels:
            ref_ch = enabled_channels[0]

        if ref_ch in data_dict:
            ref_data = data_dict[ref_ch]
            min_val = np.min(ref_data)
            max_val = np.max(ref_data)
            rms_val = np.sqrt(np.mean(ref_data ** 2))

            self.editMin.setText(f"{min_val:.3f}")
            self.editMax.setText(f"{max_val:.3f}")
            self.editRMS.setText(f"{rms_val:.3f}")

            if sample_rate is not None:
                fft_vals = np.abs(rfft(ref_data)) / len(ref_data)
                freqs = rfftfreq(len(ref_data), 1 / sample_rate)
                top_indices = np.argsort(fft_vals)[-10:][::-1]
                top_freqs = freqs[top_indices]
            elif len(t) >= 2:
                fs = 1 / (t[1] - t[0])
                fft_vals = np.abs(rfft(ref_data)) / len(ref_data)
                freqs = rfftfreq(len(ref_data), 1 / fs)
                top_indices = np.argsort(fft_vals)[-10:][::-1]
                top_freqs = freqs[top_indices]
            else:
                for i in range(10):
                    getattr(self, f"peakFreq{i+1}").setText("-")
                return

            for i in range(10):
                value = f"{top_freqs[i]:.1f}" if i < len(top_freqs) else ""
                getattr(self, f"peakFreq{i+1}").setText(value)
        else:
            self.editMin.setText("-")
            self.editMax.setText("-")
            self.editRMS.setText("-")
            for i in range(10):
                getattr(self, f"peakFreq{i+1}").setText("-")

    def start_auto_measurement(self):
        self.is_csv_mode = False
        self.measure_count = 0
        self.update_measure_count_label()
        if not self.auto_measuring:
            try:
                if self.task:  # 현재 활성화된 Task가 있다면 닫음
                    try:
                        self.task.control(nidaqmx.constants.TaskMode.TASK_STOP)
                        self.task.close()
                    except nidaqmx.errors.DaqError as e:
                        print(f"[DAQ Error] 기존 Task 종료 오류 (자동 측정): {e}")
                    self.task = None
                self.task = nidaqmx.system.storage.persisted_task.PersistedTask("MyTask3").load()
                self.auto_measuring = True
                self.start_measurement()
                self.timer.start(self.spinInterval.value() * 1000)
                self.lblStatus.setText("🟢 자동 측정 시작")
            except nidaqmx.errors.DaqError as e:
                QMessageBox.critical(self, "DAQ Task 오류", f"Task 로드 실패 (자동 측정): {e}")
                self.lblStatus.setText("❌ 자동 측정 시작 실패")
                self.auto_measuring = False
        else:
            self.lblStatus.setText("⚠️ 이미 자동 측정 중입니다.")

    def stop_auto_measurement(self):
        if self.timer.isActive():
            self.timer.stop()
        if self.task:
            try:
                self.task.control(nidaqmx.constants.TaskMode.TASK_STOP)
                self.task.close()
            except nidaqmx.errors.DaqError as e:
                print(f"[DAQ Error] Task close skipped: {e}")
            self.task = None
        self.auto_measuring = False
        self.lblStatus.setText("🛑 측정 중단됨")

    def calibrate_channel(self):
        target_rms = 0.7071  # 1g 진동 캘리브레이터의 이론 RMS
        rms_values = []

        selected_index = self.comboChannelSelect.currentIndex()
        selected_channel_name = self.comboChannelSelect.currentText()

        if selected_channel_name == "ai3":
            QMessageBox.warning(self, "경고", "ai3은 캘리브레이션 대상이 아닙니다.")
            return

        try:
            if self.task: # 현재 활성화된 Task가 있다면 닫음
                try:
                    self.task.control(nidaqmx.constants.TaskMode.TASK_STOP)
                    self.task.close()
                except nidaqmx.errors.DaqError as e:
                    print(f"[DAQ Error] 기존 캘리브레이션 Task 종료 오류: {e}")
                self.task = None

            self.task = nidaqmx.system.storage.persisted_task.PersistedTask("MyTask3").load()
            # ... (기존 캘리브레이션 로직) ...
            sample_rate = self.task.timing.samp_clk_rate
            samples = self.task.timing.samp_quant_samp_per_chan

            selected_index = self.comboChannelSelect.currentIndex()
            selected_channel_name = self.comboChannelSelect.currentText()

            if selected_channel_name == "ai3":
                QMessageBox.warning(self, "경고", "ai3은 캘리브레이션 대상이 아닙니다.")
                return

            for _ in range(10):
                data = self.task.read(number_of_samples_per_channel=samples)
                data = np.array(data)
                if data.ndim == 2:
                    data_ch = data[selected_index]
                else:
                    data_ch = data
                data_ch = data_ch - np.mean(data_ch)
                rms = np.sqrt(np.mean(data_ch ** 2))
                rms_values.append(rms)

            avg_rms_voltage = np.mean(rms_values)
            new_sensitivity = avg_rms_voltage / target_rms

            self.sensitivity_per_channel[selected_channel_name] = round(new_sensitivity, 5)
            with open(CONFIG_FILE, 'w') as f:
                json.dump(self.sensitivity_per_channel, f, indent=4)

            QMessageBox.information(self, "캘리브레이션 완료",
                                    f"{selected_channel_name} 감도: {new_sensitivity:.5f} V/g (10회 평균) 저장됨")
            self.task.close()
            self.task = None



        except nidaqmx.errors.DaqError as e:
            QMessageBox.critical(self, "DAQ Task 오류", f"캘리브레이션 Task 오류: {e}")
        except Exception as e:
            QMessageBox.critical(self, "캘리브레이션 오류", str(e))
        finally:
            if self.task and not self.auto_measuring:
                try:
                    self.task.control(nidaqmx.constants.TaskMode.TASK_STOP)
                    self.task.close()
                except nidaqmx.errors.DaqError as e:
                    print(f"[DAQ Error] 캘리브레이션 Task close 오류 (finally): {e}")
                self.task = None

    def start_measurement(self):
        try:
            self.sensitivity_per_channel = self.load_sensitivity_config()
            max_count = self.spinMaxCount.value()
            if max_count > 0 and self.measure_count >= max_count and self.auto_measuring:
                if self.timer.isActive():
                    self.timer.stop()
                self.lblStatus.setText("✅ 설정된 최대 측정 횟수에 도달하였습니다.")
                self.auto_measuring = False
                return
            elif max_count > 0 and self.measure_count >= max_count and not self.auto_measuring:
                return # 자동 측정이 아닐 때는 최대 횟수 도달 시 추가 측정 안함

            if not self.task:
                try:
                    self.task = nidaqmx.system.storage.persisted_task.PersistedTask("MyTask3").load()
                except nidaqmx.errors.DaqError as e:
                    QMessageBox.critical(self, "DAQ Task 오류", f"Task 로드 실패 (측정): {e}")
                    self.lblStatus.setText("❌ 측정 실패")
                    return

            sample_rate = self.task.timing.samp_clk_rate
            samples = self.task.timing.samp_quant_samp_per_chan
            data = self.task.read(number_of_samples_per_channel=samples)
            data = np.array(data)
            if data.ndim == 1:
                data = data.reshape((1, -1))

            self.measure_count += 1
            self.update_measure_count_label()
            self.process_and_display_all_channels(data, sample_rate)

        except nidaqmx.errors.DaqError as e:
            QMessageBox.critical(self, "DAQ Task 오류", f"측정 Task 읽기 오류: {e}")
            self.lblStatus.setText("❌ 측정 실패")
            if self.task and not self.auto_measuring:
                try:
                    self.task.control(nidaqmx.constants.TaskMode.TASK_STOP)
                    self.task.close()
                except nidaqmx.errors.DaqError as e:
                    print(f"[DAQ Error] 측정 Task close 오류 (start_measurement): {e}")
                self.task = None
            self.auto_measuring = False
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))
            self.lblStatus.setText("❌ 측정 실패")
            if self.task and not self.auto_measuring:
                try:
                    self.task.control(nidaqmx.constants.TaskMode.TASK_STOP)
                    self.task.close()
                except nidaqmx.errors.DaqError as e:
                    print(f"[DAQ Error] 측정 Task close 오류 (start_measurement - general): {e}")
                self.task = None
            self.auto_measuring = False
        finally:
            if not self.auto_measuring and self.task:
                try:
                    self.task.control(nidaqmx.constants.TaskMode.TASK_STOP)
                    self.task.close()
                    self.task = None
                except nidaqmx.errors.DaqError as e:
                    print(f"[DAQ Error] 측정 Task close 오류 (finally): {e}")

    def process_and_display_all_channels(self, data, sample_rate):
        t = np.arange(data.shape[1]) / sample_rate
        proc_data = {}
        cutoff = self.spinCutoffFrequency.value()

        ai3_scale = self.config.get("ai3_scale", DEFAULT_AI3_SCALE)

        for i, ch in enumerate(["ai0", "ai1", "ai2", "ai3"]):
            filtered = butter_lowpass_filter(data[i], cutoff, sample_rate)
            if ch == "ai3":
                current_mA = (filtered / CAL_RESISTOR) * 1000
                proc_data[ch] = (current_mA - ai3_scale["offset"]) / ai3_scale["gain"] * ai3_scale["range"]
            else:
                proc_data[ch] = (filtered - np.mean(filtered)) / self.sensitivity_per_channel.get(ch, 1.0)

        self.last_csv_time = t
        self.last_csv_data = proc_data
        self.csv_sampling_rate = sample_rate # Store for potential CSV save
        self.is_csv_mode = False

        self.figure.clear()
        ax1 = self.figure.add_subplot(211)
        ax2 = self.figure.add_subplot(212)

        for ch, chk in zip(["ai0", "ai1", "ai2", "ai3"], [self.chkAi0, self.chkAi1, self.chkAi2, self.chkAi3]):
            if chk.isChecked():
                ax1.plot(t, proc_data[ch], label=ch)
                fft_vals = np.abs(rfft(proc_data[ch])) / len(proc_data[ch])
                freqs = rfftfreq(len(proc_data[ch]), 1 / sample_rate)
                ax2.plot(freqs, fft_vals, label=ch)

        ax1.set_title("Time Domain")
        ax1.set_ylabel("Acceleration (g) / Other Units")
        ax1.grid(True)
        ax1.legend()

        ax2.set_title("Frequency Domain")
        ax2.set_xlabel("Frequency (Hz)")
        ax2.set_ylabel("Amplitude")
        ax2.grid(True)
        ax2.legend()

        self.figure.tight_layout(pad=3.0)
        self.canvas.draw()

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        base = os.path.join(self.save_directory, f"iepe_{timestamp}")
        save_df = pd.DataFrame({"Time(s)": t, **{f"{k} (g)": v for k, v in proc_data.items()}})
        save_df["Sampling Rate (Hz)"] = sample_rate
        save_df.to_csv(f"{base}.csv", index=False)
        self.figure.savefig(f"{base}.png")

        self.update_statistics(proc_data, t, sample_rate)

    def update_measure_count_label(self):
        self.labelCurrentCount.setText(f"현재 측정 횟수: {self.measure_count}")

    def load_sensitivity_config(self):
        if os.path.exists(SENSITIVITY_FILE):
            with open(SENSITIVITY_FILE, 'r') as f:
                return json.load(f)
        return {f"ai{i}": 1.0 for i in range(4)}

    def save_sensitivity_config(self):
        with open(SENSITIVITY_FILE, 'w') as f:
            json.dump(self.sensitivity_per_channel, f, indent=4)

    def select_directory(self):
        path = QFileDialog.getExistingDirectory(self, "CSV 저장 폴더 선택", self.save_directory)
        if path:
            self.save_directory = path
            self.lblDirectory.setText(f"📁 저장 경로: {path}")
            self.save_config()

    def closeEvent(self, event):
        self.save_config()
        if self.task:
            try:
                self.task.control(nidaqmx.constants.TaskMode.TASK_STOP)
                self.task.close()
            except nidaqmx.errors.DaqError as e:
                print(f"[DAQ Error] 어플리케이션 종료 중 Task close 오류: {e}")
        event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = IEPEWindow()
    window.show()
    sys.exit(app.exec())