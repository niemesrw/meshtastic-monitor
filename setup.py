from setuptools import setup, find_packages

setup(
    name="meshtastic-monitor",
    version="0.1.0",
    description="Monitor Meshtastic mesh networks with CLI and Web UI",
    author="Ryan Niemes",
    packages=find_packages(),
    include_package_data=True,
    install_requires=[
        "meshtastic>=2.3.0",
        "click>=8.1.0",
        "flask>=3.0.0",
    ],
    extras_require={
        "dev": [
            "pytest>=8.0.0",
            "pytest-cov>=4.1.0",
            "pytest-asyncio>=0.23.0",
            "black>=24.0.0",
            "ruff>=0.2.0",
        ],
    },
    entry_points={
        "console_scripts": [
            "mesh-monitor=mesh_monitor.cli:cli",
        ],
    },
    python_requires=">=3.9",
)
