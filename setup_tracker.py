#!/usr/bin/env python3
"""
Setup State Tracker with atomic write support for real-time frontend monitoring.
Provides safe updating of setup_state.json with production-ready status messages.
"""

import json
import os
import sys
import tempfile
import time
import threading
import platform
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime
# import fcntl

IS_WINDOWS = platform.system() == 'Windows'
if IS_WINDOWS:
    import msvcrt
else:
    import fcntl


class SetupStateTracker:
    """Manages setup state with atomic writes and frontend-friendly progress tracking."""
    
    def __init__(self, state_file_path: Optional[str] = None):
        """
        Initialize the setup state tracker.
        
        Args:
            state_file_path: Optional custom path for setup_state.json
        """
        # Default path inside .codemate/meta directory
        if state_file_path is None:
            codemate_dir = Path.home() / ".codemate"
            meta_dir = codemate_dir / "meta"
            meta_dir.mkdir(parents=True, exist_ok=True)
            self.state_file_path = meta_dir / "setup_state.json"
        else:
            self.state_file_path = Path(state_file_path)
            
        self._lock_file_path = self.state_file_path.parent / f"{self.state_file_path.stem}.lock"
        self._lock_timeout = 5  # 5 second timeout for lock acquisition
        self._lock = threading.Lock()
        
        # Only initialize state if file doesn't exist
        if not self.state_file_path.exists():
            self._initialize_state()

    
    def _initialize_state(self) -> None:
        """Initialize the setup state structure."""
        initial_state = {
            "setup_id": f"setup_{int(time.time())}",
            "timestamp": datetime.now().isoformat(),
            "overall_status": "initializing",
            "overall_progress": 0,
            "phases": {
                "codebase_update": {
                    "status": "pending",
                    "progress": 0,
                    "current_step": "Initializing codebase update",
                    "steps_completed": [],
                    "steps_total": 10,
                    "start_time": None,
                    "end_time": None
                },
                "environment_verification": {
                    "status": "pending", 
                    "progress": 0,
                    "current_step": "Initializing environment verification",
                    "steps_completed": [],
                    "steps_total": 8,
                    "start_time": None,
                    "end_time": None
                }
            },
            "error_details": None,
            "metadata": {
                "version": "1.0",
                "platform": sys.platform,
                "python_version": sys.version.split()[0]
            }
        }
        
        self._safe_atomic_write(initial_state)
    
    def _acquire_lock(self, timeout: Optional[int] = None) -> bool:
        """Acquire file lock with timeout (cross-platform)."""
        if timeout is None:
            timeout = self._lock_timeout
            
        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                # Create lock file if it doesn't exist
                self._lock_file_path.parent.mkdir(parents=True, exist_ok=True)
                self._lock_file = open(self._lock_file_path, 'w')
                
                # Platform-specific locking
                if IS_WINDOWS:
                    # Windows locking using msvcrt
                    msvcrt.locking(self._lock_file.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    # Unix locking using fcntl
                    fcntl.flock(self._lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                return True
            except (IOError, OSError):
                # Lock not available, wait and retry
                time.sleep(0.1)
                continue
        
        return False

    
    def _release_lock(self) -> None:
        """Release file lock (cross-platform)."""
        try:
            if hasattr(self, '_lock_file') and self._lock_file:
                if IS_WINDOWS:
                    # Windows unlock
                    msvcrt.locking(self._lock_file.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    # Unix unlock
                    fcntl.flock(self._lock_file.fileno(), fcntl.LOCK_UN)
                self._lock_file.close()
                self._lock_file = None
        except Exception:
            pass  # Best effort cleanup

    
    def _safe_atomic_write(self, data: Dict[str, Any]) -> bool:
        """Write data atomically using temporary file + rename."""
        try:
            with self._lock:
                # Acquire file lock
                if not self._acquire_lock():
                    print(f"Warning: Could not acquire lock for {self.state_file_path}")
                    return False
                
                try:
                    # Create temporary file in same directory
                    temp_fd, temp_path = tempfile.mkstemp(
                        dir=self.state_file_path.parent,
                        prefix=f"{self.state_file_path.stem}.tmp.",
                        suffix=""
                    )
                    
                    try:
                        with os.fdopen(temp_fd, 'w') as temp_file:
                            json.dump(data, temp_file, indent=2, ensure_ascii=False)
                        
                        # Atomic rename (requires same filesystem)
                        os.replace(temp_path, self.state_file_path)
                        return True
                        
                    finally:
                        # Clean up temp file if rename failed
                        if os.path.exists(temp_path):
                            os.unlink(temp_path)
                            
                finally:
                    self._release_lock()
                    
        except Exception as e:
            print(f"Error writing setup state: {e}")
            return False
        
        return False
    
    def load_setup_state(self) -> Dict[str, Any]:
        """Load the current setup state."""
        try:
            if self.state_file_path.exists():
                with self._lock:
                    if not self._acquire_lock():
                        return self._get_default_state()
                    
                    try:
                        with open(self.state_file_path, 'r') as f:
                            return json.load(f)
                    finally:
                        self._release_lock()
        except Exception as e:
            print(f"Error loading setup state: {e}")
            
        return self._get_default_state()
    
    def _get_default_state(self) -> Dict[str, Any]:
        """Return default state structure."""
        return {
            "setup_id": f"setup_{int(time.time())}",
            "timestamp": datetime.now().isoformat(),
            "overall_status": "error",
            "overall_progress": 0,
            "phases": {
                "codebase_update": {
                    "status": "error",
                    "progress": 0,
                    "current_step": "Error occurred",
                    "steps_completed": [],
                    "steps_total": 10,
                    "start_time": None,
                    "end_time": None
                },
                "environment_verification": {
                    "status": "error",
                    "progress": 0,
                    "current_step": "Error occurred", 
                    "steps_completed": [],
                    "steps_total": 8,
                    "start_time": None,
                    "end_time": None
                }
            },
            "error_details": "Failed to load setup state",
            "metadata": {
                "version": "1.0",
                "platform": sys.platform,
                "python_version": sys.version.split()[0]
            }
        }
    
    def update_phase_progress(self, phase: str, step_description: str,
                             step_completed: bool = True,
                             additional_progress: int = 0) -> bool:
        """
        Update progress for a specific phase with production-ready status messages.
        Uses cumulative progress calculation for true overall progress tracking.
        
        Args:
            phase: Phase name ('codebase_update' or 'environment_verification')
            step_description: High-level step description (no technical details)
            step_completed: Whether this step is completed
            additional_progress: Additional progress percentage to add (0-100 scale per phase)
            
        Returns:
            True if update was successful
        """
        state = self.load_setup_state()
        
        if phase not in state["phases"]:
            print(f"Warning: Unknown phase '{phase}'")
            return False
        
        phase_data = state["phases"][phase]
        
        # Update current step and progress
        phase_data["current_step"] = step_description
        
        if step_completed:
            if step_description not in phase_data["steps_completed"]:
                phase_data["steps_completed"].append(step_description)
        
        # Calculate dynamic progress for this phase
        current_progress = phase_data["progress"]
        # max_progress = min(100, current_progress + additional_progress)
        max_progress = min(100, additional_progress)
        phase_data["progress"] = max_progress
        
        # Update overall progress using cumulative calculation
        self._update_cumulative_overall_progress(state)
        
        # Update status based on progress
        if phase_data["progress"] >= 100:
            phase_data["status"] = "completed"
            phase_data["end_time"] = datetime.now().isoformat()
            if not phase_data["start_time"]:
                phase_data["start_time"] = datetime.now().isoformat()
        elif phase_data["progress"] > 0 and not phase_data["start_time"]:
            phase_data["start_time"] = datetime.now().isoformat()
        
        return self._safe_atomic_write(state)
    
    def _update_cumulative_overall_progress(self, state: Dict[str, Any]) -> None:
        """
        Update overall progress using cumulative calculation.
        Each phase contributes to overall progress based on completion status.
        
        Args:
            state: Current state dictionary
        """
        total_phases = len(state["phases"])
        phase_contribution = 100 / total_phases  # Each phase contributes equally to 100%
        
        overall_progress = 0
        
        for phase_name, phase_data in state["phases"].items():
            if phase_data["status"] == "completed":
                # Phase is complete, contributes full amount
                overall_progress += phase_contribution
            elif phase_data["status"] == "failed":
                # Phase failed, contributes 0%
                continue
            else:
                # Phase in progress, contributes proportionally to completion
                phase_progress = (phase_data["progress"] / 100) * phase_contribution
                overall_progress += phase_progress
        
        # Ensure overall progress is between 0 and 100
        state["overall_progress"] = max(0, min(100, int(overall_progress)))
    
    def update_overall_status(self, status: str, error_details: Optional[str] = None) -> bool:
        """
        Update overall setup status.
        
        Args:
            status: Overall status ('running', 'completed', 'failed', 'error')
            error_details: Optional error details for debugging
        """
        state = self.load_setup_state()
        state["overall_status"] = status
        state["timestamp"] = datetime.now().isoformat()
        
        if error_details:
            state["error_details"] = error_details
        
        return self._safe_atomic_write(state)
    
    def mark_phase_failed(self, phase: str, error_message: str) -> bool:
        """
        Mark a phase as failed with error details.
        
        Args:
            phase: Phase name to mark as failed
            error_message: Error description (user-friendly)
        """
        state = self.load_setup_state()
        
        if phase in state["phases"]:
            state["phases"][phase]["status"] = "failed"
            state["phases"][phase]["current_step"] = error_message
            state["phases"][phase]["end_time"] = datetime.now().isoformat()
            
            # Update overall status if this is a critical failure
            state["overall_status"] = "failed"
            state["error_details"] = f"{phase}: {error_message}"
        
        return self._safe_atomic_write(state)
    
    def get_setup_summary(self) -> Dict[str, Any]:
        """Get a summary of the current setup state for frontend display."""
        state = self.load_setup_state()
        
        return {
            "overall_status": state["overall_status"],
            "overall_progress": state["overall_progress"],
            "setup_id": state["setup_id"],
            "timestamp": state["timestamp"],
            "phases": {
                phase: {
                    "status": data["status"],
                    "progress": data["progress"],
                    "current_step": data["current_step"]
                }
                for phase, data in state["phases"].items()
            },
            "error_details": state.get("error_details")
        }


# Global tracker instance for easy import
_tracker = None

def get_tracker() -> SetupStateTracker:
    """Get the global setup state tracker instance."""
    global _tracker
    if _tracker is None:
        _tracker = SetupStateTracker()
    return _tracker


def update_phase_progress(phase: str, step_description: str, 
                         step_completed: bool = True, 
                         additional_progress: int = 0) -> bool:
    """
    Convenience function to update phase progress.
    
    Args:
        phase: Phase name ('codebase_update' or 'environment_verification')
        step_description: High-level step description
        step_completed: Whether this step is completed
        additional_progress: Additional progress percentage
        
    Returns:
        True if update was successful
    """
    return get_tracker().update_phase_progress(phase, step_description, step_completed, additional_progress)


def update_overall_status(status: str, error_details: Optional[str] = None) -> bool:
    """Convenience function to update overall status."""
    return get_tracker().update_overall_status(status, error_details)


def mark_phase_failed(phase: str, error_message: str) -> bool:
    """Convenience function to mark a phase as failed."""
    return get_tracker().mark_phase_failed(phase, error_message)


def get_setup_summary() -> Dict[str, Any]:
    """Get setup summary for frontend polling."""
    return get_tracker().get_setup_summary()