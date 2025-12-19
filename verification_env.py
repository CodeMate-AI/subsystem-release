#!/usr/bin/env python3
"""
CodeMate Environment Verification Script
Python equivalent of verification_env.ps1

Enhanced with:
- Removed hardcoded Python installation paths and commands
- Configurable server variables via environment variables
- Integration with updater middleware server for fetching requirements.txt
- Version reading from version.txt in .codemate folder
"""

import os
import sys
import subprocess
import platform
import requests
import socket
import shutil
from pathlib import Path
from typing import List, Tuple, Optional

# Setup tracker import for progress tracking
try:
    import setup_tracker
except ImportError:
    # Fallback when setup_tracker is not available (backward compatibility)
    setup_tracker = None

# Configuration - Server variables that can be modified later via environment variables
class Config:
    # Server configuration - easily configurable
    SERVER_HOST = os.getenv('UPDATER_SERVER_HOST', 'localhost')
    SERVER_PORT = int(os.getenv('UPDATER_SERVER_PORT', '8000'))
    SERVER_BASE_URL = f"http://{SERVER_HOST}:{SERVER_PORT}"
    
    # Environment paths (fully configurable)
    CODEMATE_BASE_DIR = Path.home() / ".codemate"
    BIN_DIR = CODEMATE_BASE_DIR / "bin"
    ENVIRONMENT_DIR = BIN_DIR / "environment"
    MICROMAMBA_PATH = BIN_DIR / ("micromamba.exe" if platform.system() == "Windows" else "micromamba")

    # Version management
    DEFAULT_VERSION = os.getenv('DEFAULT_VERSION', '1.0.0')
    REQUIREMENTS_PATH = BIN_DIR / "requirements.txt"
    REQ_DOWNLOAD_PATH = BIN_DIR / "req_downloads.txt"
    VERSION_FILE_PATH = CODEMATE_BASE_DIR / "meta" / "version.txt"
    
    # Port configuration
    HTTP_SERVER_PORT = int(os.getenv('HTTP_SERVER_PORT', '45223'))
    WEBSOCKET_SERVER_PORT = int(os.getenv('WEBSOCKET_SERVER_PORT', '45224'))
    QDRANT_PORT = int(os.getenv('QDRANT_PORT', '45225'))
    OLLAMA_PORT = int(os.getenv('OLLAMA_PORT', '11434'))

# Global state tracking
class State:
    def __init__(self):
        self.issues_found: List[str] = []
        self.issues_fixed: List[str] = []
        self.critical_errors: List[str] = []

# Color codes for terminal output
class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    CYAN = '\033[96m'
    WHITE = '\033[97m'
    RESET = '\033[0m'

def write_status(message: str, message_type: str = "Info") -> None:
    """Print formatted status message with color coding"""
    color_map = {
        "Success": Colors.GREEN,
        "Error": Colors.RED,
        "Warning": Colors.YELLOW,
        "Info": Colors.CYAN
    }
    
    prefix_map = {
        "Success": "[OK]",
        "Error": "[FAIL]",
        "Warning": "[WARN]",
        "Info": "[INFO]"
    }
    
    color = color_map.get(message_type, Colors.WHITE)
    prefix = prefix_map.get(message_type, "[-]")
    
    print(f"{color}{prefix} {message}{Colors.RESET}")

def get_version_from_file() -> str:
    """Read version from version.txt in .codemate folder"""
    try:
        if Config.VERSION_FILE_PATH.exists():
            version = Config.VERSION_FILE_PATH.read_text().strip()
            if version:
                write_status(f"Read version from file: {version}", "Info")
                return version
    except Exception as e:
        write_status(f"Could not read version.txt: {e}", "Warning")
    
    # Fallback to default
    write_status(f"Using default version: {Config.DEFAULT_VERSION}", "Info")
    return Config.DEFAULT_VERSION

def fetch_requirements_from_server(version: str = None) -> Optional[str]:
    """Fetch requirements.txt content from the updater middleware server
    
    Securely fetches the requirements.txt file using the endpoint:
    @app.get("/download/{version}/{path:path}")
    """
    if version is None:
        version = get_version_from_file()
    
    try:
        url = f"{Config.SERVER_BASE_URL}/download/{version}/requirements.txt"
        write_status(f"Fetching requirements from server: {url}", "Info")
        
        response = requests.get(url, timeout=30)
        if response.status_code == 200:
            write_status(f"Successfully fetched requirements.txt from server (version {version})", "Success")
            return response.text
        else:
            write_status(f"Server returned status {response.status_code} for requirements.txt", "Warning")
    except Exception as e:
        write_status(f"Failed to fetch requirements from server: {e}", "Warning")
    return None

def test_internet_connection(state: State) -> bool:
    """Test internet connectivity"""
    if setup_tracker:
        setup_tracker.update_phase_progress("environment_verification", "Checking network connectivity", True, 10)
    
    write_status("Checking internet connectivity...", "Info")
    try:
        response = requests.get("https://www.google.com", timeout=5)
        if response.status_code == 200:
            write_status("Internet connection: OK", "Success")
            return True
    except Exception:
        write_status("Internet connection: FAILED", "Warning")
        state.issues_found.append("No internet connection")
        return False

def test_port_available(port: int, service_name: str) -> bool:
    """Test if a port is available"""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(1)
            result = sock.connect_ex(('localhost', port))
            if result == 0:
                write_status(f"{service_name} (port {port}): Already running", "Success")
                return True
            else:
                write_status(f"{service_name} (port {port}): Not running (will start with initiate.py)", "Info")
                return True
    except Exception:
        write_status(f"{service_name} (port {port}): Port check OK", "Success")
        return True

import platform

def get_micromamba_url() -> str:
    """Get appropriate micromamba download URL based on platform."""
    base_url = "https://github.com/mamba-org/micromamba-releases/releases/download/2.3.2-0"
    system = platform.system()
    machine = platform.machine().lower()

    print(f"[DEBUG] Detected system: {system}")
    print(f"[DEBUG] Detected machine: {machine}")

    if system == "Windows":
        url = f"{base_url}/micromamba-win-64.exe"
        print(f"[DEBUG] Using URL: {url}")
        return url

    elif system == "Darwin":  # macOS
        if "arm" in machine or "aarch64" in machine:
            url = f"{base_url}/micromamba-osx-arm64"
        else:
            url = f"{base_url}/micromamba-osx-64"
        print(f"[DEBUG] Using URL: {url}")
        return url

    else:  # Linux
        if "arm" in machine or "aarch64" in machine:
            url = f"{base_url}/micromamba-linux-aarch64"
        else:
            url = f"{base_url}/micromamba-linux-64"
        print(f"[DEBUG] Using URL: {url}")
        return url



def test_micromamba_installation(state: State) -> bool:
    """Check for micromamba installation and download if missing"""
    if setup_tracker:
        setup_tracker.update_phase_progress("environment_verification", "Checking package manager installation", True, 15)
    
    write_status("Checking micromamba installation...", "Info")
    
    if Config.MICROMAMBA_PATH.exists():
        write_status("Micromamba: Found", "Success")
        return True
    else:
        write_status("Micromamba: NOT FOUND", "Error")
        state.issues_found.append("Micromamba not installed")
        
        write_status("Downloading micromamba...", "Info")
        try:
            # Create directory
            Config.CODEMATE_BASE_DIR.mkdir(parents=True, exist_ok=True)
            
            # Download micromamba
            url = get_micromamba_url()
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            
            with open(Config.MICROMAMBA_PATH, 'wb') as f:
                f.write(response.content)
            
            # Make executable on Unix systems
            if platform.system() != "Windows":
                Config.MICROMAMBA_PATH.chmod(0o755)
            
            write_status("Micromamba downloaded successfully", "Success")
            state.issues_fixed.append("Downloaded micromamba")
            return True
        except Exception as e:
            write_status(f"Failed to download micromamba: {e}", "Error")
            state.critical_errors.append("Micromamba download failed")
            return False

def get_python_path() -> Optional[Path]:
    """Get Python executable path using Config variables"""
    try:
        if platform.system() == "Windows":
            python_path = Config.ENVIRONMENT_DIR / "python.exe"
        else:
            python_path = Config.ENVIRONMENT_DIR / "bin" / "python"
        
        return python_path if python_path.exists() else None
    except Exception:
        return None

def test_python_environment(state: State) -> bool:
    """Check Python environment"""
    if setup_tracker:
        setup_tracker.update_phase_progress("environment_verification", "Validating Python runtime environment", True, 25)
    
    write_status("Checking Python environment...", "Info")
    
    python_path = get_python_path()
    
    if python_path:
        try:
            result = subprocess.run([str(python_path), "--version"], capture_output=True, text=True, timeout=5)
            version = result.stdout.strip()
            write_status(f"Python environment: Found ({version})", "Success")
            return True
        except Exception:
            write_status("Python environment: Corrupted", "Error")
            state.issues_found.append("Python environment corrupted")
            write_status("Recreating Python environment...", "Info")
            return create_python_environment(state)
    else:
        write_status("Python environment: NOT FOUND", "Error")
        state.issues_found.append("Python environment not created")
        write_status("Creating Python environment...", "Info")
        return create_python_environment(state)

def create_python_environment(state: State) -> bool:
    """Create new Python environment"""
    if not Config.MICROMAMBA_PATH.exists():
        write_status("Cannot create environment: micromamba not found", "Error")
        state.critical_errors.append("Micromamba not available for environment creation")
        return False
    
    try:
        # Remove corrupted environment if it exists
        if Config.ENVIRONMENT_DIR.exists():
            shutil.rmtree(Config.ENVIRONMENT_DIR, ignore_errors=True)
        
        write_status("Creating Python 3.11 environment...", "Info")
        
        cmd = [str(Config.MICROMAMBA_PATH), "create", "--prefix", str(Config.ENVIRONMENT_DIR), "python=3.11", "-y"]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        
        # Check if Python was created successfully
        python_exe = get_python_path()
        
        if python_exe and python_exe.exists():
            write_status("Python environment created successfully", "Success")
            state.issues_fixed.append("Created Python environment")
            return True
        else:
            write_status("Failed to create Python environment", "Error")
            state.critical_errors.append("Python environment creation failed")
            return False
    except Exception as e:
        write_status(f"Error creating Python environment: {e}", "Error")
        state.critical_errors.append(f"Python environment creation error: {e}")
        return False

def test_python_packages(state: State) -> bool:
    """Check and install Python packages from local req_downloads.txt file"""
    if setup_tracker:
        setup_tracker.update_phase_progress("environment_verification", "Installing required application packages (takes some time)", True, 35)

    write_status("Checking Python packages...", "Info")

    python_path = get_python_path()

    if not python_path:
        write_status("Cannot check packages: Python not found", "Error")
        return False

    # Read requirements from local file
    if Config.REQ_DOWNLOAD_PATH.exists():
        try:
            requirements_content = Config.REQ_DOWNLOAD_PATH.read_text()
            # Save the requirements content for reference
            Config.REQUIREMENTS_PATH.write_text(requirements_content)
            write_status(f"Requirements file prepared for installation", "Info")

            # Upgrade pip first
            subprocess.run([str(python_path), "-m", "pip", "install", "--upgrade", "pip"],
                         check=True, capture_output=True)

            # Install requirements
            subprocess.run([str(python_path), "-m", "pip", "install", "-r", str(Config.REQUIREMENTS_PATH)],
                         check=True, capture_output=True)

            write_status("Packages installed successfully", "Success")
            state.issues_fixed.append("Installed packages from local file")
            return True
        except Exception as e:
            write_status(f"Failed to install packages: {e}", "Error")
            state.critical_errors.append(f"Package installation failed: {e}")
            return False
    else:
        write_status("Could not find req_downloads.txt file", "Error")
        write_status("Please ensure req_downloads.txt exists in .codemate directory", "Error")
        state.critical_errors.append("Unable to find req_downloads.txt file")
        return False

def test_required_files(state: State) -> bool:
    """Check for required application files"""
    if setup_tracker:
        setup_tracker.update_phase_progress("environment_verification", "Verifying application files", True, 45)

    write_status("Checking required files...", "Info")

    required_files = [
        Config.BIN_DIR / "initiate.py",
        # Config.BIN_DIR / "http_server.py",
        # Config.BIN_DIR / "websocket_server.py",
        # Config.BIN_DIR / "ipc.py"
    ]
    
    all_files_exist = True
    for file_path in required_files:
        if file_path.exists():
            write_status(f"  {file_path.name}: Found", "Success")
        else:
            write_status(f"  {file_path.name}: NOT FOUND", "Error")
            state.critical_errors.append(f"Required file missing: {file_path.name}")
            all_files_exist = False
    
    return all_files_exist

def test_qdrant_binary(state: State) -> bool:
    """Check for Qdrant binary"""
    if setup_tracker:
        setup_tracker.update_phase_progress("environment_verification", "Checking vector database components", True, 55)

    write_status("Checking Qdrant binary...", "Info")

    # Qdrant will be downloaded by initiate.py if not present
    possible_paths = [
        Config.BIN_DIR / ("qdrant.exe" if platform.system() == "Windows" else "qdrant"),
        Config.BIN_DIR / ("qdrant.exe" if platform.system() == "Windows" else "qdrant"),
        Config.BIN_DIR / "BASE" / "vdb" / ("qdrant.exe" if platform.system() == "Windows" else "qdrant")
    ]
    
    found = False
    for path in possible_paths:
        if path.exists():
            write_status(f"Qdrant binary: Found at {path}", "Success")
            found = True
            break
    
    if not found:
        write_status("Qdrant binary: Not found (will be downloaded by initiate.py)", "Info")
    
    return True  # Not critical since initiate.py handles this

def test_system_requirements(state: State) -> bool:
    """Check system requirements"""
    if setup_tracker:
        setup_tracker.update_phase_progress("environment_verification", "Analyzing system requirements", True, 65)
    
    write_status("Checking system requirements...", "Info")
    
    # Check disk space
    free_space_gb = shutil.disk_usage('.').free / (1024**3)
    
    if free_space_gb < 5:
        write_status(f"Disk space: LOW ({free_space_gb:.2f} GB free)", "Warning")
        state.issues_found.append(f"Low disk space: {free_space_gb:.2f} GB")
    else:
        write_status(f"Disk space: OK ({free_space_gb:.2f} GB free)", "Success")
    
    # Check memory (cross-platform approach)
    try:
        if platform.system() == "Windows":
            import ctypes
            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("sAvailVirtual", ctypes.c_ulonglong),
                    ("sAvailExtendedVirtual", ctypes.c_ulonglong),
                ]
            
            memory_status = MEMORYSTATUSEX()
            memory_status.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(memory_status))
            
            free_ram_gb = memory_status.ullAvailPhys / (1024**3)
        else:
            # Linux/Mac: read from /proc/meminfo or use psutil if available
            try:
                import psutil
                free_ram_gb = psutil.virtual_memory().available / (1024**3)
            except ImportError:
                # Fallback: estimate based on total memory
                with open('/proc/meminfo', 'r') as f:
                    for line in f:
                        if 'MemAvailable:' in line:
                            free_ram_kb = int(line.split()[1])
                            free_ram_gb = free_ram_kb / (1024**2)
                            break
                        elif 'MemFree:' in line:
                            free_ram_kb = int(line.split()[1])
                            free_ram_gb = free_ram_kb / (1024**2)
                            break
                    else:
                        free_ram_gb = 4.0  # Conservative estimate
        
        if free_ram_gb < 2:
            write_status(f"Available RAM: LOW ({free_ram_gb:.2f} GB free)", "Warning")
            state.issues_found.append("Low available RAM")
        else:
            write_status(f"Available RAM: OK ({free_ram_gb:.2f} GB free)", "Success")
    except Exception:
        write_status("Available RAM: Check unavailable", "Warning")
        state.issues_found.append("Unable to check available RAM")
    
    return True

def show_summary(state: State) -> bool:
    """Display verification summary"""
    print("")
    print("=" * 40)
    print(f"{Colors.CYAN}         VERIFICATION SUMMARY{Colors.RESET}")
    print("=" * 40)
    print("")
    
    if state.issues_fixed:
        print(f"{Colors.GREEN}Issues Fixed ({len(state.issues_fixed)}):{Colors.RESET}")
        for fix in state.issues_fixed:
            print(f"  [OK] {fix}")
        print("")
    
    if state.issues_found:
        print(f"{Colors.YELLOW}Issues Found ({len(state.issues_found)}):{Colors.RESET}")
        for issue in state.issues_found:
            print(f"  ! {issue}")
        print("")
    
    if state.critical_errors:
        print(f"{Colors.RED}Critical Errors ({len(state.critical_errors)}):{Colors.RESET}")
        for error in state.critical_errors:
            print(f"  [FAIL] {error}")
        print("")
        print(f"{Colors.RED}RESULT: VERIFICATION FAILED{Colors.RESET}")
        print(f"{Colors.RED}Please run install_env.ps1 again or fix the errors above.{Colors.RESET}")
        print("")
        return False
    else:
        print(f"{Colors.GREEN}RESULT: ALL CHECKS PASSED [OK]{Colors.RESET}")
        print("")
        print(f"{Colors.GREEN}Your environment is ready to run initiate.py!{Colors.RESET}")
        print("")
        print(f"{Colors.CYAN}Next steps:{Colors.RESET}")
        print(f"  1. Run: python initiate.py{Colors.WHITE}")
        
        python_path = get_python_path()
        if python_path:
            print(f"  2. Or use the correct Python: {python_path} initiate.py{Colors.WHITE}")
        print("")
        
        # Show configuration information
        print(f"{Colors.CYAN}Configuration:{Colors.RESET}")
        print(f"  Server: {Config.SERVER_BASE_URL}{Colors.WHITE}")
        print(f"  Version: {get_version_from_file()}{Colors.WHITE}")
        print("")

        # initiate.py will be started by setup_orchestrator.py when overall_status is completed

        return True

def main():
    """Main execution function"""
    # Initialize progress tracking for environment verification
    # Reset phase FIRST, before any updates
    if setup_tracker:
        current_state = setup_tracker.get_tracker().load_setup_state()
        if "environment_verification" in current_state["phases"]:
            current_state["phases"]["environment_verification"]["progress"] = 0
            current_state["phases"]["environment_verification"]["status"] = "pending"
            current_state["phases"]["environment_verification"]["current_step"] = "Initializing environment verification"
            current_state["phases"]["environment_verification"]["steps_completed"] = []
            setup_tracker.get_tracker()._safe_atomic_write(current_state)

    
    print("")
    print("=" * 40)
    print(f"{Colors.CYAN}  CodeMate Environment Verification{Colors.RESET}")
    print("=" * 40)
    print("")
    
    state = State()
    
    # Run all checks
    internet_ok = test_internet_connection(state)
    micromamba_ok = test_micromamba_installation(state)
    python_ok = test_python_environment(state)
    
    # Only check packages if Python is available
    packages_ok = test_python_packages(state) if python_ok else False
    
    files_ok = test_required_files(state)
    qdrant_ok = test_qdrant_binary(state)
    system_ok = test_system_requirements(state)
    
    # Check required ports
    if setup_tracker:
        setup_tracker.update_phase_progress("environment_verification", "Verifying service ports", True, 75)
    
    write_status("Checking required ports...", "Info")
    test_port_available(Config.HTTP_SERVER_PORT, "HTTP Server")
    test_port_available(Config.WEBSOCKET_SERVER_PORT, "WebSocket Server") 
    test_port_available(Config.QDRANT_PORT, "Qdrant")
    test_port_available(Config.OLLAMA_PORT, "Ollama")
    
    # Final progress update
    if setup_tracker:
        setup_tracker.update_phase_progress("environment_verification", "Environment verification completed", True, 100)
    
    # Show summary
    success = show_summary(state)
    
    return 0 if success else 1

if __name__ == "__main__":
    sys.exit(main())