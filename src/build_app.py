import subprocess
import shutil
import sys
from pathlib import Path

def main():
    if sys.platform == 'win32':
        try:
            sys.stdout.reconfigure(encoding='utf-8')
            sys.stderr.reconfigure(encoding='utf-8')
        except Exception:
            pass

    print("[+] Đang dọn dẹp các thư mục build cũ...")
    for folder in ["build", "dist"]:
        path = Path(folder)
        if path.exists():
            shutil.rmtree(path)
            
    print("[+] Đang chạy PyInstaller để đóng gói ứng dụng...")
    cmd = [
        "pyinstaller",
        "--noconfirm",
        "--onedir",
        "--console",
        "--name", "Sky-Player",
        "--paths", "./src",
        "src/main.py"
    ]
    subprocess.run(cmd, check=True)
    
    print("[+] Đang sao chép thư mục bài hát (songs) và tài liệu hướng dẫn...")
    dist_dir = Path("dist/Sky-Player")
    
    songs_dir = Path("songs")
    if songs_dir.exists():
        shutil.copytree(songs_dir, dist_dir / "songs", dirs_exist_ok=True)
        
    readme_file = Path("README.md")
    if readme_file.exists():
        shutil.copy2(readme_file, dist_dir / "README.md")
        
    print("\n===================================================")
    print("[v] THÀNH CÔNG: Đã đóng gói xong ứng dụng!")
    print(f"Thư mục ứng dụng hoàn chỉnh nằm tại:\n  {dist_dir.resolve()}")
    print("===================================================\n")

if __name__ == "__main__":
    main()
