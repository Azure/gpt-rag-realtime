

import asyncio
from collections import defaultdict
import inspect


class RealtimeEventHandler:
    """
    A base class to manage real-time event handlers.
    Allows registering, unregistering, and dispatching events.
    """
    def __init__(self):
        self.event_handlers = defaultdict(list)

    def on(self, event_name, handler):
        """
        Register an event handler for a specific event.
        
        :param event_name: Name of the event to listen for.
        :param handler: Callable to be invoked when the event is dispatched.
        """
        self.event_handlers[event_name].append(handler)

    def clear_all_event(self):
        """
        Clear all registered event handlers.
        """
        self.event_handlers = defaultdict(list)

    def dispatch(self, event_name, event, **kwargs):
        """
        Dispatch an event, invoking all registered handlers for that event.
        
        :param event_name: Name of the event to dispatch.
        :param args: Positional arguments to pass to the handlers.
        :param kwargs: Keyword arguments to pass to the handlers.
        """
        handlers = self.event_handlers.get(event_name, [])
        for handler in handlers:
            if inspect.iscoroutinefunction(handler):
                import asyncio
                asyncio.create_task(handler(event, **kwargs))
            else:
                handler(event, **kwargs)

    async def wait_for_next_event(self, event_name):
        """
        Wait for the next occurrence of a specific event.
        
        :param event_name: Name of the event to wait for.
        :return: The event data when the event occurs.
        """
        future = asyncio.Future()

        def _handler(event):
            if not future.done():
                future.set_result(event)
            # self.event_handlers[event_name].remove(_handler)

        self.on(event_name, _handler)
        return await future