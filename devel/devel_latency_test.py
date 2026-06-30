"""
Test latency between Arduino digital output and sound card output.

Set frequency, amplitude, and duration of a pure tone and select which
Arduino output pin to trigger. Pressing the button sets the output HIGH
and plays the sound simultaneously. Both signals can be recorded on an
oscilloscope to measure the latency.

Requires config.py with ARDUINO_PORT, OUTPUT_PINS, and SOUND_BACKEND set.
"""

import sys
import numpy as np
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                              QHBoxLayout, QLabel, QDoubleSpinBox, QComboBox,
                              QPushButton, QStatusBar)
from PyQt6.QtCore import Qt
from pyfirmata2 import Arduino
from phonotaxis import config
from phonotaxis.soundmodule import Sound, create_player

SAMPLERATE = 44100


class LatencyTestWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('Arduino + Sound Latency Test')
        self.board = None
        self.output_pins = {}
        self.sound_player = None

        self._build_ui()
        self._connect_arduino()
        self._init_sound_player()

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setSpacing(10)

        # --- Sound parameters ---
        params_layout = QHBoxLayout()

        params_layout.addWidget(QLabel('Frequency (Hz):'))
        self.freq_spin = QDoubleSpinBox()
        self.freq_spin.setRange(20, 20000)
        self.freq_spin.setValue(1000)
        self.freq_spin.setDecimals(0)
        params_layout.addWidget(self.freq_spin)

        params_layout.addWidget(QLabel('Amplitude (0–1):'))
        self.amp_spin = QDoubleSpinBox()
        self.amp_spin.setRange(0.0, 1.0)
        self.amp_spin.setValue(0.5)
        self.amp_spin.setSingleStep(0.05)
        self.amp_spin.setDecimals(2)
        params_layout.addWidget(self.amp_spin)

        params_layout.addWidget(QLabel('Duration (s):'))
        self.dur_spin = QDoubleSpinBox()
        self.dur_spin.setRange(0.01, 10.0)
        self.dur_spin.setValue(0.5)
        self.dur_spin.setSingleStep(0.1)
        self.dur_spin.setDecimals(2)
        params_layout.addWidget(self.dur_spin)

        layout.addLayout(params_layout)

        # --- Output selector + trigger button ---
        trigger_layout = QHBoxLayout()

        trigger_layout.addWidget(QLabel('Arduino output:'))
        self.output_combo = QComboBox()
        for name in config.OUTPUT_PINS:
            self.output_combo.addItem(f'{name}  (D{config.OUTPUT_PINS[name]})', name)
        trigger_layout.addWidget(self.output_combo)

        self.trigger_btn = QPushButton('Trigger')
        self.trigger_btn.setMinimumHeight(40)
        self.trigger_btn.clicked.connect(self._on_trigger)
        trigger_layout.addWidget(self.trigger_btn)

        layout.addLayout(trigger_layout)

        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage('Connecting to Arduino...')

    def _connect_arduino(self):
        try:
            self.board = Arduino(config.ARDUINO_PORT)
            for name, pin_num in config.OUTPUT_PINS.items():
                pin = self.board.get_pin(f'd:{pin_num}:o')
                pin.write(0)
                self.output_pins[name] = pin
            self.status_bar.showMessage(
                f'Arduino connected on {config.ARDUINO_PORT}')
        except Exception as e:
            self.status_bar.showMessage(f'Arduino error: {e}')

    def _init_sound_player(self):
        try:
            self.sound_player = create_player()
        except Exception as e:
            self.status_bar.showMessage(f'Sound player error: {e}')

    def _on_trigger(self):
        pin_name = self.output_combo.currentData()
        freq = self.freq_spin.value()
        amp = self.amp_spin.value()
        duration = self.dur_spin.value()

        # Build the sound
        sound = Sound(duration, SAMPLERATE, nchannels=2)
        sound.add_tone(freq, amp=amp, channel='all')
        sound.apply_rise_fall()
        self.sound_player.set_sound(1, sound)

        # Set Arduino output HIGH, play sound, then reset output
        if pin_name in self.output_pins:
            self.output_pins[pin_name].write(1)

        self.sound_player.play(1)

        if pin_name in self.output_pins:
            # Reset after sound duration
            from PyQt6.QtCore import QTimer
            QTimer.singleShot(int(duration * 1000), lambda: self._reset_output(pin_name))

        self.status_bar.showMessage(
            f'Triggered: {pin_name}, {freq:.0f} Hz, amp={amp:.2f}, dur={duration:.2f}s')

    def _reset_output(self, pin_name):
        if pin_name in self.output_pins:
            self.output_pins[pin_name].write(0)

    def closeEvent(self, event):
        if self.sound_player:
            self.sound_player.close()
        if self.board:
            for pin in self.output_pins.values():
                pin.write(0)
            self.board.exit()
        event.accept()


if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = LatencyTestWindow()
    window.show()
    sys.exit(app.exec())
