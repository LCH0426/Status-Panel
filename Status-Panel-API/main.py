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
        "Status Panel API ",
        "作者: LCH0426",
        "版本: 1.1.3",
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
if getattr(sys, 'frozen', False):
    APP_DIR = os.path.dirname(sys.executable)
else:
    APP_DIR = os.path.dirname(os.path.abspath(__file__))

# ================= 配置加载 =================
CONFIG_FILE = 'config.json'
DEFAULT_CONFIG = {
    "api_port": 8000,
    "log_enabled": True,
    "console_log": True,
    "monitor_gpu": False
}

def load_config():
    console = Console()
    try:
        app_dir_config = os.path.join(APP_DIR, CONFIG_FILE)
        resource_dir_config = os.path.join(sys._MEIPASS, CONFIG_FILE) if hasattr(sys, '_MEIPASS') else None

        if os.path.exists(app_dir_config):
            config_path = app_dir_config
        elif resource_dir_config and os.path.exists(resource_dir_config):
            try:
                shutil.copy(resource_dir_config, app_dir_config)
                console.print(f"已复制默认配置文件到: {app_dir_config}")
                config_path = app_dir_config
            except Exception as e:
                console.print(f"复制配置文件失败: {e}")
                config_path = resource_dir_config
        else:
            config_path = app_dir_config

        if os.path.exists(config_path):
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
                final_config = {**DEFAULT_CONFIG, **config}
                console.print(f"加载配置文件: {config_path}")
                return final_config
        else:
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(DEFAULT_CONFIG, f, indent=4, ensure_ascii=False)
            console.print(f"创建默认配置文件: {config_path}")
            return DEFAULT_CONFIG
    except Exception as e:
        console.print(f"配置文件加载错误: {e}")
        return DEFAULT_CONFIG

config = load_config()


# ================= 配置日志 =================
def setup_logging(config):
    log_enabled = config["log_enabled"]
    console_log_enabled = config["console_log"]
    
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    logger.handlers = []  

    if console_log_enabled:
        console_handler = logging.StreamHandler()
        console_formatter = logging.Formatter(
            '%(asctime)s - %(levelname)s - %(message)s',
            datefmt='%H:%M:%S'
        )
        console_handler.setFormatter(console_formatter)
        logger.addHandler(console_handler)
    
    if log_enabled:
        log_dir = os.path.join(APP_DIR, "logs")
        os.makedirs(log_dir, exist_ok=True)
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

logger = setup_logging(config)
logger.info(f"日志系统初始化完成，文件日志{'已启用' if config['log_enabled'] else '已禁用'}")
logger.info(f"控制台日志{'已启用' if config['console_log'] else '已禁用'}")
logger.info(f"程序目录: {APP_DIR}")

# ================= 服务控制变量 =================
SERVICE_SHUTDOWN = threading.Event()
server = None  # 用于存储服务器实例，便于关闭

# ================= 信号处理函数 =================
def handle_exit_signal(signum, frame):
    """处理退出信号，确保优雅关闭"""
    logger.info(f"接收到退出信号 {signum}，正在关闭服务...")
    SERVICE_SHUTDOWN.set()
    
    # 强制退出，避免Waitress阻塞
    logger.info("强制退出进程...")
    os._exit(0)

def setup_signal_handlers():
    """设置信号处理器"""
    signal.signal(signal.SIGINT, handle_exit_signal)   # Ctrl+C
    signal.signal(signal.SIGTERM, handle_exit_signal)  # kill 命令
    if hasattr(signal, 'SIGBREAK'):
        signal.signal(signal.SIGBREAK, handle_exit_signal)  # Windows Ctrl+Break

def cleanup():
    if SERVICE_SHUTDOWN.is_set():
        logger.info("执行清理工作...")
        logger.info("清理完成，程序已退出")

atexit.register(cleanup)

# ================= 创建API应用 =================
api_app = Flask(__name__)
CORS(api_app)

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
    "cpu_cores": 0,
    "cpu_name": "Unknown",
    "cpu_arch": "Unknown",
    "is_vm": False,
    "cpu_base_freq_ghz": 0.0,
    "system_type": "",
    "system_kernel": "",
    "gpu_name": "N/A",
    "gpu_usage": 0.0,
    "root_disk_total_gb": 0.0,
    "root_disk_used_gb": 0.0
}

# ================= 常量与全局变量 =================
GB_DIVISOR = 1024 ** 3
MB_DIVISOR = 1024 ** 2
PROGRAM_START_TIME = time.perf_counter()
system_data_lock = threading.Lock()
last_net_io = psutil.net_io_counters()
last_disk_io = psutil.disk_io_counters()
last_update_time = time.perf_counter()
last_gpu_update = 0

# ================= 状态码定义 =================
STATUS_CODES = {
    "SUCCESS": 200,
    "SERVER_ERROR": 500,
    "SERVICE_STOPPED": 503
}

# ================= 辅助函数 =================
def get_cpu_name():
    """获取CPU名称（ARM架构仅返回基于架构的通用名称）"""
    try:
        # Windows系统处理
        if platform.system() == "Windows":
            try:
                result = subprocess.run(
                    ['wmic', 'cpu', 'get', 'name', '/value'],
                    capture_output=True, text=True, timeout=2
                )
                if result.returncode == 0 and result.stdout.strip():
                    match = re.search(r'Name=([^\n]+)', result.stdout)
                    if match:
                        return match.group(1).strip()
            except Exception as e:
                logger.debug(f"Windows wmic获取CPU名称失败: {e}")
            
            try:
                result = subprocess.run(
                    ['powershell', '-Command', 'Get-WmiObject Win32_Processor | Select-Object -ExpandProperty Name'],
                    capture_output=True, text=True, timeout=2
                )
                if result.returncode == 0 and result.stdout.strip():
                    return result.stdout.strip()
            except Exception as e:
                logger.debug(f"Windows Powershell获取CPU名称失败: {e}")
        
        elif platform.system() == "Linux":
            machine_arch = platform.machine()
            is_arm = machine_arch in ["armv7l", "aarch64", "arm64", "armv8l", "armv6l"]
            logger.debug(f"架构: {machine_arch}, 是否为ARM: {is_arm}")

            if is_arm:
                arch_to_name = {
                    "aarch64": "ARMv8 Processor",
                    "arm64": "ARMv8 Processor",
                    "armv8l": "ARMv8 Processor",
                    "armv7l": "ARMv7 Processor",
                    "armv6l": "ARMv6 Processor"
                }
                return arch_to_name.get(machine_arch, f"ARM Processor ({machine_arch})")
            
            else:
                if os.path.exists('/proc/cpuinfo'):
                    with open('/proc/cpuinfo', 'r', encoding='utf-8') as f:
                        content = f.read()
                        model_match = re.search(r'model name\s*:\s*(.+)', content)
                        if model_match:
                            return model_match.group(1).strip()
                
                try:
                    result = subprocess.run(
                        ['lscpu'], capture_output=True, text=True, timeout=2
                    )
                    if result.returncode == 0:
                        model_match = re.search(r'Model name:\s*(.+)', result.stdout)
                        if model_match:
                            return model_match.group(1).strip()
                except Exception as e:
                    logger.debug(f"lscpu获取CPU名称失败: {e}")
        
        # macOS系统处理
        elif platform.system() == "Darwin":
            try:
                result = subprocess.run(
                    ['sysctl', '-n', 'machdep.cpu.brand_string'],
                    capture_output=True, text=True, timeout=2
                )
                if result.returncode == 0 and result.stdout.strip():
                    return result.stdout.strip()
            except Exception as e:
                logger.debug(f"macOS获取CPU名称失败: {e}")
    
    except Exception as e:
        logger.error(f"获取CPU名称失败: {e}")
    
    # 最终fallback
    fallback = platform.processor() or f"Unknown Processor ({platform.machine()})"
    return fallback

def get_gpu_info():
    gpu_name = "N/A"
    gpu_usage = 0.0
    
    try:
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
        
        elif platform.system() == "Linux":
            try:
                result = subprocess.run(
                    ['nvidia-smi', '--query-gpu=name,utilization.gpu', '--format=csv,noheader,nounits'],
                    capture_output=True, text=True, timeout=2
                )
                if result.returncode == 0 and result.stdout.strip():
                    gpu_info = result.stdout.splitlines()[0].split(',')
                    if len(gpu_info) >= 2:
                        gpu_name = gpu_info[0].strip()
                        gpu_usage = float(gpu_info[1].strip())
                    return gpu_name, gpu_usage
            except:
                pass
            
            if platform.machine() in ["armv7l", "aarch64", "arm64"]:
                if os.path.exists("/proc/device-tree/model"):
                    try:
                        with open("/proc/device-tree/model", "r", encoding="utf-8") as f:
                            model = f.read().strip()
                            if "RK3399" in model:
                                gpu_name = "Mali-T860MP4"
                            elif "RK3588" in model:
                                gpu_name = "Mali-G610"
                            elif "Raspberry Pi 4" in model:
                                gpu_name = "VideoCore VI"
                    except:
                        pass
        
        elif platform.system() == "Darwin":
            result = subprocess.run(
                ['system_profiler', 'SPDisplaysDataType'],
                capture_output=True, text=True, timeout=2
            )
            if result.returncode == 0:
                name_match = re.search(r'Chipset Model: (.+)', result.stdout)
                if name_match:
                    gpu_name = name_match.group(1).strip()
                gpu_usage = 0.0
    
    except Exception as e:
        logger.warning(f"获取GPU信息失败: {e}")
    
    return gpu_name, gpu_usage

def get_system_info():
    system = platform.system()
    system_type = ""
    kernel_version = ""
    
    try:
        if system == "Windows":
            kernel_version = platform.version()
            if not kernel_version:
                win_version = sys.getwindowsversion()
                kernel_version = f"{win_version.major}.{win_version.minor}.{win_version.build}"
            
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
                win_version = platform.win32_ver()
                system_type = f"Windows {win_version[0]}" if win_version[0] else "Windows"
        
        elif system == "Linux":
            if os.path.exists('/etc/os-release'):
                with open('/etc/os-release', 'r', encoding='utf-8') as f:
                    for line in f:
                        if line.startswith('PRETTY_NAME='):
                            system_type = line.split('=')[1].strip().strip('"')
                            break
                        elif line.startswith('NAME=') and not system_type:
                            system_type = line.split('=')[1].strip().strip('"')
            
            if not system_type:
                try:
                    result = subprocess.run(
                        ['lsb_release', '-d'], 
                        capture_output=True, text=True, timeout=2
                    )
                    if result.returncode == 0:
                        match = re.search(r'Description:\s*(.+)', result.stdout)
                        if match:
                            system_type = match.group(1).strip()
                except:
                    system_type = "Linux"
            
            kernel_version = platform.release()
        
        elif system == "Darwin":
            try:
                result = subprocess.run(
                    ['sw_vers', '-productName'], 
                    capture_output=True, text=True, timeout=2
                )
                product_name = result.stdout.strip() if result.returncode == 0 else "macOS"
                
                result_ver = subprocess.run(
                    ['sw_vers', '-productVersion'], 
                    capture_output=True, text=True, timeout=2
                )
                version = result_ver.stdout.strip() if result_ver.returncode == 0 else ""
                system_type = f"{product_name} {version}".strip()
            except:
                system_type = "macOS"
            kernel_version = platform.release()
        
        else:
            system_type = system
            kernel_version = platform.release()
    
    except Exception as e:
        logger.error(f"获取系统信息失败: {e}")
        system_type = system
        kernel_version = platform.release()
    
    return system_type, kernel_version

def detect_virtual_machine():
    try:
        system = platform.system()
        manufacturer = platform.uname().system.lower()

        if any(keyword in manufacturer for keyword in ["vmware", "virtual", "kvm", "qemu", "xen", "hyperv"]):
            return True

        if system == "Linux":
            if os.path.exists("/proc/cpuinfo"):
                with open("/proc/cpuinfo", "r", encoding="utf-8") as f:
                    if "hypervisor" in f.read().lower():
                        return True
            
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
            
            if os.path.exists("/proc/modules"):
                with open("/proc/modules", "r", encoding="utf-8") as f:
                    modules = f.read().lower()
                    if "vboxguest" in modules or "vmw_balloon" in modules or "xen_" in modules:
                        return True
            
            try:
                result = subprocess.run(
                    ["dmidecode", "-s", "system-product-name"],
                    capture_output=True, text=True, timeout=2, check=True
                )
                output = result.stdout.lower()
                if any(keyword in output for keyword in ["vmware", "virtualbox", "kvm", "qemu"]):
                    return True
            except:
                pass
        
        elif system == "Windows":
            try:
                result = subprocess.run(
                    ["wmic", "computersystem", "get", "manufacturer"],
                    capture_output=True, text=True, timeout=2, check=True
                )
                output = result.stdout.lower()
                if any(keyword in output for keyword in ["vmware", "innotek", "xen", "qemu"]):
                    return True
            except:
                pass
            
            try:
                result = subprocess.run(
                    ["wmic", "bios", "get", "manufacturer"],
                    capture_output=True, text=True, timeout=2, check=True
                )
                output = result.stdout.lower()
                if any(keyword in output for keyword in ["vmware", "virtualbox", "xen", "qemu"]):
                    return True
            except:
                pass
        
        elif system == "Darwin":
            try:
                result = subprocess.run(
                    ["sysctl", "-n", "machdep.cpu.features"],
                    capture_output=True, text=True, timeout=2, check=True
                )
                if "hypervisor" in result.stdout.lower():
                    return True
            except:
                pass
        
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
        
        return False
    
    except Exception as e:
        logger.error(f"虚拟机检测失败: {e}")
        return False

# ================= 监控线程 =================
def system_monitor_thread():
    global system_data, last_net_io, last_disk_io, last_update_time, last_gpu_update
    
    try:
        with system_data_lock:
            system_data["cpu_name"] = get_cpu_name()
            system_data["cpu_arch"] = platform.machine()
            system_data["is_vm"] = detect_virtual_machine()
            system_data["cpu_cores"] = psutil.cpu_count(logical=True)
            
            cpu_freq = psutil.cpu_freq()
            if cpu_freq:
                system_data["cpu_base_freq_ghz"] = round(cpu_freq.max / 1000, 2)
            
            system_type, kernel_version = get_system_info()
            system_data["system_type"] = system_type
            system_data["system_kernel"] = kernel_version
            
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
    
    while not SERVICE_SHUTDOWN.is_set():
        try:
            current_time = time.perf_counter()
            time_diff = max(current_time - last_update_time, 1e-6)
            
            with system_data_lock:
                system_data["cpu_usage"] = psutil.cpu_percent(interval=0.1)
                
                mem = psutil.virtual_memory()
                system_data["memory_total_gb"] = mem.total / GB_DIVISOR
                system_data["memory_used_gb"] = mem.used / GB_DIVISOR
                
                system_data["system_uptime_hr"] = (time.time() - psutil.boot_time()) / 3600
                
                current_net_io = psutil.net_io_counters()
                system_data["net_total_sent_gb"] = current_net_io.bytes_sent / GB_DIVISOR
                system_data["net_total_recv_gb"] = current_net_io.bytes_recv / GB_DIVISOR
                system_data["net_sent_rate_mbps"] = (
                    (current_net_io.bytes_sent - last_net_io.bytes_sent) * 8
                ) / MB_DIVISOR / time_diff
                system_data["net_recv_rate_mbps"] = (
                    (current_net_io.bytes_recv - last_net_io.bytes_recv) * 8
                ) / MB_DIVISOR / time_diff
                last_net_io = current_net_io
                
                current_disk_io = psutil.disk_io_counters()
                system_data["disk_read_rate_mbs"] = (
                    current_disk_io.read_bytes - last_disk_io.read_bytes
                ) / MB_DIVISOR / time_diff
                system_data["disk_write_rate_mbs"] = (
                    current_disk_io.write_bytes - last_disk_io.write_bytes
                ) / MB_DIVISOR / time_diff
                last_disk_io = current_disk_io
                last_update_time = current_time
                
                current_time_sec = time.time()
                if config["monitor_gpu"] and current_time_sec - last_gpu_update > 5:
                    gpu_name, gpu_usage = get_gpu_info()
                    system_data["gpu_name"] = gpu_name
                    system_data["gpu_usage"] = gpu_usage
                    last_gpu_update = current_time_sec
                elif not config["monitor_gpu"]:
                    system_data["gpu_name"] = "Monitoring Disabled"
                    system_data["gpu_usage"] = 0.0
                
                root_disk = psutil.disk_usage('/')
                system_data["root_disk_total_gb"] = root_disk.total / GB_DIVISOR
                system_data["root_disk_used_gb"] = root_disk.used / GB_DIVISOR
                
        except Exception as e:
            logger.error(f"系统监控线程错误: {e}", exc_info=True)
        # 关键修改：使用带超时的wait替代sleep，确保能及时响应退出信号
        SERVICE_SHUTDOWN.wait(1)

# ================= API端点 =================
@api_app.route('/', methods=['GET'])
def get_system_status():
    if SERVICE_SHUTDOWN.is_set():
        return jsonify({
            "status": "error",
            "code": STATUS_CODES["SERVICE_STOPPED"],
            "message": "服务已停止"
        }), STATUS_CODES["SERVICE_STOPPED"]
    
    program_uptime_hours = (time.perf_counter() - PROGRAM_START_TIME) / 3600
    
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
    
    response_data = {
        "status": "success",
        "code": STATUS_CODES["SUCCESS"],
        "system_status": system_status
    }
    
    return jsonify(response_data), response_data["code"]

# ================= 主程序 =================
def run_api_server():
    """启动API服务"""
    global server
    
    # 设置信号处理器
    setup_signal_handlers()
    
    monitor_thread = threading.Thread(target=system_monitor_thread, daemon=True)
    monitor_thread.start()
    
    api_port = config["api_port"]
    
    try:
        from waitress import serve
        logger.info(f"使用Waitress启动API服务: http://localhost:{api_port}")
        
        # 关键修改：使用单独的线程运行Waitress，避免阻塞主线程
        def run_waitress():
            try:
                serve(api_app, host='0.0.0.0', port=api_port, threads=4)
            except Exception as e:
                logger.error(f"Waitress服务器错误: {e}")
        
        waitress_thread = threading.Thread(target=run_waitress, daemon=True)
        waitress_thread.start()
        
        # 主线程等待退出信号
        while not SERVICE_SHUTDOWN.is_set():
            time.sleep(0.5)
            
        logger.info("接收到退出信号，正在关闭Waitress服务器...")
        
    except ImportError:
        logger.warning("Waitress未安装，使用Flask内置服务器")
        logger.info(f"使用Flask内置服务器启动API服务: http://localhost:{api_port}")
        
        def run_flask():
            api_app.run(host='0.0.0.0', port=api_port, threaded=True, use_reloader=False)
        
        flask_thread = threading.Thread(target=run_flask, daemon=True)
        flask_thread.start()
        
        while not SERVICE_SHUTDOWN.is_set():
            time.sleep(1)

if __name__ == '__main__':
    run_api_server()
