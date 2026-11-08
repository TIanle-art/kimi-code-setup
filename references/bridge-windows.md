# exa-bridge 常驻：Windows 11（启动器 + 计划任务 / 注册表 / 启动文件夹）

> `references/web-tools-exa.md` 第 3 节「起常驻」的 Windows 分支。前面的 1~2 节（放脚本、写 `config.toml`）和后面的 4~5 节（三层验证、回滚）是三个平台共用的，仍在 `web-tools-exa.md` 里；**走 DeepSeek 后端时**模板里的 Exa key 留空即可（见 `web-tools-exa.md`「收集参数」第 3 条）。
>
> 下文 **`$SKILL_DIR`** = 这个 skill 所在目录（通常是 `~/.kimi-code/skills/kimi-code-setup`）。

**Windows 11（2026-09-16 实测：Windows 11 + kimi-code 0.43.1 + Store 版 Python 3.13，非管理员账户）**——分两步：先做第 0 步生成启动器，再按可用性从上往下挑一条常驻路。

**0. 生成启动器（三条常驻路都要用）**：`pythonw.exe` 是 GUI 子系统程序、没有控制台，计划任务和启动文件夹又都塞不进环境变量——所以令牌和日志得靠一个 `.pyw` 包装器（它等价于 macOS plist 里的 `EnvironmentVariables` + `StandardErrorPath`）：

```powershell
$skillDir = "$env:USERPROFILE\.kimi-code\skills\kimi-code-setup"   # 没拷进 skills 目录就改成实际路径
$dst = "$env:USERPROFILE\.kimi-code\exa-bridge"
New-Item -ItemType Directory -Force -Path $dst | Out-Null
Copy-Item "$skillDir\assets\exa-bridge.py" "$dst\exa-bridge.py" -Force

$exaKey = ''            # 留空 = 桥改读 mcp.json 的 x-api-key（推荐，省得把 key 散在三处）
$token  = '<本地令牌>'   # 留空 = 不校验（verify.py 报 WARN，别留空）；填了就要和 config.toml 两处 [services].api_key 一致
$tpl = Get-Content "$skillDir\assets\windows-launch.pyw.template" -Raw
$tpl = $tpl.Replace('__SCRIPT__', "$dst\exa-bridge.py".Replace('\','/')) `
           .Replace('__LOG__', "$dst\bridge.log".Replace('\','/')) `
           .Replace('__EXA_API_KEY__', $exaKey).Replace('__EXA_BRIDGE_TOKEN__', $token)
Set-Content "$dst\launch.pyw" $tpl -Encoding UTF8

python --version                                    # 没有就先装：winget install -e --id Python.Python.3.12
$pyw = (Get-Command pythonw.exe).Source             # Store 版 Python 也有 pythonw；机器上没有 py 启动器不代表没有它
Start-Process -FilePath $pyw -ArgumentList "`"$dst\launch.pyw`"" -WindowStyle Hidden   # 先手动起一次
curl.exe -s http://127.0.0.1:8787/health            # 期望 {"ok":true,..."key":true}
```

**1. 三条常驻路**（实测结论：①②在本机被挡，③可用）：

| 路 | 做法 | 实测 |
|----|------|------|
| ① 计划任务 | 见下方脚本 | ❌ 非管理员账户下 `Register-ScheduledTask`、`schtasks /Create`、计划任务 COM 三种写法全是 `Access is denied (0x80070005)` |
| ② `HKCU\...\Run` | `reg add "HKCU\Software\Microsoft\Windows\CurrentVersion\Run" /v kimi-exa-bridge /t REG_SZ /d "\"$pyw\" \"$dst\launch.pyw\"" /f` | ❌ 命令报成功、**下一条命令回读就没了**——被安全软件静默回滚（本机装火绒 HIPS）；把它加进白名单后可再用 |
| ③ 启动文件夹快捷方式 | 见下方脚本，**不需要管理员** | ✅ 本机采用；`.lnk` 落盘正常。⚠️ 2026-09-16 实测有一次重启后它**没被处理**，见下方 **2.5** |

①计划任务（管理员 / 组策略允许时最标准）：
```powershell
$action  = New-ScheduledTaskAction -Execute $pyw -Argument "`"$dst\launch.pyw`""
$trigger = New-ScheduledTaskTrigger -AtLogOn
# 两个默认设置的坑（计划任务通用默认行为）：电池供电时不启动/被停、执行满 72 小时被强杀：
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)
Register-ScheduledTask -TaskName "kimi-exa-bridge" -Action $action -Trigger $trigger -Settings $settings -Force
Start-ScheduledTask -TaskName "kimi-exa-bridge"     # 立即起，不必重登录
```

③启动文件夹（用户级，无需提权）：
```powershell
$lnk = Join-Path ([Environment]::GetFolderPath('Startup')) 'kimi-exa-bridge.lnk'
$sc = (New-Object -ComObject WScript.Shell).CreateShortcut($lnk)
$sc.TargetPath = $pyw
$sc.Arguments = '"' + $dst + '\launch.pyw"'
$sc.WorkingDirectory = $dst
$sc.WindowStyle = 7        # 最小化，避免登录时闪一下
$sc.Save()
```

**2. 判据（三条路相同）**：`curl.exe -s http://127.0.0.1:8787/health` 返回 `"ok":true` 且 `"key":true`；`$dst\bridge.log` 里出现 `exa-bridge listening on ...`。写完自启项**立刻回读一次**，别只信命令回显的"成功"——`Get-ScheduledTaskInfo -TaskName kimi-exa-bridge` / `reg query "HKCU\..." /v kimi-exa-bridge` / `Get-ChildItem ([Environment]::GetFolderPath('Startup'))`。

**2.5 桥没在跑（重启后没起来 / 中途被杀，2026-09-16 两次实测）**：① **重启后没起来**——01:07 重启、01:08 登录，之后桥没有自己起来（`/health` 连接被拒、`bridge.log` 里没有新横幅），而 Windows「设置 → 应用 → 启动」里那条 `pythonw.exe`（就是本快捷方式）**显示为「开」**；同一次登录里 OneDrive、TranslucentTB 等**用户级**自启项同样"标记为开却没在跑"（服务级的火绒 / RtkAudUService 正常）。② **没重启也会挂**——同一天 02:01 又发现桥没了，`bridge.log` 里**只有请求行、没有任何 traceback**，说明它是**被杀**而不是自己崩（火绒是头号嫌疑，未坐实）；那次同样是"手动跑一次快捷方式"救活。**快捷方式本身两次都是好的**：跑一次那个 `.lnk`，桥立刻 `listening`。另外注意：桥的进程名是 **`pythonw3.13`**（Store 版 Python 的真名），`Get-Process pythonw` 查不到它，别据此判定"桥没在跑"——**判断存活只认 `/health`，别依赖日志**。**兜底（2026-09-16 加，已实测自愈）**：状态栏脚本（每秒被 runner 调一次）现在顺手探活——只做 TCP `connect`、30 秒最多一次，拒连就拉起——**优先走启动文件夹快捷方式**（ShellExecute 由 explorer 起、不在我们的进程树里，runner 超时那记 `taskkill /T /F` 杀不到它），**没有快捷方式才回退直接 `Popen` `exa-bridge/launch.pyw`**；重试间隔 30 秒（与探活同频；原来是 60 秒冷却，被连坐时桥要多躺 30~90 秒）；门闩是 `KIMI_CODE_STATUS_LINE=1`，只有 runner 调用时才生效（手动跑 / `verify.py` 自测都不会误拉起）。实测：杀掉桥后 **2 秒内自动回来**。边界：**只在 kimi 会话活着时有效**（关掉 kimi 就没守护，而那正是用不上搜索的时候）。实现细节见 `references/statusline.md` 已知边界。

处理顺序：① `verify.py` 或 `curl /health` 确认桥不在；② **先等最多 30 秒**——兜底探活最多 30 秒跑一次，撞上就会把它拉起来（`statusline/bridge-watch.json` 里能看到 `last_ok`/`relaunched`）；③ 还没起来就跑一次快捷方式；④ 只有重现失败才去查配置。

**火绒这条线索（2026-09-16 翻过日志）**：把火绒的「安全日志」按当天翻了一遍——只有 5 条，全是它自己的动作（01:41:55 升级到 6.0.11.3、01:42 系统修复/漏洞修复、**01:58:06 手动清理 1.2GB 垃圾**），**没有任何"拦截 / 结束进程"记录**；而桥被发现死亡是 02:01，紧跟在 01:58 那次清理之后——"升级或垃圾清理顺带把它带走了"仍是最像的解释，但**没坐实**。已把 `%USERPROFILE%\.kimi-code\exa-bridge` 加进火绒信任区（类型：文件夹及子目录）。**别把信任区当护身符**：它只让病毒扫描跳过这个目录，不等于放行进程行为；下次再被杀，先打开火绒「安全日志」按时间点对一遍（没有条目就说明不是它的主动拦截，往别处查）。

**3. 排错**：`.pyw` 起不来时用 `python.exe`（不是 pythonw）前台跑同一个 `launch.pyw`，日志会同时打到终端（Ctrl+C 退出）；端口被占就在启动器里加一行 `os.environ.setdefault("EXA_BRIDGE_PORT", "8788")`，并同步改 `config.toml` 两处 `base_url`。

**改完怎么生效**：改了启动器（`launch.pyw`）或常驻方式——计划任务就重建任务，启动文件夹就重建那个 `.lnk`，注册表就重写值，然后重启桥；**只改了 `exa-bridge.py`** 时跑 `python3 "$SKILL_DIR/assets/deploy.py" --bridge` 即可（拷贝 + 重启桥）。
