# FULL INTEGRATED VERSION OF UPDATED scan.py

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
from kivy.uix.floatlayout import FloatLayout
from kivy.graphics import Color, Rectangle
import requests

# Global variables
data_matrix = []
IMAGE_DIRECTORY = "/home/furdeengregg/Desktop/Senior Design Team & Gregg Data Collection/KIVY GUI"


def move_motor(motor, steps, direction):
    for _ in range(steps):
        motor.onestep(direction=direction)
        time.sleep(0.002)

def move_third_actuator(motor_z, distance_mm, steps_per_mm=10):
    steps = int(distance_mm * steps_per_mm)
    for _ in range(steps):
        motor_z.onestep(direction=stepper.FORWARD)
        time.sleep(0.01)

def acquire_adc_data(chan, sampling_rate, data_list, stop_event):
    interval = 1 / sampling_rate
    while not stop_event.is_set():
        data_list.append(chan.voltage)
        time.sleep(interval)

def move_in_zigzag_pattern(motor_x, motor_y, chan, sampling_rate, step_increment_y, steps_per_mm):
    global data_matrix
    data_matrix = []
    total_x_steps = int(110 * steps_per_mm)
    total_y_steps = int(step_increment_y * steps_per_mm)
    total_y_increments = int(130 / step_increment_y)

    stop_event = threading.Event()

    for i in range(total_y_increments):
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
    heatmap_filename = os.path.join(IMAGE_DIRECTORY, f"heatmap_{timestamp}.png")
    plt.savefig(heatmap_filename)
    return heatmap_filename

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

        main_layout = BoxLayout(orientation='vertical', spacing=10, padding=10)
        title_label = Label(text="ScanProTech", font_size='40sp', color=(1, 0, 0, 1), size_hint=(1, None), height=60)
        main_layout.add_widget(title_label)

        content_layout = BoxLayout(orientation='horizontal')
        left_layout = BoxLayout(orientation='vertical', spacing=10, size_hint=(0.65, 1))
        self.image_widget = Image(size_hint=(1, 0.7), opacity=0)
        left_layout.add_widget(self.image_widget)

        self.ai_feedback_label = Label(text="", font_size='16sp', color=(0.9, 0.9, 0.9, 1), size_hint=(1, None), height=80)
        self.ai_caption_label = Label(text="", font_size='18sp', color=(0.2, 1, 0.2, 1), size_hint=(1, None), height=30)
        left_layout.add_widget(self.ai_feedback_label)
        left_layout.add_widget(self.ai_caption_label)

        button_layout = BoxLayout(size_hint=(1, None), height=50)
        scan_button = Button(text="Scan Now")
        scan_button.bind(on_release=self.start_scan)
        button_layout.add_widget(scan_button)
        left_layout.add_widget(button_layout)

        right_layout = BoxLayout(orientation='vertical', size_hint=(0.35, 1))
        self.sampling_input = TextInput(hint_text="Sampling Rate", multiline=False)
        self.y_input = TextInput(hint_text="Y-axis increment", multiline=False)
        self.z_input = TextInput(hint_text="Z-axis movement", multiline=False)
        right_layout.add_widget(Label(text="Sampling Rate:"))
        right_layout.add_widget(self.sampling_input)
        right_layout.add_widget(Label(text="Y-axis:"))
        right_layout.add_widget(self.y_input)
        right_layout.add_widget(Label(text="Z-axis:"))
        right_layout.add_widget(self.z_input)

        content_layout.add_widget(left_layout)
        content_layout.add_widget(right_layout)
        main_layout.add_widget(content_layout)
        self.add_widget(main_layout)

    def analyze_image_with_ai(self, image_path):
        try:
            url = "http://127.0.0.1:8000/analyze"
            with open(image_path, "rb") as image_file:
                files = {"file": image_file}
                response = requests.post(url, files=files)
            return response.json() if response.ok else {"error": "API error"}
        except Exception as e:
            return {"error": str(e)}

    def start_scan(self, *args):
        try:
            sampling = float(self.sampling_input.text)
            y_step = float(self.y_input.text)
            z_move = float(self.z_input.text)

            move_third_actuator(self.motor_z, z_move)
            move_in_zigzag_pattern(self.motor_x, self.motor_y, self.chan, sampling, y_step, self.steps_per_mm)
            heatmap_path = generate_heatmap(data_matrix)
            ai_result = self.analyze_image_with_ai(heatmap_path)

            self.image_widget.source = heatmap_path
            self.image_widget.opacity = 1
            self.image_widget.reload()

            if "error" in ai_result:
                self.ai_feedback_label.text = f"[AI Error] {ai_result['error']}"
                self.ai_caption_label.text = ""
            else:
                heur = ai_result.get("heuristic", {})
                obj = heur.get("object", "Unknown")
                threat = heur.get("threat_score", "N/A")
                sharp = heur.get("sharpness", "N/A")
                self.ai_feedback_label.text = f"[AI Feedback]\n - Object: {obj}\n - Threat: {threat}\n - Sharpness: {sharp}"

                if threat < 0.3:
                    self.ai_caption_label.text = "Likely unharmful object, no further inspection needed."
                elif threat < 0.7:
                    self.ai_caption_label.text = "Caution advised. Object moderately dense."
                else:
                    self.ai_caption_label.text = "Potentially harmful object detected. Further inspection advised."
        except Exception as e:
            self.ai_feedback_label.text = f"[Scan Error] {str(e)}"

class mmWaveApp(App):
    def build(self):
        sm = ScreenManager()
        sm.add_widget(MainScreen(name='main'))
        sm.current = 'main'
        return sm

if __name__ == '__main__':
    mmWaveApp().run()
