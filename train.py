import os
from ultralytics import YOLO
import torch

if __name__ == '__main__':
    # Check CUDA availability
    device = 0 if torch.cuda.is_available() else 'cpu'
    print(f"Using device: {device}")
    if device == 'cpu':
        print("WARNING: CUDA not available. Training will be slower on CPU.")
    
    # 1. Verify your old model exists so we can build on top of it
    model_path = 'ppe_yolov8.pt'
    dataset_path = 'C:/VisionDesk_AI/ppe_dataset/data.yaml'
    
    if not os.path.exists(model_path):
        print("Error: ppe_yolov8.pt not found in the root directory!")
        print("Make sure it is next to this script.")
        exit(1)
    
    if not os.path.exists(dataset_path):
        print("Error: Dataset configuration not found at:", dataset_path)
        print("Please check the path and try again.")
        exit(1)
    
    # Load your PREVIOUS model weights
    model = YOLO(model_path)
    print(f"✅ Loaded model: {model_path}")
    
    # Display model summary
    print("\n📊 Model Architecture Summary:")
    print("-" * 50)
    print(model.model)
    print("-" * 50)
    
    # 2. Training parameters
    training_params = {
        'data': dataset_path,
        'epochs': 30,
        'imgsz': 640,
        'batch': 8,           # Lower this to 4 if your system runs out of memory
        'device': device,     # Auto-detects GPU or CPU
        'workers': 4,         # Number of data loading workers
        'patience': 50,       # Early stopping patience
        'save_period': 5,     # Save checkpoint every 5 epochs
        'pretrained': True,   # Use pretrained weights
        'optimizer': 'auto',  # Auto-select optimizer
        'verbose': True,      # Print detailed training info
        'project': 'ppe_detection',  # Project name
        'name': 'fine_tuned_v2',     # Experiment name
        'exist_ok': True,     # Overwrite existing results
        'plots': True,        # Generate plots
        'seed': 42,           # Random seed for reproducibility
    }
    
    print("\n🚀 Starting fine-tuning pipeline optimization on expanded dataset...")
    print(f"📁 Dataset: {dataset_path}")
    print(f"⚙️  Epochs: {training_params['epochs']}")
    print(f"📦 Batch Size: {training_params['batch']}")
    print(f"🖥️  Device: {training_params['device']}")
    print("-" * 50)
    
    try:
        # 3. Start the extended custom safety data training loop
        results = model.train(**training_params)
        
        print("\n✅ Extended training process completed successfully!")
        print("📊 Training results saved in: ppe_detection/fine_tuned_v2/")
        
        # Print best results
        if results:
            print("\n🏆 Best Results:")
            print(f"   - Best mAP50: {results.get('metrics/mAP50(B)', 0):.4f}")
            print(f"   - Best mAP50-95: {results.get('metrics/mAP50-95(B)', 0):.4f}")
            print(f"   - Best F1 Score: {results.get('metrics/F1', 0):.4f}")
        
        # 4. Validate the trained model
        print("\n🧪 Validating trained model...")
        val_results = model.val()
        print(f"✅ Validation complete!")
        
        # 5. Save the final model
        final_model_path = 'ppe_yolov8_final.pt'
        model.save(final_model_path)
        print(f"\n💾 Final model saved as: {final_model_path}")
        print(f"   Size: {os.path.getsize(final_model_path) / (1024*1024):.2f} MB")
        
        print("\n🎉 Fine-tuning complete! You can now use 'ppe_yolov8_final.pt' for inference.")
        
    except Exception as e:
        print(f"\n❌ Error during training: {str(e)}")
        print("Check the error message above and fix any issues.")
        
        # Provide helpful suggestions
        if "CUDA out of memory" in str(e):
            print("\n💡 SUGGESTION: Reduce batch size to 4 or 2")
            print("   Update the 'batch' parameter in training_params")
        elif "No such file or directory" in str(e):
            print("\n💡 SUGGESTION: Check that your dataset paths are correct")
            print(f"   Dataset YAML path: {dataset_path}")
            print("   Make sure the images and labels directories exist")
        elif "module 'torch' has no attribute 'cuda'" in str(e):
            print("\n💡 SUGGESTION: Install PyTorch with CUDA support")
            print("   Or set device='cpu' in training_params")