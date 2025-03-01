# ClypyyBot Development Guidelines

## Commands
- Run bot: `python main.py`
- Install dependencies: `pip install -r requirements.txt`
- Create venv: `python -m venv venv`
- Activate venv: `source venv/bin/activate` (Unix) or `venv\Scripts\activate` (Windows)

## Code Style
- Use PEP 8 conventions with 4-space indentation
- Classes: CamelCase (e.g., `BaseClip`, `TwitchMisc`)
- Functions/methods: snake_case (e.g., `get_clip`, `parse_clip_url`)
- Constants: UPPER_CASE (e.g., `MAX_VIDEO_LEN_SEC`)
- Always use type hints for parameters and return values
- Document classes and complex methods with docstrings
- Handle exceptions with specific catch blocks and proper logging
- Use async/await consistently for asynchronous operations

## Project Structure
- Platform-specific code goes in `bot/platforms/`
- Discord commands in `cogs/` directory
- Shared utilities in `bot/tools/`
- Database operations in `bot/db.py`
- Inherit from `BaseClip` and `BaseMisc` for new platforms
- Use environment variables for all credentials and tokens

## API Communication
- Use `bot.upload.get_aiohttp_session()` for clyppy.io API requests to ensure consistent User-Agent
- All HTTP requests should have User-Agent set to identify ClyppyBot
