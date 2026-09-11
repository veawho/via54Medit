"""Setup configuration for medit-telemetry standalone package."""

import os
from setuptools import setup, find_packages

HERE = os.path.abspath(os.path.dirname(__file__))

readme_path = os.path.join(HERE, "README.md")
long_description = ""
if os.path.exists(readme_path):
    with open(readme_path, "r", encoding="utf-8") as f:
        long_description = f.read()

setup(
    name="medit-telemetry",
    version="1.5.19",
    description="TraeWork 文献整理与 Highlight 监控统计、人效分析及飞书自动同步工具 (via54Medit 独立模块)",
    long_description=long_description,
    long_description_content_type="text/markdown",
    author="via54Medit Team",
    packages=["telemetry"],
    package_dir={"telemetry": "."},
    # scripts/ 无 __init__.py 不是 Python 包, 但存放着部署时要安装的外壳启动器模板,
    # 必须显式声明为包数据, 否则从 wheel 安装时该模板缺失。
    package_data={"telemetry": ["scripts/*"]},
    python_requires=">=3.8",
    install_requires=[
        # Zero mandatory dependencies - pure Python standard library!
    ],
    extras_require={
        "pdf": ["pypdf>=3.0.0"],
        "all": ["pypdf>=3.0.0"],
    },
    entry_points={
        "console_scripts": [
            "medit-telemetry = telemetry.cli:main",
            "traework-telemetry = telemetry.cli:main",
        ],
    },
    classifiers=[
        "Development Status :: 5 - Production/Stable",
        "Intended Audience :: Developers",
        "Intended Audience :: Science/Research",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Operating System :: OS Independent",
    ],
)
