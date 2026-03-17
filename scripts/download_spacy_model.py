# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.

#!/usr/bin/env python
"""Script to download the required spaCy model."""
import subprocess
import sys

def main():
    """Download the spaCy model."""
    print("Downloading spaCy model...")
    try:
        subprocess.check_call([sys.executable, "-m", "spacy", "download", "en_core_web_sm"])
        print("Successfully downloaded spaCy model.")
    except subprocess.CalledProcessError as e:
        print(f"Error downloading spaCy model: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main() 