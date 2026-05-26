#!/usr/bin/env python3
"""Setup script for OpenEO Workspaces API"""

from setuptools import setup, find_packages

with open("requirements.txt") as f:
    requirements = [line.strip() for line in f if line.strip() and not line.startswith("#")]

setup(
    name="openeo-workspaces-api",
    version="0.1.0",
    description="OpenEO Workspaces API - A FastAPI implementation for managing workspaces",
    author="OpenEO Consortium",
    author_email="openeo.psc@uni-muenster.de",
    url="https://github.com/Open-EO/openeo-api",
    packages=find_packages(),
    python_requires=">=3.11",
    install_requires=requirements,
    entry_points={
        "console_scripts": [
            "openeo-workspaces-api=main:app",
        ],
    },
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: Apache Software License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.11",
        "Topic :: Scientific/Engineering :: GIS",
    ],
)

