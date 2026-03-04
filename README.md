# 六合彩记账机器人 - 完整使用说明书

📖 **适合 Python 小白的零基础教程**

---

## 📋 目录

1. [项目简介](#项目简介)
2. [准备工作](#准备工作)
3. [本地安装与运行](#本地安装与运行)
4. [使用指南](#使用指南)
5. [命令说明](#命令说明)
6. [云平台部署](#云平台部署)
7. [常见问题](#常见问题)
8. [备份与恢复](#备份与恢复)

---

## 项目简介

这是一个基于 **Telegram** 的智能记账机器人，专门处理六合彩下注信息。

### ✨ 核心功能

- 🤖 **AI 智能解析**：自动识别混乱的下注文本（支持生肖、波色、多种单位）
- 📊 **实时统计**：自动累加金额，显示风险最高的号码
- 🗓️ **农历自动切换**：根据农历年份自动更新生肖对照表
- 💾 **数据备份**：每日自动备份，支持手动恢复
- 📝 **日志记录**：记录所有操作，方便追踪问题
- ⚠️ **错误通知**：系统异常时自动通过 Telegram 通知

### 🎯 适用场景

- 个人记账使用
- 本地测试通过后可部署到云平台（Railway.app），无需 24 小时开机

---

## 准备工作

### 1. 检查 Python 版本

打开 **PowerShell**（Windows 搜索"PowerShell"），输入：

```powershell
python --version
```

**要求**：Python 3.10 或更高版本

如果没有安装 Python，请访问：[https://www.python.org/downloads/](https://www.python.org/downloads/)

### 2. 获取 API 密钥

您已经拥有以下密钥（已配置在代码中）：

- **Telegram Bot Token**：`8f6azbpZVY`
- **DeepSeek API Key**：`1b2b935df`

---

## 本地安装与运行

### 第一步：打开项目文件夹

在 **PowerShell** 中，切换到您的项目目录：

```powershell
cd D:\六
```

### 第二步：创建虚拟环境

虚拟环境可以将所有依赖库安装在本地文件夹，不会污染 C 盘。

```powershell
python -m venv venv
```

执行后，会在 `D:\六` 下生成 `venv` 文件夹。

### 第三步：激活虚拟环境

```powershell
.\venv\Scripts\Activate.ps1
```

**如果遇到权限错误**（红色提示），先执行：

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

然后再次激活虚拟环境。

**成功标志**：命令行前会显示 `(venv)`，例如：
```
(venv) PS D:\六>
```

### 第四步：安装依赖库

确保虚拟环境已激活（有 `(venv)` 标记），然后执行：

```powershell
pip install -r requirements.txt
```

安装过程大约需要 1-2 分钟，会自动安装以下库：
- `python-telegram-bot`（Telegram 机器人框架）
- `openai`（用于调用 DeepSeek API）
- `python-dotenv`（读取环境变量）
- `LunarDate`（农历计算）

### 第五步：运行机器人

```powershell
python main.py
```

**预期输出**：

```
🚀 六合彩记账机器人启动中...
📅 当前农历年份：2025年蛇年
🐍 当年生肖：蛇 (01, 13, 25, 37, 49)
✅ Bot started successfully!
```

现在机器人已经在运行了！打开 **Telegram**，搜索您的 Bot 并开始使用。

---

## 使用指南

### 基础操作流程

1. **打开 Telegram**，找到您的机器人（根据您的 Bot Token 对应的用户名）

2. **发送 `/start`** 开始使用

3. **直接发送下注文本**，例如：
   ```
   猪猴龙各号10#，14，31，26，38，15各5井
   ```

4. **机器人会自动解析并回复**：
   ```
   ✅ 已记录本单：
   • 07号 $10.00
   • 19号 $10.00
   • 31号 $10.00
   ...
   ━━━━━━━━━━━━
   📊 本单总额：$145.00
   
   🔥 当前风险 Top 10：
   1️⃣ 07号 - $120.00
   2️⃣ 31号 - $95.00
   ...
   ```

### 支持的文本格式

机器人可以识别以下所有格式：

#### 1. 生肖下注
```
虎马各号10
猪狗龙各号5#
牛各数15点
```

#### 2. 号码下注
```
07,13,25,37各50
12.48各30
06-20-16-40-46各五米澳门
```

#### 3. 波色下注
```
红波200
绿双蓝单各号5#
```

#### 4. 混合格式
```
猪狗龙各号5#，牛虎蛇各号15#，07，31，20各10#，绿双蓝单各号5#
```

**支持的单位**：`#`、`井`、`米`、`点`、`蚊`、`元`（都视为同一单位）

**支持的分隔符**：逗号（`,`）、句号（`.`）、斜杠（`/`）、横杠（`-`）、空格

---

## 命令说明

### `/start` - 开始使用

发送此命令开启机器人，会显示欢迎信息和功能说明。

---

### `/top` - 查看风险 Top 10

显示当前累计金额最高的 10 个号码。

**示例**：
```
/top
```

**回复**：
```
🔥 当前风险 Top 10：
1️⃣ 07号 - $1,250.50
2️⃣ 23号 - $980.00
3️⃣ 12号 - $875.25
...
```

---

### `/reset` - 清空所有数据

⚠️ **危险操作**：此命令会清空所有记账数据，无法恢复（除非有备份）。

**示例**：
```
/reset
```

**回复**：
```
✅ 所有数据已清空
当前所有号码金额归零
```

---

### `/backup` - 手动备份

立即备份当前数据到 `backups/` 文件夹。

**示例**：
```
/backup
```

**回复**：
```
✅ 数据已备份
文件：backups/numbers_state_2026-01-30.json
```

---

### `/restore 2026-01-30` - 恢复备份

恢复指定日期的备份数据（会覆盖当前数据）。

**示例**：
```
/restore 2026-01-30
```

**回复**：
```
✅ 数据已恢复
已从 backups/numbers_state_2026-01-30.json 恢复数据
```

---

### `/logs` - 查看日志摘要

显示今日的最近 10 条操作记录。

**示例**：
```
/logs
```

**回复**：
```
📋 今日日志摘要（最近10条）：
19:50:12 - 用户输入：虎马各号10
19:50:13 - AI 解析成功：8 个号码
19:50:14 - 数据更新成功
...
```

---

## 云平台部署

如果您希望机器人 24/7 在线运行，而不需要本机一直开着，可以部署到 **Railway.app**。

### 为什么选择 Railway？

- ✅ 每月 $5 免费额度（个人使用足够）
- ✅ 一键部署，无需复杂配置
- ✅ 自动休眠节省资源
- ✅ 支持环境变量加密（API Key 安全）

### 部署步骤

#### 第一步：准备 GitHub 仓库

1. **创建 GitHub 账号**（如果没有）：[https://github.com](https://github.com)

2. **创建私有仓库**：
   - 点击右上角 **"+"** → **"New repository"**
   - 仓库名：`mark-six-bot`
   - 选择 **Private**（私有，保护 API Key）
   - 点击 **Create repository**

3. **上传代码到 GitHub**：

   在 `D:\六` 目录下执行：

   ```powershell
   git init
   git add .
   git commit -m "Initial commit"
   git branch -M main
   git remote add origin https://github.com/你的用户名/mark-six-bot.git
   git push -u origin main
   ```

   ⚠️ **注意**：不要上传 `.env` 文件（已在 `.gitignore` 中排除）

---

#### 第二步：部署到 Railway

1. **访问 Railway**：[https://railway.app](https://railway.app)

2. **登录**：使用 GitHub 账号登录

3. **创建新项目**：
   - 点击 **"New Project"**
   - 选择 **"Deploy from GitHub repo"**
   - 选择您刚才创建的仓库 `mark-six-bot`

4. **配置环境变量**：
   - 在 Railway Dashboard 找到 **"Variables"** 标签
   - 添加以下环境变量：

   | Key | Value |
   |-----|-------|
   | `TELEGRAM_TOKEN` | `8364469234:AAEIGoaxHl_1cvGrAY1TAbAou8f6azbpZVY` |
   | `DEEPSEEK_API_KEY` | `sk-b4d2be45c898499dab17e771b2b935df` |

5. **部署**：
   - Railway 会自动检测到 `requirements.txt`
   - 自动安装依赖并启动 `main.py`

6. **查看日志**：
   - 在 Railway Dashboard 的 **"Deployments"** 标签查看运行日志
   - 看到 `✅ Bot started successfully!` 表示部署成功

---

#### 第三步：测试云端 Bot

打开 Telegram，发送消息给机器人，确认响应正常。

**恭喜！** 🎉 您的机器人现在 24/7 在线运行了，无需本地电脑开机。

---

## 常见问题

### Q1: 执行 `.\venv\Scripts\Activate.ps1` 时提示权限错误？

**解决方法**：

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

然后再次执行激活命令。

---

### Q2: 机器人没有响应我的消息？

**检查清单**：

1. **确认机器人正在运行**：PowerShell 窗口应该显示 `Bot started successfully!`
2. **检查网络连接**：确保电脑能访问外网
3. **查看日志**：打开 `logs/bot_YYYY-MM-DD.log` 查看错误信息
4. **重启机器人**：按 `Ctrl+C` 停止，然后再次运行 `python main.py`

---

### Q3: 如何停止机器人？

在运行 `main.py` 的 PowerShell 窗口按 **`Ctrl+C`**。

---

### Q4: 数据文件存放在哪里？

- **主数据文件**：`D:\六\numbers_state.json`
- **备份文件**：`D:\六\backups\numbers_state_YYYY-MM-DD.json`
- **日志文件**：`D:\六\logs\bot_YYYY-MM-DD.log`

---

### Q5: 如何更新 API Key？

修改 `D:\六\.env` 文件中的对应值，然后重启机器人。

---

### Q6: Railway 部署后机器人崩溃怎么办？

1. **查看 Railway 日志**：Dashboard → Deployments → 点击最新部署 → 查看日志
2. **检查环境变量**：确认 `TELEGRAM_TOKEN` 和 `DEEPSEEK_API_KEY` 设置正确
3. **重新部署**：Dashboard → Deployments → 点击 **"Redeploy"**

---

### Q7: 如何升级代码？

本地修改代码后：

```powershell
git add .
git commit -m "Update code"
git push
```

Railway 会自动检测到更新并重新部署。

---

## 备份与恢复

### 自动备份

机器人每天凌晨 00:00 会自动备份数据到 `backups/` 文件夹，保留最近 7 天。

### 手动备份

```
/backup
```

### 恢复数据

1. **查看可用备份**：打开 `D:\六\backups` 文件夹，查看备份文件名（格式：`numbers_state_2026-01-30.json`）

2. **恢复指定日期**：
   ```
   /restore 2026-01-30
   ```

3. **确认恢复成功**：发送 `/top` 查看数据是否正确

---

## 📞 技术支持

如遇到其他问题，请检查：

1. **日志文件**：`logs/bot_YYYY-MM-DD.log`
2. **错误通知**：机器人会自动通过 Telegram 发送错误信息

---

## 🎓 附录：文件结构说明

```
D:\六\
├── venv/                   虚拟环境（不要删除）
├── logs/                   日志文件夹
├── backups/                备份文件夹
├── main.py                 主程序
├── requirements.txt        依赖清单
├── .env                    环境变量（包含 API Key）
├── .gitignore              Git 忽略规则
├── README.md               本说明书
└── numbers_state.json      数据文件（自动生成）
```

---

**祝您使用愉快！** 🚀
