from ultralytics import YOLO

if __name__ == '__main__':
    # Load the base lightweight model weights
    model = YOLO('yolov8n.pt')
    
    # Start the custom safety data training processing loop
    model.train(
        data='C:/VisionDesk_AI/ppe_dataset/data.yaml',  # Pointing to the folder
        epochs=25,
        imgsz=640,
        device='cpu'  
    )