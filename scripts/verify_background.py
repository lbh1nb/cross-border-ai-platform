"""验证 pythonw.exe 后台调度器是否正常运行。"""
import subprocess
import time
import os

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
pythonw = os.path.join(project_root, ".venv", "Scripts", "pythonw.exe")
script = os.path.join(project_root, "scripts", "start_scheduler.py")

# 启动后台进程
proc = subprocess.Popen([pythonw, script], cwd=project_root)
print(f"Started pythonw.exe with PID: {proc.pid}")

# 等待 3 秒
time.sleep(3)

# 检查进程是否存活
if proc.poll() is None:
    print("STATUS: RUNNING (scheduler is active in background)")
else:
    print(f"STATUS: EXITED with code {proc.returncode}")

# 检查日志文件
log_dir = os.path.join(project_root, "logs")
if os.path.isdir(log_dir):
    logs = os.listdir(log_dir)
    print(f"Log files: {logs}")
else:
    print("Log directory not created yet")
