# check_model.py
from ultralytics import YOLO
import os
import sys

print("=" * 60)
print("🔍 YOLO Model Diagnostics")
print("=" * 60)

model_path = 'ppe_yolov8.pt'
if not os.path.exists(model_path):
    print(f"❌ Model file not found at: {model_path}")
    sys.exit(1)

model = YOLO(model_path)

print("\n📋 Model Classes Index:")
print("-" * 40)
for idx, name in model.names.items():
    print(f"   ID {idx}: '{name}'")

# Test on a target image if provided, or search upload directory
test_image = None
if len(sys.argv) > 1:
    test_image = sys.argv[1]
elif os.path.exists('uploads') and len(os.listdir('uploads')) > 0:
    for f in os.listdir('uploads'):
        if f.lower().endswith(('.jpg', '.jpeg', '.png')):
            test_image = os.path.join('uploads', f)
            break

if test_image and os.path.exists(test_image):
    print(f"\n🧪 Running test inference on: {test_image}")
    results = model(test_image, conf=0.20, imgsz=640)
    
    print(f"\n📊 Detections Found: {len(results[0].boxes)}")
    for box in results[0].boxes:
        cls_name = model.names[int(box.cls[0])]
        conf = float(box.conf[0])
        print(f"   - Detected '{cls_name}' with confidence: {conf:.2f}")
    
    results[0].save('test_result.jpg')
    print("\n✅ Annotated diagnostic image saved as: test_result.jpg")
else:
    print("\n⚠️ No test images found in 'uploads/'. Place a test image in the project directory to verify bounding boxes.")

print("=" * 60)