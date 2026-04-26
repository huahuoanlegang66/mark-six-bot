#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import json
import logging
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


# ======================== 进程锁 ========================

def acquire_lock() -> bool:
    if LOCK_FILE.exists():
        try:
            with open(LOCK_FILE, 'r') as f:
                old_pid = int(f.read().strip())
            import psutil
            if psutil.pid_exists(old_pid):
                print(f"错误：Bot 已在运行中（进程 ID: {old_pid}）")
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


# ======================== 日志 ========================

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


# ======================== 农历年份 ========================

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


# ======================== 号码对照表（Python查表，精确100%）========================

# 波色对照表（固定）
COLOR_MAP = {
    "红波": ["01", "02", "07", "08", "12", "13", "18", "19", "23", "24", "29", "30", "34", "35", "40", "45", "46"],
    "蓝波": ["03", "04", "09", "10", "14", "15", "20", "25", "26", "31", "36", "37", "41", "42", "47", "48"],
    "绿波": ["05", "06", "11", "16", "17", "21", "22", "27", "28", "32", "33", "38", "39", "43", "44", "49"],
}

# 波色单双细分（固定）
COLOR_PARITY_MAP = {
    "红单": ["01", "07", "13", "19", "23", "29", "35", "45"],
    "红双": ["02", "08", "12", "18", "24", "30", "34", "40", "46"],
    "蓝单": ["03", "09", "15", "25", "31", "37", "41", "47"],
    "蓝双": ["04", "10", "14", "20", "26", "36", "42", "48"],
    "绿单": ["05", "11", "17", "21", "27", "33", "39", "43", "49"],
    "绿双": ["06", "16", "22", "28", "32", "38", "44"],
}

# 大小单双（固定）
SIZE_PARITY_MAP = {
    "小数": [f"{i:02d}" for i in range(1, 25)],
    "大数": [f"{i:02d}" for i in range(25, 50)],
    "小单": [f"{i:02d}" for i in range(1, 25) if i % 2 != 0],
    "小双": [f"{i:02d}" for i in range(1, 25) if i % 2 == 0],
    "大单": [f"{i:02d}" for i in range(25, 50) if i % 2 != 0],
    "大双": [f"{i:02d}" for i in range(25, 50) if i % 2 == 0],
    "单号": [f"{i:02d}" for i in range(1, 50) if i % 2 != 0],
    "双号": [f"{i:02d}" for i in range(1, 50) if i % 2 == 0],
}

# 头组对照表（固定）
HEAD_MAP = {
    "0": [f"{i:02d}" for i in range(1, 10)],   # 0头: 01-09
    "1": [f"{i:02d}" for i in range(10, 20)],  # 1头: 10-19
    "2": [f"{i:02d}" for i in range(20, 30)],  # 2头: 20-29
    "3": [f"{i:02d}" for i in range(30, 40)],  # 3头: 30-39
    "4": [f"{i:02d}" for i in range(40, 50)],  # 4头: 40-49
}


def lookup_numbers(item: dict, zodiac_mapping: Dict[str, List[str]]) -> List[str]:
    """
    根据 AI 解析的 item 类型，从 Python 对照表精确查出号码列表
    AI 只负责识别结构，Python 负责查表，100% 准确
    """
    t = item.get("type", "")
    numbers = []

    if t == "zodiac":
        # 生肖：从农历生肖对照表查
        for name in item.get("names", []):
            if name in zodiac_mapping:
                numbers.extend(zodiac_mapping[name])
            else:
                logger.warning(f"未知生肖：{name}")

    elif t == "color":
        # 波色：红波/蓝波/绿波
        for name in item.get("names", []):
            if name in COLOR_MAP:
                numbers.extend(COLOR_MAP[name])
            else:
                logger.warning(f"未知波色：{name}")

    elif t == "color_parity":
        # 波色单双：红单/红双/蓝单/蓝双/绿单/绿双
        for name in item.get("names", []):
            if name in COLOR_PARITY_MAP:
                numbers.extend(COLOR_PARITY_MAP[name])
            else:
                logger.warning(f"未知波色单双：{name}")

    elif t == "size_parity":
        # 大小单双：小数/大数/小单/小双/大单/大双/单号/双号
        for name in item.get("names", []):
            if name in SIZE_PARITY_MAP:
                numbers.extend(SIZE_PARITY_MAP[name])
            else:
                logger.warning(f"未知大小单双：{name}")

    elif t == "head":
        # 头组：0头/1头/2头/3头/4头
        for h in item.get("heads", []):
            h = str(h)
            if h in HEAD_MAP:
                numbers.extend(HEAD_MAP[h])
            else:
                logger.warning(f"未知头组：{h}")

    elif t == "number":
        # 直接号码
        for n in item.get("numbers", []):
            n = str(n).zfill(2)
            if 1 <= int(n) <= 49:
                numbers.append(n)

    # 去重（同一个item内不去重，允许多个生肖有重叠号码累加）
    return numbers


def expand_bets(items: List[dict], zodiac_mapping: Dict[str, List[str]]) -> Dict[str, float]:
    """
    把 AI 解析的 items 展开成 {号码: 金额} 字典，同号自动累加
    """
    result: Dict[str, float] = {}
    for item in items:
        amount = float(item.get("amount", 0))
        numbers = lookup_numbers(item, zodiac_mapping)
        for num in numbers:
            result[num] = result.get(num, 0) + amount
    return result


# ======================== 数据管理 ========================

def load_data() -> Dict[str, float]:
    if DATA_FILE.exists():
        try:
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
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


# ======================== DeepSeek API ========================

client = OpenAI(
    api_key=DEEPSEEK_API_KEY,
    base_url="https://api.deepseek.com"
)


def build_system_prompt(zodiac_mapping: Dict[str, List[str]]) -> str:
    """
    AI 只负责识别语义结构，不负责查号码
    号码查表完全由 Python 代码处理
    """
    zodiac_names = "、".join(zodiac_mapping.keys())

    prompt = f"""你是六合彩下注语义解析助手。你的唯一任务是识别用户输入的结构，输出JSON。
你不需要知道任何号码，号码查表由程序自动完成。

【你需要识别的类型】

1. type=zodiac（生肖）
   - 识别关键词：{zodiac_names}
   - 示例：马鼠鸡各号15米 → {{"type":"zodiac","names":["马","鼠","鸡"],"amount":15}}

2. type=color（波色）
   - 识别关键词：红波、蓝波、绿波
   - 示例：红波各号10 → {{"type":"color","names":["红波"],"amount":10}}

3. type=color_parity（波色单双）
   - 识别关键词：红单、红双、蓝单、蓝双、绿单、绿双
   - 示例：红双蓝单各号5 → {{"type":"color_parity","names":["红双","蓝单"],"amount":5}}

4. type=size_parity（大小单双）
   - 识别关键词：小数、大数、小单、小双、大单、大双、单号、双号
   - 示例：小单各号10 → {{"type":"size_parity","names":["小单"],"amount":10}}

5. type=head（头组）
   - 识别关键词：0头、1头、2头、3头、4头
   - 示例：03头各号10 → {{"type":"head","heads":["3"],"amount":10}}
   - 注意：03头=3头，头前面的0去掉

6. type=number（直接号码）
   - 用户直接写出的数字号码
   - 示例：07,13,25各15 → {{"type":"number","numbers":["07","13","25"],"amount":15}}
   - 注意：号码必须是01-49的两位数字符串

【金额单位】
"#" "井" "米" "文" "蚊" "点" "元" 都表示金额，直接读数字

【分隔符】
逗号、句号、斜杠、横杠、空格 都是分隔符

【忽略内容】
- "澳门" "香港" "澳" 等地区名
- "共XXX" "合计XXX" 总金额说明

【输出格式】只输出JSON，不要任何其他文字：
{{"items":[
  {{"type":"zodiac","names":["马","鼠"],"amount":15}},
  {{"type":"number","numbers":["07","13"],"amount":10}}
]}}

无法解析时返回：{{"items":[]}}"""
    return prompt


async def parse_bet_text(text: str, zodiac_mapping: Dict[str, List[str]]) -> Dict[str, float]:
    """
    第一步：AI 识别语义结构
    第二步：Python 查表展开号码
    返回 {号码: 金额} 字典
    """
    try:
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": build_system_prompt(zodiac_mapping)},
                {"role": "user", "content": text}
            ],
            response_format={"type": "json_object"},
            temperature=0.1,
            max_tokens=2000,
            timeout=30
        )
        result = response.choices[0].message.content
        logger.info(f"AI返回：{result}")
        parsed = json.loads(result)
        items = parsed.get("items", [])

        # Python 查表展开，精确100%
        bets = expand_bets(items, zodiac_mapping)
        logger.info(f"展开结果：{len(bets)} 个号码，共 ${sum(bets.values()):.2f}")
        return bets

    except Exception as e:
        logger.error(f"API调用失败：{e}")
        return {}


# ======================== 消息去重 ========================

processed_messages = set()


def is_message_processed(message_id: int) -> bool:
    return message_id in processed_messages


def mark_message_processed(message_id: int):
    global processed_messages
    if len(processed_messages) >= 1000:
        processed_list = list(processed_messages)
        processed_messages = set(processed_list[500:])
    processed_messages.add(message_id)


# ======================== Telegram 命令处理器 ========================

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome_message = """🎰 欢迎使用六合彩记账机器人！

📝 直接发送下注文本，自动解析记账。

支持格式：
• 生肖：马鼠鸡各号15米
• 波色：红波各号10井
• 波色单双：红双蓝单各号5#
• 大小单双：小单各号10米
• 头组：03头各号10井
• 直接号码：07,13,25各15米

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

    logger.info(f"处理消息 [ID:{message_id}] 用户{user_id}：{text[:80]}")

    # 获取当前生肖对照表
    _, _, zodiac_mapping = get_current_lunar_year()

    # AI识别结构 + Python查表展开
    bets = await parse_bet_text(text, zodiac_mapping)

    if not bets:
        await update.message.reply_text("⚠️ 解析失败，请人工核对")
        return

    # 加载并更新数据
    data = load_data()
    total_amount = 0
    details = []

    for number, amount in sorted(bets.items()):
        if number in data:
            data[number] += amount
            total_amount += amount
            details.append(f"• {number}号 ${amount:.2f}")

    save_data(data)

    # Top 10
    sorted_numbers = sorted(
        [(num, amount) for num, amount in data.items() if amount > 0],
        key=lambda x: x[1], reverse=True
    )[:10]

    top_text = "\n".join([
        f"{i+1}️⃣ {num}号 - ${amt:,.2f}"
        for i, (num, amt) in enumerate(sorted_numbers)
    ])

    reply = f"""✅ 已记录本单：
{chr(10).join(details)}
━━━━━━━━━━━━
📊 本单总额：${total_amount:.2f}（共{len(bets)}个号码）

🔥 当前风险 Top 10：
{top_text}"""

    await update.message.reply_text(reply)
    logger.info(f"记账成功：${total_amount:.2f}，{len(bets)}个号码")


# ======================== 定时任务 ========================

async def daily_backup_task(context: ContextTypes.DEFAULT_TYPE):
    backup_data()
    logger.info("定时备份完成")


# ======================== 主程序 ========================

def main():
    WEBHOOK_URL = os.environ.get("WEBHOOK_URL", "")

    if not WEBHOOK_URL:
        if not acquire_lock():
            print(f"请手动删除：{LOCK_FILE}")
            return

    try:
        logger.info("🚀 六合彩记账机器人启动中...")
        _, current_zodiac, zodiac_mapping = get_current_lunar_year()
        print(f"📅 当年生肖：{current_zodiac} ({', '.join(zodiac_mapping[current_zodiac])})")

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
            PORT = int(os.environ.get("PORT", 10000))
            logger.info(f"✅ Webhook模式启动，端口：{PORT}")
            print("✅ Bot started successfully! (Webhook模式)")
            application.run_webhook(
                listen="0.0.0.0",
                port=PORT,
                webhook_url=f"{WEBHOOK_URL}/webhook",
                url_path="webhook"
            )
        else:
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
