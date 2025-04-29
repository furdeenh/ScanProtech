import requests

img_path = "Scan1.png"  # Use your uploaded scan image here
files = {'file': open(img_path, 'rb')}
response = requests.post("http://localhost:8000/analyze", files=files)
print(response.json())