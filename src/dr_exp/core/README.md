# Core Utilities

Contains the building blocks used by both the worker and backend.

- `supabase_client.py` – wrapper around the Supabase Python client.
- `client_provider.py` – selects real or mock clients via environment settings.
- `structured_logger.py` – handles local metric and artifact logging.
