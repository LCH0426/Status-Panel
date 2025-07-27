from flask import Flask, jsonify, send_from_directory, abort
from flask_cors import CORS
import psutil
import time
import threading
import requests
import json
import os
import sys
import logging
from logging.handlers import RotatingFileHandler
import datetime
import signal
import atexit
import platform
import subprocess
import re
import shutil

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
    "web_port": 8001,     # Web服务器端口
    "web_enabled": True,  # 是否启用Web服务器
    "web_root": "web",    # Web服务器根目录
    "game_api_port": 8080,
    "game_api": "http://127.0.0.1:8080/",  # 游戏API地址
    "game_update_interval": 3,  # 游戏数据更新间隔
    "game_api_timeout": 10,     # 游戏API连接超时时间(秒)
    "node": "Node1",            # 节点名称
    "bg": "https://example.com/background.jpg",  # 背景图片URL
    "footer": "Server Monitor v1.0",  # 页脚信息
    "log_enabled": True,        # 是否启用日志
    "wsgi_server": "waitress",   # WSGI服务器类型 (waitress/gunicorn)
    # 新增监控项开关
    "monitor_cpu": True,        # 是否监控CPU
    "monitor_memory": True,     # 是否监控内存
    "monitor_network": True,    # 是否监控网络（上传+下载）
    "monitor_disk": True,       # 是否监控磁盘
    "monitor_gpu": False         # 是否监控GPU
}

def load_config():
    """加载配置文件，优先使用程序所在目录的配置"""
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
                print(f"已复制默认配置文件到: {app_dir_config}")
                config_path = app_dir_config
            except Exception as e:
                print(f"复制配置文件失败: {e}")
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
                print(f"加载配置文件: {config_path}")
                return final_config
        else:
            # 创建默认配置文件到程序目录，使用UTF-8编码
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(DEFAULT_CONFIG, f, indent=4, ensure_ascii=False)
            print(f"创建默认配置文件: {config_path}")
            return DEFAULT_CONFIG
    except Exception as e:
        print(f"配置文件加载错误: {e}")
        return DEFAULT_CONFIG

# 先加载配置
config = load_config()

# ================= 配置日志 =================
def setup_logging(log_enabled):
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    
    # 控制台日志处理器 (始终启用)
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(logging.Formatter(
        '%(asctime)s - %(levelname)s - %(message)s'
    ))
    logger.addHandler(console_handler)
    
    # 文件日志处理器 (根据配置决定是否启用)
    if log_enabled:
        # 日志目录在程序目录下
        log_dir = os.path.join(APP_DIR, "logs")
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)
        
        log_file = os.path.join(log_dir, "api_service.log")
        
        file_handler = RotatingFileHandler(
            log_file, maxBytes=5*1024*1024, backupCount=3, encoding='utf-8'
        )
        file_handler.setFormatter(logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        ))
        logger.addHandler(file_handler)
    
    return logger

# 现在可以初始化日志系统
logger = setup_logging(config["log_enabled"])
logger.info(f"日志系统初始化完成，文件日志{'已启用' if config['log_enabled'] else '已禁用'}")
logger.info(f"程序目录: {APP_DIR}")

# ================= 全局变量 =================
# 游戏API连接状态
GAME_API_STATUS = {
    "last_success": time.time(),  # 上次成功连接时间
    "last_attempt": time.time(),  # 上次尝试连接时间
    "consecutive_failures": 0,    # 连续失败次数
    "active": True                # 服务是否活跃
}

# 服务停止标志
SERVICE_SHUTDOWN = threading.Event()

# ================= 信号处理函数 =================
def handle_exit_signal(signum, frame):
    """处理退出信号"""
    logger.info(f"接收到退出信号 {signum}，程序即将退出")
    SERVICE_SHUTDOWN.set()
    GAME_API_STATUS["active"] = False

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

# ================= 创建Web应用 =================
if config["web_enabled"]:
    # Web目录在程序目录下
    web_root = os.path.join(APP_DIR, config["web_root"])
    logger.info(f"Web根目录: {web_root}")
    
    # 确保Web目录存在
    if not os.path.exists(web_root):
        logger.warning(f"Web目录 '{web_root}' 不存在，创建空目录")
        os.makedirs(web_root, exist_ok=True)
    
    web_app = Flask(__name__, static_folder=web_root)
    
    @web_app.route('/', defaults={'path': ''})
    @web_app.route('/<path:path>')
    def serve_static(path):
        """提供静态文件服务"""
        # 检查服务是否已停止
        if not GAME_API_STATUS["active"] or SERVICE_SHUTDOWN.is_set():
            return "<h1>服务已停止</h1><p>程序正在退出</p>", 503
        
        # 处理根路径
        if path == "" or not os.path.exists(os.path.join(web_root, path)):
            # 对于SPA应用，所有未知路径返回index.html
            return send_from_directory(web_root, 'index.html')
        
        # 检查文件是否存在
        file_path = os.path.join(web_root, path)
        if os.path.exists(file_path) and os.path.isfile(file_path):
            return send_from_directory(web_root, path)
        
        # 文件不存在
        return abort(404)

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
    "cpu_base_freq_ghz": 0.0,
    "memory_total_int_gb": 0,
    "system_version": "",
    "gpu_name": "N/A",
    "gpu_usage": 0.0
}

# 游戏服务器数据缓存
game_server_data = {
    "playerCount": 0,
    "maxPlayers": 100,
    "onlinePlayers": [],
    "tps": 20,
    "version": "v1.21.80",
    "protocol": 800,
    "weather": "Rain",
    "time": 7701,
    "last_updated": 0,  # 最后更新时间戳
    "status": "offline"  # 添加服务器状态字段
}

# ================= 常量与全局变量 =================
GB_DIVISOR = 1024 ** 3
MB_DIVISOR = 1024 ** 2
PROGRAM_START_TIME = time.perf_counter()

# 线程锁
system_data_lock = threading.Lock()
game_data_lock = threading.Lock()
api_status_lock = threading.Lock()

# 网络与磁盘IO记录
last_net_io = psutil.net_io_counters()
last_disk_io = psutil.disk_io_counters()
last_update_time = time.perf_counter()
last_gpu_update = 0  # 上次更新GPU信息的时间

# 游戏API配置（从配置文件读取）
GAME_API_URL = config["game_api"]
GAME_UPDATE_INTERVAL = config["game_update_interval"]
GAME_API_TIMEOUT = config["game_api_timeout"]

# ================= 状态码定义 =================
STATUS_CODES = {
    "SUCCESS": 200,
    "SERVER_ERROR": 500,
    "GAME_SERVER_DOWN": 503,
    "SERVICE_STOPPED": 503
}

# ================= 辅助函数 =================
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

# ================= 监控线程 =================
def system_monitor_thread():
    """实时更新系统监控数据（每秒执行）"""
    global system_data, last_net_io, last_disk_io, last_update_time, last_gpu_update
    
    # 初始化CPU核心数和频率
    try:
        with system_data_lock:
            # 获取CPU核心数量
            system_data["cpu_cores"] = psutil.cpu_count(logical=True)
            
            # 获取CPU最大频率（GHz）
            cpu_freq = psutil.cpu_freq()
            if cpu_freq:
                system_data["cpu_base_freq_ghz"] = round(cpu_freq.max / 1000, 2)
            
            # 获取系统版本信息
            system_data["system_version"] = f"{platform.system()} {platform.release()} {platform.version()}"
    except Exception as e:
        logger.error(f"初始化系统信息失败: {e}", exc_info=True)
    
    while GAME_API_STATUS["active"] and not SERVICE_SHUTDOWN.is_set():  # 检查退出标志
        try:
            current_time = time.perf_counter()
            time_diff = max(current_time - last_update_time, 1e-6)  # 防止除零
            
            with system_data_lock:
                # 1. CPU监控
                if config["monitor_cpu"]:
                    system_data["cpu_usage"] = psutil.cpu_percent(interval=0.1)
                else:
                    system_data["cpu_usage"] = 0.0
                
                # 2. 内存监控
                if config["monitor_memory"]:
                    mem = psutil.virtual_memory()
                    system_data["memory_total_gb"] = mem.total / GB_DIVISOR
                    system_data["memory_used_gb"] = mem.used / GB_DIVISOR
                    
                    # 计算内存整数GB值（
                    memory_total_gb = mem.total / GB_DIVISOR
                    system_data["memory_total_int_gb"] = int(memory_total_gb) + (1 if memory_total_gb % 1 > 0 else 0)
                else:
                    system_data["memory_total_gb"] = 0.0
                    system_data["memory_used_gb"] = 0.0
                    system_data["memory_total_int_gb"] = 0
                
                system_data["system_uptime_hr"] = (time.time() - psutil.boot_time()) / 3600
                
                # 3. 网络监控
                current_net_io = psutil.net_io_counters()
                
                # 总是更新总量（即使监控关闭）
                system_data["net_total_sent_gb"] = current_net_io.bytes_sent / GB_DIVISOR
                system_data["net_total_recv_gb"] = current_net_io.bytes_recv / GB_DIVISOR
                
                if config["monitor_network"]:
                    # 计算实时速率
                    system_data["net_sent_rate_mbps"] = (
                        (current_net_io.bytes_sent - last_net_io.bytes_sent) * 8
                    ) / MB_DIVISOR / time_diff
                    system_data["net_recv_rate_mbps"] = (
                        (current_net_io.bytes_recv - last_net_io.bytes_recv) * 8
                    ) / MB_DIVISOR / time_diff
                else:
                    # 监控关闭时设为0
                    system_data["net_sent_rate_mbps"] = 0.0
                    system_data["net_recv_rate_mbps"] = 0.0
                
                last_net_io = current_net_io
                
                # 4. 磁盘监控
                current_disk_io = psutil.disk_io_counters()
                if config["monitor_disk"]:
                    system_data["disk_read_rate_mbs"] = (
                        current_disk_io.read_bytes - last_disk_io.read_bytes
                    ) / MB_DIVISOR / time_diff
                    system_data["disk_write_rate_mbs"] = (
                        current_disk_io.write_bytes - last_disk_io.write_bytes
                    ) / MB_DIVISOR / time_diff
                else:
                    system_data["disk_read_rate_mbs"] = 0.0
                    system_data["disk_write_rate_mbs"] = 0.0
                
                last_disk_io = current_disk_io
                last_update_time = current_time
                
                # 5. GPU监控（每5秒更新一次）
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
                
        except Exception as e:
            logger.error(f"系统监控线程错误: {e}", exc_info=True)
        time.sleep(1)

def game_data_thread():
    """定期更新游戏服务器数据"""
    global GAME_API_STATUS
    
    while GAME_API_STATUS["active"] and not SERVICE_SHUTDOWN.is_set():  # 检查退出标志
        current_time = time.time()
        
        with api_status_lock:
            GAME_API_STATUS["last_attempt"] = current_time
        
        try:
            response = requests.get(GAME_API_URL, timeout=2)
            if response.status_code == 200:
                data = response.json()
                with game_data_lock:
                    game_server_data.update(data)
                    game_server_data["last_updated"] = current_time
                    game_server_data["status"] = "online"
                
                # 更新连接状态
                with api_status_lock:
                    GAME_API_STATUS["last_success"] = current_time
                    GAME_API_STATUS["consecutive_failures"] = 0
            else:
                # 更新失败状态
                with api_status_lock:
                    GAME_API_STATUS["consecutive_failures"] += 1
                    if current_time - GAME_API_STATUS["last_success"] > GAME_API_TIMEOUT:
                        logger.error(f"游戏API连接失败超过{GAME_API_TIMEOUT}秒，程序即将退出")
                        GAME_API_STATUS["active"] = False
                        SERVICE_SHUTDOWN.set()  # 设置退出标志
                        return  # 退出线程
                
                with game_data_lock:
                    game_server_data["status"] = "offline"
        except Exception as e:
            logger.error(f"游戏API请求失败: {e}", exc_info=True)
            
            # 更新失败状态
            with api_status_lock:
                GAME_API_STATUS["consecutive_failures"] += 1
                if current_time - GAME_API_STATUS["last_success"] > GAME_API_TIMEOUT:
                    logger.error(f"游戏API连接失败超过{GAME_API_TIMEOUT}秒，程序即将退出")
                    GAME_API_STATUS["active"] = False
                    SERVICE_SHUTDOWN.set()  # 设置退出标志
                    return  # 退出线程
            
            with game_data_lock:
                game_server_data["status"] = "offline"
        
        # 检查连接超时
        with api_status_lock:
            if current_time - GAME_API_STATUS["last_success"] > GAME_API_TIMEOUT:
                logger.error(f"游戏API连接失败超过{GAME_API_TIMEOUT}秒，程序即将退出")
                GAME_API_STATUS["active"] = False
                SERVICE_SHUTDOWN.set()  # 设置退出标志
                return  # 退出线程
        
        time.sleep(GAME_UPDATE_INTERVAL)

# ================= API端点 =================
@api_app.route('/', methods=['GET'])
def get_aggregated_status():
    """聚合API：返回系统状态+游戏服务器状态"""
    # 检查服务是否已停止
    if not GAME_API_STATUS["active"] or SERVICE_SHUTDOWN.is_set():
        return jsonify({
            "status": "error",
            "code": STATUS_CODES["SERVICE_STOPPED"],
            "message": f"服务已停止：游戏API连接失败超过{GAME_API_TIMEOUT}秒或收到退出信号"
        }), STATUS_CODES["SERVICE_STOPPED"]
    
    # 实时计算程序运行时间
    program_uptime_hours = (time.perf_counter() - PROGRAM_START_TIME) / 3600
    
    # 获取系统数据
    try:
        with system_data_lock:
            system_status = {
                "cpu_usage_percent": round(system_data["cpu_usage"], 1),
                "memory_total_gb": round(system_data["memory_total_gb"], 2),
                "memory_used_gb": round(system_data["memory_used_gb"], 2),
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
                "memory_total_int_gb": system_data["memory_total_int_gb"],
                "system_version": system_data["system_version"],
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
    
    # 获取游戏数据
    try:
        with game_data_lock:
            game_status = {k: v for k, v in game_server_data.items() if k != "last_updated"}
            
            # 根据游戏服务器状态设置HTTP状态码
            http_status = STATUS_CODES["SUCCESS"]
            if game_server_data["status"] == "offline":
                http_status = STATUS_CODES["GAME_SERVER_DOWN"]
    except Exception as e:
        logger.error(f"获取游戏状态失败: {e}", exc_info=True)
        return jsonify({
            "status": "error",
            "code": STATUS_CODES["SERVER_ERROR"],
            "message": "Failed to retrieve game status"
        }), STATUS_CODES["SERVER_ERROR"]
    
    # 成功响应
    response = jsonify({
        "status": "success",
        "code": http_status,
        "system_status": system_status,
        "game_server_status": game_status,
        "api_status": {
            "last_success": GAME_API_STATUS["last_success"],
            "last_attempt": GAME_API_STATUS["last_attempt"],
            "consecutive_failures": GAME_API_STATUS["consecutive_failures"],
            "active": GAME_API_STATUS["active"]
        },
        # 新增配置信息
        "config": {
            "node": config["node"],
            "bg": config["bg"],
            "footer": config["footer"]
        }
    })
    
    return response, http_status

# ================= WSGI 入口点 =================
def create_app():
    """创建WSGI应用（用于Gunicorn等服务器）"""
    # 启动监控线程
    threading.Thread(target=system_monitor_thread, daemon=True).start()
    threading.Thread(target=game_data_thread, daemon=True).start()
    
    return api_app

# ================= 主程序 =================
def run_servers():
    """启动所有服务"""
    # 启动监控线程
    threading.Thread(target=system_monitor_thread, daemon=True).start()
    threading.Thread(target=game_data_thread, daemon=True).start()
    
    # 根据配置选择WSGI服务器
    wsgi_server = config.get("wsgi_server", "waitress").lower()
    api_port = config["api_port"]
    web_port = config["web_port"]
    
    if wsgi_server == "gunicorn":
        try:
            from gunicorn.app.base import BaseApplication
            
            class GunicornApp(BaseApplication):
                def __init__(self, app, options=None):
                    self.options = options or {}
                    self.application = app
                    super().__init__()
                
                def load_config(self):
                    config = {key: value for key, value in self.options.items()
                              if key in self.cfg.settings and value is not None}
                    for key, value in config.items():
                        self.cfg.set(key.lower(), value)
                
                def load(self):
                    return self.application
            
            # 启动API服务
            api_options = {
                'bind': f'0.0.0.0:{api_port}',
                'workers': 2,
                'threads': 4,
                'timeout': 30,
                'loglevel': 'info'
            }
            api_gunicorn = GunicornApp(api_app, api_options)
            threading.Thread(target=api_gunicorn.run, daemon=True).start()
            logger.info(f"使用Gunicorn启动API服务: http://localhost:{api_port}")
            
            # 启动Web服务器
            if config["web_enabled"]:
                web_options = {
                    'bind': f'0.0.0.0:{web_port}',
                    'workers': 1,
                    'threads': 2,
                    'timeout': 30,
                    'loglevel': 'info'
                }
                web_gunicorn = GunicornApp(web_app, web_options)
                threading.Thread(target=web_gunicorn.run, daemon=True).start()
                logger.info(f"使用Gunicorn启动Web服务: http://localhost:{web_port}")
        
        except ImportError:
            logger.warning("Gunicorn未安装，使用内置服务器")
            wsgi_server = "waitress"
    
    if wsgi_server == "waitress":
        try:
            from waitress import serve
            
            # 启动API服务
            threading.Thread(
                target=lambda: serve(api_app, host='0.0.0.0', port=api_port),
                daemon=True
            ).start()
            logger.info(f"使用Waitress启动API服务: http://localhost:{api_port}")
            
            # 启动Web服务器
            if config["web_enabled"]:
                threading.Thread(
                    target=lambda: serve(web_app, host='0.0.0.0', port=web_port),
                    daemon=True
                ).start()
                logger.info(f"使用Waitress启动Web服务: http://localhost:{web_port}")
        
        except ImportError:
            logger.warning("Waitress未安装，使用Flask内置服务器")
            # 启动API服务
            threading.Thread(
                target=lambda: api_app.run(
                    host='0.0.0.0', 
                    port=api_port,
                    threaded=True
                ),
                daemon=True
            ).start()
            logger.info(f"使用Flask内置服务器启动API服务: http://localhost:{api_port}")
            
            # 启动Web服务器
            if config["web_enabled"]:
                threading.Thread(
                    target=lambda: web_app.run(
                        host='0.0.0.0', 
                        port=web_port,
                        threaded=True
                    ),
                    daemon=True
                ).start()
                logger.info(f"使用Flask内置服务器启动Web服务: http://localhost:{web_port}")
    
    # 保持主线程运行，直到服务停止或收到退出信号
    try:
        while not SERVICE_SHUTDOWN.is_set() and GAME_API_STATUS["active"]:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("接收到中断信号，程序即将退出")
        SERVICE_SHUTDOWN.set()
    finally:
        # 服务停止时记录日志
        if not GAME_API_STATUS["active"]:
            logger.error(f"游戏API连接失败超过{GAME_API_TIMEOUT}秒，程序退出")
        
        logger.info("等待线程退出...")
        time.sleep(2)  # 给线程一点时间退出
        
        logger.info("程序退出")
        # 确保程序退出
        os._exit(0)

if __name__ == '__main__':
    run_servers()
