"""Check GPU and PyTorch CUDA availability"""
import sys
sys.stdout.reconfigure(encoding='utf-8')

try:
    import torch
    print(f"PyTorch version: {torch.__version__}")
    print(f"CUDA available: {torch.cuda.is_available()}")
    if torch.cuda.is_available():
        print(f"CUDA version (PyTorch): {torch.version.cuda}")
        print(f"GPU device: {torch.cuda.get_device_name(0)}")
        props = torch.cuda.get_device_properties(0)
        print(f"Total VRAM: {props.total_memory / 1024**3:.1f} GB")
        print(f"Compute capability: {props.major}.{props.minor}")
        # Quick test
        x = torch.randn(1000, 1000).cuda()
        y = torch.randn(1000, 1000).cuda()
        z = torch.mm(x, y)
        print("GPU computation test: PASSED")
    else:
        print("CUDA not available. Need to install PyTorch with CUDA support.")
        print("Current PyTorch is CPU-only.")
except ImportError:
    print("PyTorch is NOT installed.")
    print("Need: pip install torch torchvision --index-url https://download.pytorch.org/whl/cu121")

try:
    import transformers
    print(f"\nTransformers version: {transformers.__version__}")
except ImportError:
    print("\nTransformers is NOT installed.")
    print("Need: pip install transformers")

try:
    import datasets
    print(f"Datasets version: {datasets.__version__}")
except ImportError:
    print("Datasets is NOT installed.")
    print("Need: pip install datasets")
