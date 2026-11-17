"""General local job service entry point.

The voice_jobs module retains the shared store and HTTP API for compatibility
with existing installations and voice clients. Both entry points own the same
store lock, queue, token, and port; never run separate copies for each task type.
"""
from lm_launcher.voice_jobs import JobService, JobStore, handler, main

__all__ = ['JobService', 'JobStore', 'handler', 'main']

if __name__ == '__main__':
    main()
