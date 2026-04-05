# System Diagram

> Last updated: 2026-04-05

## High-Level Architecture

```
+-------------------+          +-------------------+
|  Android Phones   |   USB    |   Host Machine    |
|                   |<-------->|                   |
|  - TikTok         |   ADB    |  run.py           |
|  - Any app        |          |                   |
|                   |          +---+-------+---+---+
+-------------------+              |       |   |
                                   |       |   |
                    +--------------+   +---+   +-------------+
                    |                  |                      |
                    v                  v                      v
          +------------------+  +-----------+  +----------------------------+
          | FastAPI (:5055)  |  |  SQLite   |  | Vue Frontend (:6175)      |
          |                  |  |           |  |                            |
          | 14 routers       |  | WAL mode  |  | Vue 3 + Vite + Tailwind   |
          | Pydantic schemas |  | 11 tables |  | 9 tabs                    |
          | SQLAlchemy ORM   |  | Alembic   |  | Proxies /api/* -> :5055   |
          +--------+---------+  +-----------+  +----------------------------+
                   |
          +--------+---------+
          |                  |
          v                  v
  +---------------+  +----------------+
  | Bot Runner    |  | Skill System   |
  |               |  |                |
  | Queue + logs  |  | skills/tiktok/ |
  | Subprocess    |  | skills/_base/  |
  | management    |  | _run_skill.py  |
  +-------+-------+  +-------+--------+
          |                   |
          +----->  ADB  <-----+
                   |
                   v
          +------------------+
          |  Android Device  |
          +------------------+
```

## Data Flow

```
                  Vue Dashboard (:6175)
                        |
                   /api/* (Vite proxy)
                        |
                        v
                  FastAPI (:5055)
                   /          \
                  /            \
        SQLAlchemy          Subprocess spawn
            |                     |
            v                     v
     data/gitd.db     Bot / Skill runner
                                  |
                                  v
                           Device (adb.py)
                                  |
                              ADB over USB
                                  |
                                  v
                           Android Phone
```

## Background Services

```
FastAPI Lifespan (app.py)
  |
  +-- startup:
  |     +-- Base.metadata.create_all()     # ensure tables exist
  |     +-- setup_log_capture()            # capture server logs
  |     +-- scheduler_service.start()      # 30s tick thread
  |
  +-- shutdown:
        +-- scheduler_service.stop()
```

## External Integrations

```
+---------------------+     +-------------------+
|  Skill Hub (GitHub) |     |  LLM Providers    |
|                     |     |                   |
|  Public registry    |     |  OpenAI           |
|  Community skills   |     |  Anthropic        |
|  android-agent-skill|     |  OpenRouter       |
|  topic tag          |     |  Ollama (local)   |
+---------------------+     +-------------------+
```

## Plugin System

```
create_app()
  |
  +-- register core routers (14)
  |
  +-- try: import ghost_premium
  |     ghost_premium.register(app)
  |       +-- import premium models (onto shared Base)
  |       +-- register premium routers
  |       +-- add premium tabs to app.state.premium_tabs
  |
  +-- lifespan: Base.metadata.create_all()
        (creates all tables — core + premium if installed)
```
