# Xinlv (心履) — Web App

A warm, healing mental-health companion web app for teens. Record daily moods, get personalized soothing recommendations (music, activities, psychology tips, videos), chat anonymously with an AI confidant (DeepSeek), and play a relaxing mini-game. Supports Chinese/English bilingual UI. Responsive design for mobile and desktop.

## Features

- **Mood Calendar** — Month/week/year views, multiple entries per day with intensity slider
- **AI Confidant** — DeepSeek-powered anonymous chat with crisis keyword interception + voice朗读
- **Smart Recommendations** — Mood-based推送 of music, activities, psychology tips, Bilibili videos
- **User System** — Register/login, import local records to account
- **Streak Badges** — Achievement badges for consecutive mood logging
- **User Contributions** — Submit content, AI auto-review then publish
- **Relaxation Game** — "Merge Big Watermelon" clone, pure frontend Canvas
- **Bilingual** — One-click switch between Chinese and English
- **Minimal Admin Panel** — Non-technical site managers can manage music, content, users via browser
- **Client API** — RESTful API (`/api/v1/`) for Android/desktop clients with offline sync

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.11+ / Django 5.1 |
| Database | SQLite |
| Production Server | waitress |
| Static Files | whitenoise |
| AI Chat | DeepSeek API (`deepseek-v4-flash`) |
| TTS | edge-tts (free, no API key) |
| Frontend | Vanilla HTML + CSS + JavaScript, no build step |
| Image Processing | Pillow |
| Tunnel | Cloudflare Tunnel (xin-lv.com) |

## Quick Start

```bash
git clone <your-repo-url>
cd moodsite
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
# Edit .env with your keys and domain
python manage.py migrate
python manage.py collectstatic --noinput
python manage.py createsuperuser
python -m waitress --listen=0.0.0.0:8000 moodsite.wsgi:application
```

Visit `http://localhost:8000`.

## Project Structure

```
moodsite/
├── manage.py
├── moodsite/           # Django project config
│   ├── settings.py
│   └── urls.py
├── core/               # Business logic (single app)
│   ├── models.py       # All data models + constants
│   ├── views.py        # Calendar, moods, confidant
│   ├── api.py          # Client REST API
│   ├── deepseek.py     # DeepSeek wrapper + persona
│   ├── crisis.py       # Crisis keyword interception
│   └── recommendations.py
├── templates/          # Django templates
├── static/css/         # Single stylesheet
└── media/              # User uploads
```

## API Endpoints

Client sync API (`/api/v1/`):
- `POST /api/v1/login/` — Token login
- `POST /api/v1/logout/` — Logout
- `GET /api/v1/sync/pull/?since=` — Incremental pull
- `POST /api/v1/sync/push/` — Batch push (≤500)
- `GET /api/v1/catalog/` — Recommendation catalog (offline cache)
- `GET /api/v1/recommend/?mood=` — Get recommendations
- `POST /api/v1/chat/` — AI confidant chat
- `GET /api/v1/chat/history/` — Chat history
- `GET /api/v1/profile/` — User profile data

## License

Personal learning and non-commercial use only.