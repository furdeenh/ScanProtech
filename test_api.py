
import random
import time
import os
import board
import threading
from adafruit_motorkit import MotorKit
from adafruit_motor import stepper
import adafruit_ads1x15.ads1115 as ADS
from adafruit_ads1x15.analog_in import AnalogIn
from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.screenmanager import ScreenManager, Screen
from kivy.uix.button import Button
from kivy.clock import Clock
from kivy.uix.image import Image
from kivy.uix.scrollview import ScrollView
import matplotlib.pyplot as plt
import seaborn as sns
import numpy as np
from scipy.ndimage import gaussian_filter
from datetime import datetime
from backend.model_utils import analyze_with_heuristics

IMAGE_DIRECTORY = "./heatmaps"
os.makedirs(IMAGE_DIRECTORY, exist_ok=True)

data_matrix = []
x_velocities = []
y_velocities = []

def reset_axes(motor_x, motor_y, steps_per_mm):
    move_motor(motor_y, int(130 * steps_per_mm), stepper.BACKWARD)
    move_motor(motor_x, int((110 - 5) * steps_per_mm), stepper.BACKWARD)

def move_motor(motor, steps, direction):
    start = time.time()
    for _ in range(steps):
        motor.onestep(direction=direction)
        time.sleep(0.002)
    return time.time() - start

def acquire_adc_data(chan, rate, data_list, stop_event):
    interval = 1 / rate
    while not stop_event.is_set():
        data_list.append(chan.voltage)
        time.sleep(interval)

def move_in_zigzag_pattern(motor_x, motor_y, chan, rate, y_step_mm, spmm, update_vel):
    global data_matrix, x_velocities, y_velocities
    data_matrix = []
    total_x = int(110 * spmm)
    total_y = int(y_step_mm * spmm)
    rows = int(130 / y_step_mm)
    for i in range(rows):
        row = []
        stop = threading.Event()
        thread = threading.Thread(target=acquire_adc_data, args=(chan, rate, row, stop))
        thread.start()
        dur = move_motor(motor_x, total_x, stepper.FORWARD)
        stop.set()
        thread.join()
        data_matrix.append(row)
        x_velocities.append(110 / dur)
        move_motor(motor_y, total_y, stepper.FORWARD)
        y_velocities.append(y_step_mm / (0.002 * total_y))

        row = []
        stop = threading.Event()
        thread = threading.Thread(target=acquire_adc_data, args=(chan, rate, row, stop))
        thread.start()
        dur = move_motor(motor_x, total_x, stepper.BACKWARD)
        stop.set()
        thread.join()
        row.reverse()
        data_matrix.append(row)
        x_velocities.append(110 / dur)
        move_motor(motor_y, total_y, stepper.FORWARD)
        y_velocities.append(y_step_mm / (0.002 * total_y))

    Clock.schedule_once(lambda dt: update_vel(np.mean(x_velocities), np.mean(y_velocities)))

def generate_heatmap(matrix):
    max_len = max(len(r) for r in matrix)
    padded = np.full((len(matrix), max_len), np.nan)
    for i, r in enumerate(matrix):
        padded[i, :len(r)] = r
    filtered = gaussian_filter(np.nan_to_num(padded), sigma=1)
    plt.figure(figsize=(10, 8))
    sns.heatmap(filtered, cmap="coolwarm", xticklabels=False, yticklabels=False,
                mask=np.isnan(padded), cbar_kws={'label': 'Voltage (V)', 'shrink': 0.8})
    plt.title('mmWave Signal Intensity')
    plt.xlabel('X')
    plt.ylabel('Y')
    fname = os.path.join(IMAGE_DIRECTORY, f"heatmap_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.png")
    plt.savefig(fname)
    plt.close()
    return fname

class MainScreen(Screen):
    def __init__(self, **kwargs):
        super(MainScreen, self).__init__(**kwargs)
        self.kit1 = MotorKit(address=0x60)
        self.kit2 = MotorKit(address=0x61)
        self.spmm = 200 / (2 * 3.14 * 10)
        self.mx = self.kit1.stepper1
        self.my = self.kit1.stepper2
        self.mz = self.kit2.stepper1
        i2c = board.I2C()
        ads = ADS.ADS1115(i2c)
        self.chan = AnalogIn(ads, ADS.P0)

        layout = BoxLayout(orientation='vertical')
        self.info = Label(text='Results will show here')
        self.sampling_input = TextInput(hint_text="Sampling Rate", multiline=False)
        self.y_input = TextInput(hint_text="Y Step (mm)", multiline=False)
        self.z_input = TextInput(hint_text="Z Travel (mm)", multiline=False)
        scan_btn = Button(text='Start Scan')
        scan_btn.bind(on_release=self.run_scan)
        layout.add_widget(self.sampling_input)
        layout.add_widget(self.y_input)
        layout.add_widget(self.z_input)
        layout.add_widget(scan_btn)
        layout.add_widget(self.info)
        self.add_widget(layout)

    def update_velocity(self, x, y):
        print(f"Velocity - X: {x:.2f} mm/s | Y: {y:.2f} mm/s")

    def run_scan(self, *args):
        try:
            s = float(self.sampling_input.text)
            y = float(self.y_input.text)
            z = float(self.z_input.text)
            move_motor(self.mz, int(z * 10), stepper.FORWARD)
            reset_axes(self.mx, self.my, self.spmm)
            move_in_zigzag_pattern(self.mx, self.my, self.chan, s, y, self.spmm, self.update_velocity)
            img_path = generate_heatmap(data_matrix)
            result = analyze_with_heuristics(img_path)
            self.info.text = f"Object: {result['object']} | Threat Score: {result['threat_score']}"
        except Exception as e:
            self.info.text = str(e)

class mmWaveApp(App):
    def build(self):
        sm = ScreenManager()
        sm.add_widget(MainScreen(name='main'))
        return sm

if __name__ == '__main__':
    mmWaveApp().run()
