# Graceful Shutdown Implementation

## Overview

This document describes the graceful shutdown system that allows the bot to handle restarts without losing user requests.

## How It Works

### 1. Shutdown Flag
When shutdown is initiated, `bot.is_shutting_down` is set to `True`. This signals all request handlers to queue new requests instead of processing them.

### 2. Task Queue (Pickle-based)
All pending tasks are serialized to `task_queue.pkl` using Python's pickle module. This file persists across restarts.

**Task Types:**
- **QuickembedTask**: Automatic embeds from messages containing clip links
- **SlashCommandTask**: `/embed` commands from users

### 3. Shutdown Process

```python
1. Set bot.is_shutting_down = True
2. Wait for active tasks to complete (max 3 minutes)
3. Save task queue to disk (task_queue.pkl)
4. Save database to server
5. Stop bot gracefully
```

### 4. Startup Process

```python
1. Load task queue from disk
2. Start bot and wait for ready event
3. Process all queued tasks
4. Clear queue file
```

## File Structure

### `/bot/task_queue.py`
Main task queue implementation:
- `QuickembedTask` - Dataclass for quickembed tasks
- `SlashCommandTask` - Dataclass for slash command tasks
- `TaskQueue` - Queue manager with pickle persistence
- `process_queued_tasks()` - Processes all tasks on startup
- `process_quickembed_task()` - Handles quickembed tasks
- `process_slash_command_task()` - Handles slash command tasks

### `/bot/tools/embedder.py`
Updated to check shutdown flag in `on_message_create()`:
```python
if self.bot.is_shutting_down:
    # Queue the task instead of processing
    task = QuickembedTask(...)
    self.bot.task_queue.add_quickembed(task)
    return
```

### `/cogs/base.py`
Updated `/embed` command to check shutdown flag:
```python
if self.bot.is_shutting_down:
    await ctx.defer()  # Defer so we can edit later
    task = SlashCommandTask(...)
    self.bot.task_queue.add_slash_command(task)
    return  # Don't send response, will be edited on restart
```

Also processes queued tasks in `on_ready()`:
```python
await process_queued_tasks(self.bot, self.bot.task_queue)
```

### `/main.py`
Updated shutdown handler:
- Sets shutdown flag
- Waits for active tasks
- Saves queue and database
- Stops bot gracefully

Updated startup:
- Loads task queue before starting bot

## Task Queue Details

### QuickembedTask Fields
```python
message_id: int          # Discord message ID to reply to
channel_id: int          # Channel where message was sent
guild_id: int            # Guild ID (or user ID for DMs)
guild_name: str          # Guild name
is_dm: bool              # Whether this was a DM
clip_url: str            # The clip URL to embed
author_id: int           # User who posted the message
author_username: str     # Username
created_at: datetime     # When task was queued
```

### SlashCommandTask Fields
```python
interaction_id: int      # Discord interaction ID
interaction_token: str   # Token for editing response (expires 15min)
channel_id: int          # Channel where command was used
guild_id: Optional[int]  # Guild ID (None for DMs)
user_id: int             # User who ran command
user_username: str       # Username
clip_url: str            # The clip URL to embed
extend_with_ai: bool     # Whether AI extension was requested
created_at: datetime     # When task was queued
context_data: Dict       # Additional context if needed
```

## Interaction Token Expiry

Discord interaction tokens expire after **15 minutes**. The system handles this:

1. **On queue load**: Tasks older than 15 minutes are automatically removed
2. **On processing**: Age is checked again before processing
3. **Fallback**: If token expired, could send new message (not implemented yet)

## Deployment Timeline

For deployments under 5 minutes:
- ✅ Quickembed tasks: Processed successfully on restart
- ✅ Slash commands: Deferred responses edited on restart
- ✅ No user-visible failures

For deployments over 15 minutes:
- ✅ Quickembed tasks: Still processed (message replies never expire)
- ⚠️ Slash commands: Skipped (interaction token expired)
  - Could be improved to send new message mentioning user

## Testing

### Test Quickembed Queueing
1. Start bot
2. Send SIGTERM to trigger shutdown
3. Post a message with a clip link while shutdown is in progress
4. Restart bot
5. Verify the clip is embedded as a reply to the original message

### Test Slash Command Queueing
1. Start bot
2. Send SIGTERM to trigger shutdown
3. Run `/embed <url>` while shutdown is in progress
4. Verify you see "thinking..." spinner (deferred)
5. Restart bot within 15 minutes
6. Verify the deferred response is edited with the embed

## Performance

At 60 clips/minute:
- 3-minute shutdown window = ~180 queued tasks max
- Pickle file size: < 100KB for 180 tasks
- Queue processing time: ~2-5 seconds for 180 tasks (processed in parallel)

## Future Improvements

1. **Expired slash command fallback**: Send new message if token expired
2. **Queue size limits**: Reject tasks if queue grows too large
3. **Priority queue**: Process slash commands before quickembeds
4. **Graceful task cancellation**: Cancel long-running downloads during shutdown
5. **Database queue**: Move from pickle to SQLite for better reliability
6. **Queue monitoring**: Expose queue stats via `/status` command
