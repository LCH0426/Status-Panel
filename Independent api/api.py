from flask import Flask, jsonify, request
from flask_cors import CORS
import psutil
import time
import threading
import json
import os
import sys
import logging
from logging.handlers import RotatingFileHandler
import signal
import atexit
import platform
import subprocess
import re
import shutil
from rich.console import Console
from rich.panel import Panel
from rich import box


# ================= 版本信息 =================
def inf():
    console = Console()
    content = "\n".join([
        "Status Panel for LeviLamina (No Web)",
        "作者: LCH0426",
        "版本: 1.1.0",
        "https://github.com/LCH0426/Status-Panel"
    ])
    
    panel = Panel(content, 
                 expand=False,
                 width=86,
                 border_style="white",
                 style="default",
                 box=box.SQUARE)
    console.print(panel)

inf()

# ================= 全局变量 =================
# 确定程序目录（打包后为可执行文件所在目录）
if getattr(sys, 'frozen', False):
    # 打包环境
    APP_DIR = os.path.dirname(sys.executable)
else:
    # 开发环境
    APP_DIR = os.path.dirname(os.path.abspath(__file__))

# ================= 配置加载 =================
CONFIG_FILE = 'config.json'
DEFAULT_CONFIG = {
    "api_port": 8000,    # API服务端口
    "log_enabled": True,        # 是否启用日志
    "console_log": True,         # 是否启用控制台日志
    "monitor_gpu": False         # 是否监控GPU
}

def load_config():
    """加载配置文件，优先使用程序所在目录的配置"""
    console = Console()  # 使用Rich控制台输出
    try:
        # 程序目录中的配置文件
        app_dir_config = os.path.join(APP_DIR, CONFIG_FILE)
        
        # 资源目录中的配置文件（打包后的临时目录）
        resource_dir_config = None
        if hasattr(sys, '_MEIPASS'):
            resource_dir_config = os.path.join(sys._MEIPASS, CONFIG_FILE)
        
        # 优先使用程序所在目录的配置文件
        if os.path.exists(app_dir_config):
            config_path = app_dir_config
        elif resource_dir_config and os.path.exists(resource_dir_config):
            # 如果程序目录没有配置文件，但从资源目录找到，则复制到程序目录
            try:
                shutil.copy(resource_dir_config, app_dir_config)
                console.print(f"已复制默认配置文件到: {app_dir_config}")
                config_path = app_dir_config
            except Exception as e:
                console.print(f"复制配置文件失败: {e}")
                config_path = resource_dir_config
        else:
            # 没有配置文件，在程序目录创建默认配置
            config_path = app_dir_config
        
        if os.path.exists(config_path):
            # 使用UTF-8编码打开文件
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
                # 合并配置，确保所有必要的键都存在
                final_config = {**DEFAULT_CONFIG, **config}
                console.print(f"加载配置文件: {config_path}")
                return final_config
        else:
            # 创建默认配置文件到程序目录，使用UTF-8编码
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(DEFAULT_CONFIG, f, indent=4, ensure_ascii=False)
            console.print(f"创建默认配置文件: {config_path}")
            return DEFAULT_CONFIG
    except Exception as e:
        console.print(f"配置文件加载错误: {e}")
        return DEFAULT_CONFIG

# 先加载配置
config = load_config()


# ================= 配置日志 =================
def setup_logging(config):
    """根据配置设置日志系统"""
    log_enabled = config["log_enabled"]
    console_log_enabled = config["console_log"]
    
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    
    # 控制台日志处理器 (根据配置决定)
    if console_log_enabled:
        console_handler = logging.StreamHandler()
        console_formatter = logging.Formatter(
            '%(asctime)s - %(levelname)s - %(message)s',
            datefmt='%H:%M:%S'  # 只显示时间（时:分:秒）
        )
        console_handler.setFormatter(console_formatter)
        logger.addHandler(console_handler)
    
    # 文件日志处理器 (根据配置决定)
    if log_enabled:
        # 日志目录在程序目录下
        log_dir = os.path.join(APP_DIR, "logs")
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)
        
        log_file = os.path.join(log_dir, "api_service.log")
        
        file_handler = RotatingFileHandler(
            log_file, maxBytes=5 * 1024 * 1024, backupCount=3, encoding='utf-8'
        )
        file_formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)
    
    return logger

# 现在可以初始化日志系统
logger = setup_logging(config)
logger.info(f"日志系统初始化完成，文件日志{'已启用' if config['log_enabled'] else '已禁用'}")
logger.info(f"控制台日志{'已启用' if config['console_log'] else '已禁用'}")
logger.info(f"程序目录: {APP_DIR}")

# ================= 服务停止标志 =================
SERVICE_SHUTDOWN = threading.Event()

# ================= 信号处理函数 =================
def handle_exit_signal(signum, frame):
    """处理退出信号"""
    logger.info(f"接收到退出信号 {signum}，程序即将退出")
    SERVICE_SHUTDOWN.set()

# 注册信号处理
signal.signal(signal.SIGINT, handle_exit_signal)   # Ctrl+C
signal.signal(signal.SIGTERM, handle_exit_signal)  # kill 命令
if hasattr(signal, 'SIGBREAK'):
    signal.signal(signal.SIGBREAK, handle_exit_signal)  # Windows Ctrl+Break

# 注册退出处理
def cleanup():
    """程序退出前的清理工作"""
    if SERVICE_SHUTDOWN.is_set():
        logger.info("执行清理工作...")
        # 添加任何必要的清理操作
        logger.info("清理完成，程序退出")

atexit.register(cleanup)

# ================= 创建API应用 =================
api_app = Flask(__name__)
CORS(api_app)

# 添加请求日志记录
@api_app.before_request
def log_request_info():
    if request.path == '/':
        logger.info(f">>> {request.remote_addr} - {request.method} {request.path}")

@api_app.after_request
def log_response_info(response):
    if request.path == '/':
        logger.info(f"<<< {request.remote_addr} - {request.method} {request.path} - {response.status}")
    return response

# ================= 全局数据结构 =================
system_data = {
    "cpu_usage": 0.0,
    "memory_total_gb": 0.0,
    "memory_used_gb": 0.0,
    "net_sent_rate_mbps": 0.0,
    "net_recv_rate_mbps": 0.0,
    "net_total_sent_gb": 0.0,
    "net_total_recv_gb": 0.0,
    "disk_read_rate_mbs": 0.0,
    "disk_write_rate_mbs": 0.0,
    "system_uptime_hr": 0.0,
    # 新增系统信息字段
    "cpu_cores": 0,
    "cpu_name": "Unknown",
    "cpu_arch": "Unknown",
    "is_vm": False,
    "cpu_base_freq_ghz": 0.0,
    "system_type": "",        # 操作系统类型
    "system_kernel": "",      # 内核版本
    "gpu_name": "N/A",
    "gpu_usage": 0.0,
    # 新增磁盘信息
    "root_disk_total_gb": 0.0,
    "root_disk_used_gb": 0.0
}

# ================= 常量与全局变量 =================
GB_DIVISOR = 1024 ** 3
MB_DIVISOR = 1024 ** 2
PROGRAM_START_TIME = time.perf_counter()

# 线程锁
system_data_lock = threading.Lock()

# 网络与磁盘IO记录
last_net_io = psutil.net_io_counters()
last_disk_io = psutil.disk_io_counters()
last_update_time = time.perf_counter()
last_gpu_update = 0  # 上次更新GPU信息的时间

# ================= 状态码定义 =================
STATUS_CODES = {
    "SUCCESS": 200,
    "SERVER_ERROR": 500,
    "SERVICE_STOPPED": 503
}

# ================= 辅助函数 =================
def get_cpu_name():
    """获取CPU名称（跨平台实现）"""
    try:
        # Windows系统
        if platform.system() == "Windows":
            try:
                # 方法1: 使用wmic命令
                result = subprocess.run(
                    ['wmic', 'cpu', 'get', 'name', '/value'],
                    capture_output=True, text=True, timeout=2
                )
                if result.returncode == 0 and result.stdout.strip():
                    match = re.search(r'Name=([^\n]+)', result.stdout)
                    if match:
                        return match.group(1).strip()
            except:
                # 方法1失败时尝试方法2
                pass
            
            try:
                # 方法2: 使用Powershell
                result = subprocess.run(
                    ['powershell', '-Command', 'Get-WmiObject Win32_Processor | Select-Object -ExpandProperty Name'],
                    capture_output=True, text=True, timeout=2
                )
                if result.returncode == 0 and result.stdout.strip():
                    return result.stdout.strip()
            except:
                # 两种方法都失败时使用platform
                pass
        
        # Linux系统
        elif platform.system() == "Linux":
            try:
                # 方法1: 读取/proc/cpuinfo
                if os.path.exists('/proc/cpuinfo'):
                    with open('/proc/cpuinfo', 'r', encoding='utf-8') as f:
                        for line in f:
                            if line.startswith('model name'):
                                return line.split(':')[1].strip()
                
                # 方法2: 使用lscpu命令
                result = subprocess.run(
                    ['lscpu'], capture_output=True, text=True, timeout=2
                )
                if result.returncode == 0 and result.stdout.strip():
                    match = re.search(r'Model name:\s*(.+)', result.stdout)
                    if match:
                        return match.group(1).strip()
            except:
                pass
        
        # macOS系统
        elif platform.system() == "Darwin":
            try:
                result = subprocess.run(
                    ['sysctl', '-n', 'machdep.cpu.brand_string'],
                    capture_output=True, text=True, timeout=2
                )
                if result.returncode == 0 and result.stdout.strip():
                    return result.stdout.strip()
            except:
                pass
    
    except Exception as e:
        logger.error(f"获取CPU名称失败: {e}")
    
    # 所有方法失败时使用platform.processor()
    try:
        return platform.processor() or "Unknown"
    except:
        return "Unknown"

def get_gpu_info():
    """
    获取GPU信息（跨平台实现）
    返回: (gpu_name, gpu_usage)
    """
    gpu_name = "N/A"
    gpu_usage = 0.0
    
    try:
        # Windows 使用 nvidia-smi
        if platform.system() == "Windows":
            result = subprocess.run(
                ['nvidia-smi', '--query-gpu=name,utilization.gpu', '--format=csv,noheader,nounits'],
                capture_output=True, text=True, timeout=2
            )
            if result.returncode == 0 and result.stdout.strip():
                gpu_info = result.stdout.splitlines()[0].split(',')
                if len(gpu_info) >= 2:
                    gpu_name = gpu_info[0].strip()
                    gpu_usage = float(gpu_info[1].strip())
        
        # Linux 使用 nvidia-smi
        elif platform.system() == "Linux":
            result = subprocess.run(
                ['nvidia-smi', '--query-gpu=name,utilization.gpu', '--format=csv,noheader,nounits'],
                capture_output=True, text=True, timeout=2
            )
            if result.returncode == 0 and result.stdout.strip():
                gpu_info = result.stdout.splitlines()[0].split(',')
                if len(gpu_info) >= 2:
                    gpu_name = gpu_info[0].strip()
                    gpu_usage = float(gpu_info[1].strip())
        
        # macOS 使用 system_profiler
        elif platform.system() == "Darwin":
            result = subprocess.run(
                ['system_profiler', 'SPDisplaysDataType'],
                capture_output=True, text=True, timeout=2
            )
            if result.returncode == 0:
                # 提取显卡名称
                name_match = re.search(r'Chipset Model: (.+)', result.stdout)
                if name_match:
                    gpu_name = name_match.group(1).strip()
                
                # 提取显存使用情况
                vram_match = re.search(r'VRAM \(Total\): (\d+)', result.stdout)
                if vram_match:
                    # 这里简化处理，显示为0
                    gpu_usage = 0.0
    
    except (subprocess.TimeoutExpired, subprocess.CalledProcessError, FileNotFoundError, ValueError) as e:
        logger.warning(f"获取GPU信息失败: {e}")
    except Exception as e:
        logger.error(f"获取GPU信息时发生错误: {e}", exc_info=True)
    
    return gpu_name, gpu_usage

# ================= 获取系统类型和内核版本 =================
def get_system_info():
    """获取操作系统类型和内核版本信息"""
    system = platform.system()
    system_type = ""
    kernel_version = ""
    
    try:
        # Windows 系统
        if system == "Windows":
            # 方法1: 使用 platform.version()
            kernel_version = platform.version()
            
            # 方法2: 使用 sys.getwindowsversion()
            if not kernel_version:
                win_version = sys.getwindowsversion()
                kernel_version = f"{win_version.major}.{win_version.minor}.{win_version.build}"
            
            # 方法3: 使用 wmic 命令
            if not kernel_version:
                try:
                    result = subprocess.run(
                        ['wmic', 'os', 'get', 'version', '/value'],
                        capture_output=True, text=True, timeout=2
                    )
                    if result.returncode == 0 and result.stdout.strip():
                        match = re.search(r'Version=([^\n]+)', result.stdout)
                        if match:
                            kernel_version = match.group(1).strip()
                except:
                    pass
            
            # 方法4: 读取注册表
            if not kernel_version:
                try:
                    import winreg
                    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows NT\CurrentVersion") as key:
                        kernel_version, _ = winreg.QueryValueEx(key, "CurrentVersion")
                except:
                    pass
            
            # 获取友好的系统名称
            try:
                result = subprocess.run(
                    ['wmic', 'os', 'get', 'caption', '/value'],
                    capture_output=True, text=True, timeout=2
                )
                if result.returncode == 0 and result.stdout.strip():
                    match = re.search(r'Caption=([^\n]+)', result.stdout)
                    if match:
                        system_type = match.group(1).strip()
            except:
                # 如果失败，使用 platform
                win_version = platform.win32_ver()
                if win_version[0]:
                    system_type = f"Windows {win_version[0]}"
                else:
                    system_type = "Windows"
        
        # Linux 系统
        elif system == "Linux":
            # 获取发行版名称
            try:
                # 检查 /etc/os-release 文件
                if os.path.exists('/etc/os-release'):
                    with open('/etc/os-release', 'r', encoding='utf-8') as f:
                        for line in f:
                            if line.startswith('PRETTY_NAME='):
                                system_type = line.split('=')[1].strip().strip('"')
                                break
                            elif line.startswith('NAME=') and not system_type:
                                system_type = line.split('=')[1].strip().strip('"')
                
                # 如果未找到，尝试使用 lsb_release 命令
                if not system_type:
                    result = subprocess.run(
                        ['lsb_release', '-d'], 
                        capture_output=True, text=True, timeout=2
                    )
                    if result.returncode == 0 and result.stdout.strip():
                        match = re.search(r'Description:\s*(.+)', result.stdout)
                        if match:
                            system_type = match.group(1).strip()
                
                # 如果仍然未找到，使用通用 Linux 名称
                if not system_type:
                    system_type = "Linux"
                
                # 获取内核版本
                kernel_version = platform.release()
            except:
                system_type = "Linux"
                kernel_version = platform.release()
        
        # macOS 系统
        elif system == "Darwin":
            try:
                # 获取系统名称
                result = subprocess.run(
                    ['sw_vers', '-productName'], 
                    capture_output=True, text=True, timeout=2
                )
                if result.returncode == 0 and result.stdout.strip():
                    product_name = result.stdout.strip()
                    
                    # 获取版本号
                    result_ver = subprocess.run(
                        ['sw_vers', '-productVersion'], 
                        capture_output=True, text=True, timeout=2
                    )
                    if result_ver.returncode == 0 and result_ver.stdout.strip():
                        system_type = f"{product_name} {result_ver.stdout.strip()}"
                    else:
                        system_type = product_name
                else:
                    system_type = "macOS"
                
                # 获取内核版本
                kernel_version = platform.release()
            except:
                system_type = "macOS"
                kernel_version = platform.release()
        
        # 其他系统
        else:
            system_type = system
            kernel_version = platform.release()
    
    except Exception as e:
        logger.error(f"获取系统信息失败: {e}")
        system_type = system
        kernel_version = platform.release()
    
    return system_type, kernel_version

# ================= 虚拟机检测函数 =================
def detect_virtual_machine():
    """检测当前是否在虚拟机中运行"""
    try:
        system = platform.system()
        manufacturer = platform.uname().system.lower()

        # 通用检测方法
        if any(keyword in manufacturer for keyword in ["vmware", "virtual", "kvm", "qemu", "xen", "hyperv"]):
            return True

        # Linux 系统检测
        if system == "Linux":
            # 方法1: 检查 /proc/cpuinfo 中的 hypervisor 标志
            if os.path.exists("/proc/cpuinfo"):
                with open("/proc/cpuinfo", "r", encoding="utf-8") as f:
                    if "hypervisor" in f.read().lower():
                        return True
            
            # 方法2: 检查系统文件
            vm_files = [
                "/sys/class/dmi/id/product_name",
                "/sys/class/dmi/id/sys_vendor",
                "/sys/class/dmi/id/board_vendor"
            ]
            vm_keywords = ["vmware", "virtualbox", "kvm", "qemu", "xen", "oracle", "innotek", "bochs"]
            
            for file_path in vm_files:
                if os.path.exists(file_path):
                    with open(file_path, "r", encoding="utf-8") as f:
                        content = f.read().lower()
                        if any(keyword in content for keyword in vm_keywords):
                            return True
            
            # 方法3: 检查系统模块
            if os.path.exists("/proc/modules"):
                with open("/proc/modules", "r", encoding="utf-8") as f:
                    modules = f.read().lower()
                    if "vboxguest" in modules or "vmw_balloon" in modules or "xen_" in modules:
                        return True
            
            # 方法4: 使用 dmidecode 命令
            try:
                result = subprocess.run(
                    ["dmidecode", "-s", "system-product-name"],
                    capture_output=True,
                    text=True,
                    timeout=2,
                    check=True
                )
                output = result.stdout.lower()
                if any(keyword in output for keyword in ["vmware", "virtualbox", "kvm", "qemu"]):
                    return True
            except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
                pass
        
        # Windows 系统检测
        elif system == "Windows":
            # 方法1: 检查系统制造商
            try:
                result = subprocess.run(
                    ["wmic", "computersystem", "get", "manufacturer"],
                    capture_output=True,
                    text=True,
                    timeout=2,
                    check=True
                )
                output = result.stdout.lower()
                if any(keyword in output for keyword in ["vmware", "innotek", "xen", "qemu"]):
                    return True
            except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
                pass
            
            # 方法2: 检查 BIOS 信息
            try:
                result = subprocess.run(
                    ["wmic", "bios", "get", "manufacturer"],
                    capture_output=True,
                    text=True,
                    timeout=2,
                    check=True
                )
                output = result.stdout.lower()
                if any(keyword in output for keyword in ["vmware", "virtualbox", "xen", "qemu"]):
                    return True
            except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
                pass
            
            # 方法3: 检查磁盘控制器
            try:
                result = subprocess.run(
                    ["wmic", "diskdrive", "get", "model"],
                    capture_output=True,
                    text=True,
                    timeout=2,
                    check=True
                )
                output = result.stdout.lower()
                if any(keyword in output for keyword in ["vmware", "virtual"]):
                    return True
            except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
                pass
            
            # 方法4: 检查注册表
            try:
                import winreg
                vm_registry_keys = [
                    r"SOFTWARE\Oracle\VirtualBox",
                    r"SOFTWARE\VMware, Inc.\VMware Tools",
                    r"SOFTWARE\XenSource",
                    r"HARDWARE\ACPI\DSDT\VBOX__",
                ]
                
                for key_path in vm_registry_keys:
                    try:
                        winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path)
                        return True
                    except FileNotFoundError:
                        pass
            except ImportError:
                pass
        
        # macOS 系统检测
        elif system == "Darwin":
            # 方法1: 检查系统信息
            try:
                result = subprocess.run(
                    ["sysctl", "-n", "machdep.cpu.features"],
                    capture_output=True,
                    text=True,
                    timeout=2,
                    check=True
                )
                output = result.stdout.lower()
                if "hypervisor" in output:
                    return True
            except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
                pass
            
            # 方法2: 检查硬件模型
            try:
                result = subprocess.run(
                    ["sysctl", "-n", "hw.model"],
                    capture_output=True,
                    text=True,
                    timeout=2,
                    check=True
                )
                output = result.stdout.lower()
                if any(keyword in output for keyword in ["virtualbox", "vmware", "parallels"]):
                    return True
            except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
                pass
            
            # 方法3: 检查进程列表
            try:
                result = subprocess.run(
                    ["ps", "-ax"],
                    capture_output=True,
                    text=True,
                    timeout=2,
                    check=True
                )
                output = result.stdout.lower()
                if any(keyword in output for keyword in ["vmware", "virtualbox", "parallels"]):
                    return True
            except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
                pass
        
        # 云服务提供商检测
        cloud_files = [
            "/sys/devices/virtual/dmi/id/product_uuid",
            "/sys/class/dmi/id/product_serial"
        ]
        cloud_keywords = ["ec2", "amazon", "google", "gce", "azure", "microsoft"]
        
        for file_path in cloud_files:
            if os.path.exists(file_path):
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read().lower()
                    if any(keyword in content for keyword in cloud_keywords):
                        return True
        
        # 如果所有检测都通过，则不是虚拟机
        return False
    
    except Exception as e:
        logger.error(f"虚拟机检测失败: {e}")
        return False

# ================= 监控线程 =================
def system_monitor_thread():
    """实时更新系统监控数据（每秒执行）"""
    global system_data, last_net_io, last_disk_io, last_update_time, last_gpu_update
    
    # 初始化系统信息
    try:
        with system_data_lock:
            # 获取CPU信息
            system_data["cpu_name"] = get_cpu_name()
            system_data["cpu_arch"] = platform.machine()
            
            # 检测是否为虚拟机
            system_data["is_vm"] = detect_virtual_machine()
            
            # 获取CPU核心数量
            system_data["cpu_cores"] = psutil.cpu_count(logical=True)
            
            # 获取CPU最大频率（GHz）
            cpu_freq = psutil.cpu_freq()
            if cpu_freq:
                system_data["cpu_base_freq_ghz"] = round(cpu_freq.max / 1000, 2)
            
            # 获取系统类型和内核版本
            system_type, kernel_version = get_system_info()
            system_data["system_type"] = system_type
            system_data["system_kernel"] = kernel_version
            
            # 获取根目录磁盘信息
            root_disk = psutil.disk_usage('/')
            system_data["root_disk_total_gb"] = root_disk.total / GB_DIVISOR
            system_data["root_disk_used_gb"] = root_disk.used / GB_DIVISOR
            
            logger.info(f"CPU名称: {system_data['cpu_name']}")
            logger.info(f"CPU架构: {system_data['cpu_arch']}")
            logger.info(f"虚拟机状态: {'是' if system_data['is_vm'] else '否'}")
            logger.info(f"系统类型: {system_type}")
            logger.info(f"内核版本: {kernel_version}")
    except Exception as e:
        logger.error(f"初始化系统信息失败: {e}", exc_info=True)
    
    while not SERVICE_SHUTDOWN.is_set():  # 检查退出标志
        try:
            current_time = time.perf_counter()
            time_diff = max(current_time - last_update_time, 1e-6)  # 防止除零
            
            with system_data_lock:
                # 1. CPU监控 (总是开启)
                system_data["cpu_usage"] = psutil.cpu_percent(interval=0.1)
                
                # 2. 内存监控 (总是开启)
                mem = psutil.virtual_memory()
                # 精确读取内存总量（不考虑核显占用）
                system_data["memory_total_gb"] = mem.total / GB_DIVISOR
                system_data["memory_used_gb"] = mem.used / GB_DIVISOR
                
                # 3. 系统运行时间
                system_data["system_uptime_hr"] = (time.time() - psutil.boot_time()) / 3600
                
                # 4. 网络监控 (总是开启)
                current_net_io = psutil.net_io_counters()
                
                # 更新总量
                system_data["net_total_sent_gb"] = current_net_io.bytes_sent / GB_DIVISOR
                system_data["net_total_recv_gb"] = current_net_io.bytes_recv / GB_DIVISOR
                
                # 计算实时速率
                system_data["net_sent_rate_mbps"] = (
                    (current_net_io.bytes_sent - last_net_io.bytes_sent) * 8
                ) / MB_DIVISOR / time_diff
                system_data["net_recv_rate_mbps"] = (
                    (current_net_io.bytes_recv - last_net_io.bytes_recv) * 8
                ) / MB_DIVISOR / time_diff
                
                last_net_io = current_net_io
                
                # 5. 磁盘监控 (总是开启)
                current_disk_io = psutil.disk_io_counters()
                system_data["disk_read_rate_mbs"] = (
                    current_disk_io.read_bytes - last_disk_io.read_bytes
                ) / MB_DIVISOR / time_diff
                system_data["disk_write_rate_mbs"] = (
                    current_disk_io.write_bytes - last_disk_io.write_bytes
                ) / MB_DIVISOR / time_diff
                
                last_disk_io = current_disk_io
                last_update_time = current_time
                
                # 6. GPU监控（根据配置决定）
                current_time_sec = time.time()
                if config["monitor_gpu"] and current_time_sec - last_gpu_update > 5:
                    gpu_name, gpu_usage = get_gpu_info()
                    system_data["gpu_name"] = gpu_name
                    system_data["gpu_usage"] = gpu_usage
                    last_gpu_update = current_time_sec
                elif not config["monitor_gpu"]:
                    # 监控关闭时设为默认值
                    system_data["gpu_name"] = "Monitoring Disabled"
                    system_data["gpu_usage"] = 0.0
                
                # 7. 更新根目录磁盘信息
                root_disk = psutil.disk_usage('/')
                system_data["root_disk_total_gb"] = root_disk.total / GB_DIVISOR
                system_data["root_disk_used_gb"] = root_disk.used / GB_DIVISOR
                
        except Exception as e:
            logger.error(f"系统监控线程错误: {e}", exc_info=True)
        time.sleep(1)

# ================= API端点 =================
@api_app.route('/', methods=['GET'])
def get_system_status():
    """仅返回系统状态"""
    # 检查服务是否已停止
    if SERVICE_SHUTDOWN.is_set():
        return jsonify({
            "status": "error",
            "code": STATUS_CODES["SERVICE_STOPPED"],
            "message": "服务已停止"
        }), STATUS_CODES["SERVICE_STOPPED"]
    
    # 实时计算程序运行时间
    program_uptime_hours = (time.perf_counter() - PROGRAM_START_TIME) / 3600
    
    # 获取系统数据
    try:
        with system_data_lock:
            system_status = {
                "cpu_usage_percent": round(system_data["cpu_usage"], 1),
                "cpu_name": system_data["cpu_name"],
                "cpu_arch": system_data["cpu_arch"],
                "is_vm": system_data["is_vm"],
                "memory_total_gb": round(system_data["memory_total_gb"], 2),
                "memory_used_gb": round(system_data["memory_used_gb"], 2),
                "root_disk_total_gb": round(system_data["root_disk_total_gb"], 2),
                "root_disk_used_gb": round(system_data["root_disk_used_gb"], 2),
                "net_upload_rate_mbps": round(system_data["net_sent_rate_mbps"], 2),
                "net_download_rate_mbps": round(system_data["net_recv_rate_mbps"], 2),
                "net_total_upload_gb": round(system_data["net_total_sent_gb"], 3),
                "net_total_download_gb": round(system_data["net_total_recv_gb"], 3),
                "disk_read_rate_mbs": round(system_data["disk_read_rate_mbs"], 2),
                "disk_write_rate_mbs": round(system_data["disk_write_rate_mbs"], 2),
                "system_uptime_hours": round(system_data["system_uptime_hr"], 1),
                "program_uptime_hours": round(program_uptime_hours, 1),
                "cpu_cores": system_data["cpu_cores"],
                "cpu_base_freq_ghz": system_data["cpu_base_freq_ghz"],
                "system_type": system_data["system_type"],
                "system_kernel": system_data["system_kernel"],
                "gpu_name": system_data["gpu_name"],
                "gpu_usage_percent": round(system_data["gpu_usage"], 1)
            }
    except Exception as e:
        logger.error(f"获取系统状态失败: {e}", exc_info=True)
        return jsonify({
            "status": "error",
            "code": STATUS_CODES["SERVER_ERROR"],
            "message": "Failed to retrieve system status"
        }), STATUS_CODES["SERVER_ERROR"]
    
    # 准备响应数据
    response_data = {
        "status": "success",
        "code": STATUS_CODES["SUCCESS"],
        "system_status": system_status
    }
    
    # 返回响应
    return jsonify(response_data), response_data["code"]

# ================= 主程序 =================
def run_api_server():
    """启动API服务"""
    # 启动监控线程
    threading.Thread(target=system_monitor_thread, daemon=True).start()
    
    api_port = config["api_port"]
    
    try:
        from waitress import serve
        logger.info(f"使用Waitress启动API服务: http://localhost:{api_port}")
        serve(api_app, host='0.0.0.0', port=api_port)
    except ImportError:
        logger.warning("Waitress未安装，使用Flask内置服务器")
        logger.info(f"使用Flask内置服务器启动API服务: http://localhost:{api_port}")
        api_app.run(host='0.0.0.0', port=api_port, threaded=True)

if __name__ == '__main__':
    run_api_server()
