"""One command to verify everything: python check.py"""
import subprocess, sys
sys.exit(subprocess.call([sys.executable, "-m", "pytest", "tests/", "-q"]))
