"""
🎭 МАФИЯ BOT для Telegram
Полнофункциональный бот для игры в Мафию в групповом чате.
Версия: 1.0

Требования:
    pip install python-telegram-bot==20.7

Запуск:
    python mafia_bot.py
"""

import asyncio
import logging
import random
import json
import os
from collections import defaultdict
from datetime import datetime
from typing import Dict, List, Optional, Set, Tuple
from enum import Enum, auto

from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    BotCommand, Chat, User
)
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes, ConversationHandler
)
from telegram.constants import ParseMode

# ═══════════════════════════════════════════════════════════════
# НАСТРОЙКИ
# ═══════════════════════════════════════════════════════════════

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Токен бота (замените на свой из @BotFather)
BOT_TOKEN = "YOUR_BOT_TOKEN_HERE"

# ═══════════════════════════════════════════════════════════════
# ПЕРЕЧИСЛЕНИЯ И КОНСТАНТЫ
# ═══════════════════════════════════════════════════════════════

class GamePhase(Enum):
    WAITING = auto()
    NIGHT = auto()
    DAY = auto()
    VOTING = auto()
    JUDGE = auto()
    FINISHED = auto()

class Role(Enum):
    # Мирные
    SHERIFF = "🤠 Шериф"
    SERGEANT = "👮 Сержант"
    DOCTOR = "👨‍⚕️ Доктор"
    COURTESAN = "💃 Куртизанка"
    JOURNALIST = "📰 Журналист"
    BUM = "🧙 Бомж"
    POSTMAN = "📮 Почтальон"
    JAILER = "🔒 Тюремщик"
    GUNMAN = "🔫 Стрелок"
    CUPID = "💘 Амур"
    JUDGE = "⚖️ Судья"
    VETERAN = "🛡️ Ветеран"
    # Нейтральные
    MANIAC = "🔪 Маньяк"
    HARLOT = "🦠 Путана"
    WITCH = "🧙‍♀️ Ведьма"
    # Мафия
    MAFIA = "🎩 Мафиози"
    MAFIA_BOSS = "👑 Босс Мафии"
    MAFIA_HENCHMAN = "🦹 Подручный Мафии"
    # Якудза
    YAKUZA = "🐉 Якудза"
    YAKUZA_BOSS = "🐲 Босс Якудза"
    YAKUZA_HENCHMAN = "🥷 Подручный Якудза"

class Team(Enum):
    CIVILIAN = "Мирные"
    MAFIA = "Мафия"
    YAKUZA = "Якудза"
    NEUTRAL = "Нейтральные"
    MANIAC = "Маньяк"

ROLE_TEAMS = {
    Role.SHERIFF: Team.CIVILIAN, Role.SERGEANT: Team.CIVILIAN,
    Role.DOCTOR: Team.CIVILIAN, Role.COURTESAN: Team.CIVILIAN,
    Role.JOURNALIST: Team.CIVILIAN, Role.BUM: Team.CIVILIAN,
    Role.POSTMAN: Team.CIVILIAN, Role.JAILER: Team.CIVILIAN,
    Role.GUNMAN: Team.CIVILIAN, Role.CUPID: Team.CIVILIAN,
    Role.JUDGE: Team.CIVILIAN, Role.VETERAN: Team.CIVILIAN,
    Role.MANIAC: Team.MANIAC, Role.HARLOT: Team.NEUTRAL,
    Role.WITCH: Team.NEUTRAL,
    Role.MAFIA: Team.MAFIA, Role.MAFIA_BOSS: Team.MAFIA,
    Role.MAFIA_HENCHMAN: Team.MAFIA,
    Role.YAKUZA: Team.YAKUZA, Role.YAKUZA_BOSS: Team.YAKUZA,
    Role.YAKUZA_HENCHMAN: Team.YAKUZA,
}

# ═══════════════════════════════════════════════════════════════
# КЛАСС ИГРОКА
# ═══════════════════════════════════════════════════════════════

class Player:
    def __init__(self, user_id: int, username: str, first_name: str):
        self.user_id = user_id
        self.username = username
        self.first_name = first_name
        self.display_name = f"@{username}" if username else first_name
        self.role: Optional[Role] = None
        self.team: Optional[Team] = None
        self.is_alive = True
        self.is_active = True
        # Ролевые данные
        self.courtesan_target: Optional[int] = None
        self.courtesan_previous: Optional[int] = None
        self.doctor_heals: Dict[int, int] = defaultdict(int)
        self.journalist_targets: Tuple[Optional[int], Optional[int]] = (None, None)
        self.bum_target: Optional[int] = None
        self.postman_from: Optional[int] = None
        self.postman_to: Optional[int] = None
        self.postman_sent_to: Set[int] = set()
        self.jailer_targets: List[int] = []
        self.jailer_weapon_given = False
        self.gunman_bullets = 3
        self.gunman_shot_day = False
        self.veteran_guards = 3
        self.veteran_guarding = False
        self.maniac_target: Optional[int] = None
        self.harlot_target: Optional[int] = None
        self.witch_target: Optional[int] = None
        self.witch_control_target: Optional[int] = None
        self.mafia_target: Optional[int] = None
        self.yakuza_target: Optional[int] = None
        self.is_lover = False
        self.lover_id: Optional[int] = None
        self.is_infected = False
        self.judge_pardon: Optional[bool] = None
        self.sheriff_invited: Set[int] = set()
        self.sheriff_station_guarded = False
        self.sheriff_check_target: Optional[int] = None
        self.sheriff_kill_target: Optional[int] = None
        self.vote_target: Optional[int] = None
        self.has_voted = False
        self.night_action_done = False
        self.doctor_target: Optional[int] = None

    def __repr__(self):
        status = "🟢" if self.is_alive else "🔴"
        role = self.role.value if self.role else "❓"
        return f"{status} {self.display_name} ({role})"


# ═══════════════════════════════════════════════════════════════
# КЛАСС ИГРЫ
# ═══════════════════════════════════════════════════════════════

class MafiaGame:
    def __init__(self, chat_id: int, creator_id: int):
        self.chat_id = chat_id
        self.creator_id = creator_id
        self.host_id: Optional[int] = None
        self.phase = GamePhase.WAITING
        self.day_number = 0
        self.players: Dict[int, Player] = {}
        self.player_order: List[int] = []
        self.mafia_chat: Set[int] = set()
        self.yakuza_chat: Set[int] = set()
        self.police_station: Set[int] = set()
        self.jail_chat: Set[int] = set()
        self.lovers_chat: Set[int] = set()
        self.night_deaths: List[int] = []
        self.day_deaths: List[int] = []
        self.vote_results: Dict[int, List[int]] = {}
        self.game_log: List[str] = []
        self.sheriff_id: Optional[int] = None
        self.sergeant_id: Optional[int] = None
        self.mafia_boss_id: Optional[int] = None
        self.yakuza_boss_id: Optional[int] = None
        self.judge_id: Optional[int] = None
        self.cupid_id: Optional[int] = None
        self.night_kills: Dict[int, Set[Tuple[str, int]]] = {}
        self.night_saves: Dict[int, Set[str]] = {}
        self.night_checks: Dict[int, str] = {}
        self.first_night = True
        self.voting_active = False
        self.judge_decision_pending = False
        self.gunman_shot_today = False
        self.pending_lover2: Optional[int] = None

    def add_player(self, user_id: int, username: str, first_name: str) -> bool:
        if user_id in self.players:
            return False
        self.players[user_id] = Player(user_id, username, first_name)
        self.player_order.append(user_id)
        return True

    def remove_player(self, user_id: int) -> bool:
        if user_id not in self.players:
            return False
        self.players[user_id].is_active = False
        self.players[user_id].is_alive = False
        if user_id in self.player_order:
            self.player_order.remove(user_id)
        return True

    def get_alive_players(self) -> Dict[int, Player]:
        return {uid: p for uid, p in self.players.items() if p.is_alive}

    def get_alive_by_role(self, role: Role) -> List[Player]:
        return [p for p in self.get_alive_players().values() if p.role == role]

    def get_alive_by_team(self, team: Team) -> List[Player]:
        return [p for p in self.get_alive_players().values() if p.team == team]

    def assign_roles(self, role_list: List[Role]):
        # Назначаем роли только игрокам (не ведущему)
        players_only = [uid for uid in self.get_alive_players().keys() if uid != self.host_id]
        random.shuffle(players_only)
        for i, user_id in enumerate(players_only):
            if i < len(role_list):
                role = role_list[i]
                self.players[user_id].role = role
                self.players[user_id].team = ROLE_TEAMS[role]
                if role == Role.SHERIFF:
                    self.sheriff_id = user_id
                    self.police_station.add(user_id)
                elif role == Role.SERGEANT:
                    self.sergeant_id = user_id
                    self.police_station.add(user_id)
                elif role == Role.MAFIA_BOSS:
                    self.mafia_boss_id = user_id
                    self.mafia_chat.add(user_id)
                elif role in [Role.MAFIA, Role.MAFIA_HENCHMAN]:
                    self.mafia_chat.add(user_id)
                elif role == Role.YAKUZA_BOSS:
                    self.yakuza_boss_id = user_id
                    self.yakuza_chat.add(user_id)
                elif role in [Role.YAKUZA, Role.YAKUZA_HENCHMAN]:
                    self.yakuza_chat.add(user_id)
                elif role == Role.JUDGE:
                    self.judge_id = user_id
                elif role == Role.CUPID:
                    self.cupid_id = user_id
                elif role == Role.GUNMAN:
                    self.players[user_id].gunman_bullets = 3
                elif role == Role.VETERAN:
                    self.players[user_id].veteran_guards = 3

    def log(self, message: str):
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.game_log.append(f"[{timestamp}] {message}")
        logger.info(f"[Game {self.chat_id}] {message}")


# ═══════════════════════════════════════════════════════════════
# ГЛОБАЛЬНОЕ ХРАНИЛИЩЕ
# ═══════════════════════════════════════════════════════════════

games: Dict[int, MafiaGame] = {}
user_game: Dict[int, int] = {}


def get_game(chat_id: int) -> Optional[MafiaGame]:
    return games.get(chat_id)

def create_game(chat_id: int, creator_id: int) -> MafiaGame:
    game = MafiaGame(chat_id, creator_id)
    games[chat_id] = game
    return game

def delete_game(chat_id: int):
    if chat_id in games:
        game = games[chat_id]
        for uid in list(game.players.keys()):
            if uid in user_game and user_game[uid] == chat_id:
                del user_game[uid]
        del games[chat_id]

def get_player_game(user_id: int) -> Optional[MafiaGame]:
    chat_id = user_game.get(user_id)
    if chat_id:
        return games.get(chat_id)
    return None

def format_players_list(game: MafiaGame, show_roles: bool = False, include_host: bool = True) -> str:
    lines = []
    for uid in game.player_order:
        p = game.players[uid]
        # Ведущий не отображается в списке игроков (только в своей вкладке)
        if uid == game.host_id and not include_host:
            continue
        status = "🟢" if p.is_alive else "💀"
        if show_roles and p.role:
            lines.append(f"{status} {p.display_name} — {p.role.value}")
        else:
            lines.append(f"{status} {p.display_name}")
    return "\n".join(lines) if lines else "Нет игроков"

def get_role_description(role: Role) -> str:
    descriptions = {
        Role.SHERIFF: "Проверяет роли и может убивать ночью. Имеет полицейский участок.",
        Role.SERGEANT: "Помощник Шерифа. Если Шериф погибает — становится Шерифом.",
        Role.DOCTOR: "Лечит одного игрока ночью. Каждого можно спасти 2 раза (не подряд).",
        Role.COURTESAN: "Забирает клиента к себе, спасая от убийства, но мешая его роли.",
        Role.JOURNALIST: "Сравнивает 2 игроков на принадлежность к одной группировке.",
        Role.BUM: "Следит за игроком ночью. Узнаёт убийцу, если игрока убьют.",
        Role.POSTMAN: "Проверяет одного игрока, результат приходит другому.",
        Role.JAILER: "Заключает 2 игроков в тюрьму. Может дать оружие.",
        Role.GUNMAN: "Имеет 3 пули. Может стрелять днем (не в 1-й день).",
        Role.CUPID: "Выбирает 2 влюблённых. Если один умирает — умирает и второй.",
        Role.JUDGE: "Решает судьбу приговорённого — казнить или помиловать.",
        Role.VETERAN: "Может встать на защиту 3 раза за игру. Убивает ночных посетителей.",
        Role.MANIAC: "Убивает одного игрока ночью. Побеждает в одиночку. Видится мирным для Шерифа.",
        Role.HARLOT: "Заражает чумой. Побеждает, когда все заражены. Доктор лечит чуму.",
        Role.WITCH: "Контролирует действия других. Имеет магический барьер.",
        Role.MAFIA: "Член мафии. Убивает ночью вместе с командой.",
        Role.MAFIA_BOSS: "Босс мафии. Руководит командой.",
        Role.MAFIA_HENCHMAN: "Подручный мафии.",
        Role.YAKUZA: "Член якудза. Убивает ночью вместе с командой.",
        Role.YAKUZA_BOSS: "Босс якудза. +1 голос при ничьей. Ниндзя для Шерифа.",
        Role.YAKUZA_HENCHMAN: "Подручный якудза.",
    }
    return descriptions.get(role, "Описание отсутствует")


# ═══════════════════════════════════════════════════════════════
# ОБРАБОТЧИКИ КОМАНД
# ═══════════════════════════════════════════════════════════════

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎭 *Добро пожаловать в бота Мафия!*\n\n"
        "Я управляю игрой в Мафию прямо в групповом чате.\n"
        "Создатель игры становится *Ведущим* и контролирует ход.\n\n"
        "📋 *Основные команды:*\n"
        "`/newgame` — создать новую игру\n"
        "`/join` — присоединиться\n"
        "`/roles` — список ролей\n"
        "`/rules` — правила\n"
        "`/startnight` — начать ночь (ведущий)\n"
        "`/endnight` — закончить ночь (ведущий)\n"
        "`/startvote` — начать голосование (ведущий)\n"
        "`/endvote` — закончить голосование (ведущий)\n"
        "`/kill @ник` — убить днём (стрелок)\n\n"
        "Начните с `/newgame` в групповом чате!",
        parse_mode=ParseMode.MARKDOWN
    )

async def newgame_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user
    if chat.type == "private":
        await update.message.reply_text("❌ Игра создаётся только в *групповом чате*!", parse_mode=ParseMode.MARKDOWN)
        return
    if chat.id in games:
        delete_game(chat.id)
    game = create_game(chat.id, user.id)
    game.host_id = user.id
    game.add_player(user.id, user.username, user.first_name)
    user_game[user.id] = chat.id
    keyboard = [
        [InlineKeyboardButton("🎮 Присоединиться", callback_data="join_game")],
        [InlineKeyboardButton("▶️ Начать игру", callback_data="start_game")],
        [InlineKeyboardButton("❌ Отменить", callback_data="cancel_game")]
    ]
    host_name = game.players[user.id].display_name
    await update.message.reply_text(
        f"🎭 *Новая игра Мафия создана!*\n\n"
        f"👤 *Ведущий:* {host_name}\n"
        f"👥 *Игроки (0):*\n_пока никто не присоединился_\n\n"
        f"Нажмите «Присоединиться» чтобы войти в игру!",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def join_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user
    if chat.type == "private":
        await update.message.reply_text("❌ Только в групповом чате!")
        return
    game = get_game(chat.id)
    if not game:
        await update.message.reply_text("❌ Нет активной игры. Создайте с помощью `/newgame`", parse_mode=ParseMode.MARKDOWN)
        return
    if game.phase != GamePhase.WAITING:
        await update.message.reply_text("❌ Игра уже началась!")
        return
    if user.id in game.players:
        await update.message.reply_text("❌ Вы уже в игре!")
        return
    game.add_player(user.id, user.username, user.first_name)
    user_game[user.id] = chat.id

    # Уведомление о присоединении
    host = game.players.get(game.host_id)
    host_name = host.display_name if host else "Ведущий"
    player_count = len([p for p in game.players.values() if p.user_id != game.host_id])

    await update.message.reply_text(
        f"✅ *{game.players[user.id].display_name}* присоединился к игре!\n"
        f"👥 Всего игроков: {player_count}\n"
        f"👤 Ведущий: {host_name}\n\n"
        f"📋 *Текущие игроки:*\n{format_players_list(game, include_host=False)}",
        parse_mode=ParseMode.MARKDOWN
    )

async def leave_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user
    game = get_game(chat.id)
    if not game or user.id not in game.players:
        await update.message.reply_text("❌ Вы не в игре!")
        return
    game.remove_player(user.id)
    if game.phase == GamePhase.WAITING:
        remaining = len([p for p in game.players.values() if p.is_active and p.user_id != game.host_id])
        await update.message.reply_text(
            f"👋 {user.first_name} покинул игру.\n"
            f"👥 Осталось игроков: {remaining}"
        )
    else:
        await update.message.reply_text(f"💀 {user.first_name} вышел из игры и считается мёртвым.")

async def players_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    game = get_game(chat.id)
    if not game:
        await update.message.reply_text("❌ Нет активной игры!")
        return
    show_roles = game.phase == GamePhase.FINISHED
    host = game.players.get(game.host_id)
    host_name = host.display_name if host else "?"
    player_count = len([p for p in game.players.values() if p.user_id != game.host_id])

    text = f"👤 *Ведущий:* {host_name}\n\n"
    text += f"👥 *Игроки ({player_count}):*\n{format_players_list(game, show_roles, include_host=False)}"

    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

async def roles_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = "🎭 *Доступные роли:*\n\n"
    text += "*🟦 Мирные:*\n"
    for role in [Role.SHERIFF, Role.SERGEANT, Role.DOCTOR, Role.COURTESAN,
                 Role.JOURNALIST, Role.BUM, Role.POSTMAN, Role.JAILER,
                 Role.GUNMAN, Role.CUPID, Role.JUDGE, Role.VETERAN]:
        text += f"{role.value} — {get_role_description(role)}\n"
    text += "\n*🟨 Нейтральные:*\n"
    for role in [Role.MANIAC, Role.HARLOT, Role.WITCH]:
        text += f"{role.value} — {get_role_description(role)}\n"
    text += "\n*🟥 Мафия:*\n"
    for role in [Role.MAFIA, Role.MAFIA_BOSS, Role.MAFIA_HENCHMAN]:
        text += f"{role.value} — {get_role_description(role)}\n"
    text += "\n*🟫 Якудза:*\n"
    for role in [Role.YAKUZA, Role.YAKUZA_BOSS, Role.YAKUZA_HENCHMAN]:
        text += f"{role.value} — {get_role_description(role)}\n"
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

async def rules_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rules = (
        "📜 *Правила игры Мафия*\n\n"
        "*Фазы:* 1️⃣ Ночь — роли делают ходы | 2️⃣ День — обсуждение и голосование\n\n"
        "*Голосование:*\n"
        "• Открытое, каждый называет ник (против себя нельзя!)\n"
        "• Повторно голосовать нельзя\n"
        "• При равенстве решает Судья → последний убитый мирный → случайный выбор\n\n"
        "*Победа:* Мирные (нет мафии/маньяка) | Мафия/Якудза (равенство/превосходство) | "
        "Маньяк (один остался) | Путана (все заражены)\n\n"
        "*Особенности:* Приватные каналы для команд, у всех есть роль!"
    )
    await update.message.reply_text(rules, parse_mode=ParseMode.MARKDOWN)


# ═══════════════════════════════════════════════════════════════
# КОМАНДЫ ВЕДУЩЕГО
# ═══════════════════════════════════════════════════════════════

async def setroles_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user
    game = get_game(chat.id)
    if not game or game.phase != GamePhase.WAITING:
        await update.message.reply_text("❌ Игра не в режиме ожидания!")
        return
    if user.id != game.host_id:
        await update.message.reply_text("❌ Только Ведущий может назначать роли!")
        return
    if not context.args:
        await update.message.reply_text(
            "❌ Укажите роли! Пример:\n"
            "`/setroles sheriff doctor mafia mafia_boss maniac yakuza judge cupid`",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    role_map = {
        "sheriff": Role.SHERIFF, "шериф": Role.SHERIFF,
        "sergeant": Role.SERGEANT, "сержант": Role.SERGEANT,
        "doctor": Role.DOCTOR, "доктор": Role.DOCTOR,
        "courtesan": Role.COURTESAN, "куртизанка": Role.COURTESAN,
        "journalist": Role.JOURNALIST, "журналист": Role.JOURNALIST,
        "bum": Role.BUM, "бомж": Role.BUM,
        "postman": Role.POSTMAN, "почтальон": Role.POSTMAN,
        "jailer": Role.JAILER, "тюремщик": Role.JAILER,
        "gunman": Role.GUNMAN, "стрелок": Role.GUNMAN,
        "cupid": Role.CUPID, "амур": Role.CUPID,
        "judge": Role.JUDGE, "судья": Role.JUDGE,
        "veteran": Role.VETERAN, "ветеран": Role.VETERAN,
        "maniac": Role.MANIAC, "маньяк": Role.MANIAC,
        "harlot": Role.HARLOT, "путана": Role.HARLOT,
        "witch": Role.WITCH, "ведьма": Role.WITCH,
        "mafia": Role.MAFIA, "мафия": Role.MAFIA,
        "mafia_boss": Role.MAFIA_BOSS, "босс_мафии": Role.MAFIA_BOSS,
        "mafia_henchman": Role.MAFIA_HENCHMAN, "подручный_мафии": Role.MAFIA_HENCHMAN,
        "yakuza": Role.YAKUZA, "якудза": Role.YAKUZA,
        "yakuza_boss": Role.YAKUZA_BOSS, "босс_якудза": Role.YAKUZA_BOSS,
        "yakuza_henchman": Role.YAKUZA_HENCHMAN, "подручный_якудза": Role.YAKUZA_HENCHMAN,
    }
    roles = []
    for arg in context.args:
        role_key = arg.lower()
        if role_key in role_map:
            roles.append(role_map[role_key])
        else:
            await update.message.reply_text(f"❌ Неизвестная роль: `{arg}`", parse_mode=ParseMode.MARKDOWN)
            return
    player_count = len([p for p in game.players.values() if p.user_id != game.host_id])
    if len(roles) != player_count:
        await update.message.reply_text(f"❌ Ролей ({len(roles)}) != игроков ({player_count})! Ведущий не получает роль.")
        return
    game.assign_roles(roles)
    for uid, player in game.players.items():
        if player.role:
            try:
                team_text = ""
                if player.team == Team.MAFIA:
                    mafia_names = [game.players[m].display_name for m in game.mafia_chat if m != uid]
                    team_text = f"\n🎩 *Союзники мафии:* {', '.join(mafia_names)}" if mafia_names else ""
                elif player.team == Team.YAKUZA:
                    yakuza_names = [game.players[y].display_name for y in game.yakuza_chat if y != uid]
                    team_text = f"\n🐉 *Союзники якудза:* {', '.join(yakuza_names)}" if yakuza_names else ""
                elif player.role == Role.SERGEANT:
                    if game.sheriff_id:
                        team_text = f"\n🤠 *Ваш Шериф:* {game.players[game.sheriff_id].display_name}"
                await context.bot.send_message(
                    chat_id=uid,
                    text=f"🎭 *Ваша роль:* {player.role.value}\n"
                         f"{get_role_description(player.role)}"
                         f"{team_text}\n\n"
                         f"🎮 *Игра в чате:* {chat.title}",
                    parse_mode=ParseMode.MARKDOWN
                )
            except Exception as e:
                logger.warning(f"Не удалось отправить роль {uid}: {e}")
    await update.message.reply_text(
        f"✅ Роли назначены! Каждый игрок получил роль в ЛС.\n"
        f"Всего ролей: {len(roles)}"
    )

async def startnight_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user
    game = get_game(chat.id)
    if not game:
        await update.message.reply_text("❌ Нет активной игры!")
        return
    if user.id != game.host_id:
        await update.message.reply_text("❌ Только Ведущий!")
        return
    if game.phase == GamePhase.WAITING:
        if not any(p.role for p in game.players.values()):
            await update.message.reply_text("❌ Сначала назначьте роли `/setroles`!")
            return
    game.phase = GamePhase.NIGHT
    game.day_number += 1
    game.night_deaths = []
    game.night_kills = {}
    game.night_saves = {}
    game.night_checks = {}
    for p in game.get_alive_players().values():
        p.night_action_done = False
        p.veteran_guarding = False
        p.courtesan_target = None
        p.sheriff_check_target = None
        p.sheriff_kill_target = None
        p.sheriff_station_guarded = False
        p.doctor_target = None
        p.journalist_targets = (None, None)
        p.bum_target = None
        p.postman_from = None
        p.postman_to = None
        p.jailer_targets = []
        p.jailer_weapon_given = False
        p.maniac_target = None
        p.harlot_target = None
        p.witch_target = None
        p.witch_control_target = None
        p.mafia_target = None
        p.yakuza_target = None
        p.gunman_shot_day = False
    game.log(f"Ночь {game.day_number}")
    await send_night_actions(context, game)
    night_text = f"🌙 *НАЧАЛАСЬ НОЧЬ {game.day_number}* 🌙\n\nВсе жители засыпают...\n"
    if game.first_night:
        night_text += "\n🎭 *Первая ночь — знакомства:*\n"
        if game.mafia_chat:
            mafia_names = [game.players[uid].display_name for uid in game.mafia_chat if game.players[uid].is_alive]
            night_text += f"🎩 Мафия: {', '.join(mafia_names)}\n"
        if game.yakuza_chat:
            yakuza_names = [game.players[uid].display_name for uid in game.yakuza_chat if game.players[uid].is_alive]
            night_text += f"🐉 Якудза: {', '.join(yakuza_names)}\n"
        if game.police_station:
            police_names = [game.players[uid].display_name for uid in game.police_station if game.players[uid].is_alive]
            night_text += f"🤠 Полиция: {', '.join(police_names)}\n"
        game.first_night = False
    await update.message.reply_text(night_text, parse_mode=ParseMode.MARKDOWN)


async def send_night_actions(context: ContextTypes.DEFAULT_TYPE, game: MafiaGame):
    alive = game.get_alive_players()
    alive_ids = list(alive.keys())
    for uid, player in alive.items():
        if not player.role:
            continue
        try:
            if player.role == Role.SHERIFF:
                keyboard = []
                for tid in alive_ids:
                    if tid != uid:
                        t = alive[tid]
                        keyboard.append([InlineKeyboardButton(t.display_name, callback_data=f"sheriff_check_{tid}")])
                keyboard.append([InlineKeyboardButton("🔫 Убить", callback_data="sheriff_kill_menu")])
                keyboard.append([InlineKeyboardButton("🛡️ Охранять участок", callback_data="sheriff_guard")])
                await context.bot.send_message(
                    chat_id=uid, text="🤠 *Ночь Шерифа*\nВыберите действие:",
                    parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup(keyboard)
                )
            elif player.role == Role.DOCTOR:
                keyboard = []
                for tid in alive_ids:
                    t = alive[tid]
                    heals = player.doctor_heals.get(tid, 0)
                    can_heal = heals < 2
                    btn = f"{t.display_name} (лечил: {heals}/2)"
                    if not can_heal: btn += " ❌"
                    keyboard.append([InlineKeyboardButton(btn, callback_data=f"doctor_heal_{tid}" if can_heal else "noop")])
                await context.bot.send_message(
                    chat_id=uid, text="👨‍⚕️ *Ночь Доктора*\nВыберите пациента (макс 2 раза, не подряд):",
                    parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup(keyboard)
                )
            elif player.role == Role.COURTESAN:
                keyboard = []
                for tid in alive_ids:
                    if tid != uid and tid != player.courtesan_previous:
                        t = alive[tid]
                        keyboard.append([InlineKeyboardButton(t.display_name, callback_data=f"courtesan_{tid}")])
                await context.bot.send_message(
                    chat_id=uid, text="💃 *Ночь Куртизанки*\nВыберите клиента (не подряд, не себя):",
                    parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup(keyboard)
                )
            elif player.role == Role.JOURNALIST:
                keyboard = []
                for tid in alive_ids:
                    if tid != uid:
                        t = alive[tid]
                        keyboard.append([InlineKeyboardButton(t.display_name, callback_data=f"journalist_1_{tid}")])
                await context.bot.send_message(
                    chat_id=uid, text="📰 *Ночь Журналиста*\nВыберите *первого* игрока для сравнения:",
                    parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup(keyboard)
                )
            elif player.role == Role.BUM:
                keyboard = []
                for tid in alive_ids:
                    if tid != uid:
                        t = alive[tid]
                        keyboard.append([InlineKeyboardButton(t.display_name, callback_data=f"bum_{tid}")])
                await context.bot.send_message(
                    chat_id=uid, text="🧙 *Ночь Бомжа*\nВыберите, за кем следить:",
                    parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup(keyboard)
                )
            elif player.role == Role.POSTMAN:
                keyboard = []
                for tid in alive_ids:
                    t = alive[tid]
                    keyboard.append([InlineKeyboardButton(f"Проверить: {t.display_name}", callback_data=f"postman_check_{tid}")])
                await context.bot.send_message(
                    chat_id=uid, text="📮 *Ночь Почтальона*\nВыберите, кого проверить:",
                    parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup(keyboard)
                )
            elif player.role == Role.JAILER:
                keyboard = []
                for tid in alive_ids:
                    if tid != uid:
                        t = alive[tid]
                        keyboard.append([InlineKeyboardButton(t.display_name, callback_data=f"jailer_1_{tid}")])
                await context.bot.send_message(
                    chat_id=uid, text="🔒 *Ночь Тюремщика*\nВыберите *первого* заключённого (всего 2):",
                    parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup(keyboard)
                )
            elif player.role == Role.CUPID:
                keyboard = []
                for tid in alive_ids:
                    t = alive[tid]
                    keyboard.append([InlineKeyboardButton(t.display_name, callback_data=f"cupid_1_{tid}")])
                await context.bot.send_message(
                    chat_id=uid, text="💘 *Ночь Амура*\nВыберите *первого* влюблённого:",
                    parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup(keyboard)
                )
            elif player.role == Role.VETERAN:
                keyboard = [
                    [InlineKeyboardButton(f"🛡️ Защищать дом ({player.veteran_guards}/3)", callback_data="veteran_guard")],
                    [InlineKeyboardButton("😴 Спать", callback_data="veteran_sleep")]
                ]
                await context.bot.send_message(
                    chat_id=uid, text="🛡️ *Ночь Ветерана*\nВстать на защиту?",
                    parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup(keyboard)
                )
            elif player.role == Role.MANIAC:
                keyboard = []
                for tid in alive_ids:
                    if tid != uid:
                        t = alive[tid]
                        keyboard.append([InlineKeyboardButton(t.display_name, callback_data=f"maniac_{tid}")])
                await context.bot.send_message(
                    chat_id=uid, text="🔪 *Ночь Маньяка*\nВыберите жертву:",
                    parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup(keyboard)
                )
            elif player.role == Role.HARLOT:
                keyboard = []
                for tid in alive_ids:
                    if tid != uid:
                        t = alive[tid]
                        inf = "🦠" if t.is_infected else ""
                        keyboard.append([InlineKeyboardButton(f"{t.display_name} {inf}", callback_data=f"harlot_{tid}")])
                await context.bot.send_message(
                    chat_id=uid, text="🦠 *Ночь Путаны*\nВыберите, кого заразить:",
                    parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup(keyboard)
                )
            elif player.role == Role.WITCH:
                keyboard = []
                for tid in alive_ids:
                    if tid != uid:
                        t = alive[tid]
                        keyboard.append([InlineKeyboardButton(t.display_name, callback_data=f"witch_target_{tid}")])
                await context.bot.send_message(
                    chat_id=uid, text="🧙‍♀️ *Ночь Ведьмы*\nВыберите цель для контроля:",
                    parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup(keyboard)
                )
            elif player.role in [Role.MAFIA, Role.MAFIA_BOSS, Role.MAFIA_HENCHMAN]:
                is_boss = (uid == game.mafia_boss_id)
                is_backup = (not game.players.get(game.mafia_boss_id, Player(0,"","")).is_alive and 
                            uid == min([u for u in game.mafia_chat if game.players[u].is_alive], default=uid))
                if is_boss or is_backup:
                    keyboard = []
                    for tid in alive_ids:
                        if tid not in game.mafia_chat:
                            t = alive[tid]
                            keyboard.append([InlineKeyboardButton(t.display_name, callback_data=f"mafia_kill_{tid}")])
                    await context.bot.send_message(
                        chat_id=uid, text="🎩 *Ночь Мафии*\nВы — представитель. Выберите жертву:",
                        parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup(keyboard)
                    )
                else:
                    await context.bot.send_message(
                        chat_id=uid, text="🎩 *Ночь Мафии*\nОжидайте решения Босса...",
                        parse_mode=ParseMode.MARKDOWN
                    )
            elif player.role in [Role.YAKUZA, Role.YAKUZA_BOSS, Role.YAKUZA_HENCHMAN]:
                is_boss = (uid == game.yakuza_boss_id)
                is_backup = (not game.players.get(game.yakuza_boss_id, Player(0,"","")).is_alive and 
                            uid == min([u for u in game.yakuza_chat if game.players[u].is_alive], default=uid))
                if is_boss or is_backup:
                    keyboard = []
                    for tid in alive_ids:
                        if tid not in game.yakuza_chat:
                            t = alive[tid]
                            keyboard.append([InlineKeyboardButton(t.display_name, callback_data=f"yakuza_kill_{tid}")])
                    await context.bot.send_message(
                        chat_id=uid, text="🐉 *Ночь Якудза*\nВы — представитель. Выберите жертву:",
                        parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup(keyboard)
                    )
                else:
                    await context.bot.send_message(
                        chat_id=uid, text="🐉 *Ночь Якудза*\nОжидайте решения Босса...",
                        parse_mode=ParseMode.MARKDOWN
                    )
        except Exception as e:
            logger.error(f"Ошибка отправки действия игроку {uid}: {e}")

async def endnight_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user
    game = get_game(chat.id)
    if not game or game.phase != GamePhase.NIGHT:
        await update.message.reply_text("❌ Сейчас не ночь!")
        return
    if user.id != game.host_id:
        await update.message.reply_text("❌ Только Ведущий!")
        return
    results = await process_night(context, game)
    game.phase = GamePhase.DAY
    day_text = f"☀️ *НАСТУПИЛ ДЕНЬ {game.day_number}* ☀️\n\n{results}\n\nЖивых: {len(game.get_alive_players())}\nНачинается обсуждение!"
    await update.message.reply_text(day_text, parse_mode=ParseMode.MARKDOWN)
    await check_win_condition(context, game)

async def process_night(context: ContextTypes.DEFAULT_TYPE, game: MafiaGame) -> str:
    alive = game.get_alive_players()
    deaths = []
    messages = []

    # 1. Амур
    cupid = alive.get(game.cupid_id)
    if cupid and cupid.is_alive and cupid.lover_id:
        lover1 = cupid.lover_id
        lover2 = None
        for uid, p in alive.items():
            if p.lover_id == game.cupid_id and uid != game.cupid_id:
                lover2 = uid
                break
        if lover1 and lover2:
            game.lovers_chat.add(lover1)
            game.lovers_chat.add(lover2)
            messages.append("💘 Амур связал двух сердец...")
            try:
                await context.bot.send_message(
                    chat_id=lover1,
                    text=f"💘 *Вы влюблены!* Ваш партнёр: {alive[lover2].display_name}",
                    parse_mode=ParseMode.MARKDOWN
                )
                await context.bot.send_message(
                    chat_id=lover2,
                    text=f"💘 *Вы влюблены!* Ваш партнёр: {alive[lover1].display_name}",
                    parse_mode=ParseMode.MARKDOWN
                )
            except: pass

    # 2. Куртизанка
    courtesan_clients = {}
    for uid, p in alive.items():
        if p.role == Role.COURTESAN and p.courtesan_target:
            courtesan_clients[p.courtesan_target] = uid
            p.courtesan_previous = p.courtesan_target
            messages.append("💃 Куртизанка забрала клиента...")

    # 3. Тюремщик
    jailed = set()
    for uid, p in alive.items():
        if p.role == Role.JAILER and p.jailer_targets:
            for tid in p.jailer_targets:
                jailed.add(tid)
            messages.append("🔒 Тюремщик заключил игроков...")
            # Создать тюремный чат
            for tid in p.jailer_targets:
                if tid in alive:
                    try:
                        await context.bot.send_message(
                            chat_id=tid,
                            text=f"🔒 *Вы в тюрьме!*\nСобеседник: {alive[p.jailer_targets[0] if p.jailer_targets[0] != tid else p.jailer_targets[1]].display_name if len(p.jailer_targets) > 1 else 'нет'}\nТюремщик подслушивает...",
                            parse_mode=ParseMode.MARKDOWN
                        )
                    except: pass

    # 4. Ветеран
    veterans_guarding = set()
    for uid, p in alive.items():
        if p.role == Role.VETERAN and p.veteran_guarding and p.veteran_guards > 0:
            veterans_guarding.add(uid)
            p.veteran_guards -= 1

    # 5. Шериф охраняет участок
    station_guarded = False
    sheriff = alive.get(game.sheriff_id)
    if sheriff and sheriff.is_alive and sheriff.sheriff_station_guarded:
        station_guarded = True

    # 6. Доктор лечит
    doctor_saves = set()
    for uid, p in alive.items():
        if p.role == Role.DOCTOR and p.doctor_target:
            tid = p.doctor_target
            if p.doctor_heals.get(tid, 0) < 2:
                doctor_saves.add(tid)
                p.doctor_heals[tid] += 1

    # 7. Мафия убивает
    mafia_kills = {}
    mafia_votes = {}
    for uid, p in alive.items():
        if p.role in [Role.MAFIA, Role.MAFIA_BOSS, Role.MAFIA_HENCHMAN] and p.mafia_target:
            mafia_votes[p.mafia_target] = mafia_votes.get(p.mafia_target, 0) + 1
            # Босс мафии не имеет +1 голоса
    if mafia_votes:
        mafia_target = max(mafia_votes, key=mafia_votes.get)
        alive_mafia = [u for u, p in alive.items() if p.team == Team.MAFIA]
        if len(alive_mafia) == 1:
            only_mafia = alive_mafia[0]
            if only_mafia in courtesan_clients:
                mafia_target = None
                messages.append("💃 Куртизанка отвлекла единственного мафиози...")
        if mafia_target and mafia_target not in jailed:
            if mafia_target in courtesan_clients:
                pass  # Спасён куртизанкой
            elif mafia_target in doctor_saves:
                pass  # Спасён доктором
            elif station_guarded and mafia_target in game.police_station:
                pass  # Участок охраняется
            elif mafia_target in veterans_guarding:
                for muid in alive:
                    if alive[muid].team == Team.MAFIA and alive[muid].mafia_target == mafia_target:
                        deaths.append((muid, "ветеран"))
            else:
                mafia_kills[mafia_target] = "мафия"

    # 8. Якудза убивает
    yakuza_kills = {}
    yakuza_votes = {}
    for uid, p in alive.items():
        if p.role in [Role.YAKUZA, Role.YAKUZA_BOSS, Role.YAKUZA_HENCHMAN] and p.yakuza_target:
            yakuza_votes[p.yakuza_target] = yakuza_votes.get(p.yakuza_target, 0) + 1
            # Босс якудза не имеет +1 голоса
    if yakuza_votes:
        yakuza_target = max(yakuza_votes, key=yakuza_votes.get)
        alive_yakuza = [u for u, p in alive.items() if p.team == Team.YAKUZA]
        if len(alive_yakuza) == 1:
            only_yakuza = alive_yakuza[0]
            if only_yakuza in courtesan_clients:
                yakuza_target = None
                messages.append("💃 Куртизанка отвлекла единственного якудза...")
        if yakuza_target and yakuza_target not in jailed:
            if yakuza_target in courtesan_clients:
                pass
            elif yakuza_target in doctor_saves:
                pass
            elif station_guarded and yakuza_target in game.police_station:
                pass
            elif yakuza_target in veterans_guarding:
                for yuid in alive:
                    if alive[yuid].team == Team.YAKUZA and alive[yuid].yakuza_target == yakuza_target:
                        deaths.append((yuid, "ветеран"))
            else:
                yakuza_kills[yakuza_target] = "якудза"

    # 9. Маньяк убивает
    maniac_kills = {}
    for uid, p in alive.items():
        if p.role == Role.MANIAC and p.maniac_target:
            target = p.maniac_target
            if target not in jailed:
                if target in courtesan_clients and courtesan_clients[target] == uid:
                    pass  # Маньяк — клиент куртизанки
                elif target in doctor_saves:
                    pass
                elif target in veterans_guarding:
                    deaths.append((uid, "ветеран"))
                else:
                    maniac_kills[target] = "маньяк"

    # 10. Шериф убивает
    sheriff_kills = {}
    if sheriff and sheriff.is_alive and sheriff.sheriff_kill_target:
        target = sheriff.sheriff_kill_target
        if target not in jailed:
            if target in doctor_saves:
                pass
            elif target in veterans_guarding:
                deaths.append((game.sheriff_id, "ветеран"))
            else:
                sheriff_kills[target] = "шериф"

    # 11. Путана заражает
    for uid, p in alive.items():
        if p.role == Role.HARLOT and p.harlot_target:
            target = alive.get(p.harlot_target)
            if target:
                target.is_infected = True
                p.harlot_infected.add(p.harlot_target)

    # 12. Проверки и результаты ролей
    # Шериф проверяет
    if sheriff and sheriff.is_alive and sheriff.sheriff_check_target:
        target = alive.get(sheriff.sheriff_check_target)
        if target:
            if target.role == Role.MANIAC:
                result = "🟢 Мирный житель"
            elif target.role == Role.YAKUZA_BOSS:
                result = "🟢 Мирный житель"
            elif target.team in [Team.MAFIA, Team.YAKUZA]:
                result = "🔴 Преступник!"
            else:
                result = "🟢 Мирный житель"
            try:
                await context.bot.send_message(
                    chat_id=game.sheriff_id,
                    text=f"🤠 *Результат проверки {target.display_name}:*\n{result}",
                    parse_mode=ParseMode.MARKDOWN
                )
            except: pass

    # Журналист сравнивает
    for uid, p in alive.items():
        if p.role == Role.JOURNALIST and p.journalist_targets[0] and p.journalist_targets[1]:
            t1_id, t2_id = p.journalist_targets
            t1 = alive.get(t1_id)
            t2 = alive.get(t2_id)
            if t1 and t2:
                def get_group(pl):
                    if pl.role in [Role.MANIAC, Role.WITCH]:
                        return "одиночка"
                    elif pl.team == Team.MAFIA:
                        return "мафия"
                    elif pl.team == Team.YAKUZA:
                        return "якудза"
                    else:
                        return "мирный"
                g1, g2 = get_group(t1), get_group(t2)
                same = (g1 == g2)
                if (t1.role == Role.MANIAC or t2.role == Role.MANIAC) and g1 != g2:
                    same = False
                result = "🟢 *Одинаковые*" if same else "🔴 *Разные*"
                try:
                    await context.bot.send_message(
                        chat_id=uid,
                        text=f"📰 *Результат сравнения:*\n{t1.display_name} и {t2.display_name}\n{result}",
                        parse_mode=ParseMode.MARKDOWN
                    )
                except: pass

    # Бомж следит
    for uid, p in alive.items():
        if p.role == Role.BUM and p.bum_target:
            tid = p.bum_target
            all_kills = {**mafia_kills, **yakuza_kills, **maniac_kills, **sheriff_kills}
            if tid in all_kills:
                killer = all_kills[tid]
                try:
                    await context.bot.send_message(
                        chat_id=uid,
                        text=f"🧙 *Бомж увидел убийцу!*\n{alive[tid].display_name} убит: {killer}",
                        parse_mode=ParseMode.MARKDOWN
                    )
                except: pass
            else:
                try:
                    await context.bot.send_message(
                        chat_id=uid,
                        text=f"🧙 *Результат слежки:*\n{alive[tid].display_name} жив.",
                        parse_mode=ParseMode.MARKDOWN
                    )
                except: pass

    # Почтальон
    for uid, p in alive.items():
        if p.role == Role.POSTMAN and p.postman_from and p.postman_to:
            target = alive.get(p.postman_from)
            receiver = alive.get(p.postman_to)
            if target and receiver:
                role_text = target.role.value if target.role else "Неизвестно"
                try:
                    await context.bot.send_message(
                        chat_id=p.postman_to,
                        text=f"📮 *Письмо от Почтальона:*\n{target.display_name} — {role_text}",
                        parse_mode=ParseMode.MARKDOWN
                    )
                except: pass

    # Объединить убийства
    all_deaths = {}
    for target, killer in {**mafia_kills, **yakuza_kills, **maniac_kills, **sheriff_kills}.items():
        if target not in all_deaths:
            all_deaths[target] = []
        all_deaths[target].append(killer)

    # Смерти влюблённых
    lover_deaths = []
    for dead_id in all_deaths:
        dead = alive.get(dead_id)
        if dead and dead.is_lover and dead.lover_id:
            lover = alive.get(dead.lover_id)
            if lover and lover.is_alive and dead.lover_id not in all_deaths:
                lover_deaths.append(dead.lover_id)

    # Применить смерти
    death_names = []
    for dead_id in list(all_deaths.keys()) + lover_deaths:
        if dead_id in alive and dead_id not in [d[0] for d in deaths]:
            game.players[dead_id].is_alive = False
            name = alive[dead_id].display_name
            role = alive[dead_id].role.value if alive[dead_id].role else "?"
            killers = all_deaths.get(dead_id, ["горе"])
            death_names.append(f"💀 {name} ({role}) — {', '.join(killers)}")
            game.night_deaths.append(dead_id)

    # Проверка победы Путаны
    harlot_win = True
    for uid, p in alive.items():
        if p.is_alive and not p.is_infected and p.role != Role.HARLOT:
            harlot_win = False
            break
    if harlot_win and any(p.role == Role.HARLOT and p.is_alive for p in alive.values()):
        game.phase = GamePhase.FINISHED
        return "🦠 *ПУТАНА ПОБЕДИЛА!* Все заражены чумой!"

    if death_names:
        result = "🌙 *Ночные события:*\n" + "\n".join(death_names)
    else:
        result = "🌙 *Ночь прошла спокойно...*\nНикто не погиб."
    if messages:
        result = "\n".join(messages) + "\n\n" + result
    return result


async def startvote_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user
    game = get_game(chat.id)
    if not game or game.phase != GamePhase.DAY:
        await update.message.reply_text("❌ Сейчас не день!")
        return
    if user.id != game.host_id:
        await update.message.reply_text("❌ Только Ведущий!")
        return
    game.phase = GamePhase.VOTING
    game.voting_active = True
    game.vote_results = {}
    for p in game.get_alive_players().values():
        p.has_voted = False
        p.vote_target = None
    alive = game.get_alive_players()
    keyboard = []
    for tid in alive:
        t = alive[tid]
        keyboard.append([InlineKeyboardButton(t.display_name, callback_data=f"vote_{tid}")])
    await update.message.reply_text(
        "🗳️ *НАЧАЛОСЬ ГОЛОСОВАНИЕ!*\n\n"
        "Каждый живой игрок должен проголосовать.\n"
        "Против себя голосовать нельзя!\n"
        "Повторно голосовать нельзя!\n\n"
        "Используйте кнопки ниже или команду `/vote @ник`",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def vote_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user
    game = get_game(chat.id)
    if not game or game.phase != GamePhase.VOTING:
        await update.message.reply_text("❌ Сейчас не идёт голосование!")
        return
    if user.id not in game.players or not game.players[user.id].is_alive:
        await update.message.reply_text("❌ Вы не можете голосовать!")
        return
    if game.players[user.id].has_voted:
        await update.message.reply_text("❌ Вы уже проголосовали!")
        return
    if not context.args:
        await update.message.reply_text("❌ Укажите ник! Пример: `/vote @username`", parse_mode=ParseMode.MARKDOWN)
        return
    target_name = context.args[0].replace("@", "")
    target_id = None
    for uid, p in game.get_alive_players().items():
        if p.username == target_name or p.first_name == target_name:
            target_id = uid
            break
    if not target_id:
        await update.message.reply_text("❌ Игрок не найден!")
        return
    if target_id == user.id:
        await update.message.reply_text("❌ Против себя голосовать нельзя!")
        return
    await process_vote(update, context, game, user.id, target_id)

async def process_vote(update, context, game, voter_id, target_id):
    voter = game.players[voter_id]
    target = game.players[target_id]
    voter.has_voted = True
    voter.vote_target = target_id
    if target_id not in game.vote_results:
        game.vote_results[target_id] = []
    game.vote_results[target_id].append(voter_id)
    # Показать текущие результаты
    vote_text = "🗳️ *Текущие голоса:*\n"
    for tid, voters in game.vote_results.items():
        voter_names = [game.players[v].display_name for v in voters]
        vote_text += f"{game.players[tid].display_name}: {len(voters)} ({', '.join(voter_names)})\n"
    not_voted = [p.display_name for p in game.get_alive_players().values() if not p.has_voted]
    if not_voted:
        vote_text += f"\n⏳ Не проголосовали: {', '.join(not_voted)}"
    if isinstance(update, Update):
        await update.message.reply_text(vote_text, parse_mode=ParseMode.MARKDOWN)
    else:
        await context.bot.send_message(chat_id=game.chat_id, text=vote_text, parse_mode=ParseMode.MARKDOWN)

async def endvote_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user
    game = get_game(chat.id)
    if not game or game.phase != GamePhase.VOTING:
        await update.message.reply_text("❌ Сейчас не идёт голосование!")
        return
    if user.id != game.host_id:
        await update.message.reply_text("❌ Только Ведущий!")
        return
    game.voting_active = False
    game.phase = GamePhase.JUDGE

    if not game.vote_results:
        await update.message.reply_text("🗳️ *Голосование завершено!*\nНикто не проголосовал.", parse_mode=ParseMode.MARKDOWN)
        game.phase = GamePhase.DAY
        return

    # Подсчёт голосов
    max_votes = max(len(v) for v in game.vote_results.values())
    candidates = [tid for tid, v in game.vote_results.items() if len(v) == max_votes]

    vote_text = "🗳️ *Результаты голосования:*\n"
    for tid, voters in game.vote_results.items():
        voter_names = [game.players[v].display_name for v in voters]
        vote_text += f"{game.players[tid].display_name}: {len(voters)} голосов ({', '.join(voter_names)})\n"

    if len(candidates) == 1:
        candidate = candidates[0]
        candidate_name = game.players[candidate].display_name
        vote_text += f"\n⚖️ *{candidate_name}* отправляется на суд!"
        await update.message.reply_text(vote_text, parse_mode=ParseMode.MARKDOWN)

        # Судья решает
        judge = game.players.get(game.judge_id) if game.judge_id else None
        if judge and judge.is_alive and candidate != game.judge_id:
            game.judge_decision_pending = True
            try:
                keyboard = [
                    [InlineKeyboardButton("☠️ Казнить", callback_data=f"judge_execute_{candidate}")],
                    [InlineKeyboardButton("🕊️ Помиловать", callback_data=f"judge_pardon_{candidate}")]
                ]
                await context.bot.send_message(
                    chat_id=game.judge_id,
                    text=f"⚖️ *Судье решать!*\n{candidate_name} приговорён.\nКазнить или помиловать?",
                    parse_mode=ParseMode.MARKDOWN,
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
                await update.message.reply_text("⚖️ Судья получил решение в ЛС...")
            except:
                # Судья недоступен — случайный выбор
                execute = random.choice([True, False])
                await execute_verdict(context, game, candidate, execute)
        else:
            # Нет судьи — случайный выбор или автоказнь
            if candidate == game.judge_id:
                await execute_verdict(context, game, candidate, True)
            else:
                # Последний убитый мирный или случайный
                execute = random.choice([True, False])
                await execute_verdict(context, game, candidate, execute)
    else:
        # Ничья — судья решает
        vote_text += f"\n⚖️ *Ничья!* Вызывается Судья..."
        await update.message.reply_text(vote_text, parse_mode=ParseMode.MARKDOWN)
        judge = game.players.get(game.judge_id) if game.judge_id else None
        if judge and judge.is_alive:
            game.judge_decision_pending = True
            try:
                keyboard = []
                for cid in candidates:
                    cname = game.players[cid].display_name
                    keyboard.append([InlineKeyboardButton(f"☠️ Казнить {cname}", callback_data=f"judge_execute_{cid}")])
                keyboard.append([InlineKeyboardButton("🕊️ Помиловать всех", callback_data="judge_pardon_all")])
                await context.bot.send_message(
                    chat_id=game.judge_id,
                    text=f"⚖️ *Ничья в голосовании!*\nВыберите, кого казнить, или помилуйте всех.",
                    parse_mode=ParseMode.MARKDOWN,
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
            except:
                # Случайный выбор
                chosen = random.choice(candidates)
                await execute_verdict(context, game, chosen, True)
        else:
            chosen = random.choice(candidates)
            await execute_verdict(context, game, chosen, True)

async def execute_verdict(context, game, target_id, execute):
    game.judge_decision_pending = False
    target = game.players[target_id]
    if execute:
        target.is_alive = False
        game.day_deaths.append(target_id)
        role_text = target.role.value if game.phase == GamePhase.FINISHED else "❓"
        await context.bot.send_message(
            chat_id=game.chat_id,
            text=f"☠️ *КАЗНЬ!*\n\n{target.display_name} ({role_text}) отправляется на виселицу!",
            parse_mode=ParseMode.MARKDOWN
        )
    else:
        await context.bot.send_message(
            chat_id=game.chat_id,
            text=f"🕊️ *ПОМИЛОВАНИЕ!*\n\n{target.display_name} помилован и остаётся в живых.",
            parse_mode=ParseMode.MARKDOWN
        )
    game.phase = GamePhase.DAY
    await check_win_condition(context, game)

async def kill_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Стрелок стреляет днём"""
    chat = update.effective_chat
    user = update.effective_user
    game = get_game(chat.id)
    if not game or game.phase not in [GamePhase.DAY, GamePhase.VOTING]:
        await update.message.reply_text("❌ Сейчас нельзя стрелять!")
        return
    player = game.players.get(user.id)
    if not player or player.role != Role.GUNMAN or not player.is_alive:
        await update.message.reply_text("❌ Вы не Стрелок!")
        return
    if player.gunman_bullets <= 0:
        await update.message.reply_text("❌ У вас закончились пули!")
        return
    if game.day_number == 1:
        await update.message.reply_text("❌ В первый день стрелять нельзя!")
        return
    if not context.args:
        await update.message.reply_text("❌ Укажите цель! `/kill @ник`", parse_mode=ParseMode.MARKDOWN)
        return
    target_name = context.args[0].replace("@", "")
    target_id = None
    for uid, p in game.get_alive_players().items():
        if p.username == target_name or p.first_name == target_name:
            target_id = uid
            break
    if not target_id:
        await update.message.reply_text("❌ Игрок не найден!")
        return
    if target_id == user.id:
        await update.message.reply_text("❌ Нельзя стрелять в себя!")
        return

    target = game.players[target_id]
    player.gunman_bullets -= 1
    target.is_alive = False
    game.day_deaths.append(target_id)

    # Проверить, мафия ли цель
    reveal = target.team not in [Team.MAFIA, Team.YAKUZA]

    await update.message.reply_text(
        f"🔫 *ВЫСТРЕЛ!*\n\n"
        f"{player.display_name} стреляет в {target.display_name}!\n"
        f"💀 {target.display_name} погибает!\n"
        f"{'🔍 Роль Стрелка раскрыта!' if reveal else '🔍 Роль Стрелка остаётся тайной.'}",
        parse_mode=ParseMode.MARKDOWN
    )
    await check_win_condition(context, game)

async def check_win_condition(context, game):
    alive = game.get_alive_players()
    alive_mafia = [p for p in alive.values() if p.team == Team.MAFIA]
    alive_yakuza = [p for p in alive.values() if p.team == Team.YAKUZA]
    alive_civilians = [p for p in alive.values() if p.team == Team.CIVILIAN]
    alive_maniac = [p for p in alive.values() if p.role == Role.MANIAC]
    alive_harlot = [p for p in alive.values() if p.role == Role.HARLOT]

    winners = None

    # Маньяк побеждает, если остался один
    if len(alive_maniac) == 1 and len(alive) == 1:
        winners = "🔪 МАНЬЯК ПОБЕДИЛ!"
    # Мафия побеждает
    elif len(alive_mafia) >= len([p for p in alive.values() if p.team != Team.MAFIA]):
        winners = "🎩 МАФИЯ ПОБЕДИЛА!"
    # Якудза побеждает
    elif len(alive_yakuza) >= len([p for p in alive.values() if p.team != Team.YAKUZA]):
        winners = "🐉 ЯКУДЗА ПОБЕДИЛИ!"
    # Мирные побеждают
    elif not alive_mafia and not alive_yakuza and not alive_maniac:
        winners = "🟦 МИРНЫЕ ЖИТЕЛИ ПОБЕДИЛИ!"
    # Путана
    elif alive_harlot:
        all_infected = all(p.is_infected or p.role == Role.HARLOT for p in alive.values())
        if all_infected:
            winners = "🦠 ПУТАНА ПОБЕДИЛА!"

    if winners:
        game.phase = GamePhase.FINISHED
        alive_text = format_players_list(game, show_roles=True)
        await context.bot.send_message(
            chat_id=game.chat_id,
            text=f"🏆 *ИГРА ОКОНЧЕНА!*\n\n{winners}\n\n"
                 f"📊 *Итоговые роли:*\n{alive_text}\n\n"
                 f"📝 Используйте `/newgame` для новой игры!",
            parse_mode=ParseMode.MARKDOWN
        )

async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user
    game = get_game(chat.id)
    if not game:
        await update.message.reply_text("❌ Нет активной игры!")
        return
    if user.id != game.host_id and user.id != game.creator_id:
        await update.message.reply_text("❌ Только создатель может отменить игру!")
        return
    delete_game(chat.id)
    await update.message.reply_text("❌ Игра отменена!")


# ═══════════════════════════════════════════════════════════════
# CALLBACK ОБРАБОТЧИКИ
# ═══════════════════════════════════════════════════════════════

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = query.from_user.id

    if data == "join_game":
        chat_id = query.message.chat_id
        game = get_game(chat_id)
        if not game:
            await query.edit_message_text("❌ Игра не найдена!")
            return
        if game.phase != GamePhase.WAITING:
            await query.answer("❌ Игра уже началась!")
            return
        if user_id in game.players:
            await query.answer("❌ Вы уже в игре!")
            return
        user = query.from_user
        game.add_player(user_id, user.username, user.first_name)
        user_game[user_id] = chat_id
        keyboard = [
            [InlineKeyboardButton("🎮 Присоединиться", callback_data="join_game")],
            [InlineKeyboardButton("▶️ Начать игру", callback_data="start_game")],
            [InlineKeyboardButton("❌ Отменить", callback_data="cancel_game")]
        ]
        host = game.players.get(game.host_id)
        host_name = host.display_name if host else "?"
        player_count = len([p for p in game.players.values() if p.user_id != game.host_id])
        await query.edit_message_text(
            f"🎭 *Игра Мафия*\n\n"
            f"👤 *Ведущий:* {host_name}\n"
            f"👥 *Игроки ({player_count}):*\n"
            f"{format_players_list(game, include_host=False)}\n\n"
            f"Нажмите «Присоединиться» чтобы войти!",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    elif data == "start_game":
        chat_id = query.message.chat_id
        game = get_game(chat_id)
        if not game:
            await query.edit_message_text("❌ Игра не найдена!")
            return
        if user_id != game.host_id:
            await query.answer("❌ Только Ведущий может начать!")
            return
        if not any(p.role for p in game.players.values()):
            await query.answer("❌ Сначала назначьте роли /setroles!")
            return
        player_count = len([p for p in game.players.values() if p.user_id != game.host_id])
        await query.edit_message_text(
            f"🎭 *Игра начинается!*\n\n"
            f"👥 *Игроки ({player_count}):*\n"
            f"{format_players_list(game, include_host=False)}\n\n"
            f"Ведущий, используйте `/startnight` для начала первой ночи!",
            parse_mode=ParseMode.MARKDOWN
        )

    elif data == "cancel_game":
        chat_id = query.message.chat_id
        game = get_game(chat_id)
        if not game:
            await query.edit_message_text("❌ Игра не найдена!")
            return
        if user_id != game.host_id and user_id != game.creator_id:
            await query.answer("❌ Только создатель может отменить!")
            return
        delete_game(chat_id)
        await query.edit_message_text("❌ Игра отменена.")

    # Ночные действия
    elif data.startswith("sheriff_check_"):
        target_id = int(data.split("_")[-1])
        game = get_player_game(user_id)
        if game and game.phase == GamePhase.NIGHT:
            game.players[user_id].sheriff_check_target = target_id
            game.players[user_id].sheriff_kill_target = None
            await query.edit_message_text(f"🤠 Вы проверяете {game.players[target_id].display_name}. Ожидайте результат...")

    elif data == "sheriff_kill_menu":
        game = get_player_game(user_id)
        if game and game.phase == GamePhase.NIGHT:
            alive = game.get_alive_players()
            keyboard = []
            for tid in alive:
                if tid != user_id:
                    t = alive[tid]
                    keyboard.append([InlineKeyboardButton(t.display_name, callback_data=f"sheriff_kill_{tid}")])
            keyboard.append([InlineKeyboardButton("❌ Отмена", callback_data="sheriff_cancel_kill")])
            await query.edit_message_text("🔫 *Выберите жертву:*", parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup(keyboard))

    elif data.startswith("sheriff_kill_"):
        target_id = int(data.split("_")[-1])
        game = get_player_game(user_id)
        if game and game.phase == GamePhase.NIGHT:
            game.players[user_id].sheriff_kill_target = target_id
            game.players[user_id].sheriff_check_target = None
            game.players[user_id].sheriff_station_guarded = False
            await query.edit_message_text(f"🔫 Вы решаете убить {game.players[target_id].display_name}.")

    elif data == "sheriff_cancel_kill":
        game = get_player_game(user_id)
        if game and game.phase == GamePhase.NIGHT:
            game.players[user_id].sheriff_kill_target = None
            await query.edit_message_text("❌ Убийство отменено.")

    elif data == "sheriff_guard":
        game = get_player_game(user_id)
        if game and game.phase == GamePhase.NIGHT:
            game.players[user_id].sheriff_station_guarded = True
            game.players[user_id].sheriff_check_target = None
            game.players[user_id].sheriff_kill_target = None
            await query.edit_message_text("🛡️ Вы охраняете полицейский участок.")

    elif data.startswith("doctor_heal_"):
        target_id = int(data.split("_")[-1])
        game = get_player_game(user_id)
        if game and game.phase == GamePhase.NIGHT:
            p = game.players[user_id]
            if p.doctor_heals.get(target_id, 0) >= 2:
                await query.answer("❌ Уже лечили 2 раза!")
                return
            p.doctor_target = target_id
            await query.edit_message_text(f"👨‍⚕️ Вы лечите {game.players[target_id].display_name}.")

    elif data.startswith("courtesan_"):
        target_id = int(data.split("_")[-1])
        game = get_player_game(user_id)
        if game and game.phase == GamePhase.NIGHT:
            game.players[user_id].courtesan_target = target_id
            await query.edit_message_text(f"💃 Вы забираете {game.players[target_id].display_name} к себе.")

    elif data.startswith("journalist_1_"):
        target1_id = int(data.split("_")[-1])
        game = get_player_game(user_id)
        if game and game.phase == GamePhase.NIGHT:
            game.players[user_id].journalist_targets = (target1_id, None)
            alive = game.get_alive_players()
            keyboard = []
            for tid in alive:
                if tid != user_id and tid != target1_id:
                    t = alive[tid]
                    keyboard.append([InlineKeyboardButton(t.display_name, callback_data=f"journalist_2_{tid}")])
            await query.edit_message_text(
                f"📰 Первый: {game.players[target1_id].display_name}\nВыберите *второго*:",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )

    elif data.startswith("journalist_2_"):
        target2_id = int(data.split("_")[-1])
        game = get_player_game(user_id)
        if game and game.phase == GamePhase.NIGHT:
            t1 = game.players[user_id].journalist_targets[0]
            game.players[user_id].journalist_targets = (t1, target2_id)
            await query.edit_message_text(
                f"📰 Сравниваем {game.players[t1].display_name} и {game.players[target2_id].display_name}. "
                f"Ожидайте результат..."
            )

    elif data.startswith("bum_"):
        target_id = int(data.split("_")[-1])
        game = get_player_game(user_id)
        if game and game.phase == GamePhase.NIGHT:
            game.players[user_id].bum_target = target_id
            await query.edit_message_text(f"🧙 Вы следите за {game.players[target_id].display_name}.")

    elif data.startswith("postman_check_"):
        target_id = int(data.split("_")[-1])
        game = get_player_game(user_id)
        if game and game.phase == GamePhase.NIGHT:
            game.players[user_id].postman_from = target_id
            alive = game.get_alive_players()
            keyboard = []
            for tid in alive:
                if tid != user_id and tid not in game.players[user_id].postman_sent_to:
                    t = alive[tid]
                    keyboard.append([InlineKeyboardButton(f"Отправить: {t.display_name}", callback_data=f"postman_send_{tid}")])
            await query.edit_message_text(
                f"📮 Проверяем: {game.players[target_id].display_name}\nВыберите, кому отправить письмо:",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )

    elif data.startswith("postman_send_"):
        receiver_id = int(data.split("_")[-1])
        game = get_player_game(user_id)
        if game and game.phase == GamePhase.NIGHT:
            p = game.players[user_id]
            p.postman_to = receiver_id
            p.postman_sent_to.add(receiver_id)
            await query.edit_message_text(
                f"📮 Проверка {game.players[p.postman_from].display_name} отправлена "
                f"{game.players[receiver_id].display_name}."
            )

    elif data.startswith("jailer_1_"):
        target1_id = int(data.split("_")[-1])
        game = get_player_game(user_id)
        if game and game.phase == GamePhase.NIGHT:
            game.players[user_id].jailer_targets = [target1_id]
            alive = game.get_alive_players()
            keyboard = []
            for tid in alive:
                if tid != user_id and tid != target1_id:
                    t = alive[tid]
                    keyboard.append([InlineKeyboardButton(t.display_name, callback_data=f"jailer_2_{tid}")])
            keyboard.append([InlineKeyboardButton("✅ Готово (1 заключённый)", callback_data="jailer_done")])
            await query.edit_message_text(
                f"🔒 Первый: {game.players[target1_id].display_name}\nВыберите *второго* или завершите:",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )

    elif data.startswith("jailer_2_"):
        target2_id = int(data.split("_")[-1])
        game = get_player_game(user_id)
        if game and game.phase == GamePhase.NIGHT:
            t1 = game.players[user_id].jailer_targets[0] if game.players[user_id].jailer_targets else None
            game.players[user_id].jailer_targets = [t1, target2_id] if t1 else [target2_id]
            await query.edit_message_text(
                f"🔒 Заключены: {game.players[t1].display_name if t1 else '?'} и {game.players[target2_id].display_name}"
            )

    elif data == "jailer_done":
        game = get_player_game(user_id)
        if game and game.phase == GamePhase.NIGHT:
            targets = game.players[user_id].jailer_targets
            names = [game.players[t].display_name for t in targets if t]
            await query.edit_message_text(f"🔒 Заключены: {', '.join(names)}")

    elif data.startswith("cupid_1_"):
        target1_id = int(data.split("_")[-1])
        game = get_player_game(user_id)
        if game and game.phase == GamePhase.NIGHT:
            game.pending_lover2 = target1_id
            alive = game.get_alive_players()
            keyboard = []
            for tid in alive:
                t = alive[tid]
                keyboard.append([InlineKeyboardButton(t.display_name, callback_data=f"cupid_2_{tid}")])
            await query.edit_message_text(
                f"💘 Первый влюблённый: {game.players[target1_id].display_name}\nВыберите второго:",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )

    elif data.startswith("cupid_2_"):
        target2_id = int(data.split("_")[-1])
        game = get_player_game(user_id)
        if game and game.phase == GamePhase.NIGHT:
            t1 = game.pending_lover2
            if t1:
                game.players[t1].is_lover = True
                game.players[t1].lover_id = target2_id
                game.players[target2_id].is_lover = True
                game.players[target2_id].lover_id = t1
                game.players[user_id].lover_id = t1  # Амур помнит пару
                await query.edit_message_text(
                    f"💘 {game.players[t1].display_name} и {game.players[target2_id].display_name} теперь влюблены!"
                )

    elif data == "veteran_guard":
        game = get_player_game(user_id)
        if game and game.phase == GamePhase.NIGHT:
            p = game.players[user_id]
            if p.veteran_guards > 0:
                p.veteran_guarding = True
                await query.edit_message_text(f"🛡️ Вы встали на защиту! Осталось защит: {p.veteran_guards - 1}/3")
            else:
                await query.answer("❌ Защиты закончились!")

    elif data == "veteran_sleep":
        game = get_player_game(user_id)
        if game and game.phase == GamePhase.NIGHT:
            game.players[user_id].veteran_guarding = False
            await query.edit_message_text("😴 Вы решили спать спокойно.")

    elif data.startswith("maniac_"):
        target_id = int(data.split("_")[-1])
        game = get_player_game(user_id)
        if game and game.phase == GamePhase.NIGHT:
            game.players[user_id].maniac_target = target_id
            await query.edit_message_text(f"🔪 Вы выбрали жертву: {game.players[target_id].display_name}")

    elif data.startswith("harlot_"):
        target_id = int(data.split("_")[-1])
        game = get_player_game(user_id)
        if game and game.phase == GamePhase.NIGHT:
            game.players[user_id].harlot_target = target_id
            await query.edit_message_text(f"🦠 Вы заражаете {game.players[target_id].display_name} чумой.")

    elif data.startswith("witch_target_"):
        target_id = int(data.split("_")[-1])
        game = get_player_game(user_id)
        if game and game.phase == GamePhase.NIGHT:
            game.players[user_id].witch_target = target_id
            await query.edit_message_text(
                f"🧙‍♀️ Вы контролируете {game.players[target_id].display_name}. "
                f"Ожидайте следующей ночи для управления действием..."
            )

    elif data.startswith("mafia_kill_"):
        target_id = int(data.split("_")[-1])
        game = get_player_game(user_id)
        if game and game.phase == GamePhase.NIGHT:
            game.players[user_id].mafia_target = target_id
            await query.edit_message_text(f"🎩 Мафия выбирает: {game.players[target_id].display_name}")
            # Уведомить других мафиози
            for mid in game.mafia_chat:
                if mid != user_id and mid in game.players and game.players[mid].is_alive:
                    try:
                        await context.bot.send_message(
                            chat_id=mid,
                            text=f"🎩 Босс выбрал: {game.players[target_id].display_name}"
                        )
                    except: pass

    elif data.startswith("yakuza_kill_"):
        target_id = int(data.split("_")[-1])
        game = get_player_game(user_id)
        if game and game.phase == GamePhase.NIGHT:
            game.players[user_id].yakuza_target = target_id
            await query.edit_message_text(f"🐉 Якудза выбирает: {game.players[target_id].display_name}")
            for yid in game.yakuza_chat:
                if yid != user_id and yid in game.players and game.players[yid].is_alive:
                    try:
                        await context.bot.send_message(
                            chat_id=yid,
                            text=f"🐉 Босс выбрал: {game.players[target_id].display_name}"
                        )
                    except: pass

    elif data.startswith("vote_"):
        target_id = int(data.split("_")[-1])
        game = get_game(query.message.chat_id)
        if not game or game.phase != GamePhase.VOTING:
            await query.answer("❌ Голосование не активно!")
            return
        if user_id not in game.players or not game.players[user_id].is_alive:
            await query.answer("❌ Вы не можете голосовать!")
            return
        if game.players[user_id].has_voted:
            await query.answer("❌ Вы уже проголосовали!")
            return
        if target_id == user_id:
            await query.answer("❌ Против себя нельзя!")
            return
        await process_vote(None, context, game, user_id, target_id)
        await query.answer("✅ Голос учтён!")

    elif data.startswith("judge_execute_"):
        target_id = int(data.split("_")[-1])
        game = get_player_game(user_id)
        if game and game.phase == GamePhase.JUDGE:
            if user_id != game.judge_id:
                await query.answer("❌ Вы не Судья!")
                return
            await query.edit_message_text("☠️ Вы приговорили к смерти.")
            await execute_verdict(context, game, target_id, True)

    elif data.startswith("judge_pardon_"):
        target_id = data.split("_")[-1]
        game = get_player_game(user_id)
        if game and game.phase == GamePhase.JUDGE:
            if user_id != game.judge_id:
                await query.answer("❌ Вы не Судья!")
                return
            if target_id == "all":
                await query.edit_message_text("🕊️ Вы помиловали всех.")
                # Найти всех кандидатов и помиловать
                game.judge_decision_pending = False
                game.phase = GamePhase.DAY
                await context.bot.send_message(
                    chat_id=game.chat_id,
                    text="🕊️ *ПОМИЛОВАНИЕ!*\n\nСудья помиловал всех приговорённых!",
                    parse_mode=ParseMode.MARKDOWN
                )
            else:
                target_id = int(target_id)
                await query.edit_message_text("🕊️ Вы помиловали.")
                await execute_verdict(context, game, target_id, False)


# ═══════════════════════════════════════════════════════════════
# ГЛАВНАЯ ФУНКЦИЯ
# ═══════════════════════════════════════════════════════════════

def main():
    application = Application.builder().token(BOT_TOKEN).build()

    # Команды
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("newgame", newgame_command))
    application.add_handler(CommandHandler("join", join_command))
    application.add_handler(CommandHandler("leave", leave_command))
    application.add_handler(CommandHandler("players", players_command))
    application.add_handler(CommandHandler("roles", roles_command))
    application.add_handler(CommandHandler("rules", rules_command))
    application.add_handler(CommandHandler("setroles", setroles_command))
    application.add_handler(CommandHandler("startnight", startnight_command))
    application.add_handler(CommandHandler("endnight", endnight_command))
    application.add_handler(CommandHandler("startvote", startvote_command))
    application.add_handler(CommandHandler("endvote", endvote_command))
    application.add_handler(CommandHandler("vote", vote_command))
    application.add_handler(CommandHandler("kill", kill_command))
    application.add_handler(CommandHandler("cancel", cancel_command))

    # Callback
    application.add_handler(CallbackQueryHandler(button_callback))

    # Команды бота
    application.bot.set_my_commands([
        BotCommand("start", "Начать работу с ботом"),
        BotCommand("newgame", "Создать новую игру"),
        BotCommand("join", "Присоединиться к игре"),
        BotCommand("leave", "Выйти из игры"),
        BotCommand("players", "Список игроков"),
        BotCommand("roles", "Список ролей"),
        BotCommand("rules", "Правила игры"),
        BotCommand("setroles", "Назначить роли (ведущий)"),
        BotCommand("startnight", "Начать ночь (ведущий)"),
        BotCommand("endnight", "Закончить ночь (ведущий)"),
        BotCommand("startvote", "Начать голосование (ведущий)"),
        BotCommand("endvote", "Закончить голосование (ведущий)"),
        BotCommand("vote", "Проголосовать"),
        BotCommand("kill", "Выстрелить (стрелок)"),
        BotCommand("cancel", "Отменить игру"),
    ])

    print("🎭 Бот Мафия запущен!")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
