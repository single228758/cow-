# KimiChat Plugin

chatgpt-on-wechat插件

基于 [cow_plugin_kimichat](https://github.com/LargeCupPanda/cow_plugin_kimichat) 修改，增加了图片识别和链接总结功能。

## 功能特点

- 多轮对话: 支持连续对话,上下文记忆
- 双聊模式: 支持群聊共享/私聊独立会话
- 文件解析: 支持多种格式文件的智能解析
- 图片识别: 支持图片内容智能识别描述
- 链接总结: 自动总结分享链接的核心内容
- 联网搜索: 支持实时联网信息查询
- 权限管理: 支持群组白名单管理

## 安装配置

1. 下载插件到 plugins 目录
2. 复制 config.json.template 为 config.json
3. 配置 refresh_token 和其他参数
4. 重启程序生效

## 配置详解

### 核心配置
```json
{
    "refresh_token": "YOUR_REFRESH_TOKEN",    // Kimi API令牌,必填
    "keyword": "k",                          // 触发前缀,如"k 你好"
    "reset_keyword": "kimi重置会话",          // 重置会话命令
    "toggle_search_keyword": "kimi切换联网",  // 切换联网开关命令
}
```

### 群组和权限
```json
{
    "group_names": ["测试群"],      // 开启自动总结的群组列表
    "allowed_groups": [],          // 允许使用插件的群组白名单,为空则允许所有群组
    "auto_summary": true,          // 群聊自动总结开关
    "private_auto_summary": false  // 私聊自动总结开关
}
```

### 群组配置说明
- `group_names`: 指定哪些群开启链接自动总结功能
  - 只有在此列表中的群会自动总结分享的链接
  - 为空数组`[]`则不在任何群启用自动总结
  - 示例: `["新闻群", "资讯群"]`

- `allowed_groups`: 控制插件的使用权限
  - 设置哪些群可以使用插件的所有功能
  - 为空数组`[]`则允许所有群使用
  - 示例: `["测试群", "AI交流群"]`

- `auto_summary`: 群聊自动总结的总开关
  - `true`: 允许配置的群开启自动总结
  - `false`: 关闭所有群的自动总结

- `private_auto_summary`: 私聊自动总结开关
  - `true`: 开启私聊的链接自动总结
  - `false`: 关闭私聊的链接自动总结

### 链接处理
```json
{
    "summary_prompt": "你是一个新闻专家...", // 总结提示词模板
    "exclude_urls": [                      // 不进行总结的URL关键词
        "support.weixin.qq.com",
        "finder.video.qq.com"
    ]
}
```

### 文件处理
```json
{
    "file_upload": true,           // 文件上传功能开关
    "max_file_size": 50,          // 最大文件大小(MB)
    "file_triggers": [            // 文件处理触发词
        "k分析", "分析",
        "k识别", "识别", 
        "k识图", "识图"
    ],
    "file_parsing_prompts": "请帮我整理汇总文件的核心内容",  // 文件解析提示词
    "image_prompts": "请描述这张图片的内容",               // 图片识别提示词
    "use_system_prompt": true,    // 是否使用系统推荐提示词
    "show_custom_prompt": false   // 是否显示自定义提示词
}
```

### 支持的文件格式
```json
{
    "supported_file_formats": [
        // 文档类
        ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
        ".pdf", ".txt", ".md", ".csv",
        // 图片类
        ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp",
        // 代码类
        ".py", ".java", ".cpp", ".c", ".h", ".hpp",
        ".js", ".ts", ".html", ".css",
        // 配置类
        ".json", ".xml", ".yaml", ".yml", 
        ".ini", ".conf", ".properties",
        // 其他
        ".sh", ".bat", ".log"
    ]
}
```

### 日志配置
```json
{
    "logging": {
        "enabled": true,              // 日志开关
        "level": "INFO",             // 日志级别
        "format": "[KimiChat] %(message)s",  // 日志格式
        "show_init_info": true,      // 显示初始化信息
        "show_file_process": true,   // 显示文件处理日志
        "show_chat_process": false   // 显示聊天处理日志
    }
}
```

## 使用指南

### 基础对话
```
k 你好                    # 普通对话
k 查询天气               # 联网搜索
k 继续                   # 继续上文
kimi重置会话             # 重置当前会话
kimi切换联网             # 开关联网功能
```

### 文件处理
```
k识别                    # 识别单个文件
k识别 3                  # 批量识别3个文件
k识别 分析内容           # 使用自定义提示词
k分析                    # 文件分析模式
```

### 图片识别
```
k识图                    # 识别单张图片
k识图 3                  # 批量识别图片
k识图 场景分析           # 自定义分析场景
```

### 链接解析
- 群聊/私聊中直接分享链接即可自动总结
- 总结格式:
```
总结
[一句话核心观点]

💡要点
1. [关键点1]
2. [关键点2]
3. [关键点3]
```

## 会话管理

### 群聊会话
- 同群共享上下文
- 所有成员共享历史
- 重置影响整个群组

### 私聊会话  
- 独立会话上下文
- 互不影响历史
- 重置只影响个人

## 使用限制

- 文件大小: 单个最大50MB
- 批量上限: 最多50个文件
- 会话长度: 最大20万字符
- 支持格式: 见文件格式列表
- 链接限制: 部分链接可能无法访问

## 常见问题

1. refresh_token获取失败
   - 确保完全登录Kimi官网
   - 等待10-15分钟后重试
   - 检查网络连接状态

2. 文件处理失败
   - 检查文件大小是否超限
   - 确认格式是否支持
   - 验证文件是否完整

3. 图片识别问题
   - 检查图片质量清晰度
   - 确认格式是否支持
   - 尝试不同角度拍摄

4. 群聊响应问题
   - 检查群组是否在白名单
   - 确认触发词是否正确
   - 验证权限是否开启

## License

MIT License
