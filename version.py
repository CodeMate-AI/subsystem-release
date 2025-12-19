"""
Version utility module for parsing and comparing numeric versions.
Supports major.minor.patch format with hybrid comparison logic.
Uses first-digit comparison when first digits differ (0.2.0 > 0.11.0 because 2 > 1),
but standard numeric comparison when first digits match (0.13.0 > 0.11.0 because 13 > 11).
"""

import re
import requests
import json
from typing import Tuple, List, Optional


class Version:
    """Represents a numeric version with hybrid comparison capabilities.
    
    Uses first-digit comparison when first digits differ (0.2.0 > 0.11.0 because 2 > 1),
    but standard numeric comparison when first digits match (0.13.0 > 0.11.0 because 13 > 11).
    """
    
    def __init__(self, version_string: str):
        """
        Initialize a Version object from a version string.
        
        Args:
            version_string: Version in format "major.minor.patch"
            
        Raises:
            ValueError: If version string is invalid
        """
        self.version_string = version_string.strip()
        self.major, self.minor, self.patch = self._parse_version(version_string)
    
    def _parse_version(self, version_string: str) -> Tuple[int, int, int]:
        """
        Parse version string into major, minor, patch components.
        
        Args:
            version_string: Version string to parse
            
        Returns:
            Tuple of (major, minor, patch) as integers
            
        Raises:
            ValueError: If version format is invalid
        """
        # Remove 'v' prefix if present (e.g., v1.0.0)
        version_string = version_string.strip().lstrip('vV')
        
        # Match version pattern
        match = re.match(r'^(\d+)\.(\d+)\.(\d+)$', version_string)
        if not match:
            raise ValueError(f"Invalid version format: {version_string}. Expected format: major.minor.patch")
        
        major, minor, patch = map(int, match.groups())
        return major, minor, patch
    
    def _compare_numbers(self, a: int, b: int) -> int:
        """
        Compare two numbers using hybrid logic.
        First compares first digits, then full numbers if first digits match.
        
        Args:
            a: First number
            b: Second number
            
        Returns:
            -1 if a < b, 0 if a == b, 1 if a > b
        """
        if a == b:
            return 0
        
        # Get first digits
        a_first = int(str(a)[0])
        b_first = int(str(b)[0])
        
        # If first digits differ, compare by first digit only
        if a_first != b_first:
            return -1 if a_first < b_first else 1
        
        # If first digits are same, compare full numbers
        return -1 if a < b else 1
    
    def __str__(self) -> str:
        """Return version string representation."""
        return f"{self.major}.{self.minor}.{self.patch}"
    
    def __repr__(self) -> str:
        """Return detailed version representation."""
        return f"Version('{self.version_string}')"
    
    def __eq__(self, other) -> bool:
        """Check if two versions are equal."""
        if not isinstance(other, Version):
            return NotImplemented
        return (self.major, self.minor, self.patch) == (other.major, other.minor, other.patch)
    
    def __lt__(self, other) -> bool:
        """Check if this version is less than another using hybrid comparison."""
        if not isinstance(other, Version):
            return NotImplemented
        
        # Compare major
        major_cmp = self._compare_numbers(self.major, other.major)
        if major_cmp != 0:
            return major_cmp < 0
        
        # Major equal, compare minor
        minor_cmp = self._compare_numbers(self.minor, other.minor)
        if minor_cmp != 0:
            return minor_cmp < 0
        
        # Major and minor equal, compare patch
        patch_cmp = self._compare_numbers(self.patch, other.patch)
        return patch_cmp < 0
    
    def __le__(self, other) -> bool:
        """Check if this version is less than or equal to another."""
        return self < other or self == other
    
    def __gt__(self, other) -> bool:
        """Check if this version is greater than another using hybrid comparison."""
        if not isinstance(other, Version):
            return NotImplemented
        
        # Compare major
        major_cmp = self._compare_numbers(self.major, other.major)
        if major_cmp != 0:
            return major_cmp > 0
        
        # Major equal, compare minor
        minor_cmp = self._compare_numbers(self.minor, other.minor)
        if minor_cmp != 0:
            return minor_cmp > 0
        
        # Major and minor equal, compare patch
        patch_cmp = self._compare_numbers(self.patch, other.patch)
        return patch_cmp > 0
    
    def __ge__(self, other) -> bool:
        """Check if this version is greater than or equal to another."""
        return self > other or self == other
    
    def is_major_update(self, other: 'Version') -> bool:
        """
        Check if updating from other to this version is a major update.
        
        Args:
            other: The previous version
            
        Returns:
            True if major version is higher (using hybrid comparison)
        """
        return self._compare_numbers(self.major, other.major) > 0
    
    def is_minor_update(self, other: 'Version') -> bool:
        """
        Check if updating from other to this version is a minor update.
        
        Args:
            other: The previous version
            
        Returns:
            True if major is same but minor is higher (using hybrid comparison)
        """
        return (self._compare_numbers(self.major, other.major) == 0 and 
                self._compare_numbers(self.minor, other.minor) > 0)
    
    def is_patch_update(self, other: 'Version') -> bool:
        """
        Check if updating from other to this version is a patch update.
        
        Args:
            other: The previous version
            
        Returns:
            True if major and minor are same but patch is higher (using hybrid comparison)
        """
        return (self._compare_numbers(self.major, other.major) == 0 and 
                self._compare_numbers(self.minor, other.minor) == 0 and 
                self._compare_numbers(self.patch, other.patch) > 0)
    
    def bump_major(self) -> 'Version':
        """Return a new version with bumped major number (minor and patch reset to 0)."""
        return Version(f"{self.major + 1}.0.0")
    
    def bump_minor(self) -> 'Version':
        """Return a new version with bumped minor number (patch reset to 0)."""
        return Version(f"{self.major}.{self.minor + 1}.0")
    
    def bump_patch(self) -> 'Version':
        """Return a new version with bumped patch number."""
        return Version(f"{self.major}.{self.minor}.{self.patch + 1}")
    
    def get_update_type(self, other: 'Version') -> str:
        """
        Get the type of update from another version to this one.
        
        Args:
            other: The previous version
            
        Returns:
            'major', 'minor', 'patch', or 'same'
        """
        if self == other:
            return 'same'
        elif self.is_major_update(other):
            return 'major'
        elif self.is_minor_update(other):
            return 'minor'
        elif self.is_patch_update(other):
            return 'patch'
        else:
            return 'unknown'



def get_server_versions(
    current: Version,
    target: Version,
    server_url: str = "http://34.41.78.205:9001/versions"
) -> List[Version]:
    """
    Fetch all versions from current to target from the interpreter server.
    """

    print(f"[DEBUG] current={current}, target={target}")

    try:
        params = {
            "current_version": str(current),
            "target_version": str(target),
        }

        print(f"[DEBUG] Request params: {params}")

        response = requests.post(
            server_url,
            params=params,
            timeout=30
        )

        print(f"[DEBUG] Response status: {response.status_code}")
        response.raise_for_status()

        response_data = response.json()
        print(f"[DEBUG] Response JSON: {response_data}")

        if isinstance(response_data, dict) and "versions" in response_data:
            versions: List[Version] = []

            for v in response_data["versions"]:
                try:
                    ver = Version(v)

                    # REMOVE current_version if present
                    if ver == current:
                        print(f"[DEBUG] Skipping current version: {ver}")
                        continue

                    versions.append(ver)

                except ValueError as ve:
                    print(f"[WARN] Invalid version skipped: {v} ({ve})")

            print(f"[DEBUG] Final versions list: {versions}")
            return versions

        raise ValueError(f"Unexpected response format: {response_data}")

    except requests.RequestException as e:
        print(f"[ERROR] HTTP request failed: {e}")
    except ValueError as e:
        print(f"[ERROR] Parsing error: {e}")

    print("[WARN] Falling back to local version calculation...")
    return []




def validate_version_string(version_string: str) -> bool:
    """
    Validate if a string is a proper numeric version.
    
    Args:
        version_string: Version string to validate
        
    Returns:
        True if valid, False otherwise
    """
    try:
        Version(version_string)
        return True
    except ValueError:
        return False