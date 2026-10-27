"""Single owner for bounded asynchronous resource retirement.

Timeout reports pending, not closed. Cannot kill cancellation-resistant tasks;
caller must keep that limitation visible when its event loop later shuts down.
"""
import asyncio


async def settle(task, timeout, cancel=False):
    if cancel: task.cancel()
    done, _ = await asyncio.wait({task}, timeout=timeout)
    if task not in done:
        task.cancel(); return 'pending'
    if task.cancelled(): return 'cancelled'
    try: task.result()
    except Exception: return 'failed'
    return 'closed'


async def retire(writer, client, timeout=3):
    result = {}
    if writer: result['writer'] = await settle(writer, timeout, cancel=True)
    result['client'] = await settle(asyncio.create_task(client.close()), timeout)
    return result
