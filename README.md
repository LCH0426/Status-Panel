
本插件利用LSE和Python构建实时服务器监控系统，提供以下功能：

🖥️ 系统资源监控（CPU、内存、磁盘、网络）
👥 玩家在线状态统计
🕹️ 服务器运行指标（TPS、游戏时间、天气）
📊 动态数据可视化
🌐 Web访问面板（支持内网/外网访问）
安装方法
从项目页面下载Status.zip压缩包
解压至服务器plugins目录
启动游戏服务器
⚠️ ​​注意​​：监控程序会在检测到游戏API断开连接10秒后自动关闭

配置文件 (data/config.json)
{
    "api_port": 8000,           // API服务监听端口
    "web_port": 8001,           // 网页面板访问端口
    "web_enabled": true,        // 启用网页服务
    "web_root": "web",           // 网页文件存储目录
    "game_api_port": 8080,      // 游戏API通信端口
    "game_api": "http://127.0.0.1:8080/",  // 游戏API地址
    "game_update_interval": 3,  // 游戏数据更新间隔(秒)
    "game_api_timeout": 10,     // API请求超时时间(秒)
    "node": "Node1",            // 节点显示名称
    "bg": "https://example.com/background.jpg",  // 背景图URL
    "footer": "Server Monitor v1.0",   // 页脚显示文本
    "log_enabled": true,        // 启用操作日志记录
    "wsgi_server": "waitress",  // WSGI服务器类型(勿修改)
    "monitor_cpu": true,        // 启用CPU监控
    "monitor_memory": true,     // 启用内存监控
    "monitor_network": true,    // 启用网络监控
    "monitor_disk": true,       // 启用磁盘监控
    "monitor_gpu": false        // 启用GPU监控(需要NVIDIA显卡)
}
API接口数据结构
请求地址：http://127.0.0.1:8000 (默认)
响应示例：
{
  "api_status": {
    "active": true,             // API服务运行状态
    "consecutive_failures": 0,  // 连续失败请求计数
    "last_attempt": 1752359941, // 最后尝试时间戳
    "last_success": 1752359941  // 最后成功时间戳
  },
  "code": 200,                  // HTTP状态码
  "config": {                   // 当前生效配置
    "bg": "https://example.com/background.jpg",
    "footer": "Server Monitor v1.0",
    "node": "Node1"
  },
  "game_server_status": {       // 游戏服务器状态
    "maxPlayers": 1000,         // 最大玩家容量
    "onlinePlayers": [],        // 在线玩家列表
    "playerCount": 0,           // 当前在线玩家数
    "protocol": 800,            // 游戏协议版本
    "status": "online",         // 服务器状态(online/offline)
    "time": 7802,               // 游戏内时间(刻)
    "tps": 20,                  // 服务器TPS
    "version": "v1.21.80",      // 游戏版本号
    "weather": "Clear"          // 当前天气
  },
  "status": "success",          // 请求处理状态
  "system_status": {            // 系统资源状态
    "cpu_cores": 32,            // CPU物理核心数
    "cpu_base_freq_ghz": 2.4,   // CPU基准频率
    "cpu_usage_percent": 13.6,  // CPU使用率百分比
    "disk_read_rate_mbs": 0,    // 磁盘读取速率(MB/s)
    "disk_write_rate_mbs": 0.14, // 磁盘写入速率(MB/s)
    "gpu_name": "NVIDIA GeForce RTX 4060 Laptop GPU", 
    "gpu_usage_percent": 0,     // GPU使用率百分比
    "memory_total_gb": 31.29,   // 总内存容量(GB)
    "memory_total_int_gb": 32,  // 取整内存容量(GB)
    "memory_used_gb": 13.69,    // 已用内存量(GB)
    "net_download_rate_mbps": 0, // 网络下载速率(Mbps)
    "net_total_download_gb": 0.124, // 总下载量(GB)
    "net_total_upload_gb": 0.029,  // 总上传量(GB)
    "net_upload_rate_mbps": 0,  // 网络上传速率(Mbps)
    "program_uptime_hours": 0,  // 监控程序运行时间(小时)
    "system_uptime_hours": 1.2, // 系统运行时间(小时)
    "system_version": "Windows 11 10.0.26100" // 操作系统版本
  }
}
关键字段说明：
字段路径	类型	描述
api_status.active	boolean	API服务是否运行
game_server_status.tps	integer	服务器每秒帧数
system_status.cpu_usage_percent	float	CPU实时使用率
system_status.memory_used_gb	float	内存使用量
system_status.net_download_rate_mbps	float	实时下载速度
外网访问配置
步骤：
​​开放防火墙端口​​：
在服务器防火墙开启8001端口（或自定义端口）
​​配置反向代理（可选）​​：
server {
  listen 80;
  server_name status.yourserver.com;
  
  location / {
     proxy_pass http://localhost:8001;
     proxy_set_header Host $host;
  }
}
​​修改前端配置​​：
编辑文件：data/web/index.html (第680行附近)
<script>
   // ======== API地址配置 ========
   const config = {
       apiUrl: "http://your-public-ip:8000", // 改为实际公网地址
       refreshInterval: 1000,               // 数据刷新频率(ms)
       maxDataPoints: 30                    // 图表显示点数
   };
</script>
项目打包指南
1. 安装必要依赖
pip install flask flask-cors psutil requests waitress gunicorn pyinstaller
2. 执行打包命令
pyinstaller api.spec
3. 获取可执行文件
打包生成的文件位于dist/目录，包含：

api.exe (Windows)
所有依赖库
配置文件模板
