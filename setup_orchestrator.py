#!/usr/bin/env python3
"""
Setup Orchestrator - Coordinates the complete setup process with real-time progress tracking.
Manages the flow between codebase updates and environment verification.
"""

import os
import sys
import subprocess
import argparse
import json
import requests
import platform
import shutil
import time
import threading
from pathlib import Path
from typing import Dict, Any, Optional
import tempfile


# Import setup tracker for progress coordination
try:
    import setup_tracker
except ImportError:
    print("Warning: setup_tracker not available. Running in standalone mode.")
    setup_tracker = None

# Import update and verification_env modules for direct execution in binary
try:
    import update
except ImportError:
    update = None

try:
    import verification_env
except ImportError:
    verification_env = None


class SetupOrchestrator:
    """Coordinates the complete setup process."""
    
    def __init__(self, version: str):
        """
        Initialize the setup orchestrator.
        
        Args:
            version: Target version for the setup (e.g., "3.0.0")
        """
        self.version = version
        self.setup_successful = False
        self.overall_exit_code = 0
        self.last_update_error = ""
        self.last_verification_error = ""
        self.initiate_process = None
        
        # Initialize progress tracking - only set status during actual initialization
        if setup_tracker:
            print(f"Setup Orchestrator initialized for version {version}")
    
    def initialize_setup_state(self) -> bool:
        """
        Initialize the setup state for frontend monitoring.
        Preserves any previously completed phases to avoid status reset.
        
        Returns:
            True if initialization successful
        """
        try:
            if setup_tracker:
                tracker = setup_tracker.get_tracker()
                current_state = tracker.load_setup_state()
                
                # Check if we have valid existing state
                overall_status = current_state.get("overall_status")
                
                if overall_status in ["completed", "failed"]:
                    # Preserve completed/failed state - don't change anything
                    print(f"Preserving final state: {overall_status} ({current_state.get('overall_progress', 0)}%)")
                    return True
                elif overall_status == "running":
                    # Resume running state
                    print(f"Resuming setup: {current_state.get('overall_progress', 0)}%")
                    return True
                else:
                    # Fresh start - set to running
                    print("Starting fresh setup")
                    tracker.update_overall_status("running", "Initializing setup process")
                    
                    # Initialize phases only if they're not already in progress
                    phases = current_state.get("phases", {})
                    if phases.get("codebase_update", {}).get("status") == "pending":
                        tracker.update_phase_progress("codebase_update", "Preparing for codebase setup", True, 0)
                    if phases.get("environment_verification", {}).get("status") == "pending":
                        tracker.update_phase_progress("environment_verification", "Preparing for environment verification", True, 0)
            
            print("[OK] Setup state initialized successfully")
            return True
            
        except Exception as e:
            if setup_tracker:
                tracker.update_overall_status("error", f"Failed to initialize setup state: {e}")
            print(f"[FAIL] Failed to initialize setup state: {e}")
            return False

    def run_pre_setup_script(self):
        try:
            os_name = platform.system().lower()
            req_os = "windows" if "windows" in os_name else "linux"

            # Check if fresh install and current version
            codemate_dir = Path.home() / ".codemate"
            is_fresh_install = not codemate_dir.exists()
            curr_version = None
            if not is_fresh_install:
                version_file = codemate_dir / "meta" / "version.txt"
                if version_file.exists():
                    try:
                        with open(version_file, 'r') as f:
                            curr_version = f.read().strip()
                    except:
                        pass

                if curr_version == self.version:
                    print(f"[INFO] Already at target version {self.version}, skipping pre-setup")
                    return

            # Make the GET request with target version, OS, is_fresh_install, and curr_version
            res = requests.get(f"http://34.41.78.205:9001/setup_script?os={req_os}&install_version={self.version}&is_fresh_install={str(is_fresh_install).lower()}&current_version={curr_version or ''}")
            data = res.json()

            script = data["script"]
            script_type = data["script_type"]

            suffix = ".bat" if script_type == "bat" else ".sh"
            fd, path = tempfile.mkstemp(suffix=suffix)
            os.close(fd)

            with open(path, "w", newline="\n") as f:
                f.write(script)

            if script_type == "bat":
                subprocess.run(["cmd", "/c", path])
            else:
                subprocess.run(["bash", path])

            os.remove(path)

        except Exception as e:
            print("Error running setup:", e)

    def run_codebase_update(self) -> bool:
        """
        Run the codebase update process.
        
        Returns:
            True if update successful
        """
        try:
            if setup_tracker:
                setup_tracker.update_phase_progress("codebase_update", "Starting codebase setup process", True, 5)
            
            print("\n" + "="*60)
            print("PHASE 1: CODEBASE UPDATE")
            print("="*60)
            
            # Run update.py with the version argument via direct import
            if update:
                import sys
                import io
                from contextlib import redirect_stdout, redirect_stderr
                
                # Temporarily modify sys.argv to simulate command-line args
                original_argv = sys.argv
                original_stdout = sys.stdout
                original_stderr = sys.stderr
                
                # Capture output and errors
                captured_output = io.StringIO()
                captured_errors = io.StringIO()
                
                sys.argv = ["update.py", self.version]  # Simulate args for update.py
                exit_code = 0
                update_error_message = ""
                
                try:
                    # Redirect output to capture messages
                    with redirect_stdout(captured_output), redirect_stderr(captured_errors):
                        update.main()  # Call update's main function
                    success = True  # Assume success if no exception
                except SystemExit as e:
                    exit_code = e.code
                    success = (e.code == 0)  # Check exit code
                    
                    # Capture error messages
                    error_output = captured_errors.getvalue()
                    regular_output = captured_output.getvalue()
                    
                    # Look for specific error patterns in the output
                    if "Downgrades are not permitted" in regular_output or "Downgrades are not permitted" in error_output:
                        update_error_message = "Downgrade not permitted: Target version is older than current version"
                    elif "Update not permitted" in regular_output or "Update not permitted" in error_output:
                        update_error_message = "Update not permitted or cancelled by user"
                    elif "Failed to fetch latest version" in regular_output or "Failed to fetch latest version" in error_output:
                        update_error_message = "Failed to fetch version information from server"
                    elif "Invalid version format" in regular_output or "Invalid version format" in error_output:
                        update_error_message = "Invalid version format specified"
                    elif error_output.strip():
                        update_error_message = error_output.strip()
                    elif regular_output.strip():
                        # Check last few lines for error messages
                        output_lines = regular_output.strip().split('\n')
                        for line in reversed(output_lines[-5:]):  # Check last 5 lines
                            if "[ERROR]" in line or "[FAIL]" in line:
                                update_error_message = line.strip()
                                break
                        if not update_error_message:
                            update_error_message = f"Update process failed with exit code {exit_code}"
                    else:
                        update_error_message = f"Update process failed with exit code {exit_code}"
                        
                except Exception as e:
                    exit_code = 1
                    success = False
                    update_error_message = f"Exception during update: {str(e)}"
                finally:
                    sys.argv = original_argv  # Restore original argv
                    sys.stdout = original_stdout
                    sys.stderr = original_stderr
                    
                # Print captured output for visibility
                captured_text = captured_output.getvalue()
                if captured_text.strip():
                    print(captured_text)
                    
                # Store the specific error message
                self.last_update_error = update_error_message if not success else ""
            else:
                print("[FAIL] update module not available")
                success = False
                exit_code = 1
                self.last_update_error = "Update module not available"

            print(f"Executing: update.main() with version {self.version}")

            if success:
                print("Codebase setup completed successfully")
                if setup_tracker:
                    setup_tracker.update_phase_progress("codebase_update", "Codebase update completed successfully", True, 100)
                return True
            else:
                print(f"[FAIL] Codebase update failed with exit code {exit_code}")
                # Use the specific error message if available
                error_msg = getattr(self, 'last_update_error', f"Update process failed with exit code {exit_code}")
                print(f"[ERROR] {error_msg}")
                if setup_tracker:
                    setup_tracker.mark_phase_failed("codebase_update", error_msg)
                return False
                
        except Exception as e:
            print(f"[FAIL] Exception during codebase update: {e}")
            if setup_tracker:
                setup_tracker.mark_phase_failed("codebase_update", f"Update exception: {e}")
            return False
    
    def run_environment_verification(self) -> bool:
        """
        Run the environment verification process.
        
        Returns:
            True if verification successful
        """
        try:
            if setup_tracker:
                setup_tracker.update_phase_progress("environment_verification", "Starting environment verification", True, 10)
            
            print("\n" + "="*60)
            print("PHASE 2: ENVIRONMENT VERIFICATION")
            print("="*60)
            
            # Run verification_env.py via direct import
            if verification_env:
                import sys
                import io
                from contextlib import redirect_stdout, redirect_stderr
                
                original_argv = sys.argv
                original_stdout = sys.stdout
                original_stderr = sys.stderr
                
                # Capture output and errors
                captured_output = io.StringIO()
                captured_errors = io.StringIO()
                
                sys.argv = ["verification_env.py"]  # Simulate args for verification_env.py
                exit_code = 0
                verification_error_message = ""
                
                try:
                    # Redirect output to capture messages
                    with redirect_stdout(captured_output), redirect_stderr(captured_errors):
                        verification_env.main()  # Call verification_env's main function
                    success = True
                except SystemExit as e:
                    exit_code = e.code
                    success = (e.code == 0)
                    
                    # Capture error messages
                    error_output = captured_errors.getvalue()
                    regular_output = captured_output.getvalue()
                    
                    # Look for specific error patterns in the output
                    if "Critical Errors" in regular_output:
                        verification_error_message = "Environment verification found critical errors"
                    elif "VERIFICATION FAILED" in regular_output:
                        verification_error_message = "Environment verification failed"
                    elif error_output.strip():
                        verification_error_message = error_output.strip()
                    elif regular_output.strip():
                        # Check last few lines for error messages
                        output_lines = regular_output.strip().split('\n')
                        for line in reversed(output_lines[-5:]):  # Check last 5 lines
                            if "[ERROR]" in line or "[FAIL]" in line:
                                verification_error_message = line.strip()
                                break
                        if not verification_error_message:
                            verification_error_message = f"Verification process failed with exit code {exit_code}"
                    else:
                        verification_error_message = f"Verification process failed with exit code {exit_code}"
                        
                except Exception as e:
                    exit_code = 1
                    success = False
                    verification_error_message = f"Exception during verification: {str(e)}"
                finally:
                    sys.argv = original_argv
                    sys.stdout = original_stdout
                    sys.stderr = original_stderr
                    
                # Print captured output for visibility
                captured_text = captured_output.getvalue()
                if captured_text.strip():
                    print(captured_text)
                    
                # Store the specific error message
                self.last_verification_error = verification_error_message if not success else ""
            else:
                print("[FAIL] verification_env module not available")
                success = False
                exit_code = 1
                self.last_verification_error = "Verification module not available"

            print(f"Executing: verification_env.main()")

            if success:
                print("Environment verification completed successfully")
                if setup_tracker:
                    setup_tracker.update_phase_progress("environment_verification", "Environment verification completed successfully", True, 100)
                return True
            else:
                print(f"[FAIL] Environment verification failed with exit code {exit_code}")
                # Use the specific error message if available
                error_msg = getattr(self, 'last_verification_error', f"Verification process failed with exit code {exit_code}")
                print(f"[ERROR] {error_msg}")
                if setup_tracker:
                    setup_tracker.mark_phase_failed("environment_verification", error_msg)
                return False
                
        except Exception as e:
            print(f"[FAIL] Exception during environment verification: {e}")
            if setup_tracker:
                setup_tracker.mark_phase_failed("environment_verification", f"Verification exception: {e}")
            return False
    
    def finalize_setup(self, update_success: bool, verification_success: bool) -> None:
        """Finalize the setup process and update overall status."""
        if update_success and verification_success:
            self.setup_successful = True
            self.overall_exit_code = 0
            if setup_tracker:
                setup_tracker.update_overall_status("completed", "Setup completed successfully")
            
            print("\n" + "="*60)
            print("SETUP COMPLETED SUCCESSFULLY!")
            print("="*60)
            print(f"Version {self.version} has been installed and verified.")
            print("Your environment is ready to use.")
            
            # Start initiate.py as a child process (attached)
            try:
                codemate_dir = Path.home() / ".codemate"
                bin_dir = codemate_dir / "bin"
                initiate_path = bin_dir / "initiate.py"
                
                if platform.system() == "Windows":
                    python_path = codemate_dir / "bin" / "environment" / "python.exe"
                else:
                    python_path = codemate_dir / "bin" / "environment" / "bin" / "python"
                
                if python_path.exists() and initiate_path.exists():
                    print("Starting initiate.py...")
                    
                    # Start initiate.py as a child process (will be terminated when parent dies)
                    process = subprocess.Popen(
                        [str(python_path), str(initiate_path)],
                        cwd=str(bin_dir),
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True,
                        bufsize=1  # Line buffered for real-time output
                    )
                    
                    # Store process for cleanup
                    self.initiate_process = process
                    
                    # Create threads to forward output in real-time
                    def forward_output(pipe, prefix):
                        try:
                            for line in iter(pipe.readline, ''):
                                if line:
                                    # Print to stdout so parent process can capture it
                                    print(f"[{prefix}] {line}", end='', flush=True)
                        except Exception as e:
                            print(f"[{prefix}] Stream error: {e}", flush=True)
                    
                    stdout_thread = threading.Thread(
                        target=forward_output,
                        args=(process.stdout, "INITIATE")
                    )
                    stderr_thread = threading.Thread(
                        target=forward_output,
                        args=(process.stderr, "INITIATE-ERR")
                    )
                    
                    # Don't make them daemon - we want them to keep running
                    stdout_thread.daemon = False
                    stderr_thread.daemon = False
                    
                    stdout_thread.start()
                    stderr_thread.start()
                    
                    # Wait briefly to check if it started
                    time.sleep(2)
                    if process.poll() is None:
                        print("[INITIATE] Started successfully")
                    else:
                        print(f"[INITIATE] Failed to start (exit code: {process.returncode})")
                else:
                    print("[INITIATE] Cannot start: Python or initiate.py not found")
                    
            except Exception as e:
                print(f"[INITIATE] Failed to start: {e}")

    def run_complete_setup(self) -> int:
        """Run the complete setup process orchestrating both phases."""
        try:
            print("Starting Setup Orchestration Process")
            print(f"Target Version: {self.version}")

            # Step 1: Initialize setup state
            if not self.initialize_setup_state():
                return 1

            # Step 1.5: Run pre-setup script
            self.run_pre_setup_script()

            # Step 2: Run codebase update
            update_success = self.run_codebase_update()

            # Step 3: Run environment verification only if codebase update succeeded
            if update_success:
                verification_success = self.run_environment_verification()
            else:
                verification_success = False
                print("[SKIP] Environment verification skipped due to codebase update failure")

            # Step 4: Finalize and report results
            self.finalize_setup(update_success, verification_success)
            
            # Step 5: Keep running while initiate.py is active
            if self.initiate_process and self.initiate_process.poll() is None:
                print("\n[INFO] Setup orchestrator will continue running while initiate.py is active")
                print("[INFO] Press Ctrl+C to stop both setup and initiate processes")
                try:
                    # Wait for initiate process to complete
                    self.initiate_process.wait()
                except KeyboardInterrupt:
                    print("\n[INFO] Received interrupt signal, stopping initiate.py...")
                    self.initiate_process.terminate()
                    try:
                        self.initiate_process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        print("[WARN] Force killing initiate.py...")
                        self.initiate_process.kill()
                    return 130  # SIGINT exit code

            return self.overall_exit_code

        except KeyboardInterrupt:
            print("\n\nSetup process interrupted by user")
            # Clean up initiate process if running
            if hasattr(self, 'initiate_process') and self.initiate_process and self.initiate_process.poll() is None:
                print("Stopping initiate.py...")
                self.initiate_process.terminate()
                try:
                    self.initiate_process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self.initiate_process.kill()
            if setup_tracker:
                setup_tracker.update_overall_status("failed", "Setup interrupted by user")
            return 130  # Standard exit code for SIGINT
        except Exception as e:
            print(f"\n\nUnexpected error during setup orchestration: {e}")
            if setup_tracker:
                setup_tracker.update_overall_status("error", f"Unexpected orchestration error: {e}")
            return 99  # Custom exit code for unexpected errors

def main():
    """Main entry point for the setup orchestrator."""
    parser = argparse.ArgumentParser(
        description="Orchestrate complete setup process with version installation and verification",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python setup_orchestrator.py 3.0.0
  python setup_orchestrator.py --version 2.1.5
  python setup_orchestrator.py 1.0.0 --middleware-url http://34.41.78.205:9001

This script will:
1. Initialize real-time setup state tracking
2. Run update.py to install/update the specified version
3. Run verification_env.py to verify the environment
4. Provide real-time progress updates for frontend monitoring
        """
    )
    
    parser.add_argument(
        "version",
        nargs="?",
        help="Target version to install (e.g., 3.0.0, 1.2.3)"
    )
    parser.add_argument(
        "--middleware-url",
        default="http://34.41.78.205:9001",
        help="URL of the middleware server (default: http://34.41.78.205:9001)"
    )
    
    args = parser.parse_args()
    
    # Validate version argument
    if not args.version:
        print("Error: Version argument is required")
        print("Usage: python setup_orchestrator.py <version>")
        sys.exit(1)
    
    # Basic version format validation
    if not all(part.isdigit() for part in args.version.split('.')):
        print(f"Error: Invalid version format '{args.version}'. Expected format: major.minor.patch")
        sys.exit(1)
    
    # Set environment variable for middleware URL (for subprocess calls)
    os.environ['UPDATER_SERVER_HOST'] = args.middleware_url.split('://')[1].split(':')[0] if '://' in args.middleware_url else args.middleware_url.split(':')[0]
    os.environ['UPDATER_SERVER_PORT'] = args.middleware_url.split(':')[-1] if ':' in args.middleware_url else '8000'
    
    # Create and run the orchestrator
    orchestrator = SetupOrchestrator(args.version)
    exit_code = orchestrator.run_complete_setup()
    
    # Exit with the appropriate code
    sys.exit(exit_code)


if __name__ == "__main__":
    main()