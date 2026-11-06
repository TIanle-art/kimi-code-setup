# 维护这个 skill（作者 / 贡献者看）

这份文件放的是**维护 skill 本身**要用的东西：作者机器上的正本与安装副本怎么同步、扩展规范、各平台验证版本。**给新机器做配置时用不到**，`SKILL.md` 正文不再重复。

## 各平台验证版本

> **验证版本**：配置字段、权限模式文案、迁移行为、脚本契约实测于 **kimi-code 0.41.0（macOS，2026-09-15）**；Windows 分支的常驻方式、钩子/状态栏命令写法实测于 **Windows 11 + kimi-code 0.43.1（Store 版 Python 3.13，非管理员账户，2026-09-16）**；**Linux 分支的 systemd 常驻、桥三层验证、钩子实时拦截实测于 WSL2 + kimi-code 0.41.0（Python 3.14，2026-09-16）**；**Windows 11 + kimi-code 2.0.0（Python 3.11.9，非管理员，2026-09-18）复跑：主流程与 `assets/verify.py --e2e` 全通过；同期修复中文 Windows 的钩子提示 GBK 乱码（`-X utf8`，见 `references/todo-panel-guard.md`）**。实测结论都带"✅/❌ 实测"标注。换了版本（或机器上版本不同）先跑一次 `assets/verify.py` 看结论是否还对得上。

- **DeepSeek Search / Fetch 后端**：2026-11 真机实测通过（`verify.py --e2e` 搜索 / 抓取都返回正文）。

## 正本、安装副本与同步

- **怎么触发**：拷进目标机器的 `~/.kimi-code/skills/kimi-code-setup/` 后，直接说「**调试 kimi-code**」「配置 kimi-code」这类话即可——agent 按 description 命中后自动加载本文件，缺参数（Exa key、平台是 mac / win 还是 linux、要不要挂 MCP）它会先问清再动手，不用背固定提示词。
- **作者机器（macOS，桌面正本）**：**正本在桌面** `~/Desktop/kimi-code-setup/`（改动只动这份；它同时是个 git 仓库，`origin` 指向公开仓库 https://github.com/TIanle-art/kimi-code-setup ，改完 `git push` 就更新公开版），**安装副本在** `~/.kimi-code/skills/kimi-code-setup/`（kimi 自动发现、直接能命中 `kimi-code-setup` skill 的那份）。改完正本跑一次同步（**必须带 `--exclude=.git`**，否则会把仓库元数据拷进 skill 目录），再体检确认：

  ```bash
  rsync -a --delete --exclude=.git ~/Desktop/kimi-code-setup/ ~/.kimi-code/skills/kimi-code-setup/
  python3 ~/Desktop/kimi-code-setup/assets/verify.py | tail -3
  ```

  Windows 上没有 rsync（Git Bash 一般也不带），等价做法是 `robocopy` 或 `cp -r`；同步完**在 Git Bash 里**用 `diff -rq --exclude=.git 旧目录 新目录` 核对（**PowerShell 里别这么写**：`diff` 是 `Compare-Object` 的别名，不认 `-rq` / `--exclude`）：

  ```powershell
  # 下面两行只在 PowerShell / cmd 里跑——Git Bash 会把 /MIR /XD 改写成 D:/…/MIR 报错（实测）
  robocopy "$env:USERPROFILE\Desktop\kimi-code-setup" "$env:USERPROFILE\.kimi-code\skills\kimi-code-setup" /MIR /XD .git /NFL /NDL
  python "$env:USERPROFILE\Desktop\kimi-code-setup\assets\verify.py" | Select-Object -Last 3
  ```

  Git Bash 里想用 robocopy 就加 `MSYS_NO_PATHCONV=1` 关掉路径改写：`MSYS_NO_PATHCONV=1 robocopy "C:/Users/<你>/Desktop/kimi-code-setup" "C:/Users/<你>/.kimi-code/skills/kimi-code-setup" /MIR /XD .git /NFL /NDL`。
- **WSL2（Linux）那台**：正本在 `~/projects/kimi-code-setup`（同一个 git 仓库、同一个 `origin`，改完 `git push` 就更新公开版），安装副本同样在 `~/.kimi-code/skills/kimi-code-setup/`，同步就是在那个目录里跑上面同一条命令（源路径换成 `./` 或 `~/projects/kimi-code-setup/`）。
- **要用在别的机器上**：把整个目录拷到目标机器的 `~/.kimi-code/skills/kimi-code-setup/`（Windows：`%USERPROFILE%\.kimi-code\skills\kimi-code-setup\`），那里新开的 kimi 会话就会自动发现它；不拷也行，直接把文件带过去让 agent 读。
- **本机想临时当 skill 用**：`kimi --skills-dir ~/Desktop --skills-dir ~/.kimi-code/skills`（实测：`--skills-dir` 会**替换**自动发现的目录，所以要补上原来的 `~/.kimi-code/skills` 才不丢 `kimi-webbridge` / `markitdown`；它按整棵子树递归扫描，指到桌面会把 `桌面/开源工具/` 下的 170+ 个 skill 一起带进来，很吵）。更省事的是让 agent 直接读本文件。
- 下文里的 **`$SKILL_DIR`** 指这个 skill 所在目录：macOS 上正本是 `~/Desktop/kimi-code-setup`、WSL2 上是 `~/projects/kimi-code-setup`，安装副本都是 `~/.kimi-code/skills/kimi-code-setup`（两份内容一致，用哪份都行）；拷到目标机器后就是 `~/.kimi-code/skills/kimi-code-setup`（Windows 用 `%USERPROFILE%\.kimi-code\skills\kimi-code-setup`）。命令里出现 `$SKILL_DIR` 时按实际位置展开。

## 扩展规范

- **细则放 `references/<主题>.md`，本文件只留 3–6 行要点 + 判据 + 链接**，文件再长也不挤上下文。
- 加了新主题，记得在上面的主流程表里补一行，否则后来的人（或 agent）看不见它。
- 脚本、配置模板、安装脚本放 `assets/`；**新增落地点优先复用 `patch-config.py`（写）和 `verify.py`（读）**，别再手写"追加/覆盖"逻辑。
- **已实测 与 "按标准做法写的" 要分开标注**（例：Windows 那节就是这么标的），免得下次被当成已验证。
- **一律 LF**（仓库已用 `.gitattributes` 钉住）：`assets/*.template` 要拿去 `sed` 生成常驻定义，CRLF 会让令牌尾部多一个 `\r`（实测 401）。Windows 侧检出后别再把行尾改回 CRLF。
- **正本只保留一份**（本机的"安装副本"除外）：改动只动正本，改完按上面「正本、安装副本与同步」一节同步到 `~/.kimi-code/skills/kimi-code-setup/`；搬运/归档完别在别处再留第三份，前后用 `diff -rq 旧目录 新目录` 核对——`verify.py` 的「脚本漂移」只比对 **`exa-bridge.py` / `todo-panel-guard.py` / `statusline.py` / `statusline-daemon.pyw`** 这 4 个部署脚本（对应关系见 `SKILL.md`「assets 里有什么」），**不比对** `patch-config.py`、`verify.py`、`deploy.py`、`.template` 生成出的常驻定义、`statusline-fast.c` 编出的 exe、`kimi-web-status.user.js`，也不比对任何文档——所以改完部署脚本要跑一次 `assets/deploy.py`（幂等）把它们送到落地点，别靠记性。
- 正本是个 git 仓库（`origin` = 公开仓库）：动手前 `git status` 确认工作区干净，改完 `git commit` + `git push`。**别再用 `cp -a` 做目录备份**——git 就是备份，`cp -a` 只会把 `.git` / `__pycache__` 一起拷进去。
- 换了 kimi-code 版本，先跑 `verify.py`，再更新本文件「各平台验证版本」和 `SKILL.md` 顶部那句摘要。
- 改了目录名或位置，记得同步：frontmatter 的 `name`、本文件与 `references/` 里的 `$SKILL_DIR` 说明、以及作者机器上 `~/.kimi-code/AGENTS.md` 里的指路与触发约定。
