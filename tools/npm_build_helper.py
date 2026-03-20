# tools/npm_build_helper.py
import os
import subprocess
import logging
from typing import Tuple

logger = logging.getLogger(__name__)

def build_project(directory: str) -> Tuple[bool, str]:
    """
    使用 npm 构建 Node.js 项目
    返回 (success, error_message)
    """
    try:
        # 在 Windows 上使用 shell=True
        use_shell = os.name == 'nt'
        
        # 运行 npm install
        logger.info(f"Running npm install in {directory}")
        install_result = subprocess.run(
            ['npm', 'install'],
            cwd=directory,
            capture_output=True,
            text=True,
            timeout=300,
            shell=use_shell  # 关键修改
        )
        
        if install_result.returncode != 0:
            error_msg = install_result.stderr or install_result.stdout
            return False, f"npm install 失败: {error_msg}"
        
        # 运行 npm run build
        logger.info(f"Running npm run build in {directory}")
        build_result = subprocess.run(
            ['npm', 'run', 'build'],
            cwd=directory,
            capture_output=True,
            text=True,
            timeout=300,
            shell=use_shell  # 关键修改
        )
        
        if build_result.returncode != 0:
            error_msg = build_result.stderr or build_result.stdout
            return False, f"npm run build 失败: {error_msg}"
        
        logger.info(f"Build successful in {directory}")
        return True, ""
        
    except subprocess.TimeoutExpired:
        return False, "构建超时（超过5分钟）"
    except FileNotFoundError:
        return False, "服务器未安装 Node.js/npm，请先安装 Node.js"
    except Exception as e:
        return False, f"构建过程出错: {str(e)}"