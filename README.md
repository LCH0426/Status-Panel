本插件利用LSE和Python建立了一个网页监控面板，可以实时查看系统状态，游戏人数等等
在线演示​
使用方法:
1.从本页面下载Status.zip
2.解压Status.zip至plugins
3.启动服务器
服务器启动时会额外启动一个程序，它将在游戏API断开连接10秒后关闭
效果展示
1752365764928.webp​
配置文件：data/config.json
JavaScript：
{
    "api_port": 8000, //API使用的端口
    "web_port": 8001, //网页端口
    "web_enabled": true, //是否启用内置Web服务器
    "web_root": "web", //服务器根目录
    "game_api_port": 8080, //游戏API使用的端口
    "game_api": "http://127.0.0.1:8080/", //游戏API地址
    "game_update_interval": 3, //游戏API更新时间，单位:秒
    "game_api_timeout": 10, //游戏API超时时间，单位:秒
    "node": "Node1", //网页节点名称
    "bg": "https://example.com/background.jpg", //网页背景图片
    "footer": "Server Monitor v1.0", //网页页脚信息
    "log_enabled": true, //是否启用日志记录
    "wsgi_server": "waitress", //勿动
    "monitor_cpu": true, //是否监控CPU
    "monitor_memory": true, //是否监控内存
    "monitor_network": true, //是否监控网络
    "monitor_disk": true, //是否监控磁盘
    "monitor_gpu": false //是否监控GPU
}
API接口内容如下
JavaScript：
{
  "api_status": {  // API连接状态信息
    "active": true,  // 服务状态
    "consecutive_failures": 0,  // 连接失败次数
    "last_attempt": 1752359941.11088,  // 上次尝试连接时间戳
    "last_success": 1752359941.11088  // 上次成功连接时间戳
  },
  "code": 200,  // HTTP状态码
  "config": {  // 系统配置信息
    "bg": "https://example.com/background.jpg",  // 背景图片URL
    "footer": "Server Monitor v1.0",  // 页脚信息
    "node": "Node1"  // 节点名称
  },
  "game_server_status": {  // 游戏服务器状态信息
    "maxPlayers": 1000,  // 服务器最大玩家容量
    "onlinePlayers": [],  // 在线玩家列表
    "playerCount": 0,  // 当前在线玩家数量
    "protocol": 800,  // 游戏协议版本号
    "status": "online",  // 服务器状态（online/offline）
    "time": 7802,  // 游戏内时间（刻数）
    "tps": 20,  // 服务器TPS
    "version": "v1.21.80",  // 游戏版本号
    "weather": "Clear"  // 游戏内天气状况
  },
  "status": "success",  // 请求处理状态
  "system_status": {  // 系统资源状态信息
    "cpu_cores": 32,  // CPU核心数量
    "cpu_base_freq_ghz": 2.4,  // CPU基准频率（GHz）
    "cpu_usage_percent": 13.6,  // CPU使用率百分比
    "disk_read_rate_mbs": 0,  // 磁盘读取速率（MB/s）
    "disk_write_rate_mbs": 0.14,  // 磁盘写入速率（MB/s）
    "gpu_name": "NVIDIA GeForce RTX 4060 Laptop GPU",  // 显卡型号（仅限NVIDIA显卡）
    "gpu_usage_percent": 0,  // 显卡利用率百分比
    "memory_total_gb": 31.29,  // 总内存容量（GB，精确值）
    "memory_total_int_gb": 32,  // 总内存容量（GB，向上取整的整数）
    "memory_used_gb": 13.69,  // 已用内存量（GB）
    "net_download_rate_mbps": 0,  // 网络下载速率（Mbps）
    "net_total_download_gb": 0.124,  // 总下载数据量（GB）
    "net_total_upload_gb": 0.029,  // 总上传数据量（GB）
    "net_upload_rate_mbps": 0,  // 网络上传速率（Mbps）
    "program_uptime_hours": 0,  // 本监控程序运行时间（小时）
    "system_uptime_hours": 1.2,  // 系统运行时间（小时）
    "system_version": "Windows 11 10.0.26100"  // 操作系统版本信息
  }
}
如果你想在外网访问该面板，请为服务器开启相应端口，或者启用反向代理，并修改位于data/web/中的index.html的API配置，具体在680行
JavaScript：
    <script>
        // 配置信息
        const config = {
            apiUrl: "http://127.0.0.1:8000", //这里填写外网可以访问的地址
            refreshInterval: 1000, // 1秒
            maxDataPoints: 30 // 图表显示的最大数据点数
        };
