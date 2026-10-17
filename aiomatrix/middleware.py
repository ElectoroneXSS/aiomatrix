"""Minimal middleware utilities for application-level processing."""
class Middleware:
    async def __call__(self, handler, event, data): return await handler(event, data)
class LoggingMiddleware(Middleware):
    def __init__(self, logger=None):
        import logging; self.logger=logger or logging.getLogger('aiomatrix')
    async def __call__(self,handler,event,data):
        self.logger.debug('Handling event %s',type(event).__name__)
        return await handler(event,data)
