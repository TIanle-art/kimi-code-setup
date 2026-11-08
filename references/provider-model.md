# LLM provider、模型与思考强度（主流程第 1 步细则）

非交互（推荐，直接吃 models.dev 目录）：

```bash
kimi provider catalog list deepseek            # 看有哪些模型
kimi provider catalog add deepseek --api-key <你的 key> --default-model deepseek-flash
kimi provider list                             # 确认 provider 与默认模型
```

目录导入只解决 provider + 模型别名；**思考强度、默认权限模式仍要写进 `config.toml`**（用 `patch-config.py set`，命令样式见 `SKILL.md` 第 2 步）。下面这段是作者机器上正在跑的 DeepSeek V4.1 Flash + 最高强度（实测可用）：

```toml
default_model = "deepseek/deepseek-flash"

[providers.deepseek]
type = "openai"
base_url = "https://api.deepseek.com"
api_key = "<你的 key>"

[models."deepseek/deepseek-flash"]
provider = "deepseek"
model = "deepseek-flash"                    # 上游真实模型名，以 provider 文档为准
display_name = "DeepSeek V4.1 Flash"        # 界面里显示的名字
max_context_size = 1000000                  # 必填且为正数，漏了启动直接报错
capabilities = ["image_in", "thinking", "tool_use"]
reasoning_key = "reasoning_content"         # DeepSeek 的思考内容字段
support_efforts = ["low", "high", "max"]    # 这个模型允许的思考强度档位

[models."deepseek/deepseek-flash".overrides]
default_effort = "max"                      # 只对该模型生效（比全局 [thinking] 优先）

[thinking]
enabled = true
effort = "max"                              # 全局兜底强度，其它模型也按这个来
```

- 临时换：启动参数 `-m <别名>`、会话里 `/model`。
- 别名规则是 `<provider>/<别名>`；`max_context_size` 之外写错模型名也会在启动时报错。
- **⚠️ 新机器上的坑（实测）**：kimi-code 有一次性的 `thinking-effort-max-to-high` 迁移——**首次**启动某个 kimi home 时，如果 `[thinking] effort` 是 `max`，它会被自动改写成 `high`（迁移标记记在 `<home>/migrations-effort.json`，同一 home 只跑一次，之后你手写的值不再被改）。所以在新机器上要么**先启动一次再写** `[thinking] effort = "max"`，要么就别依赖全局值——把 `max` 放在模型级的 `[models."…".overrides].default_effort = "max"`（迁移只碰全局 `[thinking]`，不动它）。

注意：跑过 `/login`（登录 Kimi 账号）会把 `config.services` 重写成 Kimi 托管服务，**第 2 步的 Exa 配置会被顶掉**；两者想共存得重新加回来。
