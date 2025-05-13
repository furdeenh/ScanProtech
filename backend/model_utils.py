from PIL import Image
import numpy as np
import cv2

def analyze_with_heuristics(image_path):
    image = Image.open(image_path).convert('RGB')
    image_np = np.array(image)

    gray = cv2.cvtColor(image_np, cv2.COLOR_RGB2GRAY)
    sharpness = cv2.Laplacian(gray, cv2.CV_64F).var()
    brightness = np.mean(gray)

    if brightness > 200:
        obj_type = "Highly Reflective Object (Metal)"
        threat = 0.1
    elif brightness > 100:
        obj_type = "Moderately Dense Object"
        threat = 0.4
    else:
        obj_type = "Dense or Unknown Object"
        threat = 0.75

    return {
        "sharpness": round(sharpness / 1000, 2),
        "object": obj_type,
        "threat_score": threat
    }
