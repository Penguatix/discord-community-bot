# Discord Bot - Community & Engagement Engine

A feature-rich, plug-and-play Discord bot designed to supercharge server engagement. OmniBot acts as a complete all-in-one solution featuring a highly configurable reputation economy, private-thread matchmaking, integrated multiplayer mini-games (like Wordle), and comprehensive moderation tools. 

Built entirely in Python using `discord.py` and a lightweight SQLite database, it is 100% independent and works globally across any server it joins without relying on hardcoded IDs.

## ✨ Core Features

### 📈 Dynamic Reputation System
A fully automated, SQLite-backed server economy that rewards active and positive community members.
*   **Paced Chat Rewards:** Users earn XP for daily activity, with customizable hourly caps, cooldowns, and minimum character limits.
*   **Chat Streaks:** Tracks consecutive daily activity and automatically grants milestone roles (e.g., 3-day, 7-day, 30-day streaks).
*   **Rank Hierarchy:** Configure up to 5 positive rank tiers and 3 negative penalty tiers, which automatically assign/remove Discord roles as users gain or lose points.
*   **Inactivity Decay:** Users lose points if they stop chatting for a configurable amount of days.
*   **Action Penalties:** Users lose points for deleted messages, spamming tickets, or getting "downvoted" by the community via specific emojis.

### 🎮 Social & Mini-Games
*   **Multiplayer Wordle (`/wordle`):** Spawns a dynamic Wordle game. Players join via a button and are moved into their own private threads to guess the 4, 5, or 6-letter word against a real-time global timer. 
*   **Classic Word Guessing (`/guessword`):** A public chat game with automatic, timed hint generation.
*   **Truth or Dare (`/tod`):** Integrates with public APIs (with a local fallback bank) to provide Casual, Deep, and Spicy prompts.
*   **Heist Mini-game (`/steal`):** A gambling command where users can risk their own reputation points to steal from others.
*   **Icebreakers & Vibe Checks:** Commands like `/icebreaker`, `/wouldyourather`, and `/affinity` to spark chat activity.
*   **Anonymous Confessions (`/confess`):** Secure, embed-based anonymous message delivery.

### 🫂 Matchmaking & Support Hubs
*   **Platonic Matchmaking:** Users can click a button to join a queue. Once paired, the bot creates a private, locked thread for them to chat in safely, complete with inactivity auto-sweeping and report buttons.
*   **Support Tickets:** A clean 1-on-1 private thread ticketing system. Staff can claim, lock, save, or penalize/delete spam tickets via persistent button controls.

### 🎭 Interactive Anime Roleplay
*   Over 40+ expressive (`/dance`, `/happy`, `/cry`) and interactive (`/hug`, `/slap`, `/bite`) commands.
*   Powered dynamically by a 3-tier fallback system fetching clean GIFs from Waifu.pics, Nekos.best, and OtakuGifs.

### 🛡️ Moderation & Setup
*   **Verification Gates:** Deploy 18+ or SFW verification panels that automatically assign member roles and grant Reputation XP to whoever invited the new user!
*   **In-App Configuration:** Server admins can configure **everything** (roles, channels, point values, cooldowns, feature toggles) directly within Discord using the `/setup` and `/setup-rep` command trees. No code editing required.

---

## 🚀 Installation & Setup

### Prerequisites
*   Python 3.10 or higher.
*   A Discord Bot Token from the [Discord Developer Portal](https://discord.com/developers/applications).
*   **Important:** Ensure the `Message Content Intent` and `Server Members Intent` are enabled in your bot's portal settings!

### 1. Clone the Repository
Download or clone the repository to your local machine.

### 2. Install Dependencies
Run the following command in your terminal to install the required libraries:
```bash
pip install -r requirements.txt
```

### 3. Environment Variables
1. Find the `.env.example` file included in the root directory.
2. Rename it to `.env`.
3. Open it and paste your Discord Bot Token:
```env
DISCORD_TOKEN="YOUR_BOT_TOKEN_HERE"
```

### 4. Run the Bot
Start the bot engine by running:
```bash
python app.py
```
*Note: The bot will automatically generate `profile.db` (the SQLite database) upon first boot.*

---

## ⚙️ Initial Discord Setup

Because OmniBot is built to be modular, it remains dormant when first added to a server. To turn features on, an Administrator must run the setup commands in Discord:

1. Use `/setup toggle-feature` to turn on the Reputation and Social modules.
2. Use `/setup set-role` to map your server's specific roles (e.g., Verified, Staff, Ping roles).
3. Use `/setup set-channel` to map your Logging and Verification channels.
4. Use `/setup-rep role` to bind your specific server roles to the Reputation Rank ladder.

Run `/setup-help` at any time for a full administrative command directory!

---

## 📜 License
This project is open-source and available under the [MIT License](LICENSE). Feel free to fork, modify, and host your own instances!
