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
from kivy.uix.anchorlayout import AnchorLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.screenmanager import ScreenManager, Screen
from kivy.uix.scrollview import ScrollView
from kivy.uix.image import Image
from kivy.clock import Clock
import matplotlib.pyplot as plt
import seaborn as sns
import numpy as np
from scipy.ndimage import gaussian_filter
from datetime import datetime
from kivy.core.window import Window
from kivy.uix.widget import Widget
from kivy.graphics import Color, Rectangle
from kivy.uix.floatlayout import FloatLayout
import requests

# Global Variables
data_matrix = []
IMAGE_DIRECTORY = "/home/furdeengregg/Desktop/Senior Design Team & Gregg Data Collection/KIVY GUI"

# Function to Reset Axes
def reset_axes(motor_x, motor_y, steps_per_mm, travel_distance_x=110, travel_distance_y=130):
    x_reset_distance = 5
    y_reset_distance = travel_distance_y
    x_steps_to_reset = int((travel_distance_x - x_reset_distance) * steps_per_mm)
    y_steps_to_reset = int(y_reset_distance * steps_per_mm)
    move_motor(motor_y, y_steps_to_reset, stepper.BACKWARD)
    move_motor(motor_x, x_steps_to_reset, stepper.BACKWARD)

# Function to move the Z-axis actuator
def move_third_actuator(motor_z, distance_mm, steps_per_mm=10):
    steps = int(distance_mm * steps_per_mm)
    for _ in range(steps):
        motor_z.onestep(direction=stepper.FORWARD)
        time.sleep(0.01)

# Move Motor Function
def move_motor(motor, steps, direction):
    for _ in range(steps):
        motor.onestep(direction=direction)
        time.sleep(0.002)

# Acquire ADC Data
def acquire_adc_data(chan, sampling_rate, data_list, stop_event):
    interval = 1 / sampling_rate
    while not stop_event.is_set():
        data_list.append(chan.voltage)
        time.sleep(interval)

# Zigzag Scan Pattern
def move_in_zigzag_pattern(motor_x, motor_y, chan, sampling_rate, step_increment_y, steps_per_mm):
    global data_matrix
    data_matrix = []
    total_x_steps = int(110 * steps_per_mm)
    total_y_steps = int(step_increment_y * steps_per_mm)
    total_y_increments = int(130 / step_increment_y)
    stop_event = threading.Event()

    for _ in range(total_y_increments):
        row_data = []
        stop_event.clear()
        adc_thread = threading.Thread(target=acquire_adc_data, args=(chan, sampling_rate, row_data, stop_event))
        adc_thread.start()
        move_motor(motor_x, total_x_steps, stepper.FORWARD)
        stop_event.set()
        adc_thread.join()
        data_matrix.append(row_data)

        move_motor(motor_y, total_y_steps, stepper.FORWARD)

        row_data = []
        stop_event.clear()
        adc_thread = threading.Thread(target=acquire_adc_data, args=(chan, sampling_rate, row_data, stop_event))
        adc_thread.start()
        move_motor(motor_x, total_x_steps, stepper.BACKWARD)
        stop_event.set()
        adc_thread.join()
        row_data.reverse()
        data_matrix.append(row_data)

        move_motor(motor_y, total_y_steps, stepper.FORWARD)

# Generate Heatmap
def generate_heatmap(data_matrix):
    max_length = max(len(row) for row in data_matrix)
    padded_data_matrix = np.full((len(data_matrix), max_length), np.nan)
    for i, row in enumerate(data_matrix):
        padded_data_matrix[i, :len(row)] = row
    data_matrix_filtered = gaussian_filter(np.nan_to_num(padded_data_matrix), sigma=1)
    plt.figure(figsize=(10, 8))
    sns.heatmap(data_matrix_filtered, cmap="coolwarm", xticklabels=False, yticklabels=False,
                mask=np.isnan(padded_data_matrix), cbar_kws={'label': 'Voltage (V)', 'shrink': 0.8})
    plt.title('mmWave Signal Intensity (V)', fontsize=20)
    plt.xlabel('X Position (cm)', fontsize=16)
    plt.ylabel('Y Position (cm)', fontsize=16)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    save_path = IMAGE_DIRECTORY
    heatmap_filename = os.path.join(save_path, f"heatmap_{timestamp}.png")
    plt.savefig(heatmap_filename)
    return heatmap_filename

# Main GUI Class
class MainScreen(Screen):
    def __init__(self, **kwargs):
        super(MainScreen, self).__init__(**kwargs)
        self.kit1 = MotorKit(address=0x60)
        self.kit2 = MotorKit(address=0x61)
        self.steps_per_mm = 200 / (2 * 3.14 * 10)
        self.motor_x = self.kit1.stepper1
        self.motor_y = self.kit1.stepper2
        self.motor_z = self.kit2.stepper1
        i2c = board.I2C()
        ads = ADS.ADS1115(i2c)
        self.chan = AnalogIn(ads, ADS.P0)

        layout = BoxLayout(orientation='vertical')
        self.image_widget = Image(size_hint=(1, 0.7))
        layout.add_widget(self.image_widget)
        self.scanned_image_label = Label(text="Scan results will appear here", size_hint=(1, 0.1))
        layout.add_widget(self.scanned_image_label)

        input_layout = BoxLayout(size_hint=(1, 0.1))
        self.sampling_rate_input = TextInput(hint_text="Sampling Rate")
        self.y_axis_input = TextInput(hint_text="Y Increment (mm)")
        self.z_axis_input = TextInput(hint_text="Z Height (mm)")
        input_layout.add_widget(self.sampling_rate_input)
        input_layout.add_widget(self.y_axis_input)
        input_layout.add_widget(self.z_axis_input)
        layout.add_widget(input_layout)

        self.scan_button = Button(text="Start Scan", size_hint=(1, 0.1))
        self.scan_button.bind(on_release=self.start_scan)
        layout.add_widget(self.scan_button)

        self.add_widget(layout)

    def analyze_image_with_ai(self, image_path):
        try:
            url = "http://127.0.0.1:8000/analyze"
            with open(image_path, "rb") as f:
                files = {"file": f}
                response = requests.post(url, files=files)
            return response.json() if response.ok else {"error": "API error"}
        except Exception as e:
            return {"error": str(e)}

    def start_scan(self, *args):
        try:
            sampling_rate = float(self.sampling_rate_input.text)
            y_axis_value = float(self.y_axis_input.text)
            z_axis_value = float(self.z_axis_input.text)
            move_third_actuator(self.motor_z, z_axis_value)
            reset_axes(self.motor_x, self.motor_y, self.steps_per_mm)
            move_in_zigzag_pattern(self.motor_x, self.motor_y, self.chan, sampling_rate, y_axis_value, self.steps_per_mm)
            image_path = generate_heatmap(data_matrix)
            self.image_widget.source = image_path
            self.image_widget.reload()
            self.scanned_image_label.text = "Scan Complete."

            # AI Feedback
            analysis_result = self.analyze_image_with_ai(image_path)
            if "error" in analysis_result:
                self.scanned_image_label.text += f"\n[AI Error] {analysis_result['error']}"
            else:
                heur = analysis_result.get("heuristic", {})
                summary = (f"\n[AI Feedback]"
                           f"\n - Object: {heur.get('object', 'N/A')}"
                           f"\n - Threat: {heur.get('threat_score', 'N/A')}"
                           f"\n - Sharpness: {heur.get('sharpness', 'N/A')}")
                self.scanned_image_label.text += summary

        except ValueError:
            self.scanned_image_label.text = "Invalid input. Please enter numbers."

# App Class
class mmWaveApp(App):
    def build(self):
        sm = ScreenManager()
        sm.add_widget(MainScreen(name='main'))
        return sm

if __name__ == '__main__':
    mmWaveApp().run()
