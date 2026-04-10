#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import json
import logging
import asyncio
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Tuple
import shutil

BASE_DIR = Path(__file__).parent
SITE_PACKAGES = BASE_DIR / "venv" / "Lib" / "site-packages"
if SITE_PACKAGES.exists() and str(SITE_PACKAGES) not in sys.path:
    sys.path.insert(0, str(SITE_PACKAGES))

if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

import lunardate as LunarDate
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

load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
if not TELEGRAM_TOKEN:
    raise ValueError("缺少 TELEGRAM_TOKEN 环境变量")

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
if not DEEPSEEK_API_KEY:
    raise ValueError("缺少 DEEPSEEK_API_KEY 环境变量")

DATA_FILE = BASE_DIR / "numbers_state.json"
BACKUP_DIR = BASE_DIR / "backups"
LOG_DIR = BASE_DIR / "logs"
LOCK_FILE = BASE_DIR / ".bot.lock"

BACKUP_DIR.mkdir(exist_ok=True)
LOG_DIR.mkdir(exist_ok=True)


def acquire_lock() -> bool:
    if LOCK_FILE.exists():
        try:
            with open(LOCK_FILE, 'r') as f:
                old_pid = int(f.read().strip())
            import psutil
            if psutil.pid_exists(old_pid):
                print(f"错误：Bot 已在运行中（进程 ID: {old_pid}）")
                print(f"请删除文件：{LOCK_FILE}")
                return False
            else:
                LOCK_FILE.unlink()
        except Exception as e:
            print(f"读取锁文件失败：{e}")
            return False
    try:
        with open(LOCK_FILE, 'w') as f:
            f.write(str(os.getpid()))
        return True
    except Exception as e:
        print(f"创建锁文件失败：{e}")
        return False


def release_lock():
    if LOCK_FILE.exists():
        try:
            LOCK_FILE.unlink()
        except Exception:
            pass


def cleanup_old_files(directory: Path, days: int, pattern: str):
    cutoff_date = datetime.now() - timedelta(days=days)
    for file in directory.glob(pattern):
        if file.is_file():
            file_time = datetime.fromtimestamp(file.stat().st_mtime)
            if file_time < cutoff_date:
                file.unlink()
                print(f"已删除旧文件：{file.name}")


def setup_logging():
    today = datetime.now().strftime("%Y-%m-%d")
    log_file = LOG_DIR / f"bot_{today}.log"
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file, encoding='utf-8'),
            logging.StreamHandler()
        ]
    )
    cleanup_old_files(LOG_DIR, days=30, pattern="bot_*.log")
    return logging.getLogger(__name__)


logger = setup_logging()


def get_current_lunar_year() -> Tuple[int, str, Dict[str, List[str]]]:
    today = datetime.now()
    try:
        lunar = LunarDate.LunarDate.fromSolarDate(today.year, today.month, today.day)
        lunar_year = lunar.year
        zodiac_animals = ["鼠", "牛", "虎", "兔", "龙", "蛇", "马", "羊", "猴", "鸡", "狗", "猪"]
        zodiac_index = (lunar_year - 4) % 12
        current_zodiac = zodiac_animals[zodiac_index]
        zodiac_mapping = {}
        for i, animal in enumerate(zodiac_animals):
            offset = (i - zodiac_index) % 12
            if offset == 0:
                offset = 12
            remainder = (13 - offset) % 12
            if remainder == 0:
                remainder = 12
            numbers = []
            for num in range(1, 50):
                if num % 12 == (remainder % 12):
                    numbers.append(f"{num:02d}")
            zodiac_mapping[animal] = numbers
        logger.info(f"当前农历年份：{lunar_year}年{current_zodiac}年")
        return lunar_year, current_zodiac, zodiac_mapping
    except Exception as e:
        logger.error(f"农历计算失败：{e}")
        return 2026, "马", {"马": ["01", "13", "25", "37", "49"]}


COLOR_MAPPING = {
    "红波": ["01", "02", "07", "08", "12", "13", "18", "19", "23", "24", "29", "30", "34", "35", "40", "45", "46"],
    "蓝波": ["03", "04", "09", "10", "14", "15", "20", "25", "26", "31", "36", "37", "41", "42", "47", "48"],
    "绿波": ["05", "06", "11", "16", "17", "21", "22", "27", "28", "32", "33", "38", "39", "43", "44", "49"]
}


def load_data() -> Dict[str, float]:
    if DATA_FILE.exists():
        try:
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return data
        except Exception:
            return init_data()
    return init_data()


def init_data() -> Dict[str, float]:
    return {f"{i:02d}": 0.0 for i in range(1, 50)}


def save_data(data: Dict[str, float]):
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def backup_data(manual=False) -> str:
    try:
        today = datetime.now().strftime("%Y-%m-%d")
        backup_file = BACKUP_DIR / f"numbers_state_{today}.json"
        if DATA_FILE.exists():
            shutil.copy2(DATA_FILE, backup_file)
            cleanup_old_files(BACKUP_DIR, days=7, pattern="numbers_state_*.json")
            return str(backup_file)
        return ""
    except Exception:
        return ""


def restore_data(date_str: str) -> bool:
    try:
        backup_file = BACKUP_DIR / f"numbers_state_{date_str}.json"
        if backup_file.exists():
            shutil.copy2(backup_file, DATA_FILE)
            return True
        return False
    except Exception:
        return False


client = OpenAI(
    api_key=DEEPSEEK_API_KEY,
    base_url="https://api.deepseek.com"
)


def build_system_prompt() -> str:
    lunar_year, current_zodiac, zodiac_mapping = get_current_lunar_year()
    zodiac_text = "\n".join([f"- {animal}: {', '.join(numbers)}" for animal, numbers in zodiac_mapping.items()])
    prompt = f"""你是一个专业的六合彩下注解析助手。将用户的下注信息转换为标准 JSON 格式。

【当前年份】：{lunar_year}年{current_zodiac}年

【生肖号码对照表】
{zodiac_text}

【波色对照表】
- 红波: 01,02,07,08,12,13,18,19,23,24,29,30,34,35,40,45,46
- 蓝波: 03,04,09,10,14,15,20,25,26,31,36,37,41,42,47,48
- 绿波: 05,06,11,16,17,21,22,27,28,32,33,38,39,43,44,49

【单双号规则】
- 单号: 01,03,05...49（奇数）
- 双号: 02,04,06...48（偶数）

【解析规则】
1. "#" "井" "米" "点" "蚊" "元" 都表示金额单位
2. 逗号、句号、斜杠、横杠、空格 都是分隔符
3. "澳门" "香港" 等地区名称直接忽略
4. "猪猴龙各号10#" → 三个生肖所有号码各$10
5. "红波200" → 红波所有号码平分$200
6. "绿双蓝单各号5#" → 绿波双号+蓝波单号各$5

【输出格式】只输出JSON，不要其他文字：
{{"bets": [{{"number": "07", "amount": 50}}]}}

number必须是两位字符串(01-49)，amount是数字，无法解析返回{{"bets": []}}"""
    return prompt


async def parse_bet_text(text: str) -> List[Dict]:
    try:
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
        parsed = json.loads(result)
        return parsed.get("bets", [])
    except Exception as e:
        logger.error(f"API调用失败：{e}")
        return []


processed_messages = set()


def is_message_processed(message_id: int) -> bool:
    return message_id in processed_messages


def mark_message_processed(message_id: int):
    global processed_messages
    if len(processed_messages) >= 1000:
        processed_list = list(processed_messages)
        processed_messages = set(processed_list[500:])
    processed_messages.add(message_id)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome_message = """🎰 欢迎使用六合彩记账机器人！

📝 直接发送下注文本，自动解析记账。

📊 命令列表：
/top - 查看风险 Top 10
/reset - 清空所有数据
/backup - 手动备份数据
/restore 2026-01-30 - 恢复指定日期备份
/logs - 查看今日日志摘要"""
    await update.message.reply_text(welcome_message)


async def top_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    sorted_numbers = sorted(
        [(num, amount) for num, amount in data.items() if amount > 0],
        key=lambda x: x[1], reverse=True
    )[:10]
    if not sorted_numbers:
        await update.message.reply_text("📊 当前暂无数据")
        return
    message = "🔥 当前风险 Top 10：\n\n"
    emojis = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
    for i, (num, amount) in enumerate(sorted_numbers):
        message += f"{emojis[i]} {num}号 - ${amount:,.2f}\n"
    await update.message.reply_text(message)


async def reset_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = init_data()
    save_data(data)
    await update.message.reply_text("✅ 所有数据已清空")


async def backup_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    backup_file = backup_data(manual=True)
    if backup_file:
        await update.message.reply_text(f"✅ 数据已备份\n文件：{Path(backup_file).name}")
    else:
        await update.message.reply_text("❌ 备份失败")


async def restore_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("请指定日期，例如：/restore 2026-01-30")
        return
    date_str = context.args[0]
    if restore_data(date_str):
        await update.message.reply_text(f"✅ 数据已恢复：{date_str}")
    else:
        await update.message.reply_text(f"❌ 备份文件不存在：{date_str}")


async def logs_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    today = datetime.now().strftime("%Y-%m-%d")
    log_file = LOG_DIR / f"bot_{today}.log"
    if not log_file.exists():
        await update.message.reply_text("📋 今日暂无日志")
        return
    try:
        with open(log_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        last_lines = lines[-10:] if len(lines) > 10 else lines
        log_text = "".join(last_lines)
        await update.message.reply_text(f"📋 今日日志（最近10条）：\n\n{log_text}"[:4000])
    except Exception as e:
        await update.message.reply_text(f"❌ 读取日志失败：{e}")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message_id = update.message.message_id
    text = update.message.text
    user_id = update.effective_user.id

    if is_message_processed(message_id):
        return
    mark_message_processed(message_id)

    logger.info(f"处理消息 [ID:{message_id}] 用户{user_id}：{text[:50]}")

    bets = await parse_bet_text(text)
    if not bets:
        await update.message.reply_text("⚠️ 解析失败，请人工核对")
        return

    data = load_data()
    total_amount = 0
    details = []

    for bet in bets:
        number = bet["number"]
        amount = bet["amount"]
        if number in data:
            data[number] += amount
            total_amount += amount
            details.append(f"• {number}号 ${amount:.2f}")

    save_data(data)

    sorted_numbers = sorted(
        [(num, amount) for num, amount in data.items() if amount > 0],
        key=lambda x: x[1], reverse=True
    )[:10]

    top_text = "\n".join([f"{i+1}️⃣ {num}号 - ${amt:,.2f}" for i, (num, amt) in enumerate(sorted_numbers)])

    reply = f"""✅ 已记录本单：
{chr(10).join(details)}
━━━━━━━━━━━━
📊 本单总额：${total_amount:.2f}

🔥 当前风险 Top 10：
{top_text}"""

    await update.message.reply_text(reply)
    logger.info(f"记账成功：${total_amount:.2f}，{len(bets)}个号码")


async def daily_backup_task(context: ContextTypes.DEFAULT_TYPE):
    backup_data()
    logger.info("定时备份完成")


def main():
    # 云端 Webhook 模式不需要进程锁
    WEBHOOK_URL = os.environ.get("WEBHOOK_URL", "")

    if not WEBHOOK_URL:
        # 本地模式才需要进程锁
        if not acquire_lock():
            print(f"请手动删除：{LOCK_FILE}")
            return

    try:
        logger.info("🚀 六合彩记账机器人启动中...")

        lunar_year, current_zodiac, zodiac_mapping = get_current_lunar_year()
        print(f"📅 当前农历年份：{lunar_year}年{current_zodiac}年")
        print(f"当年生肖：{current_zodiac} ({', '.join(zodiac_mapping[current_zodiac])})")

        application = Application.builder().token(TELEGRAM_TOKEN).build()

        application.add_handler(CommandHandler("start", start_command))
        application.add_handler(CommandHandler("top", top_command))
        application.add_handler(CommandHandler("reset", reset_command))
        application.add_handler(CommandHandler("backup", backup_command))
        application.add_handler(CommandHandler("restore", restore_command))
        application.add_handler(CommandHandler("logs", logs_command))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

        job_queue = application.job_queue
        job_queue.run_daily(
            daily_backup_task,
            time=datetime.strptime("00:00", "%H:%M").time()
        )

        if WEBHOOK_URL:
            # 云端 Webhook 模式
            PORT = int(os.environ.get("PORT", 10000))
            logger.info(f"✅ Webhook模式启动，端口：{PORT}")
            print(f"✅ Bot started successfully! (Webhook模式)")
            application.run_webhook(
                listen="0.0.0.0",
                port=PORT,
                webhook_url=f"{WEBHOOK_URL}/webhook",
                url_path="webhook"
            )
        else:
            # 本地轮询模式
            logger.info("✅ Bot started successfully!")
            print("✅ Bot started successfully!")
            print("按 Ctrl+C 停止运行")
            application.run_polling(allowed_updates=Update.ALL_TYPES)

    finally:
        if not WEBHOOK_URL:
            release_lock()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n👋 机器人已停止")
        release_lock()
    except Exception as e:
        logger.critical(f"致命错误：{e}", exc_info=True)
        print(f"致命错误：{e}")
        release_lock()
