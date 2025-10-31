"""
Vercel serverless function entry point for Flask application
"""
import sys
import os

# Add parent directory to path so we can import app
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import the Flask app
from app import app

# Vercel's @vercel/python builder automatically detects WSGI applications
# The app will be exposed as a serverless function
