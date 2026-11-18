"""MDReader 启动脚本:  python main.py [文件.md ...]"""
import sys

from mdreader.app import run

if __name__ == "__main__":
    sys.exit(run(sys.argv))
