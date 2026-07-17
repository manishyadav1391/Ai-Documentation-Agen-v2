import shutil
from pathlib import Path
import subprocess
import sys

def main():
    root = Path(__file__).resolve().parent
    build_dir = root / "build"
    dist_dir = root / "dist"
    
    print("Cleaning old build artifacts...")
    if build_dir.exists():
        try:
            shutil.rmtree(build_dir)
        except Exception as e:
            print(f"Warning: could not clean build/ directory: {e}")
    if dist_dir.exists():
        try:
            shutil.rmtree(dist_dir)
        except Exception as e:
            print(f"Warning: could not clean dist/ directory: {e}")
        
    print("Running PyInstaller...")
    try:
        subprocess.run(["pyinstaller", "docbot.spec"], check=True)
        print("Build completed successfully!")
    except FileNotFoundError:
        # Fallback to python -m PyInstaller
        try:
            subprocess.run([sys.executable, "-m", "PyInstaller", "docbot.spec"], check=True)
            print("Build completed successfully!")
        except Exception as e:
            print(f"Build failed: {e}")
            sys.exit(1)
    except subprocess.CalledProcessError as e:
        print(f"Build failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
