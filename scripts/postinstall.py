import os
import sys
import subprocess
import logging
from pathlib import Path

logging.basicConfig(format='[%(levelname)s] %(asctime)s %(message)s', level=logging.INFO)
logger = logging.getLogger()

OS = sys.platform.lower()

def install_zstd():
    logger.info("Installing libzstd...")
    if(OS == "darwin"):
        if(os.path.exists("/usr/local/opt/zstd/lib/libzstd.dylib") is False):
            try:
                cmd = f'/bin/bash scripts/install_zstd_mac.sh'
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    check=True,
                    universal_newlines=True, 
                    shell=True
                )
                print(result)
            except Exception as e:
                logger.error(e)

def is_library_present(library_name):
    library_name = library_name.replace('.so', '').replace('.dll', '').replace('.dylib', '')
    
    try:
        if OS == "linux":
            result = subprocess.run(["ldconfig", "-p"], capture_output=True, text=True)
            return library_name in result.stdout
        elif OS == "windows":
            # Check if library is in PATH
            result = subprocess.run(["where", f"{library_name}.dll"], capture_output=True, text=True)
            return result.returncode == 0
        elif OS == "darwin":  # macOS
            # Check in common library paths
            result = subprocess.run(["find", "-L", "/usr/local/opt", "-name", f"lib{library_name}.dylib"], capture_output=True, text=True)
            print(result.stdout)
            return bool(result.stdout.strip())
        else:
            return False
    except Exception:
        return False

library_name = "zstd" 
if is_library_present(library_name):
    logger.info(f"Library {library_name} is installed and accessible.")
else:
    logger.info(f"Library {library_name} is not found or cannot be loaded.")
    install_zstd()
