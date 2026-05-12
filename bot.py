import discord
from discord.ext import commands
from discord import app_commands
import json
import os
TOKEN = os.environ.get("TOKEN")
GUILD_ID = int(os.environ.get("GUILD_ID"))
from datetime import datetime

# ══════════════════════════════════════════
#  CONFIG
# ══════════════════════════════════════════

# ══════════════════════════════════════════
#  SETUP
# ══════════════════════════════════════════
intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree
DATA_FILE = "data.json"

# ══════════════════════════════════════════
#  DONNÉES
# ══════════════════════════════════════════
def load_data():
    if not os.path.exists(DATA_FILE):
        return {"championnats": {}, "live_classements": {}}
    data = json.load(open(DATA_FILE, "r", encoding="utf-8"))
    if "live_classements" not in data:
        data["live_classements"] = {}
    return data

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def equipe_vide():
    return {"pts": 0, "j": 0, "v": 0, "n": 0, "d": 0, "bp": 0, "bc": 0}

def calculer_classement(champ):
    equipes = {nom: equipe_vide() for nom in champ["equipes"]}
    for match in champ["matchs"]:
        eq1, eq2 = match["eq1"], match["eq2"]
        b1, b2 = match["b1"], match["b2"]
        if eq1 not in equipes: equipes[eq1] = equipe_vide()
        if eq2 not in equipes: equipes[eq2] = equipe_vide()
        equipes[eq1]["j"] += 1; equipes[eq2]["j"] += 1
        equipes[eq1]["bp"] += b1; equipes[eq1]["bc"] += b2
        equipes[eq2]["bp"] += b2; equipes[eq2]["bc"] += b1
        if b1 > b2:
            equipes[eq1]["v"] += 1; equipes[eq1]["pts"] += 3; equipes[eq2]["d"] += 1
        elif b2 > b1:
            equipes[eq2]["v"] += 1; equipes[eq2]["pts"] += 3; equipes[eq1]["d"] += 1
        else:
            equipes[eq1]["n"] += 1; equipes[eq1]["pts"] += 1
            equipes[eq2]["n"] += 1; equipes[eq2]["pts"] += 1
    champ["equipes"] = equipes
    return equipes

def trier_classement(equipes):
    return sorted(
        equipes.items(),
        key=lambda x: (x[1]["pts"], x[1]["bp"] - x[1]["bc"], x[1]["bp"]),
        reverse=True
    )

def build_classement_embed(champ_nom, champ):
    """Construit l'embed de classement pour un championnat."""
    if not champ["equipes"]:
        return discord.Embed(
            title=f"📊 {champ_nom}",
            description="Aucune équipe pour l'instant.",
            color=0x5865F2
        )
    classement_trie = trier_classement(champ["equipes"])
    medals = ["🥇", "🥈", "🥉"]
    lignes = []
    for i, (nom, s) in enumerate(classement_trie):
        diff = s["bp"] - s["bc"]
        diff_str = f"+{diff}" if diff > 0 else str(diff)
        rang = medals[i] if i < 3 else f"`{i+1}.`"
        lignes.append(
            f"{rang} **{nom}** — {s['pts']}pts | "
            f"{s['j']}J {s['v']}V {s['n']}N {s['d']}D | "
            f"{s['bp']}:{s['bc']} ({diff_str})"
        )
    embed = discord.Embed(
        title=f"📊 Classement — {champ_nom}",
        description="\n".join(lignes),
        color=0x5865F2
    )
    embed.set_footer(text=f"Mis à jour le {datetime.now().strftime('%d/%m/%Y à %H:%M')}")
    return embed

async def mettre_a_jour_live(champ_nom):
    """Met à jour le message live du classement après un résultat."""
    data = load_data()
    live = data.get("live_classements", {})
    if champ_nom not in live:
        return
    info = live[champ_nom]
    try:
        channel = bot.get_channel(info["channel_id"])
        if channel is None:
            channel = await bot.fetch_channel(info["channel_id"])
        message = await channel.fetch_message(info["message_id"])
        champ = data["championnats"][champ_nom]
        embed = build_classement_embed(champ_nom, champ)
        await message.edit(embed=embed)
    except Exception as e:
        print(f"⚠️ Impossible de mettre à jour le live de {champ_nom} : {e}")

# ══════════════════════════════════════════
#  MODAL — SAISIE DES BUTS
# ══════════════════════════════════════════
class ButsModal(discord.ui.Modal):
    buts1 = discord.ui.TextInput(
        label="Buts équipe 1 (domicile)",
        placeholder="Ex: 2",
        min_length=1, max_length=2,
        required=True
    )
    buts2 = discord.ui.TextInput(
        label="Buts équipe 2 (visiteur)",
        placeholder="Ex: 1",
        min_length=1, max_length=2,
        required=True
    )

    def __init__(self, champ_nom, eq1, eq2):
        super().__init__(title=f"{eq1}  vs  {eq2}")
        self.champ_nom = champ_nom
        self.eq1 = eq1
        self.eq2 = eq2

    async def on_submit(self, interaction: discord.Interaction):
        try:
            b1 = int(self.buts1.value)
            b2 = int(self.buts2.value)
        except ValueError:
            await interaction.response.send_message("❌ Entre uniquement des chiffres !", ephemeral=True)
            return

        data = load_data()
        champ = data["championnats"][self.champ_nom]
        if self.eq1 not in champ["equipes"]: champ["equipes"][self.eq1] = equipe_vide()
        if self.eq2 not in champ["equipes"]: champ["equipes"][self.eq2] = equipe_vide()

        champ["matchs"].append({
            "eq1": self.eq1, "eq2": self.eq2, "b1": b1, "b2": b2,
            "date": datetime.now().strftime("%d/%m/%Y %H:%M"),
            "auteur": str(interaction.user)
        })
        calculer_classement(champ)
        save_data(data)

        # Met à jour le salon live automatiquement
        await mettre_a_jour_live(self.champ_nom)

        if b1 > b2:
            couleur, result_txt = 0x00d26a, f"🏆 Victoire de **{self.eq1}**"
        elif b2 > b1:
            couleur, result_txt = 0x00d26a, f"🏆 Victoire de **{self.eq2}**"
        else:
            couleur, result_txt = 0xf39c12, "🤝 Match nul"

        embed = discord.Embed(
            title=f"⚽ {self.champ_nom} — Résultat enregistré",
            description=f"## {self.eq1}  {b1} — {b2}  {self.eq2}\n{result_txt}",
            color=couleur,
            timestamp=datetime.now()
        )
        embed.set_footer(text=f"Saisi par {interaction.user.display_name}")
        await interaction.response.send_message(embed=embed)

# ══════════════════════════════════════════
#  VIEWS — MENUS DÉROULANTS
# ══════════════════════════════════════════
class Equipe2Select(discord.ui.Select):
    def __init__(self, champ_nom, eq1, equipes):
        options = [discord.SelectOption(label=nom, emoji="🔵") for nom in equipes if nom != eq1]
        super().__init__(placeholder="Choisis l'équipe 2 (visiteur)...", options=options)
        self.champ_nom = champ_nom
        self.eq1 = eq1

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(ButsModal(self.champ_nom, self.eq1, self.values[0]))

class Equipe2View(discord.ui.View):
    def __init__(self, champ_nom, eq1, equipes):
        super().__init__(timeout=60)
        self.add_item(Equipe2Select(champ_nom, eq1, equipes))

class Equipe1Select(discord.ui.Select):
    def __init__(self, champ_nom, equipes):
        options = [discord.SelectOption(label=nom, emoji="🔴") for nom in equipes]
        super().__init__(placeholder="Choisis l'équipe 1 (domicile)...", options=options)
        self.champ_nom = champ_nom
        self.equipes = equipes

    async def callback(self, interaction: discord.Interaction):
        eq1 = self.values[0]
        await interaction.response.edit_message(
            content=f"**{self.champ_nom}** — **{eq1}** reçoit qui ?",
            view=Equipe2View(self.champ_nom, eq1, self.equipes)
        )

class Equipe1View(discord.ui.View):
    def __init__(self, champ_nom, equipes):
        super().__init__(timeout=60)
        self.add_item(Equipe1Select(champ_nom, equipes))

class ChampionnatSelect(discord.ui.Select):
    def __init__(self, championnats):
        options = [discord.SelectOption(label=nom, emoji="🏆") for nom in championnats]
        super().__init__(placeholder="Choisis le championnat...", options=options)

    async def callback(self, interaction: discord.Interaction):
        champ_nom = self.values[0]
        data = load_data()
        equipes = list(data["championnats"][champ_nom]["equipes"].keys())
        if len(equipes) < 2:
            await interaction.response.edit_message(content="❌ Il faut au moins 2 équipes.", view=None)
            return
        await interaction.response.edit_message(
            content=f"**{champ_nom}** — Quelle est l'équipe qui reçoit ?",
            view=Equipe1View(champ_nom, equipes)
        )

class ChampionnatView(discord.ui.View):
    def __init__(self, championnats):
        super().__init__(timeout=60)
        self.add_item(ChampionnatSelect(championnats))

class ClassementSelect(discord.ui.Select):
    def __init__(self, championnats):
        options = [discord.SelectOption(label=nom, emoji="📊") for nom in championnats]
        super().__init__(placeholder="Choisis le championnat...", options=options)

    async def callback(self, interaction: discord.Interaction):
        champ_nom = self.values[0]
        data = load_data()
        champ = data["championnats"][champ_nom]
        embed = build_classement_embed(champ_nom, champ)
        await interaction.response.edit_message(content=None, embed=embed, view=None)

class ClassementView(discord.ui.View):
    def __init__(self, championnats):
        super().__init__(timeout=60)
        self.add_item(ClassementSelect(championnats))

# ══════════════════════════════════════════
#  EVENTS
# ══════════════════════════════════════════
@bot.event
async def on_ready():
    guild = discord.Object(id=GUILD_ID)
    await tree.sync(guild=guild)
    print(f"✅ Bot connecté : {bot.user}")

# ══════════════════════════════════════════
#  COMMANDES
# ══════════════════════════════════════════
guild_obj = discord.Object(id=GUILD_ID)

# ─── /setup_classement ───────────────────
@tree.command(guild=guild_obj, name="setup_classement", description="Crée un classement live dans ce salon pour un championnat")
@app_commands.describe(championnat="Nom du championnat à afficher en live")
async def setup_classement(interaction: discord.Interaction, championnat: str):
    data = load_data()
    if championnat not in data["championnats"]:
        await interaction.response.send_message(f"❌ Championnat **{championnat}** introuvable.", ephemeral=True)
        return

    champ = data["championnats"][championnat]
    embed = build_classement_embed(championnat, champ)

    # Envoie le message live dans le salon actuel
    await interaction.response.send_message(embed=embed)
    message = await interaction.original_response()

    # Sauvegarde l'ID du salon et du message
    data["live_classements"][championnat] = {
        "channel_id": interaction.channel_id,
        "message_id": message.id
    }
    save_data(data)

    await interaction.followup.send(
        f"✅ Classement live de **{championnat}** activé dans ce salon ! Il se mettra à jour automatiquement à chaque résultat.",
        ephemeral=True
    )

# ─── /resultat ───────────────────────────
@tree.command(guild=guild_obj, name="resultat", description="Enregistre un résultat de match")
async def resultat(interaction: discord.Interaction):
    data = load_data()
    championnats = list(data["championnats"].keys())
    if not championnats:
        await interaction.response.send_message("❌ Aucun championnat créé. Utilise `/creer_championnat` d'abord.", ephemeral=True)
        return
    await interaction.response.send_message("Dans quel championnat ?", view=ChampionnatView(championnats), ephemeral=True)

# ─── /classement ─────────────────────────
@tree.command(guild=guild_obj, name="classement", description="Affiche le classement d'un championnat")
async def classement(interaction: discord.Interaction):
    data = load_data()
    championnats = list(data["championnats"].keys())
    if not championnats:
        await interaction.response.send_message("❌ Aucun championnat créé.", ephemeral=True)
        return
    await interaction.response.send_message("Quel championnat ?", view=ClassementView(championnats), ephemeral=True)

# ─── /creer_championnat ───────────────────
@tree.command(guild=guild_obj, name="creer_championnat", description="Crée un nouveau championnat")
@app_commands.describe(nom="Nom du championnat (ex: Ligue1, LdC...)")
async def creer_championnat(interaction: discord.Interaction, nom: str):
    data = load_data()
    if nom in data["championnats"]:
        await interaction.response.send_message(f"❌ **{nom}** existe déjà !", ephemeral=True)
        return
    data["championnats"][nom] = {"equipes": {}, "matchs": []}
    save_data(data)
    embed = discord.Embed(
        title="🏆 Championnat créé !",
        description=f"**{nom}** est prêt. Utilise `/ajouter_equipe` pour ajouter les équipes.",
        color=0x00d26a
    )
    await interaction.response.send_message(embed=embed)

# ─── /ajouter_equipe ─────────────────────
@tree.command(guild=guild_obj, name="ajouter_equipe", description="Ajoute une équipe à un championnat")
@app_commands.describe(championnat="Nom du championnat", equipe="Nom de l'équipe")
async def ajouter_equipe(interaction: discord.Interaction, championnat: str, equipe: str):
    data = load_data()
    if championnat not in data["championnats"]:
        await interaction.response.send_message(f"❌ Championnat **{championnat}** introuvable.", ephemeral=True)
        return
    if equipe in data["championnats"][championnat]["equipes"]:
        await interaction.response.send_message(f"❌ **{equipe}** est déjà dans ce championnat.", ephemeral=True)
        return
    data["championnats"][championnat]["equipes"][equipe] = equipe_vide()
    save_data(data)
    await interaction.response.send_message(f"✅ **{equipe}** ajoutée à **{championnat}** !")

# ─── /championnats ───────────────────────
@tree.command(guild=guild_obj, name="championnats", description="Liste tous les championnats")
async def liste_championnats(interaction: discord.Interaction):
    data = load_data()
    if not data["championnats"]:
        await interaction.response.send_message("Aucun championnat créé pour l'instant.")
        return
    lignes = [
        f"🏆 **{nom}** — {len(c['equipes'])} équipes, {len(c['matchs'])} matchs"
        for nom, c in data["championnats"].items()
    ]
    embed = discord.Embed(title="📋 Championnats actifs", description="\n".join(lignes), color=0x5865F2)
    await interaction.response.send_message(embed=embed)

# ─── /stats_equipe ───────────────────────
@tree.command(guild=guild_obj, name="stats_equipe", description="Stats détaillées d'une équipe")
@app_commands.describe(championnat="Nom du championnat", equipe="Nom de l'équipe")
async def stats_equipe(interaction: discord.Interaction, championnat: str, equipe: str):
    data = load_data()
    if championnat not in data["championnats"]:
        await interaction.response.send_message(f"❌ Championnat **{championnat}** introuvable.", ephemeral=True)
        return
    champ = data["championnats"][championnat]
    if equipe not in champ["equipes"]:
        await interaction.response.send_message(f"❌ Équipe **{equipe}** introuvable.", ephemeral=True)
        return
    s = champ["equipes"][equipe]
    diff = s["bp"] - s["bc"]
    classement_trie = trier_classement(champ["equipes"])
    rang = next(i+1 for i, (n, _) in enumerate(classement_trie) if n == equipe)
    matchs_eq = [m for m in champ["matchs"] if m["eq1"] == equipe or m["eq2"] == equipe]
    historique = []
    for m in matchs_eq[-5:][::-1]:
        adversaire = m["eq2"] if m["eq1"] == equipe else m["eq1"]
        b_eq  = m["b1"] if m["eq1"] == equipe else m["b2"]
        b_adv = m["b2"] if m["eq1"] == equipe else m["b1"]
        res = "✅ V" if b_eq > b_adv else ("❌ D" if b_adv > b_eq else "🟡 N")
        historique.append(f"{res} vs **{adversaire}** {b_eq}–{b_adv}")
    embed = discord.Embed(title=f"📊 {equipe} — {championnat}", color=0x5865F2)
    embed.add_field(name="🏅 Classement", value=f"**{rang}e** place", inline=True)
    embed.add_field(name="🏆 Points", value=f"**{s['pts']} pts**", inline=True)
    embed.add_field(name="📅 Matchs joués", value=str(s["j"]), inline=True)
    embed.add_field(name="✅ V", value=str(s["v"]), inline=True)
    embed.add_field(name="🟡 N", value=str(s["n"]), inline=True)
    embed.add_field(name="❌ D", value=str(s["d"]), inline=True)
    embed.add_field(name="⚽ Buts", value=f"{s['bp']} pour / {s['bc']} contre (diff: {'+' if diff>=0 else ''}{diff})", inline=False)
    if historique:
        embed.add_field(name="🕐 5 derniers matchs", value="\n".join(historique), inline=False)
    await interaction.response.send_message(embed=embed)

# ─── /annuler_dernier_match ───────────────
@tree.command(guild=guild_obj, name="annuler_dernier_match", description="Annule le dernier match enregistré")
@app_commands.describe(championnat="Nom du championnat")
async def annuler_dernier_match(interaction: discord.Interaction, championnat: str):
    data = load_data()
    if championnat not in data["championnats"]:
        await interaction.response.send_message(f"❌ Championnat **{championnat}** introuvable.", ephemeral=True)
        return
    champ = data["championnats"][championnat]
    if not champ["matchs"]:
        await interaction.response.send_message("Aucun match à annuler.", ephemeral=True)
        return
    dernier = champ["matchs"].pop()
    calculer_classement(champ)
    save_data(data)
    await mettre_a_jour_live(championnat)
    embed = discord.Embed(
        title="↩️ Match annulé",
        description=f"**{dernier['eq1']} {dernier['b1']}–{dernier['b2']} {dernier['eq2']}** supprimé.\nClassement recalculé.",
        color=0xe74c3c
    )
    await interaction.response.send_message(embed=embed)

# ─── /reset_championnat ──────────────────
class ConfirmResetView(discord.ui.View):
    def __init__(self, championnat):
        super().__init__(timeout=30)
        self.championnat = championnat

    @discord.ui.button(label="✅ Oui, remettre à zéro", style=discord.ButtonStyle.danger)
    async def confirmer(self, interaction: discord.Interaction, button: discord.ui.Button):
        data = load_data()
        champ = data["championnats"][self.championnat]
        # Remet les matchs et stats à zéro mais garde les équipes
        champ["matchs"] = []
        champ["equipes"] = {nom: equipe_vide() for nom in champ["equipes"]}
        save_data(data)
        await mettre_a_jour_live(self.championnat)
        embed = discord.Embed(
            title="🔄 Championnat remis à zéro !",
            description=f"**{self.championnat}** repart de zéro. Les équipes sont conservées.",
            color=0x00d26a
        )
        await interaction.response.edit_message(embed=embed, view=None)

    @discord.ui.button(label="❌ Annuler", style=discord.ButtonStyle.secondary)
    async def annuler(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(content="Annulé.", embed=None, view=None)

@tree.command(guild=guild_obj, name="reset_championnat", description="Remet un championnat à zéro (garde les équipes)")
@app_commands.describe(championnat="Nom du championnat à remettre à zéro")
async def reset_championnat(interaction: discord.Interaction, championnat: str):
    data = load_data()
    if championnat not in data["championnats"]:
        await interaction.response.send_message(f"❌ Championnat **{championnat}** introuvable.", ephemeral=True)
        return
    nb_matchs = len(data["championnats"][championnat]["matchs"])
    embed = discord.Embed(
        title="⚠️ Confirmation",
        description=f"Tu vas remettre **{championnat}** à zéro.\n**{nb_matchs} matchs** seront supprimés.\nLes équipes seront conservées.\n\nTu es sûr ?",
        color=0xe74c3c
    )
    await interaction.response.send_message(embed=embed, view=ConfirmResetView(championnat), ephemeral=True)

# ──────────────────────────────────────────
bot.run(TOKEN)
