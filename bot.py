import discord
from discord.ext import commands, tasks
import json
import os
import asyncio
from datetime import datetime

# --- IMPORTURI PENTRU MUZICĂ (ADĂUGATE) ---
from discord import FFmpegPCMAudio
import yt_dlp

# =============== SETĂRI GENERALE ===============

TOKEN = "Pune_TOKENUL_AICI"   # <-- pune token-ul tău nou între ghilimele

# ID-URI (le iei cu click dreapta -> Copy ID în Discord)
GUILD_ID = 1443148994606796854        # ID server History2
WELCOME_CHANNEL_ID = 1443153107134447697
LEAVE_CHANNEL_ID = 1443153107134447697
LEVEL_UP_CHANNEL_ID = 1443155030944518264
LOG_CHANNEL_ID = 1443298219147661353
DEFAULT_ROLE_ID = 1443177369367220305  # rol Player / Member
MUTE_ROLE_ID = 1443291884146397244     # rol Muted (fără permisiuni de scris)
TICKETS_CATEGORY_ID = 1443155615827497001  # categoria unde se creează tichetele

# =============== SERVER STATS (ADĂUGAT) ===============
# Pune aici ID-urile canalelor tale de stats (din categoria SERVER STATS)
MEMBER_COUNT_CHANNEL_ID = 1443165369723387966   # ex: canal "👥 Members: 0"
ONLINE_COUNT_CHANNEL_ID = 1443326999543156911   # ex: canal "🟢 Online: 0"
METIN_SITE_CHANNEL_ID   = 1443327420630569032   # ex: canal "🌐 Site Metin2"
METIN_SITE_URL = "https://history2.ro"  # schimbă cu site-ul tău real

COMMAND_PREFIX = "!"

LEVELS_FILE = "levels.json"
WARNS_FILE = "warns.json"
TICKETS_FILE = "tickets.json"   # <--- nou: salvăm tichetele

XP_PER_MESSAGE = 5
MIN_MSG_LENGTH_FOR_XP = 3

SPAM_TIME_WINDOW = 5   # secunde
SPAM_MAX_MSG = 7       # câte mesaje max în fereastra de mai sus

# =============== SETĂRI MUZICĂ (ADĂUGATE) ===============

YTDL_OPTIONS = {
    "format": "bestaudio/best",
    "noplaylist": True,
    "default_search": "ytsearch",  # caute după numele melodiei pe YouTube
    "quiet": True
}

FFMPEG_OPTIONS = {
    "options": "-vn"
}

ytdl = yt_dlp.YoutubeDL(YTDL_OPTIONS)

# =============== INTENTS ===============

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True
intents.presences = True  # <--- pentru a vedea cine e online

bot = commands.Bot(command_prefix=COMMAND_PREFIX, intents=intents)

# =============== DATE MEMORATE ===============

levels = {}          # pentru XP / level
warns = {}           # pentru warn-uri
spam_tracker = {}    # pentru anti-spam
tickets = {}         # pentru tichete unice pe user


# =============== FUNCȚII UTILITARE ===============

def load_json(path):
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return {}
    return {}

def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)

def get_level(xp: int) -> int:
    # foarte simplu: 100 XP = 1 nivel
    return xp // 100


# =============== TICKET HELPERS + VIEW (PANEL CU BUTOANE) ===============

async def create_ticket_for_user(interaction: discord.Interaction, category_name: str):
    """Creează un ticket unic pentru user, pe baza butonului apăsat."""
    if interaction.guild is None or interaction.guild.id != GUILD_ID:
        return await interaction.response.send_message(
            "Sistemul de tichete funcționează doar pe serverul principal. ❌",
            ephemeral=True
        )

    guild = interaction.guild
    category = guild.get_channel(TICKETS_CATEGORY_ID)
    if category is None or not isinstance(category, discord.CategoryChannel):
        return await interaction.response.send_message(
            "Nu găsesc categoria de tichete. Spune unui admin să verifice `TICKETS_CATEGORY_ID` în cod.",
            ephemeral=True
        )

    uid = str(interaction.user.id)

    # verificăm dacă userul are deja ticket deschis
    user_ticket = tickets.get(uid)
    if user_ticket:
        existing_channel = guild.get_channel(user_ticket.get("channel_id"))
        if existing_channel is not None:
            return await interaction.response.send_message(
                f"📝 Ai deja un ticket deschis: {existing_channel.mention}\n"
                f"Te rog folosește acel canal sau închide-l cu `!close`.",
                ephemeral=True
            )
        else:
            tickets.pop(uid, None)
            save_json(TICKETS_FILE, tickets)

    # generăm un ID unic de ticket
    last_id = tickets.get("_last_id", 0)
    ticket_id = last_id + 1
    tickets["_last_id"] = ticket_id

    channel_name = f"{category_name.lower()}-{ticket_id:04d}".replace(" ", "-")

    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
        guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
    }

    channel = await guild.create_text_channel(
        name=channel_name,
        category=category,
        overwrites=overwrites
    )

    tickets[uid] = {
        "channel_id": channel.id,
        "ticket_id": ticket_id,
        "open": True,
        "type": category_name,
        "created_at": datetime.utcnow().isoformat()
    }
    save_json(TICKETS_FILE, tickets)

    await channel.send(
        f"🎫 Ticket #{ticket_id:04d} – **{category_name}**\n"
        f"👤 Deschis de {interaction.user.mention}\n\n"
        f"Te rugăm să descrii problema cât mai clar.\n"
        f"Un membru al staff-ului te va ajuta în curând. 🙂"
    )

    await interaction.response.send_message(
        f"✅ Ți-am deschis un ticket: {channel.mention}",
        ephemeral=True
    )


class TicketView(discord.ui.View):
    """View persistent cu butoane pentru panelul de ticket."""

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Support",
        style=discord.ButtonStyle.blurple,
        emoji="🟦",
        custom_id="ticket_support"
    )
    async def support_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await create_ticket_for_user(interaction, "Support")

    @discord.ui.button(
        label="Raportează un jucător",
        style=discord.ButtonStyle.grey,
        emoji="🧑‍⚖️",
        custom_id="ticket_player"
    )
    async def player_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await create_ticket_for_user(interaction, "Raport jucător")

    @discord.ui.button(
        label="Raportează un bug",
        style=discord.ButtonStyle.danger,
        emoji="🐞",
        custom_id="ticket_bug"
    )
    async def bug_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await create_ticket_for_user(interaction, "Bug / Problemă tehnică")

    @discord.ui.button(
        label="Probleme donații / site",
        style=discord.ButtonStyle.success,
        emoji="💸",
        custom_id="ticket_donate"
    )
    async def donate_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await create_ticket_for_user(interaction, "Donații / Site")


# =============== EVENIMENT: BOT ONLINE ===============

@bot.event
async def on_ready():
    global levels, warns, tickets
    levels = load_json(LEVELS_FILE)
    warns = load_json(WARNS_FILE)
    tickets = load_json(TICKETS_FILE)
    print(f"✅ Bot online: {bot.user} (ID: {bot.user.id})")
    await bot.change_presence(activity=discord.Game(name="pe History2"))
    if not spam_cleaner.is_running():
        spam_cleaner.start()
    if not update_server_stats.is_running():
        update_server_stats.start()

    # înregistrăm view-ul de butoane (pentru panel)
    bot.add_view(TicketView())


# =============== COMENZI BASIC ===============

@bot.command()
async def ping(ctx):
    """Test dacă botul e online."""
    await ctx.send("Pong! 🏓")

@bot.command(name="helpme")
async def helpme(ctx):
    """Listă comenzi."""
    embed = discord.Embed(title="📜 Comenzi History2 Bot", color=discord.Color.gold())
    embed.add_field(name="General", value="!ping, !helpme", inline=False)
    embed.add_field(name="Moderare", value="!clear <nr>, !kick, !ban, !mute, !unmute", inline=False)
    embed.add_field(name="Level", value="!rank [@user], !top", inline=False)
    embed.add_field(name="Warn", value="!warn @user [motiv], !warnings [@user]", inline=False)
    embed.add_field(
        name="Tickets",
        value="Folosește canalul de ticket (cu panelul de butoane).\nStaff: !setticketpanel, !close (în canalul de ticket).",
        inline=False
    )
    embed.add_field(name="🎵 Muzică", value="!join, !leave, !play <nume>, !pause, !resume, !stop", inline=False)
    await ctx.send(embed=embed)


# =============== CLEAR / KICK / BAN ===============

@bot.command(name="clear")
@commands.has_permissions(manage_messages=True)
async def clear(ctx, amount: int):
    """Șterge mesaje din canal."""
    if amount <= 0:
        await ctx.send("Pune un număr mai mare ca 0. 🙂")
        return
    deleted = await ctx.channel.purge(limit=amount + 1)  # +1 = șterge și comanda
    msg = await ctx.send(f"Am șters {len(deleted)-1} mesaje. 🧹")
    await msg.delete(delay=5)

@clear.error
async def clear_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("Ai nevoie de permisiunea *Manage Messages* ca să folosești comanda asta.")


@bot.command()
@commands.has_permissions(kick_members=True)
async def kick(ctx, member: discord.Member, *, reason: str = "Fără motiv"):
    """Kick unui membru."""
    try:
        await member.kick(reason=reason)
        await ctx.send(f"👢 {member.mention} a fost dat afară. Motiv: {reason}")
        log_ch = ctx.guild.get_channel(LOG_CHANNEL_ID)
        if log_ch:
            await log_ch.send(f"👢 {member} a fost dat afară de {ctx.author}. Motiv: {reason}")
    except discord.Forbidden:
        await ctx.send("Nu pot da kick acestui membru (permisiuni insuficiente).")


@bot.command()
@commands.has_permissions(ban_members=True)
async def ban(ctx, member: discord.Member, *, reason: str = "Fără motiv"):
    """Ban unui membru."""
    try:
        await member.ban(reason=reason, delete_message_days=1)
        await ctx.send(f"🔨 {member.mention} a fost banat. Motiv: {reason}")
        log_ch = ctx.guild.get_channel(LOG_CHANNEL_ID)
        if log_ch:
            await log_ch.send(f"🔨 {member} a fost banat de {ctx.author}. Motiv: {reason}")
    except discord.Forbidden:
        await ctx.send("Nu pot bana acest membru (permisiuni insuficiente).")


# =============== MUTE / UNMUTE ===============

@bot.command()
@commands.has_permissions(moderate_members=True)
async def mute(ctx, member: discord.Member, minutes: int = 10, *, reason: str = "Fără motiv"):
    """Mute temporar cu rol."""
    role = ctx.guild.get_role(MUTE_ROLE_ID)
    if role is None:
        await ctx.send("Nu găsesc rolul de mute. Setează MUTE_ROLE_ID în cod.")
        return
    await member.add_roles(role, reason=reason)
    await ctx.send(f"🔇 {member.mention} a fost mutat pentru {minutes} minute. Motiv: {reason}")
    log_ch = ctx.guild.get_channel(LOG_CHANNEL_ID)
    if log_ch:
        await log_ch.send(f"🔇 {member} a fost mutat de {ctx.author} pentru {minutes} minute. Motiv: {reason}")
    await asyncio.sleep(minutes * 60)
    if role in member.roles:
        await member.remove_roles(role, reason="Mute expirat")

@bot.command()
@commands.has_permissions(moderate_members=True)
async def unmute(ctx, member: discord.Member):
    """Scoate mute."""
    role = ctx.guild.get_role(MUTE_ROLE_ID)
    if role is None:
        await ctx.send("Nu găsesc rolul de mute.")
        return
    if role in member.roles:
        await member.remove_roles(role, reason="Unmute manual")
        await ctx.send(f"🔊 {member.mention} a primit unmute.")
    else:
        await ctx.send("Userul nu este mutat.")


# =============== WARN SYSTEM ===============

@bot.command()
@commands.has_permissions(moderate_members=True)
async def warn(ctx, member: discord.Member, *, reason: str = "Fără motiv"):
    """Dă avertisment."""
    uid = str(member.id)
    user_warns = warns.get(uid, [])
    user_warns.append({"reason": reason, "by": ctx.author.id, "time": datetime.utcnow().isoformat()})
    warns[uid] = user_warns
    save_json(WARNS_FILE, warns)
    await ctx.send(f"⚠️ {member.mention} a primit un avertisment. Motiv: {reason}")

@bot.command(name="warnings")
async def warnings_cmd(ctx, member: discord.Member = None):
    """Vezi avertismentele."""
    if member is None:
        member = ctx.author
    uid = str(member.id)
    user_warns = warns.get(uid, [])
    if not user_warns:
        await ctx.send(f"{member.mention} nu are avertismente.")
        return
    lines = []
    for i, w in enumerate(user_warns, start=1):
        by = ctx.guild.get_member(w["by"])
        by_name = by.name if by else "necunoscut"
        lines.append(f"*{i}.* {w['reason']} (de {by_name})")
    embed = discord.Embed(
        title=f"⚠️ Avertismente pentru {member}",
        description="\n".join(lines),
        color=discord.Color.orange()
    )
    await ctx.send(embed=embed)


# =============== WELCOME / LEAVE + AUTOROLE ===============

@bot.event
async def on_member_join(member: discord.Member):
    if GUILD_ID and member.guild.id != GUILD_ID:
        return

    # autorole
    role = member.guild.get_role(DEFAULT_ROLE_ID)
    if role:
        try:
            await member.add_roles(role, reason="Autorole la intrare")
        except discord.Forbidden:
            print("Nu am permisiune să dau rolul automat.")

    # welcome
    ch = member.guild.get_channel(WELCOME_CHANNEL_ID)
    if ch:
        embed = discord.Embed(
            title="👋 Bine ai venit pe History2!",
            description=(f"Salut {member.mention}, bine ai venit pe *History2*!\n"),
            color=discord.Color.green()
        )
        embed.set_thumbnail(url="https://cdn.discordapp.com/attachments/1443153107134447697/1443303370550153226/4sd65a4sd65as4d65a4s65d46a5s4d65a.jpeg?ex=69289482&is=69274302&hm=98477dfc3c5f8ac0bcd1b2cf7d14e526ed051076ece7fdea9f2e958daeef18d7&")
        await ch.send(embed=embed)

@bot.event
async def on_member_remove(member: discord.Member):
    if GUILD_ID and member.guild.id != GUILD_ID:
        return
    ch = member.guild.get_channel(LEAVE_CHANNEL_ID)
    if ch:
        embed = discord.Embed(
            title="🍂 Un jucător a părăsit serverul",
            description=f"*{member.name}* a părăsit *History2*.",
            color=discord.Color.red()
        )
        await ch.send(embed=embed)


# =============== LOG MESAJ ȘTERS / EDITAT ===============

@bot.event
async def on_message_delete(message: discord.Message):
    if not message.guild or message.author.bot:
        return
    ch = message.guild.get_channel(LOG_CHANNEL_ID)
    if ch:
        embed = discord.Embed(title="🗑️ Mesaj șters", color=discord.Color.dark_grey())
        embed.add_field(name="Autor", value=f"{message.author} (ID: {message.author.id})", inline=False)
        embed.add_field(name="Canal", value=message.channel.mention, inline=False)
        if message.content:
            embed.add_field(name="Conținut", value=message.content[:1000], inline=False)
        embed.timestamp = datetime.utcnow()
        await ch.send(embed=embed)

@bot.event
async def on_message_edit(before: discord.Message, after: discord.Message):
    if not before.guild or before.author.bot:
        return
    if before.content == after.content:
        return
    ch = before.guild.get_channel(LOG_CHANNEL_ID)
    if ch:
        embed = discord.Embed(title="✏️ Mesaj editat", color=discord.Color.blue())
        embed.add_field(name="Autor", value=f"{before.author} (ID: {before.author.id})", inline=False)
        embed.add_field(name="Canal", value=before.channel.mention, inline=False)
        embed.add_field(name="Înainte", value=before.content[:500] or "—", inline=False)
        embed.add_field(name="După", value=after.content[:500] or "—", inline=False)
        embed.timestamp = datetime.utcnow()
        await ch.send(embed=embed)


# =============== LEVEL / XP SYSTEM ===============

@bot.command()
async def rank(ctx, member: discord.Member = None):
    """Arată level și XP."""
    if member is None:
        member = ctx.author
    uid = str(member.id)
    data = levels.get(uid, {"xp": 0, "level": 0})
    xp = data["xp"]
    lvl = data["level"]
    embed = discord.Embed(title=f"📈 Rank pentru {member}", color=discord.Color.blurple())
    embed.add_field(name="Level", value=str(lvl))
    embed.add_field(name="XP", value=str(xp))
    await ctx.send(embed=embed)

@bot.command(name="top")
async def top_cmd(ctx):
    """Top 10 XP."""
    if not levels:
        await ctx.send("Nu există încă date de level.")
        return
    top_list = sorted(levels.items(), key=lambda x: x[1]["xp"], reverse=True)[:10]
    lines = []
    for i, (uid, data) in enumerate(top_list, start=1):
        member = ctx.guild.get_member(int(uid))
        name = member.name if member else f"User ID {uid}"
        lines.append(f"*#{i}* {name} – Level {data['level']} ({data['xp']} XP)")
    embed = discord.Embed(
        title="🏆 Top 10 jucători după XP",
        description="\n".join(lines),
        color=discord.Color.gold()
    )
    await ctx.send(embed=embed)


# =============== TICKETS – PANEL + CLOSE ===============

@bot.command(name="setticketpanel")
@commands.has_permissions(administrator=True)
async def setticketpanel(ctx):
    """Trimite panelul de ticketing cu butoane (de folosit o singură dată într-un canal)."""
    embed = discord.Embed(
        title="📨 Bun venit în sistemul de ticketing",
        description=(
            "Dacă întâmpini o problemă, ai o nelămurire sau ai nevoie de ajutor legat de server,\n"
            "te rugăm să deschizi un ticket apăsând unul dintre butoanele de mai jos.\n\n"
            "__Pentru a primi asistență cât mai rapid, te rugăm să incluzi în mesaj:__\n"
            "• Numele din joc / contul afectat\n"
            "• O descriere clară și detaliată a situației\n"
            "• Dovezi / screenshot-uri, dacă este cazul\n\n"
            "Îți mulțumim pentru înțelegere și pentru încrederea acordată echipei! ❤️"
        ),
        color=discord.Color.orange()
    )

    view = TicketView()
    await ctx.send(embed=embed, view=view)


@bot.command()
async def close(ctx):
    """Închide canalul de ticket (doar în canal de ticket)."""
    if not ctx.channel.category or ctx.channel.category.id != TICKETS_CATEGORY_ID:
        return await ctx.send("Comanda `!close` se poate folosi doar într-un canal de ticket. ❌")

    guild = ctx.guild
    channel = ctx.channel

    # găsim cui aparține ticketul după channel_id
    owner_id = None
    for uid, info in list(tickets.items()):
        if uid == "_last_id":
            continue
        if info.get("channel_id") == channel.id:
            owner_id = uid
            break

    if owner_id is not None:
        tickets.pop(owner_id, None)
        save_json(TICKETS_FILE, tickets)

    await ctx.send("✅ Ticket-ul va fi închis în 5 secunde...")
    await asyncio.sleep(5)
    try:
        await channel.delete()
    except discord.Forbidden:
        await ctx.send("Nu am permisiune să șterg acest canal. Verifică rolul botului.")


# =============== REGULAMENT PANEL (NOU) ===============

@bot.command(name="setregulament")
@commands.has_permissions(administrator=True)
async def setregulament(ctx):
    """Trimite panel de regulament (fără poze, fără butoane) — de folosit de admin într-un canal panel."""

    # Embed 1: REGULAMENT JOC
    embed1 = discord.Embed(
        title="📜 REGULAMENT JOC",
        description=(
            "1. Folositi un nume decent pentru caracter/breasla si magazinele private. Nu se accepta nume care contin "
            "cuvinte obscene, rasiste sau alte cuvinte deranjante pentru alti jucatori. "
            "(Stergerea caracterului in cauza de catre jucator sau BAN PERMANENT - in functie de situatie)\n\n"
            "2. In cazul in care gasiti anumite buguri, TREBUIE SA LE RAPORTATI! Abuzul de buguri sau folosirea de hack-uri, "
            "scripturi sau programe care ajuta la trisare sunt pedepsite. "
            "(AVERTISMENT / BAN 1-7 zile sau in unele cazuri grave BAN PERMANENT pe toate conturile)\n\n"
            "3. Negotul intre serverul nostru si un alt server este strict interzis. De mentionat, nu se accepta nici "
            "\"dau acolo pe aici\". (BAN PERMANENT pe toate conturile)\n\n"
            "4. Echipa History2 nu raspunde de iteme, conturi furate sau conturi sparte.\n"
            "RECOMANDARE: Folositi o parola complexa cu majuscule, simboluri si o parola secundara unica. "
            "Evitati parole simple precum: 1234, abcd, qwerty etc.\n\n"
            "5. Pastrati un limbaj decent pe joc fata de ceilalti jucatori. (MUTE 1-12 ore). "
            "Injuraturile si jignirile care implica membrii familiei se sanctioneaza cu MUTE de minim 24 de ore. "
            "Daca se insista de pe un cont secundar cu injuraturi, acel jucator este sanctionat cu BAN pe toate conturile "
            "pentru 1-7 zile.\n\n"
            "6. Reclama la alte servere de metin duce la blocarea permanenta a conturilor.\n\n"
            "7. Orice insulta, jignire sau injuratura la adresa unui membru STAFF poate duce la MUTE 24h sau blocarea "
            "conturilor pe IP intre 1 si 60 zile.\n\n"
            "8. RMT (Real Money Transfer/Negot cu bani reali) de orice fel este interzis. Chiar si tentativa de RMT se pedepseste la fel! "
            "(BAN PERMANENT pe toate conturile)\n\n"
            "9. Denigrarea serverului sau a STAFF-ului prin orice mijloace, mai ales prin acuzatii false/nefondate si fara dovezi, "
            "duce la blocarea conturilor pe hardware ID pentru o perioada de minim 30 de zile. (A nu se confunda cu libera exprimare)\n\n"
            "10. Folosirea identitatii din joc pe alte conturi cu scopul de a fura sau frauda un alt jucator duce la BAN permanent. "
            "Furtul prin inselaciune se sanctioneaza, de asemenea, cu BAN permanent pe IP si HWID. "
            "Aceasta sanctiune nu se aplica daca un jucator isi cedeaza contul/iteme in mod voluntar altui jucator.\n\n"
            "11. Vanzarea de conturi este permisa DOAR pe canalul de Discord: vand-cumpar-cont. "
            "Este interzisa vanzarea pe retelele de socializare pentru a evita eventuale cazuri de RMT. "
            "Se aplica aceeasi sanctiune ca la regula 8, respectiv BAN permanent.\n\n"
            "12. Furnizarea de informatii false, precum disparitia unor iteme sau alte situatii ce necesita verificari in backup-uri, "
            "iar ulterior se dovedeste ca nu a disparut nimic, va duce la banarea jucatorului pe toate conturile pentru o perioada "
            "intre 7 si 30 de zile.\n\n"
            "13. Verificati categoriile disponibile si evitati offtopic-ul [Discord].\n\n"
            "14. La categoria \"marketing\" se fac doar anunturi. Daca gasiti ceva care va place, contactati in privat persoana "
            "care a postat [Discord]."
        ),
        color=discord.Color.orange()
    )

    # Embed 2: REGULAMENT DISCORD
    embed2 = discord.Embed(
        title="📘 REGULAMENT DISCORD",
        description=(
            "1. Verificati categoriile disponibile si evitati off-topic-ul.(MUTE 1 ora - pe discord)\n\n"
            "2. In categoria \"marketing\" se fac doar anunturi. Daca gasiti ceva care va place, contactati persoana "
            "respectiva in privat.(MUTE 1 ora - pe discord)\n\n"
            "3. Cei care manifesta un comportament toxic sau nepotrivit vor fi sanctionati.(BAN PERMANENT - pe discord)\n\n"
            "4. Nu postati link-uri suspecte.(MUTE 1 zi - pe discord)\n\n"
            "5. Este interzisa postarea de materiale cu tenta sexuala, nuditate sau continut NSFW pe oricare dintre "
            "canalele text.(MUTE 1-7 zile - pe discord)\n\n"
            "6. Evitati spam-ul pe canalele vocale sau de text ale serverului de Discord.(MUTE 1 ora - pe discord)\n\n"
            "7. Nu mentionati membrii staff-ului decat daca aveti o urgenta reala.(MUTE 1 zi - pe discord in caz de spam)\n\n"
            "8. Pastrati un limbaj decent pe discord fata de ceilalti jucatori. (MUTE 1-12 ore). "
            "Injuraturile si jignirile care implica membrii familiei se sanctioneaza cu MUTE de minim 24 de ore.\n\n"
            "9. Este interzisa postarea de imagini cu alti jucatori cu scopul de a le denigra imaginea.(MUTE 7 zile - pe discord)"
        ),
        color=discord.Color.blue()
    )

    await ctx.send(embed=embed1)
    await ctx.send(embed=embed2)
    await ctx.send(
        "✅ Panelul de **REGULAMENT** a fost postat. "
        "Îți recomand să blochezi canalul la scris pentru @everyone ca să rămână curat.",
        delete_after=10
    )


# =============== SISTEM MUZICĂ 🎵 (ADĂUGAT) ===============

async def ensure_voice(ctx):
    """Verifică dacă userul e în voice și conectează botul."""
    if not ctx.author.voice or not ctx.author.voice.channel:
        await ctx.send("Intră într-un canal de voice mai întâi. 🎧")
        return None

    voice_channel = ctx.author.voice.channel
    voice_client = ctx.voice_client

    if voice_client is None:
        voice_client = await voice_channel.connect()
    else:
        if voice_client.channel != voice_channel:
            await voice_client.move_to(voice_channel)

    return voice_client


@bot.command()
async def join(ctx):
    """Botul intră în canalul tău de voice."""
    vc = await ensure_voice(ctx)
    if vc:
        await ctx.send(f"Am intrat în {vc.channel.mention} ✅")


@bot.command()
async def leave(ctx):
    """Botul iese din voice."""
    if ctx.voice_client:
        await ctx.voice_client.disconnect()
        await ctx.send("Am ieșit din voice. 👋")
    else:
        await ctx.send("Nu sunt într-un canal de voice.")


@bot.command()
async def play(ctx, *, query: str):
    """
    Redă muzică după nume sau link YouTube.
    Exemplu: !play eminem mockinbird
    """
    voice_client = await ensure_voice(ctx)
    if voice_client is None:
        return

    await ctx.send(f"🔎 Caut melodia: **{query}** ...")

    loop = asyncio.get_event_loop()
    try:
        # ytsearch: ia primul rezultat pentru numele dat
        data = await loop.run_in_executor(None, lambda: ytdl.extract_info(query, download=False))
        if "entries" in data:
            data = data["entries"][0]

        url = data["url"]
        title = data.get("title", "melodie necunoscută")

        source = FFmpegPCMAudio(url, **FFMPEG_OPTIONS)

        if voice_client.is_playing():
            voice_client.stop()

        voice_client.play(source)
        await ctx.send(f"▶️ Redau: **{title}**")
    except Exception as e:
        print(e)
        await ctx.send("A apărut o eroare la redarea melodiei. Verifică dacă FFmpeg este instalat corect.")


@bot.command()
async def stop(ctx):
    """Oprește muzica."""
    if ctx.voice_client and ctx.voice_client.is_playing():
        ctx.voice_client.stop()
        await ctx.send("⏹ Muzica a fost oprită.")
    else:
        await ctx.send("Nu cânt nimic acum.")


@bot.command()
async def pause(ctx):
    """Pune pauză la melodie."""
    if ctx.voice_client and ctx.voice_client.is_playing():
        ctx.voice_client.pause()
        await ctx.send("⏸ Pauză.")
    else:
        await ctx.send("Nu cânt nimic ca să pun pauză.")


@bot.command()
async def resume(ctx):
    """Reia melodia."""
    if ctx.voice_client and ctx.voice_client.is_paused():
        ctx.voice_client.resume()
        await ctx.send("▶️ Am reluat melodia.")
    else:
        await ctx.send("Nu am nimic în pauză.")


# =============== ANTI-SPAM + XP LA MESAJ ===============

@bot.event
async def on_message(message: discord.Message):
    if message.author.bot or not message.guild:
        return

    if GUILD_ID and message.guild.id == GUILD_ID:
        # Anti-spam
        now = datetime.utcnow()
        user_id = message.author.id
        times = spam_tracker.get(user_id, [])
        times = [t for t in times if (now - t).total_seconds() <= SPAM_TIME_WINDOW]
        times.append(now)
        spam_tracker[user_id] = times

        if len(times) > SPAM_MAX_MSG:
            try:
                await message.delete()
            except discord.Forbidden:
                pass
            await message.channel.send(
                f"{message.author.mention}, nu face spam te rog. 🛑",
                delete_after=5
            )

        # XP / level
        if len(message.content.strip()) >= MIN_MSG_LENGTH_FOR_XP:
            uid = str(user_id)
            data = levels.get(uid, {"xp": 0, "level": 0})
            data["xp"] += XP_PER_MESSAGE
            new_level = get_level(data["xp"])
            if new_level > data["level"]:
                data["level"] = new_level
                ch = message.guild.get_channel(LEVEL_UP_CHANNEL_ID) or message.channel
                await ch.send(
                    f"🚀 **LEVEL UP!**\n"
                    f"{message.author.mention} tocmai a trecut la **Nivelul {new_level}**! ⭐\n"
                    f"Continuă să crești! 🔥"
                )
            levels[uid] = data
            save_json(LEVELS_FILE, levels)

    await bot.process_commands(message)


# =============== SERVER STATS UPDATE (ADĂUGAT) ===============

@tasks.loop(seconds=30)
async def update_server_stats():
    """Actualizează canalele de stats: Members, Online, Site Metin."""
    guild = bot.get_guild(GUILD_ID)
    if guild is None:
        return

    total_members = guild.member_count
    online_members = len([m for m in guild.members if m.status != discord.Status.offline])

    # Members
    if MEMBER_COUNT_CHANNEL_ID:
        ch = guild.get_channel(MEMBER_COUNT_CHANNEL_ID)
        if ch:
            try:
                await ch.edit(name=f"👥 Members: {total_members}")
            except Exception as e:
                print("Eroare la editarea canalului Members:", e)

    # Online
    if ONLINE_COUNT_CHANNEL_ID:
        ch = guild.get_channel(ONLINE_COUNT_CHANNEL_ID)
        if ch:
            try:
                await ch.edit(name=f"🟢 Online: {online_members}")
            except Exception as e:
                print("Eroare la editarea canalului Online:", e)

    # Site Metin
    if METIN_SITE_CHANNEL_ID:
        ch = guild.get_channel(METIN_SITE_CHANNEL_ID)
        if ch:
            try:
                await ch.edit(name=f"🌐 Site Metin2: {METIN_SITE_URL}")
            except Exception as e:
                print("Eroare la editarea canalului Site Metin:", e)


@tasks.loop(minutes=1)
async def spam_cleaner():
    """Curăță buffer-ul anti-spam periodic."""
    now = datetime.utcnow()
    for user_id, times in list(spam_tracker.items()):
        times = [t for t in times if (now - t).total_seconds() <= SPAM_TIME_WINDOW]
        if times:
            spam_tracker[user_id] = times
        else:
            del spam_tracker[user_id]


# =============== PORNIRE BOT ===============

if __name__ == "__main__":
    bot.run(TOKEN)
