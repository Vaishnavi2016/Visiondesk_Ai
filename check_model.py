# check_model.py
import os
import sys
import cv2
import numpy as np
from ultralytics import YOLO

print("=" * 60)
print("🔍 YOLO Model Diagnostics")
print("=" * 60)

model_path = 'ppe_yolov8.pt'
if not os.path.exists(model_path):
    print(f"❌ Model file not found at: {model_path}")
    print("   Please ensure 'ppe_yolov8.pt' is in the project root directory.")
    sys.exit(1)

model = YOLO(model_path)

print("\n📋 Model Classes Index:")
print("-" * 40)
for idx, name in model.names.items():
    print(f"   ID {idx}: '{name}'")

# Look for real uploaded images first, fallback to argument or generated dummy
test_image = None
if len(sys.argv) > 1:
    test_image = sys.argv[1]
elif os.path.exists('uploads') and len(os.listdir('uploads')) > 0:
    for f in os.listdir('uploads'):
        if f.lower().endswith(('.jpg', '.jpeg', '.png')):
            test_image = os.path.join('uploads', f)
            break

if not test_image or not os.path.exists(test_image):
    print("\nℹ️ No existing image found in 'uploads/'. Creating synthetic test image: test_person.jpg")
    img = np.zeros((480, 640, 3), dtype=np.uint8)
    cv2.rectangle(img, (250, 200), (290, 400), (200, 200, 200), -1)  # Body
    cv2.circle(img, (270, 180), 30, (200, 200, 200), -1)              # Head
    cv2.rectangle(img, (240, 280), (300, 290), (100, 100, 100), -1)  # Belt
    test_image = 'test_person.jpg'
    cv2.imwrite(test_image, img)

print(f"\n🧪 Running test inference on: {test_image}")
results = model(test_image, conf=0.25, imgsz=640)

print(f"\n📊 Detections Found: {len(results[0].boxes)}")
for box in results[0].boxes:
    cls_name = model.names[int(box.cls[0])]
    conf = float(box.conf[0])
    print(f"   - Detected '{cls_name}' with confidence: {conf:.2f}")

annotated = results[0].plot()
cv2.imwrite('test_result.jpg', annotated)
print("\n✅ Annotated diagnostic image saved as: test_result.jpg")
print("=" * 60)