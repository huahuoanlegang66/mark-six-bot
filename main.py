#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
六合彩记账机器人 - Telegram Bot
使用 DeepSeek API 智能解析下注信息

功能特性：
- AI 智能解析混乱的下注文本
- 农历年份自动切换生肖对照表
- 数据自动备份（每日+手动）
- 日志记录系统
- 错误通知机制
"""

import os
import sys
import json
import logging
import asyncio
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Tuple
import shutil

# ----------------- 路径编码修复补丁 -----------------
# 针对 Windows 中文路径 (如 D:\六) 导致 venv site-packages 无法加载的问题
BASE_DIR = Path(__file__).parent
SITE_PACKAGES = BASE_DIR / "venv" / "Lib" / "site-packages"
if SITE_PACKAGES.exists() and str(SITE_PACKAGES) not in sys.path:
    sys.path.insert(0, str(SITE_PACKAGES))
# ----------------------------------------------------

# 强制控制台输出使用 UTF-8 (解决 Windows 打印 emoji 报错问题)
sys.stdout.reconfigure(encoding='utf-8')

import lunardate as LunarDate  # 修正模块名为 lunardate
from dotenv import load_dotenv
from openai import OpenAI
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
)

# ======================== 配置区域 ========================

# 加载环境变量
load_dotenv()

# Telegram Bot Token
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
if not TELEGRAM_TOKEN:
    raise ValueError("❌ 缺少 TELEGRAM_TOKEN 环境变量，请检查 .env 文件")

# DeepSeek API Key
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
if not DEEPSEEK_API_KEY:
    raise ValueError("❌ 缺少 DEEPSEEK_API_KEY 环境变量，请检查 .env 文件")

# 文件路径配置
BASE_DIR = Path(__file__).parent
DATA_FILE = BASE_DIR / "numbers_state.json"
BACKUP_DIR = BASE_DIR / "backups"
LOG_DIR = BASE_DIR / "logs"
LOCK_FILE = BASE_DIR / ".bot.lock"  # 进程锁文件

# 创建必要的目录
BACKUP_DIR.mkdir(exist_ok=True)
LOG_DIR.mkdir(exist_ok=True)

# ======================== 进程互斥锁 ========================

def acquire_lock() -> bool:
    """
    获取进程锁，确保只有一个 Bot 实例运行
    
    Returns:
        True: 成功获取锁
        False: 锁已被其他进程占用
    """
    if LOCK_FILE.exists():
        # 读取锁文件中的 PID
        try:
            with open(LOCK_FILE, 'r') as f:
                old_pid = int(f.read().strip())
            
            # 检查该进程是否仍在运行
            import psutil
            if psutil.pid_exists(old_pid):
                print(f"❌ 错误：Bot 已在运行中（进程 ID: {old_pid}）")
                print(f"   如果您确认没有其他实例，请删除文件：{LOCK_FILE}")
                return False
            else:
                # 旧进程已死，清理锁文件
                LOCK_FILE.unlink()
                print(f"🧹 已清理过期的锁文件（旧进程 {old_pid} 已退出）")
        except Exception as e:
            print(f"⚠️ 读取锁文件失败：{e}")
            return False
    
    # 写入当前进程 PID
    try:
        with open(LOCK_FILE, 'w') as f:
            f.write(str(os.getpid()))
        return True
    except Exception as e:
        print(f"❌ 创建锁文件失败：{e}")
        return False

def release_lock():
    """释放进程锁"""
    if LOCK_FILE.exists():
        try:
            LOCK_FILE.unlink()
            logger.info("🔓 进程锁已释放")
        except Exception as e:
            logger.error(f"❌ 释放锁文件失败：{e}")

# ======================== 日志配置 ========================

def setup_logging():
    """配置日志系统"""
    today = datetime.now().strftime("%Y-%m-%d")
    log_file = LOG_DIR / f"bot_{today}.log"
    
    # 配置日志格式
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file, encoding='utf-8'),
            logging.StreamHandler()
        ]
    )
    
    # 清理超过 30 天的日志
    cleanup_old_files(LOG_DIR, days=30, pattern="bot_*.log")
    
    return logging.getLogger(__name__)

def cleanup_old_files(directory: Path, days: int, pattern: str):
    """清理超过指定天数的文件"""
    cutoff_date = datetime.now() - timedelta(days=days)
    for file in directory.glob(pattern):
        if file.is_file():
            file_time = datetime.fromtimestamp(file.stat().st_mtime)
            if file_time < cutoff_date:
                file.unlink()
                print(f"🗑️ 已删除旧文件：{file.name}")

logger = setup_logging()

# ======================== 农历年份计算 ========================

def get_current_lunar_year() -> Tuple[int, str, Dict[str, List[str]]]:
    """
    获取当前农历年份和生肖信息
    
    Returns:
        (年份, 生肖名, 生肖号码对照字典)
    """
    today = datetime.now()
    
    try:
        # 转换为农历
        lunar = LunarDate.LunarDate.fromSolarDate(today.year, today.month, today.day)
        lunar_year = lunar.year
        
        # 十二生肖列表（固定顺序）
        zodiac_animals = ["鼠", "牛", "虎", "兔", "龙", "蛇", "马", "羊", "猴", "鸡", "狗", "猪"]
        
        # 计算当年生肖（蛇年 = 2025年农历）
        # 2025年是蛇年，蛇在十二生肖中排第6位（索引5）
        # 通过农历年份计算生肖索引
        zodiac_index = (lunar_year - 4) % 12  # 2025 - 4 = 2021, 2021 % 12 = 5 (蛇)
        current_zodiac = zodiac_animals[zodiac_index]
        
        # 生成生肖号码对照表
        # 规则：当年生肖的号码模12余1
        # 例如2025蛇年：01,13,25,37,49 模12都余1
        zodiac_mapping = {}
        
        for i, animal in enumerate(zodiac_animals):
            # 计算该生肖对应的模12余数
            # 当年生肖余1，前一年余2，以此类推
            offset = (i - zodiac_index) % 12
            if offset == 0:
                offset = 12  # 马(模12余0)应该显示为12
            
            # 余数转换：当年生肖=1, 前一年=2...
            remainder = (13 - offset) % 12
            if remainder == 0:
                remainder = 12
            
            # 生成该生肖的所有号码
            numbers = []
            for num in range(1, 50):  # 01-49
                if num % 12 == (remainder % 12):
                    numbers.append(f"{num:02d}")
            
            zodiac_mapping[animal] = numbers
        
        logger.info(f"📅 当前农历年份：{lunar_year}年{current_zodiac}年")
        logger.info(f"🐍 当年生肖：{current_zodiac} {zodiac_mapping[current_zodiac]}")
        
        return lunar_year, current_zodiac, zodiac_mapping
        
    except Exception as e:
        logger.error(f"❌ 农历计算失败：{e}")
        # 返回默认值（2025蛇年）
        return 2025, "蛇", {"蛇": ["01", "13", "25", "37", "49"]}

# 波色固定对照表
COLOR_MAPPING = {
    "红波": ["01", "02", "07", "08", "12", "13", "18", "19", "23", "24", "29", "30", "34", "35", "40", "45", "46"],
    "蓝波": ["03", "04", "09", "10", "14", "15", "20", "25", "26", "31", "36", "37", "41", "42", "47", "48"],
    "绿波": ["05", "06", "11", "16", "17", "21", "22", "27", "28", "32", "33", "38", "39", "43", "44", "49"]
}

# ======================== 数据管理 ========================

def load_data() -> Dict[str, float]:
    """加载数据文件"""
    if DATA_FILE.exists():
        try:
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
            logger.info(f"📂 数据加载成功：{len(data)} 个号码")
            return data
        except Exception as e:
            logger.error(f"❌ 数据加载失败：{e}")
            return init_data()
    else:
        logger.info("📂 数据文件不存在，初始化新数据")
        return init_data()

def init_data() -> Dict[str, float]:
    """初始化空数据（01-49全部为0）"""
    return {f"{i:02d}": 0.0 for i in range(1, 50)}

def save_data(data: Dict[str, float]):
    """保存数据到文件"""
    try:
        with open(DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.info("💾 数据保存成功")
    except Exception as e:
        logger.error(f"❌ 数据保存失败：{e}")
        raise

def backup_data(manual=False) -> str:
    """备份数据文件"""
    try:
        today = datetime.now().strftime("%Y-%m-%d")
        backup_file = BACKUP_DIR / f"numbers_state_{today}.json"
        
        if DATA_FILE.exists():
            shutil.copy2(DATA_FILE, backup_file)
            logger.info(f"💾 数据备份成功：{backup_file.name}")
            
            # 清理超过 7 天的备份
            cleanup_old_files(BACKUP_DIR, days=7, pattern="numbers_state_*.json")
            
            return str(backup_file)
        else:
            logger.warning("⚠️ 数据文件不存在，无法备份")
            return ""
    except Exception as e:
        logger.error(f"❌ 备份失败：{e}")
        return ""

def restore_data(date_str: str) -> bool:
    """从备份恢复数据"""
    try:
        backup_file = BACKUP_DIR / f"numbers_state_{date_str}.json"
        if backup_file.exists():
            shutil.copy2(backup_file, DATA_FILE)
            logger.info(f"✅ 数据恢复成功：从 {backup_file.name}")
            return True
        else:
            logger.warning(f"⚠️ 备份文件不存在：{backup_file.name}")
            return False
    except Exception as e:
        logger.error(f"❌ 数据恢复失败：{e}")
        return False

# ======================== DeepSeek API 集成 ========================

# 初始化 OpenAI 客户端（兼容 DeepSeek）
client = OpenAI(
    api_key=DEEPSEEK_API_KEY,
    base_url="https://api.deepseek.com"
)

def build_system_prompt() -> str:
    """构建 System Prompt"""
    lunar_year, current_zodiac, zodiac_mapping = get_current_lunar_year()
    
    # 生成生肖对照表文本
    zodiac_text = "\n".join([f"- {animal}: {', '.join(numbers)}" for animal, numbers in zodiac_mapping.items()])
    
    lunar_date_str = datetime.now().strftime("%Y年%m月%d日")
    
    prompt = f"""你是一个专业的六合彩下注解析助手。你的任务是将用户的混乱下注信息转换为标准 JSON 格式。

【当前年份】：{lunar_year}年{current_zodiac}年
【农历日期】：{lunar_date_str}

【生肖号码对照表 - {lunar_year}年{current_zodiac}年】
{zodiac_text}
（计算规则：号码 % 12 = 生肖偏移量，当前年生肖固定为模12余1）

【波色对照表】（固定不变）
- 红波: 01,02,07,08,12,13,18,19,23,24,29,30,34,35,40,45,46
- 蓝波: 03,04,09,10,14,15,20,25,26,31,36,37,41,42,47,48
- 绿波: 05,06,11,16,17,21,22,27,28,32,33,38,39,43,44,49

【单双号规则】
- 单号: 01, 03, 05, ..., 47, 49（所有奇数）
- 双号: 02, 04, 06, ..., 46, 48（所有偶数）

【解析规则】（极其重要！）
1. **单位词识别**：
   - "#" "井" "米" "点" "蚊" "元" → 都表示金额单位
   - 如果用户只写数字没有单位（如"各5"），默认视为金额
   
2. **分隔符容错**：
   - 逗号（，）句号（。）斜杠（/）横杠（-）空格 → 都视为号码分隔符
   - 示例："06-20-16" = "06,20,16" = "06 20 16"
   
3. **地区标记忽略**：
   - "澳门" "奥门" "香港" 等地区名称 → 直接忽略，不影响解析
   
4. **生肖组合**：
   - "猪猴龙各号10#" → 猪、猴、龙三个生肖的所有号码，每个号码 $10
   - "虎马各号10" → 虎、马两个生肖的所有号码，每个号码 $10
   
5. **波色组合**：
   - "红波200" → 红波所有号码平分 $200（17个号码，每个约 $11.76）
   - **特殊组合**："绿双蓝单各号5#"
     - 绿双：绿波中的双号（06,16,22,28,32,38,44）
     - 蓝单：蓝波中的单号（03,09,15,25,31,37,41,47）
     - 每个号码 $5
   
6. **混合表达**：
   - "14，31，26，38，15各5井" → 号码14, 31, 26, 38, 15各投注 $5
   - "12.48各50" → 号码12和48各 $50
   - "44/10米" → 号码44投注 $10
   
7. **简写处理**：
   - "各号" = "每个号码"
   - "各数" = "每个号码"
   - "牛各数5点" = 牛生肖所有号码各 $5

【输出格式】（必须严格遵守！）
你必须且只能输出一个有效的 JSON 对象，格式如下：
{{
  "bets": [
    {{"number": "07", "amount": 50}},
    {{"number": "13", "amount": 30}}
  ]
}}

注意事项：
- number 必须是两位数字符串（01-49）
- amount 必须是数字（可以是小数，如 11.76）
- 不要输出任何其他文字、解释或标记
- 如果无法解析，返回空数组：{{"bets": []}}
"""
    return prompt

async def parse_bet_text(text: str) -> List[Dict]:
    """调用 DeepSeek API 解析下注文本"""
    try:
        logger.info(f"📩 用户输入：{text}")
        
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": build_system_prompt()},
                {"role": "user", "content": text}
            ],
            response_format={"type": "json_object"},
            temperature=0.3,
            max_tokens=2000,
            timeout=30
        )
        
        result = response.choices[0].message.content
        logger.info(f"🤖 AI 返回：{result}")
        
        # 解析 JSON
        parsed = json.loads(result)
        bets = parsed.get("bets", [])
        
        logger.info(f"✅ 解析成功：{len(bets)} 个号码")
        return bets
        
    except Exception as e:
        logger.error(f"❌ API 调用失败：{e}")
        return []

# ======================== 消息去重机制 ========================

# 全局消息去重集合（存储已处理的 message_id）
processed_messages = set()
MAX_PROCESSED_MESSAGES = 1000  # 最多保留 1000 条消息ID，防止内存无限增长

def is_message_processed(message_id: int) -> bool:
    """检查消息是否已处理"""
    return message_id in processed_messages

def mark_message_processed(message_id: int):
    """标记消息为已处理"""
    global processed_messages
    
    # 如果超过最大值，清理最旧的一半
    if len(processed_messages) >= MAX_PROCESSED_MESSAGES:
        # 转换为列表，保留后半部分（较新的消息）
        processed_list = list(processed_messages)
        processed_messages = set(processed_list[MAX_PROCESSED_MESSAGES // 2:])
        logger.info(f"🧹 消息去重缓存已清理，当前保留 {len(processed_messages)} 条")
    
    processed_messages.add(message_id)

# ======================== 错误通知机制 ========================

async def send_error_notification(context: ContextTypes.DEFAULT_TYPE, error_type: str, error_detail: str):
    """发送错误通知给用户"""
    try:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        today = datetime.now().strftime("%Y-%m-%d")
        
        message = f"""⚠️ 系统错误通知

时间：{now}
错误类型：{error_type}
错误详情：{error_detail}

📋 已记录到日志：logs/bot_{today}.log
🔄 系统已自动恢复，可继续使用"""
        
        # 获取第一个更新的用户 ID（实际应该从配置读取管理员 ID）
        # 这里简化处理，发送给所有聊天过的用户
        await context.bot.send_message(
            chat_id=context._chat_id if hasattr(context, '_chat_id') else None,
            text=message
        )
        
        logger.info("📤 错误通知已发送")
        
    except Exception as e:
        logger.error(f"❌ 发送错误通知失败：{e}")

# ======================== Telegram 命令处理器 ========================

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理 /start 命令"""
    welcome_message = """🎰 欢迎使用六合彩记账机器人！

📝 **使用方法**：
直接发送下注文本，我会自动解析并记账。

支持格式示例：
• 虎马各号10
• 07,13,25,37各50
• 红波200
• 猪狗龙各号5#，牛虎蛇各号15#

📊 **命令列表**：
/top - 查看风险 Top 10
/reset - 清空所有数据
/backup - 手动备份数据
/restore 2026-01-30 - 恢复指定日期备份
/logs - 查看今日日志摘要

🤖 智能解析 by DeepSeek AI
"""
    await update.message.reply_text(welcome_message)
    logger.info(f"👋 用户 {update.effective_user.id} 启动机器人")

async def top_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理 /top 命令"""
    data = load_data()
    
    # 过滤出金额 > 0 的号码并排序
    sorted_numbers = sorted(
        [(num, amount) for num, amount in data.items() if amount > 0],
        key=lambda x: x[1],
        reverse=True
    )[:10]
    
    if not sorted_numbers:
        await update.message.reply_text("📊 当前暂无数据")
        return
    
    # 构建回复消息
    message = "🔥 当前风险 Top 10：\n\n"
    emojis = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
    
    for i, (num, amount) in enumerate(sorted_numbers):
        message += f"{emojis[i]} {num}号 - ${amount:,.2f}\n"
    
    await update.message.reply_text(message)
    logger.info(f"📊 用户 {update.effective_user.id} 查看 Top 10")

async def reset_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理 /reset 命令"""
    data = init_data()
    save_data(data)
    
    await update.message.reply_text("✅ 所有数据已清空\n当前所有号码金额归零")
    logger.info(f"🗑️ 用户 {update.effective_user.id} 清空数据")

async def backup_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理 /backup 命令"""
    backup_file = backup_data(manual=True)
    
    if backup_file:
        await update.message.reply_text(f"✅ 数据已备份\n文件：{Path(backup_file).name}")
        logger.info(f"💾 用户 {update.effective_user.id} 手动备份数据")
    else:
        await update.message.reply_text("❌ 备份失败，请检查日志")

async def restore_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理 /restore 命令"""
    if not context.args:
        await update.message.reply_text("⚠️ 请指定日期，例如：/restore 2026-01-30")
        return
    
    date_str = context.args[0]
    success = restore_data(date_str)
    
    if success:
        await update.message.reply_text(f"✅ 数据已恢复\n已从 backups/numbers_state_{date_str}.json 恢复数据")
        logger.info(f"♻️ 用户 {update.effective_user.id} 恢复备份：{date_str}")
    else:
        await update.message.reply_text(f"❌ 恢复失败\n备份文件不存在：numbers_state_{date_str}.json")

async def logs_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理 /logs 命令"""
    today = datetime.now().strftime("%Y-%m-%d")
    log_file = LOG_DIR / f"bot_{today}.log"
    
    if not log_file.exists():
        await update.message.reply_text("📋 今日暂无日志")
        return
    
    # 读取最后 10 行
    try:
        with open(log_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        last_lines = lines[-10:] if len(lines) > 10 else lines
        log_text = "".join(last_lines)
        
        message = f"📋 今日日志摘要（最近10条）：\n\n{log_text}"
        await update.message.reply_text(message[:4000])  # Telegram 限制 4096 字符
        
    except Exception as e:
        await update.message.reply_text(f"❌ 读取日志失败：{e}")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理普通文本消息"""
    message_id = update.message.message_id
    text = update.message.text
    user_id = update.effective_user.id
    
    # 消息去重检查
    if is_message_processed(message_id):
        logger.info(f"⏭️ 跳过重复消息 [ID: {message_id}]：{text[:50]}...")
        return
    
    # 标记消息为已处理
    mark_message_processed(message_id)
    logger.info(f"📨 处理新消息 [ID: {message_id}] 用户 {user_id}：{text[:50]}...")
    
    # 解析下注文本
    bets = await parse_bet_text(text)
    
    if not bets:
        await update.message.reply_text("⚠️ 解析失败，请人工核对\n\n请检查输入格式或联系管理员")
        logger.warning(f"⚠️ 用户 {user_id} 的文本解析失败：{text}")
        return
    
    # 加载当前数据
    data = load_data()
    
    # 累加金额
    total_amount = 0
    details = []
    
    for bet in bets:
        number = bet["number"]
        amount = bet["amount"]
        
        if number in data:
            data[number] += amount
            total_amount += amount
            details.append(f"• {number}号 ${amount:.2f}")
        else:
            logger.warning(f"⚠️ 无效号码：{number}")
    
    # 保存数据
    try:
        save_data(data)
    except Exception as e:
        await send_error_notification(context, "数据保存失败", str(e))
        await update.message.reply_text(f"❌ 数据保存失败：{e}")
        return
    
    # 获取 Top 10
    sorted_numbers = sorted(
        [(num, amount) for num, amount in data.items() if amount > 0],
        key=lambda x: x[1],
        reverse=True
    )[:10]
    
    top_text = "\n".join([f"{i+1}️⃣ {num}号 - ${amt:,.2f}" for i, (num, amt) in enumerate(sorted_numbers)])
    
    # 构建回复消息
    reply = f"""✅ 已记录本单：
{chr(10).join(details)}
━━━━━━━━━━━━
📊 本单总额：${total_amount:.2f}

🔥 当前风险 Top 10：
{top_text}"""
    
    await update.message.reply_text(reply)
    logger.info(f"✅ 用户 {user_id} 记账成功：本单 ${total_amount:.2f}，共 {len(bets)} 个号码")

# ======================== 定时任务 ========================

async def daily_backup_task(context: ContextTypes.DEFAULT_TYPE):
    """每日自动备份任务"""
    backup_data()
    logger.info("⏰ 定时备份任务执行完成")

# ======================== 主程序 ========================

def main():
    """主函数"""
    # 获取进程锁
    if not acquire_lock():
        print("\n💡 提示：如果您刚才强制停止了 Bot，锁文件可能残留。")
        print(f"   请手动删除：{LOCK_FILE}")
        print("   然后重新启动。")
        return
    
    try:
        logger.info("🚀 六合彩记账机器人启动中...")
        
        # 显示当前农历年份信息
        lunar_year, current_zodiac, zodiac_mapping = get_current_lunar_year()
        print(f"📅 当前农历年份：{lunar_year}年{current_zodiac}年")
        print(f"🐍 当年生肖：{current_zodiac} ({', '.join(zodiac_mapping[current_zodiac])})")
        
        # 创建 Application
        application = Application.builder().token(TELEGRAM_TOKEN).build()
        
        # 注册命令处理器
        application.add_handler(CommandHandler("start", start_command))
        application.add_handler(CommandHandler("top", top_command))
        application.add_handler(CommandHandler("reset", reset_command))
        application.add_handler(CommandHandler("backup", backup_command))
        application.add_handler(CommandHandler("restore", restore_command))
        application.add_handler(CommandHandler("logs", logs_command))
        
        # 注册消息处理器
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
        
        # 添加定时任务（每日凌晨 00:00 备份）
        job_queue = application.job_queue
        job_queue.run_daily(
            daily_backup_task,
            time=datetime.strptime("00:00", "%H:%M").time()
        )
        
        # 启动机器人
        logger.info("✅ Bot started successfully!")
        print("✅ Bot started successfully!")
        print("按 Ctrl+C 停止运行")
        
        PORT = int(os.environ.get("PORT", 10000))
WEBHOOK_URL = os.environ.get("WEBHOOK_URL", "")

if WEBHOOK_URL:
    application.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        webhook_url=f"{WEBHOOK_URL}/webhook",
        url_path="webhook"
    )
else:
    application.run_polling(allowed_updates=Update.ALL_TYPES)
    
    finally:
        # 确保退出时释放锁
        release_lock()

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("👋 机器人已停止")
        print("\n👋 机器人已停止")
        release_lock()
    except Exception as e:
        logger.critical(f"💥 致命错误：{e}", exc_info=True)
        print(f"💥 致命错误：{e}")
        release_lock()
