# KimiChat 插件说明

[`国产模型kimi`](https://kimi.moonshot.cn/) 插件,支持联网、文件解析、20万上下文。

## 功能特点

- 支持联网搜索和对话
- 支持多种文件格式解析和图片识别
- 支持视频分析(视频帧提取和音频转文字让kimi进行识别解析)
- 支持链接内容自动总结
- 支持多轮对话,保持上下文
- 支持群聊和私聊
- 支持自定义提示词

## 安装步骤

本插件基于 [cow_plugin_kimichat](https://github.com/LargeCupPanda/cow_plugin_kimichat) 修改，增加了图片识别和链接总结功能。需要先安装 [chatgpt-on-wechat](https://github.com/zhayujie/chatgpt-on-wechat) 框架。

音频转文字采用硅基流动API，如果没有账号可以走我的邀请链接https://cloud.siliconflow.cn/i/tPQSNa6I

### 1. 安装插件
在 chatgpt-on-wechat 项目的根目录下，使用管理员模式执行：
```bash
#installp https://github.com/single228758/cow-.git
```

### 2. 配置插件
```bash
# 进入插件目录
cd plugins/cow_plugin_kimichat/

# 修改配置模板
config.json
```

### 3. 安装依赖
```bash
pip install -r requirements.txt
```

### 4. 配置参数
编辑 `config.json` 文件，主要配置以下参数：
- `refresh_token`: 必填，从 Kimi 官网获取
- `keyword": "k",                        // 触发关键词,默认"k"
- `reset_keyword": "kimi重置会话",       // 重置会话的关键词
- `group_names": ["群名1", "群名2"],     // 配置在哪些群开启链接自动总结功能
- `allowed_groups": [],                  // 配置允许使用kimi插件的群ID列表,为空则允许所有群
- `auto_summary`: true,                  // 是否启用链接自动总结
- `private_auto_summary`: false,         // 是否在私聊中启用自动总结

### 5. 启用插件
执行命令扫描并启用插件：
```bash
#scanp
```

### 6. 验证安装
发送测试消息验证插件是否正常工作：
```
k 你好  # 测试基础对话
识别    # 测试文件识别
```

## 配置文件说明

### 基础配置
```json
{
    "refresh_token": "你的refresh_token",  // Kimi API的刷新令牌(必填)
    "keyword": "k",                        // 触发关键词,默认"k"
    "reset_keyword": "kimi重置会话",       // 重置会话的关键词
    "group_names": ["群名1", "群名2"],     // 配置在哪些群开启链接自动总结功能
    "allowed_groups": [],                  // 配置允许使用kimi插件的群ID列表,为空则允许所有群
    "auto_summary": true,                  // 是否启用链接自动总结
    "private_auto_summary": false,         // 是否在私聊中启用自动总结
}
```

### 提示词配置
```json
{
    "summary_prompt": "你是一个新闻专家...",  // 链接总结的提示词
    "file_parsing_prompts": "请帮我整理汇总文件的核心内容",  // 文件解析提示词
    "image_prompts": "请描述这张图片的内容",   // 图片识别提示词
    "use_system_prompt": true,               // 是否使用系统推荐提示词
    "show_custom_prompt": false,             // 是否在回复中显示自定义提示词
}
```

### 文件处理配置
```json
{
    "file_upload": true,                     // 是否启用文件功能
    "file_triggers": [                       // 文件处理触发词列表
        "k分析", "分析",                      // 可以触发文件分析
        "k识别", "识别",                      // 可以触发图片识别
        "k识图", "识图"                       // 可以触发图片识别
    ],
    "max_file_size": 50,                    // 单个文件最大大小(MB)
    "file_timeout": 300,                    // 文件上传超时时间(秒)
    "supported_file_formats": [             // 支持的文件格式列表
        ".doc", ".docx", ".pdf",           // 文档格式
        ".jpg", ".png", ".gif",            // 图片格式
        ".py", ".java", ".json"            // 代码和配置文件
        // ... 更多格式见配置文件
    ]
}
```

### 视频处理配置
```json
{
    "video_config": {
        "trigger_keywords": ["视频", "视频分析"],  // 视频分析触发词
        "save_dir": "video",                     // 视频文件保存目录
        "frame_interval": 1.0,                   // 视频帧提取间隔(秒)
        "max_frames": 50,                        // 最大提取帧数
        "max_size": 100,                         // 视频文件大小限制(MB)
        "upload_threads": 20,                    // 帧上传并发数
        "summary_prompt": "...",                 // 视频分析提示词
        "supported_formats": [                   // 支持的视频格式
            ".mp4", ".avi", ".mov", 
            ".mkv", ".flv", ".wmv"
        ]
    },
    "audio_token": "your_token"                 // 音频转写API Token
}
```

### 链接处理配置
```json
{
    "exclude_urls": [                           // 不进行总结的URL关键词
        "support.weixin.qq.com",
        "finder.video.qq.com"
    ]
}
```

### 日志配置
```json
{
    "logging": {
        "enabled": true,                        // 是否启用日志
        "level": "INFO",                        // 日志级别
        "format": "[KimiChat] %(message)s",     // 日志格式
        "show_init_info": true,                 // 显示初始化信息
        "show_file_process": true,              // 显示文件处理日志
        "show_chat_process": false              // 显示聊天过程日志
    }
}
```

## 使用方法

### 基础对话
```
k 你好                    # 普通对话
k 帮我查下今天的天气      # 联网搜索
kimi重置会话              # 重置当前会话
```

### 文件识别
```
识别                      # 默认识别1个文件
识别 3                    # 指定识别3个文件
识别 请帮我分析内容       # 使用自定义提示词
k分析/k识图              # 其他触发词都可以
```

### 视频分析
```
视频                      # 分析视频内容
视频分析                  # 同上
```
- 支持视频帧提取和分析
- 支持音频转写(需配置audio_token)
- 自动生成视频内容摘要

### 链接解析
- 直接分享链接即可自动总结内容
- 群聊需要在 group_names 中配置
- 私聊需要开启 private_auto_summary
- 可通过 exclude_urls 排除不需要总结的链接
+ - 在配置的群组(group_names)中分享链接会自动总结内容
+ - 私聊需要开启 private_auto_summary 才会自动总结
+ - 可通过 exclude_urls 排除不需要总结的链接
+ - allowed_groups 可以限制哪些群可以使用 kimi 功能

## 注意事项

1. refresh_token 必须正确配置
2. 文件上传有大小限制:
   - 普通文件: 50MB
   - 视频文件: 100MB
3. 视频分析功能:
   - 需要安装 moviepy 等依赖
   - 音频转写需要配置 audio_token
4. 建议合理配置触发词,避免冲突
+ 5. group_names 和 allowed_groups 的区别:
+    - group_names: 配置哪些群开启链接自动总结
+    - allowed_groups: 配置哪些群可以使用 kimi 功能
6. 遵守 Kimi API 使用规范

## 常见问题

1. 无法连接API
   - 检查 refresh_token 是否正确
   - 确认网络连接正常

2. 文件无法识别
   - 检查文件格式是否在 supported_file_formats 中
   - 确认文件大小未超过 max_file_size
   - 查看日志了解具体错误

3. 群聊不响应
   - 检查群名是否在 group_names 中
   - 确认机器人是否在群中

4. 视频分析失败
   - 检查视频格式是否支持
   - 确认视频大小未超限制
   - 音频转写需要正确配置 audio_token

## 更新日志

v0.2
- 添加视频分析功能


v0.1 
- 基础对话功能
- 联网搜索支持
- 多轮对话支持

## 其他
代码均由gpt生成可能会有很多bug，本人不懂代码，只能通过不断通过不同的AI进行缝缝补补，如果您有任何改进建议或者功能请求，可以尽情的创建lssue

觉得插件对您有帮助可以打赏一下




