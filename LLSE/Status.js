// Status 服务器状态监控插件
const statusPlugin = {
    config: null,
    apiProcess: null,
    tickCount: 0,
    currentTPS: 20,
    lastUpdate: Date.now(),

    // 初始化函数
    init() {
        // 确保配置文件存在
        this.ensureConfigFile();
        
        // 加载配置
        this.loadConfig();
        
        // 启动API服务
        this.startApiService();
        
        // 显示配置信息
        this.logConfigInfo();
        
        // 设置性能监控
        this.setupPerformanceMonitoring();
        
        // 启动游戏API服务
        this.setupGameApiServer();
    },

    // 确保配置文件存在
    ensureConfigFile() {
        const configPath = "plugins/Status/data/config.json";
        
        if (!File.exists(configPath)) {
            logger.info("Creating default configuration...");
            File.createDir("plugins/Status/data");
            
            const defaultConfig = {
    "api_port": 8000,
    "web_port": 8001,
    "web_enabled": true,
    "web_root": "web",
    "game_api_port": 8080,
    "game_api": "http://127.0.0.1:8080/",
    "game_update_interval": 3,
    "game_api_timeout": 10,
    "node": "Node1",
    "bg": "https://example.com/background.jpg",
    "footer": "Server Monitor v1.0",
    "log_enabled": true,
    "wsgi_server": "waitress",
    "monitor_cpu": true,
    "monitor_memory": true,
    "monitor_network": true,
    "monitor_disk": true,
    "monitor_gpu": false
            };
            
            File.writeTo(configPath, JSON.stringify(defaultConfig, null, 4));
            logger.info(`Default config created: ${configPath}`);
        }
    },

    // 加载配置文件
    loadConfig() {
        const configPath = "plugins/Status/data/config.json";
        const configContent = File.readFrom(configPath);
        this.config = JSON.parse(configContent);
    },

    // 启动API服务
    startApiService() {
        const apiServicePath = "plugins/Status/data/api_service.exe";
        
        if (File.exists(apiServicePath)) {
            logger.info("Starting API service...");
            
            // 使用start命令启动API服务
            const startCommand = `start "" "${apiServicePath}"`;
            
            // 执行启动命令
            system.cmd(startCommand, (exitCode, output) => {
                if (exitCode === 0) {
                    logger.info("API service started successfully");
                } else {
                    logger.error(`API service failed to start, code: ${exitCode}`);
                    logger.error(`Error: ${output}`);
                }
            });
        } else {
            logger.error(`API service not found: ${apiServicePath}`);
        }
    },

    // 记录配置信息
    logConfigInfo() {
        logger.info("===== Status Configuration =====");
        logger.info(`API Port: ${this.config.api_port}`);
        
        if (this.config.web_enabled) {
            logger.info(`Web Interface: http://localhost:${this.config.web_port}/`);
        } else {
            logger.info("Web Interface: Disabled");
        }
        
        logger.info(`Data Update Interval: ${this.config.game_update_interval}s`);
        logger.info("===============================");
    },

    // 设置性能监控
    setupPerformanceMonitoring() {
        mc.listen("onTick", () => {
            this.tickCount++;
            
            // 每秒更新一次TPS
            const now = Date.now();
            if (now - this.lastUpdate >= 1000) {
                this.currentTPS = Math.min(20, this.tickCount);
                this.tickCount = 0;
                this.lastUpdate = now;
            }
        });
    },

    // 启动游戏API服务
    setupGameApiServer() {
        const port = this.config.game_api_port || 8080;
        this.server = new HttpServer();

        // 根路径返回服务器信息
        this.server.onGet("/", (req, res) => {
            try {
                const info = this.getServerStatus();
                res.setHeader("Content-Type", "application/json");
                res.status = 200;
                res.body = JSON.stringify(info, null, 2);
            } catch (e) {
                res.status = 500;
                res.body = `Error: ${e.message}`;
            }
        });

        // 启动服务器
        this.server.listen("0.0.0.0", port);
        logger.info(`Server status API available at port ${port}`);
    },

    // 获取服务器状态
    getServerStatus() {
        const players = mc.getOnlinePlayers();
        
        return {
            maxPlayers: this.getMaxPlayers(),
            onlinePlayers: players.map(p => p.name),
            playerCount: players.length,
            protocol: mc.getServerProtocolVersion(),
            time: mc.getTime(0), // 游戏内时间
            tps: this.currentTPS,
            version: mc.getBDSVersion(),
            weather: this.getWeatherName(mc.getWeather())
        };
    },

    // 获取最大玩家数
    getMaxPlayers() {
        try {
            const conf = new IniConfigFile("server.properties");
            return conf.getInt("", "max-players", 100);
        } catch (e) {
            return 100;
        }
    },

    getWeatherName(weatherId) {
        return ["Clear", "Rain", "Thunderstorm"][weatherId] || "Unknown";
    }
};

// 插件入口
mc.listen("onServerStarted", () => {
    statusPlugin.init();
});
